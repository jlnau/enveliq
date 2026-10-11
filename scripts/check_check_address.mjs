// Browser check for "Forward to check" in Administration: an administrator chooses one of their own mailboxes and lists who may use it.
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_check_address.mjs [path/to/prototype/index.html]
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

let saved = null;
let state = {
  account_id: null, set_elsewhere: false, allowed: [], last: null, automatic_sync_on: true,
  accounts: [{ id: "11111111-1111-4111-8111-111111111111", name: "Forwarding", email: "check@example.invalid" }, { id: "22222222-2222-4222-8222-222222222222", name: "Mine", email: "me@example.invalid" }],
};
const external = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
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
  if (p === "/api/v1/admin/check-address" && req.method() === "GET") return json(200, state);
  if (p === "/api/v1/admin/check-address" && req.method() === "PUT") {
    saved = JSON.parse(req.postData() || "{}");
    if (saved.allowed.some((a) => !/@/.test(a))) return json(422, { detail: "“" + saved.allowed[0] + "” is not an email address." });
    state = { ...state, account_id: saved.account_id, allowed: saved.allowed };
    return json(200, state);
  }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForTimeout(800);
  await page.evaluate(() => { openSettings("admin"); });
  await page.waitForTimeout(300);
  await page.evaluate(() => { document.querySelector('#settingsNav [data-settings-tab="admincheck"]').click(); });
  await page.waitForSelector('[data-settings-panel="admincheck"] .embed-host', { state: "attached" });
  await page.locator('[data-settings-panel="admincheck"] .embed-host').locator("#ck_account").waitFor({ timeout: 8000 });
  const host = page.locator('[data-settings-panel="admincheck"] .embed-host');
  host.text = () => host.evaluate((h) => h.shadowRoot.textContent);
  return { page, errors, context, host };
}

{
  const { page, errors, context, host } = await open(1200, 900);
  const text = await host.text();
  check("the section says what it does in plain words", /Forward to check/.test(text) && /one-line answer/.test(text) && /never says an email is safe/.test(text));
  check("only the administrator's own mailboxes can be chosen, and Off is the first choice", (await host.locator("#ck_account option").allInnerTexts()).join("|") === "Off|check@example.invalid|me@example.invalid");
  check("it says the mailbox is never shown as an inbox", /never shown as an inbox/.test(text));
  await shot(page, "check-address-empty");
  await host.locator("#ck_allowed").fill("not an address");
  await host.locator("#ck_account").selectOption("11111111-1111-4111-8111-111111111111");
  await host.locator('button[type="submit"]').click();
  await page.waitForTimeout(400);
  check("a bad address is refused and the page says why", /is not an email address/.test(await host.text()) && saved.account_id === "11111111-1111-4111-8111-111111111111" && state.allowed.length === 0);
  await host.locator("#ck_allowed").fill("alex@example.invalid\nsam@example.invalid");
  await host.locator("#ck_account").selectOption("11111111-1111-4111-8111-111111111111");
  await host.locator('button[type="submit"]').click();
  await page.waitForTimeout(600);
  check("saving sends the mailbox and the list, one address per line", saved && saved.account_id === "11111111-1111-4111-8111-111111111111" && saved.allowed.join(",") === "alex@example.invalid,sam@example.invalid");
  await page.waitForSelector("#ck_allowed", { state: "attached" });
  const after = host.locator("#ck_allowed");
  check("after saving the list is shown again", (await after.inputValue()) === "alex@example.invalid\nsam@example.invalid");
  await shot(page, "check-address");
  check("the page never contacted another website", external.length === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  state = { ...state, account_id: null, allowed: [], automatic_sync_on: false, set_elsewhere: false };
  const { page, errors, context, host } = await open(390, 800);
  check("when automatic checking is off the page says forwarded emails are not looked at", /Automatic checking is off/.test(await host.text()));
  check("on a phone the form fits and the page does not scroll sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot(page, "check-address-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
