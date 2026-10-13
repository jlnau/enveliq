// Browser check: on a real Enveliq server, a person with no mailbox yet (a blank install) sees no sample emails, tasks or names, and
// signed-in person's own page appears. Meanwhile the frame (menu, buttons, logo) is shown with nothing personal in it,
// and a calm line appears if it takes more than a moment. In preview mode (no server behind it) the page appears at
// once, and a server that never answers does not leave the page half empty for ever.
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// the page shows an empty inbox with a way to set up a mailbox. The pages are served from the real files; the server is pretended.
// Usage: node scripts/check_blank_install.mjs [path/to/prototype/index.html]  (SHOTS=<folder> saves screenshots)
//   node scripts/check_no_sample_flash.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(root, "prototype", "index.html")), "utf8");
const css = fs.readFileSync(path.join(root, "web", "static", "auth.css"), "utf8");
const embed = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(root, "web", "static", n), "utf8")).join("\n");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// mode: "real" (answers, but /me is slow), "preview" (no server: status is not found), "hang" (status never answers)
function makeServer(mode, meDelay = 0) {
  return async (route) => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (u.origin !== ORIGIN) return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
    if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
    if (mode === "preview") return json(404, { detail: "not found" });
    if (p === "/api/v1/status") {
      if (mode === "hang") return new Promise(() => {});
      return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    }
    if (p === "/api/v1/system") return json(200, { version: "9.9", cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") { await sleep(meDelay); return json(200, { id: "u1", username: "riley", display_name: "Riley Example", role: "user", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } }); }
    if (p === "/api/v1/accounts") return json(200, []);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
    return json(404, { detail: "not found" });
  };
}


const browser = await chromium.launch();
for (const [name, vp] of [["desktop", { width: 1200, height: 900 }], ["phone", { width: 390, height: 800 }]]) {
  const context = await browser.newContext({ viewport: vp });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage(); const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", makeServer("real", 0));
  await page.goto(`${ORIGIN}/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.classList.contains("mail-ready"), null, { timeout: 8000 });
  await page.waitForTimeout(400);
  const text = await page.evaluate(() => document.body.innerText);
  check(name + ": no sample email is listed", (await page.locator("article.mail").count()) === 0);
  check(name + ": none of the made-up senders, subjects or people appear anywhere on the page", !/Skyline|Harbourview|Canberra Imaging|School Portal|balcony|Morgan|Cara/.test(text));
  check(name + ": no Today card of sample tasks", await page.evaluate(() => { const b = document.getElementById("dueBars"); return !b || b.hidden || getComputedStyle(b).display === "none" || !b.textContent.trim(); }));
  check(name + ": the menu shows no numbers", await page.evaluate(() => [...document.querySelectorAll(".badge")].every((e) => !e.offsetParent || !e.textContent.trim() || e.textContent.trim() === "0")));
  check(name + ": it says plainly that no mailbox is connected and links to the setup guide", /no mailbox is connected yet/i.test(text) && (await page.locator('.sample-banner a[href="/welcome"]:visible').count()) === 1 && !/These are sample emails/.test(await page.locator(".sample-banner").innerText()));
  check(name + ": the empty list invites them to set up a mailbox", /Your mail will appear here once a mailbox is connected/.test(text));
  check(name + ": it does not claim they are all caught up", !/All caught up/.test(text));
  const seen = [];
  for (const f of ["tasks", "attachments", "reviewed", "archived", "action"]) {
    if (name === "phone") await page.click("#menuBtn");
    if ((f === "reviewed" || f === "archived") && !(await page.locator("#moreToggle").getAttribute("aria-expanded")).includes("true")) await page.click("#moreToggle");
    await page.locator(`.side-nav .nav[data-filter="${f}"]`).click(); await page.waitForTimeout(250);
    seen.push(await page.evaluate(() => document.body.innerText));
  }
  check(name + ": none of the other lists (Needs action, Tasks, Attachments, Reviewed, Archived) show made-up mail either", seen.every((t) => !/Skyline|Harbourview|Canberra Imaging|School Portal|balcony|Morgan|Cara/.test(t)));
  await page.locator('.side-nav .nav[data-filter="all"]').click({ force: true }).catch(() => {});
  if (process.env.SHOTS) { fs.mkdirSync(process.env.SHOTS, { recursive: true }); await page.screenshot({ path: path.join(process.env.SHOTS, "blank-" + name + ".png") }); }
  check(name + ": no script errors", errors.length === 0);
  await context.close();
}
{
  // The hosted demo and the preview (no server) keep their made-up mail, and say it is made up.
  const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  await context.route("**/*", makeServer("preview", 0));
  await page.goto(`${ORIGIN}/`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  check("with no server (the preview) the made-up mail is still shown", (await page.locator("article.mail").count()) > 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
