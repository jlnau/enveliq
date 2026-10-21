// Browser check for the "a new version is out" notice: the card in the left panel (administrators only, with a link to the
// release notes on GitHub) and the Updates switch in Administration. The server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_update_notice.mjs      Set SHOTS=<folder> to save screenshots.
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

const LINK = "https://github.com/jlnau/enveliq/releases/tag/v9.9";
let update = { version: "9.9", url: LINK };
let enabled = true, putBody = null;
const external = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) { external.push(req.url()); return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" }); }
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
  if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { version: "9.8", cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900, ...(update ? { update } : {}) });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } });
  if (p === "/api/v1/accounts") return json(200, []);
  if (p === "/api/v1/admin/users") return json(200, [{ id: "u1", username: "morgan", display_name: "Morgan", role: "admin", source: "local", disabled: false, security: { totp_enabled: true, passkeys: [] } }]);
  if (p === "/api/v1/admin/auth-policy") return json(200, { require_mfa: "admins", password_login: "everyone", pw_min_length: 12, pw_min_digits: 1, pw_min_upper: 1, pw_min_lower: 0, pw_min_symbols: 0, remember_days: 0, remember_possible: true });
  if (p === "/api/v1/admin/sso") return json(200, { enabled: false, label: "Sign in", issuer: "", client_id: "", scopes: "openid", auto_create: true, allowed_groups: [], admin_groups: [], groups_claim: "groups", username_claim: "preferred_username", require_email_verified: false, client_secret_set: false, redirect_uri: ORIGIN + "/cb" });
  if (p === "/api/v1/admin/update-notice" && m === "GET") return json(200, { enabled, current: "9.8", update: enabled ? update : null });
  if (p === "/api/v1/admin/update-notice" && m === "PUT") { putBody = JSON.parse(req.postData() || "{}"); enabled = putBody.enabled; return json(200, { enabled, current: "9.8", update: enabled ? update : null }); }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const shot = async (page, name, clip) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png"), ...(clip ? { clip } : {}) }); };
async function open(width = 1280, height = 900) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForFunction(() => !document.body.classList.contains("booting"), null, { timeout: 8000 });
  await page.waitForTimeout(500);
  return { page, errors, context };
}
const card = (page) => page.locator("#updNote");

{
  update = { version: "9.9", url: LINK };
  const { page, errors, context } = await open();
  check("an administrator sees the card when a newer version is out", await card(page).isVisible());
  check("it says which version", /Version 9\.9 is out/.test(await card(page).innerText()) && /what's new/i.test(await card(page).innerText()));
  check("it links to the release notes on GitHub, in a new tab, safely", (await card(page).getAttribute("href")) === LINK && (await card(page).getAttribute("target")) === "_blank" && /noopener/.test(await card(page).getAttribute("rel")));
  const pos = await page.evaluate(() => { const g = (s) => document.querySelector(s).getBoundingClientRect(); return { card: g("#updNote"), foot: g(".side-foot"), agent: g("#agentBtn"), side: g("#sidebar") }; });
  check("it sits just above the line over Agent", pos.card.bottom <= pos.foot.top + 1 && pos.card.bottom >= pos.foot.top - 24 && pos.card.right <= pos.side.right && pos.card.left >= pos.side.left);
  await shot(page, "update-card", { x: 0, y: 0, width: 270, height: 900 });
  await page.click("#collapseToggle"); await page.waitForTimeout(300);
  check("with the panel collapsed it is a small icon that still links", (await card(page).isVisible()) && (await card(page).getAttribute("href")) === LINK && !(await page.locator("#updNote .updtx").isVisible()));
  await shot(page, "update-card-collapsed", { x: 0, y: 0, width: 120, height: 900 });
  check("no script errors", errors.length === 0);
  await context.close();
}
{
  update = null;
  const { page, context } = await open();
  check("with no newer version there is no card", !(await card(page).isVisible()));
  await context.close();
}
for (const [label, bad] of [["a link to another site", { version: "9.9", url: "https://evil.example/releases/tag/v9.9" }], ["a link that is not https", { version: "9.9", url: "http://github.com/jlnau/enveliq/releases/tag/v9.9" }], ["a link to a different project", { version: "9.9", url: "https://github.com/someone/else/releases/tag/v9.9" }], ["a version with markup in it", { version: "9.9<img src=x>", url: LINK }], ["no link at all", { version: "9.9" }]]) {
  update = bad;
  const { page, context } = await open();
  check("the page ignores " + label, !(await card(page).isVisible()));
  await context.close();
}
{
  update = { version: "9.9", url: LINK }; enabled = true; putBody = null;
  const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage(); const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`); await page.waitForTimeout(800);
  await page.evaluate(() => { openSettings("admin"); }); await page.waitForTimeout(300);
  await page.evaluate(() => { document.querySelector('#settingsNav [data-settings-tab~="adminupdates"]').click(); });
  await page.evaluate(() => openPanel("adminupdates", { tab: "adminbackup" }));
  const host = page.locator('[data-settings-panel="adminupdates"] .embed-host');
  await host.locator("#up_on").waitFor({ state: "attached", timeout: 8000 }).catch(async (e) => { console.log("DEBUG", await page.locator('[data-settings-panel="adminupdates"]').innerHTML().then((t) => t.slice(0, 600)), errors.join(";")); throw e; });
  const text = () => host.evaluate((h) => h.shadowRoot.textContent);
  check("Administration has an Updates section with the switch on", /Updates/.test(await text()) && await host.locator("#up_on").isChecked());
  check("it says nothing about you is sent, and that only administrators see it", /Nothing about you/.test(await text()) && /Only administrators/.test(await text()));
  check("it says a newer version is out, with a link", /Version 9\.9 is out/.test(await text()) && (await host.locator('a[href="' + LINK + '"]').count()) === 1);
  await shot(page, "update-admin");
  await host.locator("#up_on").uncheck();
  await page.waitForTimeout(1100);
  check("turning it off is saved", putBody && putBody.enabled === false);
  check("and the page now says the check is off", /The check is off/.test(await text()));
  check("no script errors in Administration", errors.length === 0);
  await context.close();
}
check("nothing was requested from another site", external.length === 0);
await browser.close();
process.exit(failed ? 1 : 0);
