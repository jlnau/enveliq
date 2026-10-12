// Browser check for the Hermes chat: the Agent button, the popup, sending, clearing and keeping text safe.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_agent.mjs [path/to/prototype/index.html]
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
const now = Math.floor(Date.now() / 1000);
const features = { compose: true, address_book: true, sent: true, media: true };
const undo = 0;

function makeServer(opts = {}) {
  const calls = [];
  let chats = (opts.chats || []).map((x) => ({ ...x }));
  let n = 0;
  const summary = () => chats.slice().sort((x, y) => y.at - x.at).map((x) => ({ id: x.id, title: x.title, at: x.at, count: x.messages.length }));
  const view = (id, latest) => { const s = summary(); const c = chats.find((x) => x.id === (id || (latest && s[0] && s[0].id))); return { name: "Hermes", ready: opts.ready !== false, chats: summary(), chat: c ? { id: c.id, title: c.title, messages: c.messages, pending: !!c.pending, error: c.error || null } : null }; };
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname, q = new URL(req.url()).searchParams;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: { send_identities: ["work@example.invalid"] } }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [{ id: "m1", subject: "Holiday photos", sender_display: "Cara", sender_address: "cara@example.invalid", summary: "Photos.", priority: "normal", category: null, action_required: false, received_at: now - 600,
      reply_context: { reply_to: "cara@example.invalid", delivered_to: null, via_alias: null, message_id: "<m1@x>", references: [] } }]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: undo });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/agent" && req.method() === "GET") { calls.push(["get", q.get("chat")]);
      for (const c of chats) if (c.pending && q.get("chat") === c.id && --c.pending === 0) { if (opts.slowFails) c.error = "The agent did not answer in time. Try again."; else c.messages.push({ role: "assistant", text: "All quiet on the network.", at: now }); } return json(200, view(q.get("chat"), !q.get("chat"))); }
    let m = /^\/api\/v1\/me\/agent\/chats\/(c[0-9a-f]{12})$/.exec(p);
    if (m && req.method() === "DELETE") { calls.push(["delete", m[1]]); chats = chats.filter((x) => x.id !== m[1]); return json(200, view()); }
    if (m && req.method() === "PATCH") { const b = JSON.parse(req.postData()); calls.push(["rename", m[1], b.title]); const c = chats.find((x) => x.id === m[1]); if (c) c.title = b.title; return json(200, view()); }
    if (p === "/api/v1/me/agent/messages") {
      const body = JSON.parse(req.postData()); calls.push(["send", body]);
      let c = chats.find((x) => x.id === body.chat);
      if (!c) { c = { id: "c" + String(++n).padStart(12, "0"), title: body.text.slice(0, 40), at: now, messages: [] }; chats.push(c); }
      c.messages.push({ role: "user", text: body.text, at: now }); c.at = now + n;
      if (opts.slow) { c.pending = opts.slow; c.error = null; return json(200, view(c.id)); }       // the agent is still working: the page must check back
      if (opts.fail) return json(502, { detail: { code: "ai_unreachable", message: "The AI server could not be reached or took too long to answer." } });
      c.messages.push({ role: "assistant", text: opts.reply || "Start with the smallest thing.\n<img src=x onerror=window.__pwned=1> <b>bold</b>", at: now });
      return json(200, view(c.id));
    }
    return json(404, { detail: "not found" });
  };
  return { handler, calls };
}

const browser = await chromium.launch();
async function open(server, { width = 1200, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) csp.push(m.text()); });
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };

