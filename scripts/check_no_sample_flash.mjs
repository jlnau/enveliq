// Browser check: on a real Enveliq server, a refresh never flashes the sample people, counts or version before the
// signed-in person's own page appears. Meanwhile the frame (menu, buttons, logo) is shown with nothing personal in it,
// and a calm line appears if it takes more than a moment. In preview mode (no server behind it) the page appears at
// once, and a server that never answers does not leave the page half empty for ever.
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
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
async function open(mode, meDelay) {
  const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  await context.route("**/*", makeServer(mode, meDelay));
  await page.goto(`${ORIGIN}/`, { waitUntil: "domcontentloaded" });
  return page;
}
const shellVisible = (page) => page.evaluate(() => getComputedStyle(document.querySelector(".app")).visibility === "visible");

const settled = (page) => page.evaluate(() => !document.body.classList.contains("booting"));
const shown = (page, sel) => page.locator(sel).first().evaluate((el) => {
  const c = getComputedStyle(el);
  return c.display !== "none" && c.visibility !== "hidden" && Number(c.opacity) > 0.5 && el.getBoundingClientRect().height > 0;
}).catch(() => false);

// ---- a real server whose answer is slow: the frame shows, nothing personal or sample does ----
{
  const page = await open("real", 2500);
  check("while the server has not said who is signed in, the menu frame is already there (not a blank page)", await shown(page, 'button[data-filter="all"]'));
  check("the sample name Morgan, the sample role and initials cannot be seen", !(await shown(page, "#userName")) && !(await shown(page, "#userRole")) && !(await shown(page, "#avatar")));
  check("no greeting, no counts and no version label show yet", !(await shown(page, ".top-left h2")) && !(await shown(page, ".badge")) && !(await shown(page, "#brandVer")));
  check("no sample emails or notices show", !(await shown(page, "article.mail")) && !(await shown(page, ".sample-banner")));
  check("a quick load shows no loading line", !(await shown(page, "#bootNote")));
  await sleep(1000);
  check("if it takes longer, a calm line says the inbox is getting ready", (await shown(page, "#bootNote")) && /Getting your inbox ready/.test(await page.locator("#bootNote").innerText()));
  if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, "starting-up.png") });
  await page.waitForFunction(() => !document.body.classList.contains("booting"), null, { timeout: 8000 });
  // Wait for the browser to paint the real identity after the boot state clears.
  // This still fails if placeholder data is displayed or the real identity never appears.
  const identityReady = await page.waitForFunction(() => {
    const u = document.querySelector("#userName"), h = document.querySelector(".top-left h2"), v = document.querySelector("#brandVer");
    const visible = (el) => el && getComputedStyle(el).display !== "none" && getComputedStyle(el).visibility !== "hidden" && el.getBoundingClientRect().height > 0;
    return visible(u) && u.textContent === "Riley Example" && visible(h) && /Riley/.test(h.textContent) && v?.textContent === "Version 9.9";
  }, null, { timeout: 3000 }).then(() => true, () => false);
  if (!identityReady) console.log("IDENTITY DEBUG", JSON.stringify(await page.evaluate(() => ["#userName", ".top-left h2", "#brandVer"].map(sel => { const e = document.querySelector(sel), c = getComputedStyle(e); return { sel, text: e.textContent, innerText: e.innerText, height: e.getBoundingClientRect().height, display: c.display, visibility: c.visibility, opacity: c.opacity, parentDisplay: getComputedStyle(e.parentElement).display }; }))));
  check("then the signed-in person's own name appears", identityReady && (await shown(page, "#userName")));
  check("and a greeting that names them, not the sample person", identityReady && /Riley/.test(await page.locator(".top-left h2").innerText()) && !/Morgan/.test(await page.locator(".top-left h2").innerText()));
  check("and the real version, not a sample one", identityReady && /Version 9\.9/.test(await page.locator("#brandVer").innerText()));
  check("and the loading line is gone", !(await shown(page, "#bootNote")));
  await page.context().close();
}

// ---- no server behind the page (a hosted preview or the demo): it appears at once, with no loading line ----
{
  const page = await open("preview", 0);
  await page.waitForFunction(() => !document.body.classList.contains("booting"), null, { timeout: 3000 });
  check("with no server behind it, the preview page appears straight away", await page.waitForFunction(() => { const e = document.querySelector("#userName"); return e?.textContent === "Morgan" && getComputedStyle(e).visibility === "visible" && e.getBoundingClientRect().height > 0; }, null, { timeout: 1500 }).then(() => true, () => false));
  check("and shows no loading line", !(await shown(page, "#bootNote")));
  await page.context().close();
}

// ---- a server that never answers: the page does not stay half empty ----
{
  const page = await open("hang", 0);
  await sleep(1000);
  check("while waiting, nothing personal shows", !(await shown(page, "#userName")) && !(await shown(page, ".top-left h2")));
  await page.waitForFunction(() => !document.body.classList.contains("booting"), null, { timeout: 9000 });
  check("after a few seconds the page appears anyway", await settled(page));
  await page.context().close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All no-flash checks passed.");
