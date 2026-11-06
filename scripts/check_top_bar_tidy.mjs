// Browser check: the tidy top bar and left menu: logo level with the search box, round Sync and Agent buttons, Calm mode only in the account menu,
// rarer views under More, see-through scroll bars, soft Mark as unread, glowing AI summary. Pretend server, as in check_top_bar_tidy.mjs.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_top_bar_tidy.mjs [path/to/prototype/index.html]
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
let layoutChoice = null;
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
  if (p === "/api/v1/me/mail-view") { if (m === "PUT") views.push(JSON.parse(req.postData() || "{}")); return json(200, m === "GET" ? { view: layoutChoice ? { layout: layoutChoice } : null } : { view: JSON.parse(req.postData() || "{}") }); }
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
  const box = (sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, w: r.width, h: r.height, left: r.left, right: r.right, shown: !e.hidden && e.offsetParent !== null }; }, sel);
  const logo = await box(".brand-wordmark"), search = await box("#search");
  check("the logo is smaller than before", logo.w <= 130);
  check("the logo sits level with the search box", Math.abs((logo.top + logo.bottom) / 2 - (search.top + search.bottom) / 2) <= 6);
  const sync = await box("#syncBtn"), agent = await box("#agentBtn"), bell = await box("#bellBtn");
  check("Sync is a round icon in the top bar", !!sync && sync.shown && sync.w === sync.h && sync.w <= 40 && (await page.textContent("#syncBtn")).trim() === "");
  check("Agent is a round icon in the top bar with no word on it", !!agent && agent.shown && agent.w === agent.h && (await page.textContent("#agentBtn")).trim() === "");
  check("Agent and Sync say their names when pointed at", (await page.getAttribute("#agentBtn", "title")) === "Agent" && (await page.getAttribute("#syncBtn", "title")) === "Sync mail");
  check("both sit in the same row as the bell", Math.abs(sync.top - agent.top) < 2 && (!bell.shown || Math.abs(bell.top - agent.top) < 2));
  check("the left menu no longer has Calm mode or Agent", !(await visible(page, "#calmBtn")) && !(await page.$("#sidebar #agentBtn")));
  check("Calm mode is still in the account menu", !!(await page.$("#previewCalmBtn")));
  await page.click("#previewCalmBtn", { force: true }).catch(() => {});
  const order = await page.evaluate(() => [...document.querySelectorAll(".side-nav > .nav:not([hidden])")].map((e) => e.textContent.trim().replace(/\d+$/, "").trim()));
  check("the main list starts with My inbox, Needs action, Tasks, Starred", order.slice(0, 4).join("|") === "My inbox|Needs action|Tasks|Starred");
  const inMore = await page.evaluate(() => [...document.querySelectorAll("#moreItems [data-filter]")].map((e) => e.dataset.filter));
  check("Archived, Drafts, Sent and Attachments are under More, and Folders and then Tags sit just above More", ["archived", "drafts", "sent", "attachments"].every((f) => inMore.includes(f)) && !inMore.includes("folders") && (await page.evaluate(() => document.querySelector("#folderNav").nextElementSibling.nextElementSibling.id === "tagNav" && document.querySelector("#tagNav").nextElementSibling.nextElementSibling.id === "moreNav")));
  check("More starts closed", (await page.getAttribute("#moreToggle", "aria-expanded")) === "false");
  await page.click("#agentBtn");
  check("the round Agent button opens the chat", await page.evaluate(() => !document.querySelector("#agentPop").hidden));
  const sb = await page.evaluate(() => { const e = document.querySelector(".side-nav"); const cs = getComputedStyle(e, "::-webkit-scrollbar"); return cs.width; });
  check("the left menu scroll bar is thin", parseFloat(sb) <= 8);
  const unread = await page.evaluate(() => { const b = document.createElement("button"); b.className = "action unread"; document.body.append(b); const c = getComputedStyle(b).color; b.remove(); return c; });
  const [r, g, bl] = unread.match(/\d+/g).map(Number);
  check("Mark as unread is no longer red", !(r > g + 60 && r > bl + 60));
  const glow = await page.evaluate(() => { const d = document.createElement("div"); d.className = "qsummary"; d.innerHTML = '<span class="qsummary-copy">x</span>'; document.body.append(d); const v = getComputedStyle(d).boxShadow; d.remove(); return v; });
  check("the AI summary box has a glow", glow && glow !== "none");
  if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, "top-bar-tidy.png") });
  const wInbox = await page.evaluate(() => document.querySelector("#sidebar").getBoundingClientRect().width);
  await page.evaluate(() => openSettings("settings"));
  await page.waitForTimeout(400);
  const wSettings = await page.evaluate(() => document.querySelector("#sidebar").getBoundingClientRect().width);
  check("the left menu is the same width in Settings as in the inbox", Math.abs(wInbox - wSettings) < 1);
  await page.evaluate(() => closeSettings());
  await page.waitForTimeout(300);
  await page.click("#agentBtn");
  await page.click("article.mail .sender, article.mail").catch(() => {});
  await page.waitForTimeout(500);
  if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, "top-bar-open.png") });
  if (process.env.SHOTS) {
    await page.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Mark as read" && x.offsetParent); if (b) { b.classList.remove("reviewed"); b.classList.add("unread"); for (const n of b.childNodes) if (n.nodeType === 3 || n.tagName === "SPAN") n.textContent = n.textContent.replace("Mark as read", "Mark as unread"); } });
    await page.screenshot({ path: path.join(process.env.SHOTS, "top-bar-unread.png"), clip: { x: 668, y: 760, width: 600, height: 120 } });
  }
  check("the Recent emails bar is hidden while a full-screen email is open", await page.evaluate(() => { document.body.classList.add("reader-open"); const v = getComputedStyle(document.querySelector("#previewListHeading")).visibility; document.body.classList.remove("reader-open"); return v === "hidden"; }));
  check("no script errors", errors.length === 0);
}
{
  const { page, errors } = await open({ width: 390, height: 800 });
  check("on a phone the top bar still has Agent", await visible(page, "#mAgentBtn"));
  await page.click("#mAgentBtn");
  check("and it opens the chat", await page.evaluate(() => !document.querySelector("#agentPop").hidden));
  check("no script errors on a phone", errors.length === 0);
}
{
  layoutChoice = "screen";
  // Full-screen reading: the Back button and the up/down arrows must be pressable, and nothing may sit over them.
  const { page, errors } = await open({ width: 1400, height: 900 });
  await page.click("article.mail");
  await page.waitForSelector(".reader");
  const top = await page.evaluate(() => [...document.querySelectorAll(".rtop .rbtn")].map((b) => { const r = b.getBoundingClientRect(), t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return t === b; }));
  check("the Back and the up and down buttons are not covered by anything", top.length === 3 && top.every(Boolean));
  const title = async () => page.textContent(".reader .rtop b");
  const first = await title();
  await page.click('.rtop .rbtn[aria-label="Next email"]');
  await page.waitForTimeout(300);
  check("the down arrow moves to the next email", (await title()) !== first);
  await page.click('.rtop .rbtn[aria-label="Previous email"]');
  await page.waitForTimeout(300);
  check("the up arrow moves back", (await title()) === first);
  await page.click(".rtop [data-reader-close]");
  await page.waitForTimeout(300);
  check("Back returns to the list", (await page.locator(".reader").count()) === 0);
  check("no script errors", errors.length === 0);
}
await browser.close();
console.log(failed ? "Some top bar checks failed." : "All top bar checks passed.");
process.exit(failed ? 1 : 0);
