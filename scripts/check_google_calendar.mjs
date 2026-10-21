// Browser check for Settings, Rules & calendar, Google Calendar: the choice between a new calendar and one the person already has,
// the calendar picker, and the phone layout. The server is pretended.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_google_calendar.mjs      (SHOTS=<dir> also saves pictures)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const html = fs.readFileSync(path.join(root, "prototype", "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "static", "auth.css"), "utf8");
const embed = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(root, "web", "static", n), "utf8")).join("\n");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };

const unknown = [], calls = [];
const state = { google: { available: true, connected: false, enabled: false, mode: "new", needs_pick: false, calendar_name: "", count: 0, last_ok: null, last_error: null } };
const overview = () => ({ feed: { on: false }, google: state.google, titles: true, internet_ready: true, origin: ORIGIN, caldav: { configured: false, enabled: false }, todo: { configured: false, enabled: false } });
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
  if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
  if (p === "/api/v1/me/sync/google/start" && m === "POST") { calls.push(["start", JSON.parse(req.postData() || "{}").mode]); return json(200, { url: ORIGIN + "/#google-calendar=pick" }); }
  if (p === "/api/v1/me/sync/google/calendar" && m === "PUT") { const b = JSON.parse(req.postData() || "{}"); calls.push(["pick", b.calendar_id]); state.google = { ...state.google, needs_pick: false, calendar_name: "Family", enabled: true }; return json(200, overview()); }
  if (m !== "GET") return json(200, {});
  const api = p.replace("/api/v1", "");
  const D = {
    "/status": { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } },
    "/system": { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 },
    "/me": { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", email: "morgan@example.com", session: { state: "full" }, security: { totp_enabled: true, passkeys: [] }, source: "local" },
    "/accounts": [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton", email_address: "morgan@example.com", server: "172.30.0.1", port: 1144, username: "morgan", settings: {} }, { id: "a2", provider: "gmail", auth_method: "app_password", owner_user_id: "u1", display_name: "Gmail", email_address: "morgan@gmail.example", server: "imap.gmail.com", port: 993, username: "morgan", settings: { color: "#c8453c" } }],
    "/admin/users": [{ id: "u1", username: "morgan", display_name: "Morgan", role: "admin", source: "local", disabled: false, security: { totp_enabled: true, passkeys: [] } }],
    "/admin/auth-policy": { require_mfa: "admins", password_login: "everyone", min_length: 12, require_number: true, require_upper: true, require_lower: false, require_symbol: false, pw_min_length: 12, pw_min_digits: 1, pw_min_upper: 1, pw_min_lower: 0, pw_min_symbols: 0, pw_forbid_username: true },
    "/admin/sso": { enabled: false, label: "Sign in", issuer: "", client_id: "", scopes: "openid", auto_create: true, allowed_groups: [], admin_groups: [], groups_claim: "groups", username_claim: "preferred_username", has_secret: false },
    "/me/preferences": { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 10 },
    "/me/features": { effective: { find_mail: true }, admin: { compose: true, find_mail: true, sent: true, media: true, messages: true }, user: { compose: true, find_mail: true, sent: true, media: true, messages: true }, labels: { compose: "New email", find_mail: "Find any email (search all your mail)", sent: "Sent (last 14 days)", media: "Pictures and attachment previews", messages: "Messages (write to the other people here)" } },
    "/admin/features": { flags: { compose: true, find_mail: true, sent: true, media: true, messages: true }, labels: { compose: "New email", find_mail: "Find any email (search all your mail)", sent: "Sent (last 14 days)", media: "Pictures and attachment previews", messages: "Messages (write to the other people here)" } },
    "/admin/backups": { backups: [], settings: { daily: false, keep_days: 7 }, folder: "backups", last_error: null, max_keep_days: 60, confirm_word: "RESTORE" },
    "/sync/status": { minutes: 5, editable: true },
    "/admin/review-settings": { max_days: 14, instructions: "" },
    "/find/fast": { mailboxes: [] },
    "/admin/notifications": { labels: { ntfy: "ntfy", gotify: "Gotify", homeassistant: "Home Assistant", telegram: "Telegram" }, channels: { ntfy: true, gotify: true, homeassistant: true, telegram: false }, local_hosts: ["192.168.1.0/24"], from_environment: [] },
    "/admin/google": { enabled: false, redirect_uri: "https://enveliq.example.com/api/v1/me/sync/google/callback", client_id: "", client_secret_set: false },
    "/admin/agent": { mode: "plain", who: "all", name: "Agent", url: "", model: "", has_key: false },
    "/admin/check-address": { accounts: [{ id: "a1", email: "check@example.com", name: "Check" }], account_id: null, allowed: ["alex@example.com"], set_elsewhere: false, automatic_sync_on: true, last: null },
    "/admin/attachment-ai": { enabled: true, cloud: false },
    "/admin/ai-prompt": { in_use: false, default: "You write short, calm summaries of emails for a busy family. Say what the email is, what is asked of the reader, and any date or amount.", custom: "", fixed: "Reply only as JSON with the fields summary, category, priority and suggested_task.", min: 100, max: 4000 },
    "/ai/config": { provider: "custom", url: "http://192.168.1.20:11434/v1/chat/completions", model: "llama3.1:8b", has_key: false, source: "saved" },
    "/ai/providers": [{ id: "custom", label: "Other server on my network", cloud: false, url_example: "http://192.168.1.20:11434/v1/chat/completions", model_example: "llama3.1:8b", steps: [] }, { id: "anthropic", label: "Claude (Anthropic)", cloud: true, company: "Anthropic", url: "https://api.anthropic.com/v1/messages", key_url: "https://console.anthropic.com/", models_url: "https://docs.anthropic.com/", model_example: "claude-sonnet-5-5", steps: [] }],
    "/admin/reporting": { enabled: false, kind: "none", url: "", has_token: false, interval: 60, sinks: {} },
    "/me/important": { items: [{ address: "beth@example.com", name: "Beth Harris" }, { address: "school@example.org", name: "Town Primary School" }] },
    "/me/saved": { signature: "Thanks, Morgan", replies: [{ id: "r0000000000000001", title: "On my way", text: "Thanks, I'm on my way." }], limits: { signature: 1000, replies: 30, title: 60, text: 3000 } },
    "/me/rules": { rules: [{ id: "u0000000000000001", sender: "news@example.com", subject: "", action: "archived" }], actions: { archived: "Archive it", reviewed: "Mark it reviewed" }, max: 50 },
    "/me/notifications": { settings: { quiet_from: "22:00", quiet_to: "07:00", enabled: true }, tz: "Australia/Sydney", channels: [{ id: "browser", label: "This device (browser)", blurb: "A pop-up on this phone or computer, even when Enveliq is closed.", steps: ["Press Turn on for this device."], fields: [], enabled: false, allowed: true, configured: false, last_ok: null, last_error: null, devices: [] }] },
    "/me/sync": { feed: { on: false }, google: { available: true, connected: false, enabled: false }, titles: true, caldav: { configured: false, enabled: false }, todo: { configured: false, enabled: false } },
    "/ai/status": { configured: true, model: "llama3.1:8b" },
    "/mail/providers": [{ id: "proton", label: "Proton Mail", blurb: "Through Proton Bridge", kind: "bridge", status: "ready" }],
    "/admin/microsoft": { enabled: false, client_id: "", tenant: "common", has_secret: false, redirect_uri: "https://enveliq.example.com/api/v1/mail/microsoft/callback", ready: false },
    "/admin/update-notice": { enabled: true, current: "0.94", update: null },
    "/me/write-help": { available: true, enabled: true, instructions: "" },
  };
  if (api === "/me/sync") return json(200, overview());
  if (api === "/me/sync/google/calendars") return json(200, { calendars: [{ id: "family@example.com", name: "Family", primary: true }, { id: "work@example.com", name: "Work", primary: false }] });
  if (api in D) return json(200, D[api]);
  unknown.push(api);
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
  await page.waitForTimeout(700);
  await page.evaluate(() => openSettings("settings"));
  await page.waitForTimeout(250);
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="rules"]').click());
  await page.waitForTimeout(1800);
  return { page, context, errors };
}
const inHost = (page, sel) => page.locator(`#settings .embed-host >> ${sel}`);
// Rules & calendar > Calendar & to-do > Google Calendar
const goGoogle = async (page) => { await inHost(page, ".li:has-text('Calendar & to-do')").first().click(); await inHost(page, ".li:has-text('Google Calendar')").first().click(); };