// ---- Working chat ----
{
  const server = makeServer();
  const { page, errors, csp } = await open(server);
  const labels = await page.locator(".side-foot .nav .nav-label").allInnerTexts();
  check("Calm mode and Agent are in the sidebar footer; Light mode, Settings and Administration live in the user menu", labels.join("|") === "Calm mode|Agent" && (await page.locator("#userMenu #themeBtn, #userMenu #settingsBtn, #userMenu #adminBtn").count()) === 3);
  check("the popup is closed to begin with", await page.locator("#agentPop").isHidden());
  await page.click("#agentBtn");
  await page.waitForSelector("#agentPop:not([hidden])");
  await page.waitForSelector(".agent-hello");
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === "agentText");     // focus is set a moment after opening
  check("opening it loads the chat and focuses the box", server.calls.some((c) => c[0] === "get") && (await page.evaluate(() => document.activeElement.id)) === "agentText");
  check("it says what Hermes can't do", (await page.locator("#agentPop").innerText()).includes("can't see your email"));
  await shot(page, "agent-empty");
  await page.fill("#agentText", "How do I start my day?");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".agent-msg.bot:not(.wait)");
  check("Enter sends the message as a new chat", server.calls.some((c) => c[0] === "send" && c[1].text === "How do I start my day?" && !c[1].chat));
  check("the answer is shown", (await page.locator(".agent-msg.bot").first().innerText()).startsWith("Start with the smallest thing."));
  check("the answer is plain text: no markup became page code", (await page.locator(".agent-log img, .agent-log b").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined);
  check("the chat is named after the first message", (await page.locator("#agentSub").innerText()) === "How do I start my day?");
  await page.fill("#agentText", "And after lunch?");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelectorAll(".agent-msg.me").length === 2 && !document.querySelector(".agent-msg.wait"));
  check("a follow-up goes into the same chat", server.calls.filter((c) => c[0] === "send")[1][1].chat === "c000000000001");
  await page.fill("#agentText", "line one");
  await page.keyboard.press("Shift+Enter");
  check("Shift+Enter makes a new line instead of sending", (await page.locator("#agentText").inputValue()).includes("\n") && server.calls.filter((c) => c[0] === "send").length === 2);
  await page.fill("#agentText", "");
  await shot(page, "agent-chat");

  await page.click("#agentNew");
  check("New starts an empty chat", (await page.locator(".agent-hello").count()) === 1 && (await page.locator(".agent-msg").count()) === 0);
  await page.fill("#agentText", "Help me word a message to my landlord");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".agent-msg.bot:not(.wait)");
  check("the second chat is separate", server.calls.filter((c) => c[0] === "send")[2][1].chat === undefined);

  await page.click("#agentChatsBtn");
  await page.waitForSelector(".agent-row");
  const titles = await page.locator(".agent-open b").allInnerTexts();
  check("Chats lists both, newest first", titles.join("|") === "Help me word a message to my landlord|How do I start my day?");
  check("the message box is hidden while the list shows", await page.locator("#agentForm").isHidden());
  await shot(page, "agent-list");
  await page.locator(".agent-open").nth(1).click();
  await page.waitForSelector(".agent-msg.me");
  check("opening an older chat shows its messages", (await page.locator(".agent-msg.me").count()) === 2 && (await page.locator("#agentSub").innerText()) === "How do I start my day?");

  await page.click("#agentChatsBtn");
  await page.locator(".agent-row").nth(1).locator("text=Rename").click();
  await page.fill(".agent-rename", "Morning routine");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => [...document.querySelectorAll(".agent-open b")].some((b) => b.textContent === "Morning routine"));
  check("a chat can be renamed", server.calls.some((c) => c[0] === "rename" && c[2] === "Morning routine"));

  const del = page.locator(".agent-row").nth(0).locator("text=Delete");
  await del.click();
  check("Delete asks for a second tap first", (await page.locator(".agent-row").nth(0).innerText()).includes("Tap again to delete") && !server.calls.some((c) => c[0] === "delete"));
  await page.locator(".agent-row").nth(0).locator("text=Tap again to delete").click();
  await page.waitForFunction(() => document.querySelectorAll(".agent-row").length === 1);
  check("the second tap deletes it", server.calls.some((c) => c[0] === "delete"));

  await page.keyboard.press("Escape");
  check("Escape from the list goes back to the chat, not out of the popup", (await page.locator("#agentPop").isVisible()) && (await page.locator("#agentChats").isHidden()) && (await page.locator("#agentForm").isVisible()));
  await page.keyboard.press("Escape");
  check("Escape closes the popup and gives focus back to the button", (await page.locator("#agentPop").isHidden()) && (await page.evaluate(() => document.activeElement.id)) === "agentBtn");
  check("no script errors or Content-Security-Policy violations", errors.length === 0 && csp.length === 0);
  await page.close();
}

