// Browser check: the version number sits at the bottom of the left panel, under Terms, Privacy and Security, not under the logo.
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_version_footer.mjs [path/to/prototype/index.html]    Set SHOTS=<folder> to save screenshots.
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
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png"), clip: { x: 0, y: 0, width: 270, height: 900 } }); };
async function open(mode, width = 1280) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  await context.route("**/*", makeServer(mode, 0));
  await page.goto(`${ORIGIN}/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !document.body.classList.contains("booting"), null, { timeout: 8000 });
  await page.waitForTimeout(300);
  return page;
}
{
  const page = await open("real");
  const v = page.locator("#brandVer");
  check("the version says Version 9.9", /^Version 9\.9$/.test((await v.innerText()).trim()));
  check("it is in the bottom block of the left panel", (await page.locator(".side-foot #brandVer").count()) === 1);
  const pos = await page.evaluate(() => { const g = (s) => document.querySelector(s).getBoundingClientRect(); return { ver: g("#brandVer"), legal: g(".legal-links"), user: g("#userPill"), tag: g(".brand small"), side: g("#sidebar") }; });
  check("it is under Terms, Privacy and Security", pos.ver.top >= pos.legal.bottom - 1);
  check("it is at the very bottom, under the person's name", pos.ver.top >= pos.user.bottom - 1 && pos.ver.bottom <= pos.side.bottom + 1);
  check("the top of the panel no longer shows a version", !/Version/.test(await page.locator(".brand").innerText()));
  check("it is not cut off or sideways", pos.ver.left >= pos.side.left && pos.ver.right <= pos.side.right);
  await shot(page, "version-footer");
  await page.click("#collapseToggle"); await page.waitForTimeout(300);
  check("with the panel collapsed it is hidden, like the links", !(await v.isVisible()));
  await page.close();
}
{
  const page = await open("preview");
  check("in the demo (no server) no empty version line is left", !(await page.locator("#brandVer").isVisible()));
  await page.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
