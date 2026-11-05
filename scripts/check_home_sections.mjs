// Browser check: the four count boxes and the Today / Coming up section can each be hidden from the View panel (also in Calm mode).
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_home_sections.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const features = { compose: true, address_book: true, sent: true, media: true, find_mail: true };
const now = Math.floor(Date.now() / 1000);
const ctx = (id, refs = []) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: refs });
const base = { summary: "A short summary.", priority: "normal", category: "Information", action_required: false, state: "unread", snoozed_until: null };
const make = () => [
  { ...base, id: "m-a", subject: "Trip plans", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: now - 300, reply_context: ctx("a2", ["<a1@x>"]) },
  { ...base, id: "m-b", subject: "Re: Trip plans", sender_display: "Bob", sender_address: "bob@example.invalid", received_at: now - 900, reply_context: ctx("a1") },
  { ...base, id: "m-c", subject: "Electricity bill", starred: true, sender_display: "Northside Power", sender_address: "bills@example.invalid", received_at: now - 1200, reply_context: ctx("c") },
  { ...base, id: "m-r", subject: "Starred and already read", sender_display: "Cara", sender_address: "cara@example.invalid", received_at: now - 5000, from_all_mail: true, starred: true, reply_context: ctx("r") },
];
let messages, views;
const _unused = (done) => ({ id: "AAAAAAAAAAAA", done, cancelled: false, total: 1, listed: 1, include_junk: false, mailboxes: [{ account_id: "a1", label: "me@example.invalid", state: done ? "done" : "searching", found: 1, message: "", fast: false }] });
const iso = (n) => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const task = (id, mid, title, n) => ({ id, account_id: "a1", message_id: mid, title, detail: "", sender: "Alice", priority: "normal", due: iso(n), days: n, remind_at: null, state: "open", reason: null, reason_text: "", closed_at: null, moved: false });
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/me/tasks") return json(200, { today: iso(0), tz: "UTC", now: Date.now() / 1000, tasks: [task("t1", "m-a", "Reply to Alice", 0), task("t2", "m-b", "Pay the bill", 3)] });
  if (p === "/api/v1/me/mail-view") { if (m === "PUT") views.push(JSON.parse(req.postData() || "{}")); return json(200, m === "GET" ? { view: null } : { view: JSON.parse(req.postData() || "{}") }); }
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
async function open() {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors };
}
const shown = (page, id) => page.evaluate((x) => { const e = document.getElementById(x); return !!e && !e.hidden && e.offsetParent !== null && e.textContent.trim().length > 0; }, id);
const openPanel = async (page) => { await page.evaluate(() => document.getElementById("viewTab").click()); await page.waitForSelector("#viewPanel #vCounts"); };

messages = make(); views = [];
{
  const { page, errors } = await open();
  await page.waitForFunction(() => { const e = document.getElementById("dueBars"); return e && !e.hidden; }, null, { timeout: 8000 });
  check("both sections show to begin with", (await shown(page, "previewOverview")) && (await shown(page, "dueBars")));
  check("the Today section lists the task and the Coming up part shows too", /Reply to Alice/.test(await page.locator("#dueBars").innerText()) && /Coming up/.test(await page.locator("#dueBars").innerText()));
  await openPanel(page);
  await page.waitForTimeout(600);
  if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, "home-sections.png") });
  check("the View panel has both switches, ticked", (await page.locator("#vCounts").isChecked()) && (await page.locator("#vToday").isChecked()));
  await page.evaluate(() => document.getElementById("vCounts").click());
  await page.waitForTimeout(200);
  check("turning off the counts hides the four boxes and keeps Today", !(await shown(page, "previewOverview")) && (await shown(page, "dueBars")));
  check("and it is saved to the server", views.some((v) => v.show_counts === false && v.show_today === true));
  await page.evaluate(() => document.getElementById("vCounts").click());
  await page.evaluate(() => document.getElementById("vToday").click());
  await page.waitForTimeout(200);
  check("turning off Today and coming up hides that section and brings the counts back", !(await shown(page, "dueBars")) && (await shown(page, "previewOverview")));
  check("and it is saved to the server too", views.some((v) => v.show_today === false));
  await page.evaluate(() => document.getElementById("vToday").click());
  await page.waitForTimeout(200);
  // Calm mode follows the same switch
  await page.evaluate(() => { document.getElementById("calmBtn").click(); });
  await page.waitForTimeout(300);
  check("Calm mode shows its Start here card while the switch is on", await shown(page, "dueBars"));
  await page.evaluate(() => document.getElementById("vToday").click());
  await page.waitForTimeout(200);
  check("Calm mode hides it when the switch is off", !(await shown(page, "dueBars")));
  await page.evaluate(() => document.getElementById("viewReset").click());
  await page.waitForTimeout(200);
  check("Reset to default brings both sections back", await page.locator("#vToday").isChecked() && await page.locator("#vCounts").isChecked());
  check("no script errors", errors.length === 0);
  await page.close();
}
await browser.close();
if (failed) process.exit(1);
console.log("All home section checks passed.");