// ---- Saved chats come back after a reload ----
{
  const server = makeServer({ chats: [{ id: "c0000000000aa", title: "Plan for Friday", at: now - 5000, messages: [{ role: "user", text: "Plan Friday", at: now - 5000 }, { role: "assistant", text: "Start with the calls.", at: now - 5000 }] }] });
  const { page } = await open(server);
  await page.click("#agentBtn");
  await page.waitForSelector(".agent-msg.bot");
  check("the latest saved chat opens by itself", (await page.locator(".agent-msg.bot").innerText()) === "Start with the calls." && (await page.locator("#agentSub").innerText()) === "Plan for Friday");
  await page.close();
}

// ---- A failing model keeps the screen calm ----
{
  const server = makeServer({ fail: true });
  const { page } = await open(server);
  await page.click("#agentBtn");
  await page.fill("#agentText", "hello?");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".agent-msg.err");
  check("an unreachable model shows a plain sentence", (await page.locator(".agent-msg.err").innerText()).includes("could not be reached"));
  check("what was typed is still on screen", (await page.locator(".agent-msg.me").innerText()) === "hello?");
  check("the box is usable again", await page.locator("#agentSend").isEnabled());
  await page.fill("#agentText", "second try");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".agent-msg.err");
  check("a retry goes into the same chat instead of starting another", server.calls.filter((c) => c[0] === "send")[1][1].chat === "c000000000001");
  await page.close();
}

// ---- A slow agent: the message goes through at once and the page keeps checking back ----
{
  const server = makeServer({ slow: 3 });
  const { page } = await open(server);
  await page.click("#agentBtn");
  await page.fill("#agentText", "Check pfSense");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".agent-msg.wait");
  check("while the agent works it says so and shows what was typed", (await page.locator(".agent-msg.wait").innerText()).startsWith("Thinking") && (await page.locator(".agent-msg.me").innerText()) === "Check pfSense");
  check("the box cannot send a second message meanwhile", await page.locator("#agentSend").isDisabled());
  await page.waitForSelector(".agent-msg.bot:not(.wait)", { timeout: 20000 });
  check("the answer appears by itself when it is ready", (await page.locator(".agent-msg.bot").innerText()) === "All quiet on the network." && (await page.locator(".agent-msg.wait").count()) === 0);
  check("it checked back more than once", server.calls.filter((c) => c[0] === "get" && c[1]).length >= 3);
  await page.waitForFunction(() => !document.getElementById("agentSend").disabled);
  check("the box is usable again", await page.locator("#agentSend").isEnabled());
  await page.close();
}
{
  const server = makeServer({ slow: 2, slowFails: true });
  const { page } = await open(server);
  await page.click("#agentBtn");
  await page.fill("#agentText", "Are you there?");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".agent-msg.err", { timeout: 20000 });
  check("a slow failure shows a plain sentence and keeps what was typed", (await page.locator(".agent-msg.err").innerText()).includes("did not answer") && (await page.locator(".agent-msg.me").innerText()) === "Are you there?");
  await page.close();
}
{
  // coming back to a chat that is still being answered picks up the wait, and the answer arrives
  const server = makeServer({ slow: 2, chats: [{ id: "c000000000009", title: "Network", at: now, pending: 2, messages: [{ role: "user", text: "Check pfSense", at: now }] }] });
  const { page } = await open(server);
  await page.click("#agentBtn");
  await page.waitForSelector(".agent-msg.wait");
  await page.waitForSelector(".agent-msg.bot:not(.wait)", { timeout: 20000 });
  check("opening a chat that is still being answered shows the answer when it lands", (await page.locator(".agent-msg.bot").innerText()) === "All quiet on the network.");
  await page.close();
}

// ---- No model set up ----
{
  const server = makeServer({ ready: false });
  const { page } = await open(server);
  await page.click("#agentBtn");
  await page.waitForSelector(".agent-msg.err");
  check("with no AI model it says where to set one up", (await page.locator(".agent-msg.err").innerText()).includes("Administration, AI model"));
  await page.close();
}

// ---- Phone ----
{
  const server = makeServer();
  const { page } = await open(server, { width: 390, height: 780 });
  await page.evaluate(() => document.getElementById("agentBtn").click());
  await page.waitForSelector("#agentPop:not([hidden])");
  check("the popup fits the phone", await page.evaluate(() => { const r = document.getElementById("agentPop").getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth && r.bottom <= window.innerHeight && r.top >= 0; }));
  check("no horizontal scroll on the phone", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await shot(page, "agent-phone");
  await page.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