{
  const { page, context, errors } = await open(1200, 900);
  await goGoogle(page);
  check("Google Calendar offers two choices, a new calendar or one I already have", (await inHost(page, ".li.pick:visible").count()) === 2 && (await inHost(page, ".li.pick:visible").first().getAttribute("aria-pressed")) === "true");
  check("the wider permission is explained before choosing", (await inHost(page, "text=can see and change events on all your Google calendars").count()) === 1);
  await inHost(page, ".li.pick:visible", ).nth(1).click();
  await inHost(page, "button:has-text('Connect Google Calendar'):visible").click();
  await page.waitForTimeout(300);
  check("choosing 'Use a calendar I already have' starts the connection in that mode", calls.some((c) => c[0] === "start" && c[1] === "existing"));
  await inHost(page, ".li.pick:visible").first().click();
  await inHost(page, "button:has-text('Connect Google Calendar'):visible").click();
  await page.waitForTimeout(300);
  check("choosing a new calendar starts it in the narrow mode", calls.some((c) => c[0] === "start" && c[1] === "new"));
  await shot(page, "google-choice");
  // after Google's consent: connected with an existing calendar, waiting for a pick
  state.google = { ...state.google, connected: true, enabled: true, mode: "existing", needs_pick: true };
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="general"]').click());
  await page.waitForTimeout(500);
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab~="rules"]').click());
  await page.waitForTimeout(1800);
  await goGoogle(page);
  await inHost(page, "select#gm_pick").waitFor();
  await page.waitForFunction(() => { const h = [...document.querySelectorAll(".embed-host")].find((x) => x.shadowRoot && x.shadowRoot.querySelector("#gm_pick")); return h && h.shadowRoot.querySelector("#gm_pick").options.length === 2; });
  check("the person's calendars are listed to pick from", (await inHost(page, "select#gm_pick option").allInnerTexts()).join("|") === "Family (main calendar)|Work");
  check("the Connect and mode choices are hidden until a calendar is picked", (await inHost(page, ".li.pick:visible").count()) === 0);
  await shot(page, "google-pick");
  await inHost(page, "select#gm_pick").selectOption("family@example.com");
  await inHost(page, "button:has-text('Use this calendar')").click();
  await page.waitForTimeout(800);
  check("Use this calendar sends the choice to the server", calls.some((c) => c[0] === "pick" && c[1] === "family@example.com"));
  check("afterwards it says which calendar is used and offers to remove only Enveliq's events", (await inHost(page, "text=your calendar “Family”").count()) === 1 && (await inHost(page, "button:has-text(\"Disconnect and remove Enveliq's events\")").count()) === 1);
  check("no script errors", errors.length === 0);
  if (errors.length) console.log("   " + errors.join(" | ").slice(0, 300));
  await context.close();
}

{
  state.google = { ...state.google, connected: false, enabled: false, mode: "new", needs_pick: false };
  const { page, context } = await open(390, 800);
  await goGoogle(page);
  await shot(page, "google-choice-phone");
  const sideways = await page.evaluate(() => { const p = document.querySelector("#settings"); return p.scrollWidth > p.clientWidth + 2; });
  const tall = await inHost(page, "button:has-text('Connect Google Calendar'):visible").evaluate((b) => b.getBoundingClientRect().height);
  check("phone: nothing sideways and the Connect button is easy to press", !sideways && tall >= 36);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All Google Calendar choice checks passed.");
