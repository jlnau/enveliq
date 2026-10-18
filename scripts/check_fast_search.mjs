// Browser check for Fast search in Settings, General: off by default, a plain warning with a tick box before it turns on,
// "Getting ready" progress, and "Turn off and delete". The pages are served from the real files; the server is pretended.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_fast_search.mjs [path/to/prototype/index.html]
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
  const st = { enabled: false, polls: 0 };
  const status = () => {
    if (!st.enabled) return { account_id: "a1", enabled: false, state: "off", done: 0, total: 0, message: "", label: "me@example.invalid", recommended: true };
    const ready = st.polls >= 2;
    return { account_id: "a1", enabled: true, state: ready ? "ready" : "building", done: ready ? 1000 : 620, total: 1000, message: "", label: "me@example.invalid", recommended: true };
  };
  const features = { compose: true, find_mail: true };
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
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [{ id: "m1", subject: "Hello", sender_display: "Dana", sender_address: "dana@example.invalid", summary: "Hi.", priority: "normal", category: null, action_required: false, received_at: now - 60, reply_context: { reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] }, attachment_summaries: [], tags: [], from_all_mail: false }]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features, labels: { compose: "New email", find_mail: "Find any email (search all your mail)" } });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/find/fast" && m === "GET") { if (st.enabled) st.polls++; return json(200, { mailboxes: [status()] }); }
    if (p === "/api/v1/find/fast/a1" && m === "PUT") { const b = JSON.parse(req.postData() || "{}"); calls.push(["set", b]); if (b.enabled && !b.agree) return json(400, { detail: "Tick the box." }); st.enabled = !!b.enabled; st.polls = 0; return json(200, status()); }
    if (p === "/api/v1/find/fast/a1/rebuild") { calls.push(["rebuild"]); return json(202, status()); }
    return json(404, { detail: "not found: " + p });
  };
  return { handler, calls, st };
}

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(server, width, height) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) csp.push(m.text()); });
  await context.route("**/*", server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.evaluate(() => openSettings("settings"));
  await page.evaluate(() => document.querySelector('#settingsNav [data-settings-tab="general"]').click());
  return { page, errors, csp, context, host: page.locator('[data-settings-panel="general"] .embed-host') };
}

for (const [label, w, h] of [["desktop", 1200, 900], ["phone", 390, 780]]) {
  const server = makeServer();
  const { page, errors, csp, context, host } = await open(server, w, h);
  await host.locator("text=Fast search").first().waitFor();
  const text = async () => await host.evaluate((el) => el.shadowRoot.textContent);
  check(`${label}: Fast search is in General settings and says it is off unless turned on`, /off unless you turn it on/.test(await text()));
  check(`${label}: it recommends Fast search for Proton Mail`, /Recommended for Proton Mail/.test(await text()));
  check(`${label}: nothing was turned on by being shown`, server.calls.length === 0);
  await host.getByRole("button", { name: "Turn on", exact: true }).click();
  check(`${label}: a plain warning appears before anything happens`, /private, locked list of the words in your emails/.test(await text()) && /Your emails themselves are not kept/.test(await text()));
  const go = host.getByRole("button", { name: "Turn on Fast search" });
  check(`${label}: the button waits until the box is ticked`, await go.isDisabled());
  await shot(page, `fast-warning-${label}`);
  await host.getByLabel("I understand").check();
  check(`${label}: ticking the box lets it go ahead`, await go.isEnabled());
  if (w < 500) check("phone: the buttons are easy to press", (await go.boundingBox()).height >= 44);
  await go.click();
  await host.locator("text=Getting ready: 62%").waitFor();
  check(`${label}: it says it agreed and shows progress`, server.calls.some((c) => c[0] === "set" && c[1].enabled === true && c[1].agree === true));
  await shot(page, `fast-building-${label}`);
  await host.locator("text=emails are ready to search").waitFor({ timeout: 15000 });
  check(`${label}: when it is built it says so`, /1,000 emails are ready to search/.test(await text()));
  await host.getByRole("button", { name: "Turn off and delete" }).click();
  await host.getByRole("button", { name: "Turn on", exact: true }).waitFor();
  check(`${label}: Turn off and delete asks the server and goes back to off`, server.calls.some((c) => c[0] === "set" && c[1].enabled === false));
  check(`${label}: no sideways scrolling`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check(`${label}: no script errors or policy violations`, errors.length === 0 && csp.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All Fast search checks passed.");
