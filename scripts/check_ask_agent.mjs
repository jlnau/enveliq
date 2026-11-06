// Browser check: "Ask the agent" beside the search box (and under the search results) sends what was typed to the Agent chat instead of searching.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_ask_agent.mjs [path/to/prototype/index.html]
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
let messages, views, chats = [], asked = [];
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
  if (p === "/api/v1/me/agent" && m === "GET") return json(200, { name: "Hermes", ready: true, chats, chat: null });
  if (p === "/api/v1/me/agent/messages" && m === "POST") {
    const body = JSON.parse(req.postData() || "{}"); asked.push(body);
    const chat = { id: "c000000000001", title: body.text.slice(0, 40), at: now, pending: null, error: null, messages: [{ role: "user", text: body.text, at: now }, { role: "assistant", text: "Here is an answer.", at: now }] };
    chats = [{ id: chat.id, title: chat.title, at: now, count: 2 }];
    return json(200, { name: "Hermes", ready: true, chats, chat });
  }
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
async function open(viewport = { width: 1280, height: 900 }) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors };
}
const visible = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); return !!e && !e.hidden && e.offsetParent !== null; }, sel);

messages = make(); views = []; chats = []; asked = [];
{
  const { page, errors } = await open();
  check("the button is hidden while the search box is empty", !(await visible(page, "#askAgentBtn")));
  await page.fill("#search", "w");
  check("one letter is not enough to show it", !(await visible(page, "#askAgentBtn")));
  await page.fill("#search", "I have a flight next week. What time do I need to be at the airport?");
  await page.waitForTimeout(300);
  check("typing shows the Ask the agent button beside the search box", await visible(page, "#askAgentBtn"));
  check("and one under the search results", await visible(page, "[data-ask-agent]"));
  if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, "ask-agent.png") });
  check("nothing was sent just by typing", asked.length === 0);
  await page.click("#askAgentBtn");
  await page.waitForSelector("#agentPop:not([hidden])");
  await page.waitForFunction(() => document.querySelector("#agentLog") && /Here is an answer/.test(document.querySelector("#agentLog").textContent), null, { timeout: 8000 });
  check("pressing it opens the Agent chat and sends what was typed as a new question", asked.length === 1 && asked[0].text.startsWith("I have a flight next week") && !asked[0].chat);
  check("the answer shows in the chat", /Here is an answer/.test(await page.locator("#agentLog").innerText()));
  check("the search box is cleared and the button goes away", (await page.inputValue("#search")) === "" && !(await visible(page, "#askAgentBtn")));
  await page.click("#agentClose");
  // the button under the results does the same
  await page.fill("#search", "electricity bill");
  await page.waitForTimeout(300);
  await page.click("[data-ask-agent]");
  await page.waitForFunction(() => document.querySelector("#agentLog") && document.querySelector("#agentLog").textContent.includes("Here is an answer"), null, { timeout: 8000 });
  check("the button under the results asks too, as another new chat", asked.length === 2 && asked[1].text === "electricity bill" && !asked[1].chat);
  check("no script errors", errors.length === 0);
  await page.close();
}
{
  const { page, errors } = await open({ width: 390, height: 800 });
  await page.evaluate(() => { const s = document.getElementById("search"); s.value = "dentist"; s.dispatchEvent(new Event("input", { bubbles: true })); });
  await page.waitForTimeout(300);
  check("on a phone the button under the results is there to press", await visible(page, "[data-ask-agent]"));
  check("no script errors on a phone", errors.length === 0);
  await page.close();
}
await browser.close();
if (failed) process.exit(1);
console.log("All Ask the agent checks passed.");
