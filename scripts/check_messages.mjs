// Browser check for Messages (v0.61): sidebar count, the Home card, the Messages page (list, conversation, new message,
// unsend, mute), the phone layout, and that hostile text is shown as text only. Loaded from a pretend Enveliq server.
//
// Usage: node scripts/check_messages.mjs [path/to/prototype/index.html]
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
const ctx = (id) => ({ reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const PEOPLE = { u2: { id: "u2", name: "Beth", avatar_v: null }, u3: { id: "u3", name: "Sam", avatar_v: "v1" } };
const ME = "u1";
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, waiting: false, messages: opts.messages !== false };
  let n = 0;
  const id = (c, len) => c + String(++n).padStart(len, "0");
  const threads = [
    { id: id("t", 24), members: [ME, "u2"], muted: false, messages: [
      { id: id("m", 16), from: "u2", at: now - 90000, text: "Did the parcel from the pharmacy arrive?", seen: true },
      { id: id("m", 16), from: ME, at: now - 89000, text: "Yes, it's on the hall table.", seen: true },
      { id: id("m", 16), from: "u2", at: now - 600, text: "<img src=x onerror=window.__pwned=1>Can you look at the strata levy email before tonight?", seen: false },
    ] },
    { id: id("t", 24), members: [ME, "u3"], muted: false, messages: [{ id: id("m", 16), from: "u3", at: now - 1200, text: "Dinner at 7, I'll bring dessert", seen: false }] },
  ];
  const name = (u) => (u === ME ? "Morgan" : PEOPLE[u].name);
  const card = (u) => PEOPLE[u];
  const unread = (t) => (t.muted ? 0 : t.messages.filter((m) => !m.seen && m.from !== ME && !m.deleted).length);
  const row = (t) => {
    const others = t.members.filter((u) => u !== ME), last = [...t.messages].reverse().find((m) => !m.deleted);
    const names = others.map(name);
    return { id: t.id, title: names.length <= 1 ? names[0] : names.length === 2 ? `${names[0]}, ${names[1]} and you` : `${names[0]}, ${names[1]} and ${names.length - 1} more`, members: others.map(card), group: t.members.length > 2, muted: t.muted,
      unread: unread(t), last: last ? { from: last.from, mine: last.from === ME, name: name(last.from), text: last.text, at: last.at } : null, updated: t.messages.length ? t.messages[t.messages.length - 1].at : now };
  };
  const view = (t) => ({ ...row(t), everyone: t.members.map((u) => (u === ME ? { id: ME, name: "Morgan", avatar_v: null } : card(u))),
    messages: t.messages.map((m) => ({ id: m.id, from: m.from, name: name(m.from), mine: m.from === ME, at: m.at, text: m.deleted ? "" : m.text, deleted: !!m.deleted })) });
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = () => { try { return JSON.parse(req.postData() || "{}"); } catch (e) { return {}; } };
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: ME, username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: ME, display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [{ id: "m1", subject: "Vote required: balcony repair levy", sender_display: "Harbourview Strata", sender_address: "s@example.invalid", summary: "A vote is needed.", priority: "normal", category: "Information", action_required: false, received_at: now - 600, reply_context: ctx("m1") }]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    if (/^\/api\/v1\/users\/u3\/avatar/.test(p)) return route.fulfill({ status: 200, contentType: "image/png", body: PNG });
    if (!p.startsWith("/api/v1/messages")) return json(404, { detail: "not found: " + p });
    const sub = p.slice("/api/v1/messages".length);
    if (sub === "/summary") {
      const L = threads.filter((t) => unread(t)).map((t) => { const u = t.messages.filter((m) => !m.seen && m.from !== ME && !m.deleted); const m = u[u.length - 1]; return { thread: t.id, from: card(m.from), text: m.text, at: m.at, count: u.length }; }).sort((a, b) => b.at - a.at);
      return json(200, { enabled: true, unread: threads.reduce((s, t) => s + unread(t), 0), conversations: L.length, latest: L.slice(0, 3) });
    }
    if (sub === "/people") return json(200, { people: Object.values(PEOPLE) });
    if (sub === "/threads" && req.method() === "GET") return json(200, { threads: threads.map(row).sort((a, b) => b.updated - a.updated) });
    if (sub === "/threads" && req.method() === "POST") {
      const b = body(); calls.push(["start", b.to, b.text]);
      const members = [ME, ...b.to], same = members.length === 2 && threads.find((t) => t.members.length === 2 && t.members.includes(b.to[0]));
      const t = same || { id: id("t", 24), members, muted: false, messages: [] };
      if (!same) threads.push(t);
      t.messages.push({ id: id("m", 16), from: ME, at: Math.floor(Date.now() / 1000), text: b.text, seen: true });
      return json(201, view(t));
    }
    let m = sub.match(/^\/threads\/(t\d{24})$/);
    if (m && req.method() === "GET") { const t = threads.find((x) => x.id === m[1]); return t ? json(200, view(t)) : json(404, { detail: "Not found." }); }
    m = sub.match(/^\/threads\/(t\d{24})\/(read|messages|mute)$/);
    if (m) {
      const t = threads.find((x) => x.id === m[1]); if (!t) return json(404, { detail: "Not found." });
      if (m[2] === "read") { calls.push(["read", t.id]); t.messages.forEach((x) => (x.seen = true)); return route.fulfill({ status: 204 }); }
      if (m[2] === "messages") { calls.push(["send", body().text]); t.messages.push({ id: id("m", 16), from: ME, at: Math.floor(Date.now() / 1000), text: body().text, seen: true }); return json(201, view(t)); }
      if (m[2] === "mute") { calls.push(["mute", body().muted]); t.muted = body().muted; return route.fulfill({ status: 204 }); }
    }
    m = sub.match(/^\/threads\/(t\d{24})\/messages\/(m\d{16})$/);
    if (m && req.method() === "DELETE") { const t = threads.find((x) => x.id === m[1]); const g = t.messages.find((x) => x.id === m[2]); calls.push(["unsend", g.text]); g.deleted = true; return route.fulfill({ status: 204 }); }
    return json(404, { detail: "not found: " + p });
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

// ---- a computer-sized window ----
{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server);
  await page.waitForFunction(() => document.getElementById("msgBadge").textContent === "2");
  check("the Messages entry is in the sidebar", await page.locator("#msgNav").isVisible());
  check("the count shows 2 unread messages and is highlighted", (await page.locator("#msgBadge").innerText()).trim() === "2" && (await page.locator("#msgBadge.hot").count()) === 1);
  const card = await page.locator("#msgBars").innerText();
  check("Home says who left you how many messages", card.includes("Beth and Sam left you 2 messages") && card.includes("Dinner at 7"));
  await shot(page, "messages-home");

  await page.click("#msgBars [data-msg-go]");
  await page.waitForSelector("#msgPage .mgrow");
  await page.waitForSelector("#mgMsgs .mgmsg");
  check("the page replaces the email list", await page.locator("#list").isHidden() && await page.locator("#msgBars").isHidden());
  check("both conversations are listed", (await page.locator("#msgPage .mgrow").count()) === 2);
  check("the conversation with something new opens by itself and says who can see it", (await page.locator("#msgPage .mgh b").innerText()).trim() === "Beth" && (await page.locator("#msgPage").innerText()).includes("Only you and Beth can see this conversation"));
  check("opening it marks it read: the count drops to 1", (await page.locator("#msgBadge").innerText()).trim() === "1" && server.calls.some((c) => c[0] === "read"));
  check("a picture shows when someone has one", (await page.locator("#msgPage .mgav img").count()) >= 1);

  check("the conversation shows its days and messages", (await page.locator("#mgMsgs .mgday").count()) >= 1 && (await page.locator("#mgMsgs .mgmsg").count()) === 3);
  check("hostile text from a message is shown as text only", (await page.locator("#mgMsgs img").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined && (await page.locator("#mgMsgs").innerText()).includes("<img src=x"));
  await page.locator("#msgPage .mgrow", { hasText: "Sam" }).click();
  await page.waitForFunction(() => document.querySelector("#msgPage .mgh b")?.textContent.trim() === "Sam");
  await page.waitForFunction(() => document.getElementById("msgBadge").hidden);
  check("with nothing left to read the count disappears", true);
  await shot(page, "messages-page");

  await page.fill("#mgText", "On it, I'll read it at lunch");
  await page.press("#mgText", "Enter");
  await page.waitForFunction(() => document.querySelector("#mgMsgs").innerText.includes("I'll read it at lunch"));
  check("Enter sends the message and it appears on the right", server.calls.some((c) => c[0] === "send" && c[1] === "On it, I'll read it at lunch") && (await page.locator("#mgMsgs .mgmsg.me").count()) === 1 && (await page.inputValue("#mgText")) === "");
  await page.fill("#mgText", "line one");
  await page.press("#mgText", "Shift+Enter");
  check("Shift+Enter makes a new line and does not send", (await page.inputValue("#mgText")).includes("\n") && server.calls.filter((c) => c[0] === "send").length === 1);
  await page.fill("#mgText", "");

  await page.locator("#mgMsgs .mgmsg.me", { hasText: "lunch" }).locator("[data-msg-unsend]").click();
  await page.waitForFunction(() => document.querySelector("#mgMsgs .mgmsg.del"));
  check("Unsend leaves a quiet 'Message removed'", server.calls.some((c) => c[0] === "unsend") && (await page.locator("#mgMsgs .mgmsg.del").innerText()).includes("Message removed"));

  await page.click("[data-msg-mute]");
  await page.waitForFunction(() => document.querySelector("[data-msg-mute]").textContent.trim() === "Unmute");
  check("Mute is remembered and the button flips to Unmute", server.calls.some((c) => c[0] === "mute" && c[1] === true));
  await page.click("[data-msg-mute]");

  await page.click("[data-msg-new]");
  await page.waitForSelector("[data-msg-pick]");
  await page.click("#mgText");
  await page.fill("#mgText", "Hello both");
  await page.click("[data-msg-send]");
  await page.waitForFunction(() => document.getElementById("toast").textContent.includes("Choose who"));
  check("a message with nobody chosen is not sent", !server.calls.some((c) => c[0] === "start"));
  await page.locator('[data-msg-pick][aria-label="Beth"]').check();
  await page.locator('[data-msg-pick][aria-label="Sam"]').check();
  await shot(page, "messages-new");
  await page.click("[data-msg-send]");
  await page.waitForFunction(() => document.querySelector("#msgPage .mgh b")?.textContent.includes("and you"));
  check("choosing two people starts a group, titled with their names", (await page.locator("#msgPage .mgh b").innerText()).trim() === "Beth, Sam and you" && (await page.locator("#msgPage").innerText()).includes("Only the 3 people in this conversation can see it"));

  check("nothing was blocked by the page's security rules and nothing crashed", csp.length === 0 && errors.length === 0);
  if (csp.length || errors.length) console.log("::error::" + [...csp, ...errors].join(" | ").slice(0, 400));
  await context.close();
}

// ---- switched off ----
{
  const server = makeServer({ messages: false });
  const { page, context } = await open(server);
  check("with Messages switched off there is no entry, no count and no card", await page.locator("#msgNav").isHidden() && await page.locator("#msgBars").isHidden());
  check("the page never even asks for messages", !server.calls.length);
  await context.close();
}

// ---- a phone ----
{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800 });
  await page.waitForFunction(() => document.getElementById("msgBars").textContent.includes("left you"));
  await page.click("#msgBars [data-msg-go]");
  await page.waitForSelector("#msgPage .mgrow");
  check("on a phone the list comes first, with no conversation squeezed beside it", (await page.locator("#msgPage .mgr").isHidden()) && await page.locator("#msgPage .mgl").isVisible());
  await shot(page, "messages-phone-list");
  await page.locator("#msgPage .mgrow", { hasText: "Sam" }).click();
  await page.waitForSelector("#mgMsgs");
  check("opening one shows only the conversation, with a Back button", await page.locator("#msgPage .mgl").isHidden() && await page.locator("[data-msg-back]").isVisible());
  const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  check("nothing runs off the side of the screen", fits);
  await shot(page, "messages-phone-thread");
  await page.click("[data-msg-back]");
  await page.waitForSelector("#msgPage .mgl");
  check("Back returns to the list", await page.locator("#msgPage .mgl").isVisible());
  await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
