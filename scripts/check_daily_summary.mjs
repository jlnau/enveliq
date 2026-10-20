// Browser check for the daily summary settings: Settings, Notifications says "A daily summary", offers "Send new email in this
// summary instead" (off until chosen), saves it to the server, and fits a phone. The server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_daily_summary.mjs [path/to/prototype/index.html]
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
const now = Math.floor(Date.now() / 1000);

function makeServer() {
  const calls = [];
  let settings = { morning_on: true, morning_time: "08:00", due_on: true, repeat_hours: 2, repeat_max: 2, quiet_on: true, quiet_from: "21:00", quiet_to: "07:00", show_titles: true,
    mail_on: false, mail_details: false, mail_filter: "all", mail_muted_accounts: [], digest_mail: false };
  const handler = async (route) => {
    const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (u.origin !== ORIGIN) return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
    if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] } });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "192.168.1.10" }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [
      { id: "m1", subject: "Newest from Sam", sender_display: "Sam Lee", sender_address: "sam@example.invalid", summary: "Hello from Sam.", priority: "normal", category: null, action_required: false, received_at: now - 60, state: "unread" },
    ]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: {}, admin: {}, user: {}, labels: {} });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/notifications" && m === "GET") return json(200, { settings, tz: "Australia/Sydney", channels: [], admin: { channels: {}, local_hosts: [] } });
    if (p === "/api/v1/me/notifications/settings" && m === "PUT") {
      const b = JSON.parse(req.postData() || "{}"); calls.push(b); settings = { ...settings, ...b };
      return json(200, { settings });
    }
    return json(404, { detail: "not found" });
  };
  return { handler, calls };
}

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(server, width, height) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors };
}

for (const [label, width, height] of [["desktop", 1200, 900], ["phone", 390, 780]]) {
  const server = makeServer();
  const { page, errors } = await open(server, width, height);
  await page.evaluate(() => openSettings("settings"));
  await page.waitForTimeout(300);
  if (width < 600) await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="reminders"]').click());
  else await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="reminders"]').click());
  const host = page.locator('[data-settings-panel="reminders"] .embed-host');
  await host.locator("#rs_digest").waitFor({ timeout: 8000 });
  const text = () => host.evaluate((h) => h.shadowRoot.textContent);
  check(label + ": the old morning summary is now the daily summary", /A daily summary/.test(await text()) && !/A morning summary/.test(await text()));
  check(label + ": it says what the summary holds", /parcels out for delivery/.test(await text()) && /replies you are waiting for/.test(await text()));
  check(label + ": 'Send new email in this summary instead' is there and off", (await host.locator("#rs_digest").isChecked()) === false && /Send new email in this summary instead/.test(await text()));
  await host.locator("#rs_digest").scrollIntoViewIfNeeded();
  await shot(page, "daily-summary-" + label);
  await host.locator("#rs_digest").check();                                  // this page saves each change by itself
  await page.waitForTimeout(1500);
  check(label + ": saving sends digest_mail: true to the server", server.calls.some((c) => c.digest_mail === true && c.morning_on === true));
  check(label + ": nothing scrolls sideways", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check(label + ": no script errors", errors.length === 0);
  await page.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All daily summary checks passed.");
