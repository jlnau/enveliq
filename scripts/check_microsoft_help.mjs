// Browser check for the Microsoft sign-in help in Administration: it must explain the "directory" requirement Microsoft now has.
// The page is served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_microsoft_help.mjs [path/to/prototype/index.html]
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

const external = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) { external.push(req.url()); return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" }); }
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
  if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } });
  if (p === "/api/v1/accounts") return json(200, []);
  if (p === "/api/v1/admin/users") return json(200, [{ id: "u1", username: "morgan", display_name: "Morgan", role: "admin", source: "local", disabled: false, security: { totp_enabled: true, passkeys: [] } }]);
  if (p === "/api/v1/admin/auth-policy") return json(200, { require_mfa: "admins", password_login: "everyone", min_length: 12, require_number: true, require_upper: true, require_lower: false, require_symbol: false });
  if (p === "/api/v1/admin/sso") return json(200, { enabled: false, label: "Sign in", issuer: "", client_id: "", scopes: "openid", auto_create: true, allowed_groups: [], admin_groups: [], groups_claim: "groups", username_claim: "preferred_username", require_email_verified: false, client_secret_set: false, redirect_uri: ORIGIN + "/cb" });
  if (p === "/api/v1/admin/microsoft") return json(200, { enabled: false, client_id: "", tenant: "common", has_secret: false, redirect_uri: "https://enveliq.example.com/api/v1/mail/microsoft/callback", ready: false });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height, tab, wait) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForTimeout(800);
  await page.evaluate((t) => { openSettings(t === "general" ? "settings" : "admin"); }, tab);
  await page.waitForTimeout(300);
  await page.evaluate((t) => { document.querySelector(`#settingsNav [data-settings-tab~="${t}"]`).click(); }, tab);
  await page.evaluate((t) => openPanel(t, { tab: t }), tab);
  const panel = `[data-settings-panel="${tab}"] .embed-host`;
  await page.waitForSelector(panel, { state: "attached" });
  const host = page.locator(panel);
  await host.locator(wait).waitFor({ timeout: 8000 }).catch(async (e) => { console.log("DEBUG", (await page.locator(panel).evaluate((h) => h.shadowRoot && h.shadowRoot.textContent)) + "|" + errors.join(";")); throw e; });
  host.text = () => host.evaluate((h) => h.shadowRoot.textContent);
  return { page, errors, context, host };
}

for (const [width, height, name] of [[1200, 1000, "desktop"], [390, 800, "phone"]]) {
  const { page, errors, context, host } = await open(width, height, "adminms", "#ms_redirect");
  const text = await host.text();
  check(name + ": the first step explains the 'directory has been deprecated' message and the Azure sign-up link", /ability to create applications outside of a directory has been deprecated/.test(text) && /Signing up for Azure/.test(text));
  check(name + ": it starts with getting a free Azure account, and no longer sends people to Exchange Online", /Get a free Azure account/.test(text) && /Microsoft Graph/.test(text) && /offline_access/.test(text) && /not find "Office 365 Exchange Online"/.test(text) && !/tick IMAP\.AccessAsUser\.All/.test(text));
  check(name + ": it no longer promises that no card is ever needed", !/No subscription or card is needed/.test(text) && /card/.test(text));
  check(name + ": the page does not scroll sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot(page, "microsoft-" + name);
  check(name + ": the page never contacted another website", external.length === 0);
  check(name + ": no page errors", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
