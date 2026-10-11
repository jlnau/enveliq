// Browser check: on a real Enveliq server, a refresh never flashes the sample people, counts or version before the
// signed-in person's own page appears. The page stays hidden until the server has said who is signed in; in preview
// mode (no server behind it) it appears at once, and a server that never answers does not leave the page blank.
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

// ---- a real server whose answer is slow: nothing of the sample page shows meanwhile ----
{
  const page = await open("real", 1500);
  await sleep(700);
  check("while the server has not said who is signed in, the page is hidden", !(await shellVisible(page)));
  check("the sample name Morgan cannot be seen in that time", !(await page.locator("#userName").isVisible()));
  await page.waitForFunction(() => getComputedStyle(document.querySelector(".app")).visibility === "visible", null, { timeout: 8000 });
  check("then the page appears with the signed-in person's own name", (await page.locator("#userName").innerText()) === "Riley Example");
  check("and a greeting that names them, not the sample person", /Riley/.test(await page.locator(".top-left h2").innerText()) && !/Morgan/.test(await page.locator(".top-left h2").innerText()));
  check("and the real version, not a sample one", /Version 9\.9/.test(await page.locator("#brandVer").innerText()));
  await page.context().close();
}

// ---- no server behind the page (a hosted preview or the demo): it appears at once ----
{
  const page = await open("preview", 0);
  await page.waitForFunction(() => getComputedStyle(document.querySelector(".app")).visibility === "visible", null, { timeout: 3000 });
  check("with no server behind it, the preview page appears straight away", (await page.locator("#userName").innerText()) === "Morgan");
  await page.context().close();
}

// ---- a server that never answers: the page is not left blank ----
{
  const page = await open("hang", 0);
  await sleep(1000);
  check("while waiting, the page is hidden", !(await shellVisible(page)));
  await page.waitForFunction(() => getComputedStyle(document.querySelector(".app")).visibility === "visible", null, { timeout: 9000 });
  check("after a few seconds it appears anyway, so the page is never left blank", true);
  await page.context().close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All no-flash checks passed.");
