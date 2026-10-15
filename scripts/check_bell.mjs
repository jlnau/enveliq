// Browser check for the notification bell: the icon next to the news-feed icon, its badge, the drop-down (notes from Home Assistant and other
// services, and your chat messages), making and removing the key, and the full-screen phone version.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_bell.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html"));
const html = fs.readFileSync(target, "utf8");
const ORIGIN = "http://enveliq.test";
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const calls = [];
let notes = [
  { id: "n0000000000000001", title: "Washer finished", message: "Empty it before it creases.", source: "Home Assistant", at: now - 90, unread: true },
  { id: "n0000000000000002", title: "Front door open", message: "", source: "", at: now - 7200, unread: true },
  { id: "n0000000000000003", title: "Backup done", message: "All good.", source: "Home Assistant", at: now - 90000, unread: false },
];
let keyMade = null;
let chatUnread = 2;
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, rss: true, tags: false, subscriptions: false, travel: false, waiting: false, messages: true, write_help: false };
const mk = (id, subject, name, n) => ({ id, subject, sender_display: name, sender_address: name.toLowerCase() + "@example.invalid", summary: "A summary.", priority: "normal", category: null, action_required: false, received_at: now - n,
  reply_context: { reply_to: name.toLowerCase() + "@example.invalid", delivered_to: null, via_alias: null, message_id: "<" + id + "@x>", references: [], cc: [], also_to: [] } });
const base = [mk("m-plain", "Just you", "Bob", 120), mk("m-other", "Another one", "Cara", 180)];
const view = () => ({ items: notes, unread: notes.filter((n) => n.unread).length, key_made: keyMade, ws_path: "/api/v1/inbound/ws" });
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, base);
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/rss") return json(200, { enabled: true, new: 0, feeds: [], max_feeds: 20 });
  if (p === "/api/v1/messages/summary") return json(200, { enabled: true, unread: chatUnread, conversations: 1, latest: [{ from: { id: "u2", name: "Cara" }, text: "Dinner at 7?", at: now - 60 }] });
  if (p === "/api/v1/messages/threads") return json(200, { threads: [] });
  if (p === "/api/v1/messages/people") return json(200, { people: [] });
  if (p === "/api/v1/me/bell" && req.method() === "GET") { calls.push(["list"]); return json(200, view()); }
  if (p === "/api/v1/me/bell" && req.method() === "DELETE") { calls.push(["clear"]); notes = []; return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/me/bell/read") { calls.push(["read"]); notes = notes.map((n) => ({ ...n, unread: false })); return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/me/bell/key" && req.method() === "POST") { calls.push(["key"]); keyMade = now; return json(200, { key: "evq_TESTKEY-not-a-real-key", ws_path: "/api/v1/inbound/ws" }); }
  if (p === "/api/v1/me/bell/key" && req.method() === "DELETE") { calls.push(["key-remove"]); keyMade = null; return route.fulfill({ status: 204 }); }
  const dm = p.match(/^\/api\/v1\/me\/bell\/(n[0-9a-f]{16})$/);
  if (dm && req.method() === "DELETE") { calls.push(["dismiss", dm[1]]); notes = notes.filter((n) => n.id !== dm[1]); return route.fulfill({ status: 204 }); }
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const run = async (width, height) => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "list" })); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};

{
  const { page, context, errors } = await run(1300, 900);
  await page.waitForSelector("#bellBtn:not([hidden])");
  const bell = await page.locator("#bellBtn").boundingBox(), rss = await page.locator("#rssBtn").boundingBox();
  check("the bell sits at the top right, next to the news-feed icon", Math.abs(bell.y - rss.y) < 3 && bell.x < rss.x && rss.x - (bell.x + bell.width) < 20);
  const badge = await page.locator("#bellBtn .rssbadge").innerText();
  check("the badge counts unread notes and unread chat messages together (2 notes + 2 messages)", badge.trim() === "4");
  await page.locator("#bellBtn").click();
  await page.waitForSelector("#bellPop:not([hidden]) .rss-item");
  const text = await page.locator("#bellPop").innerText();
  check("the drop-down shows the chat messages", /2 unread messages from Cara/.test(text) && (await page.locator("#bellPop [data-msg-go]").count()) === 1);
  check("it shows notes from other services, with where they came from", /Washer finished/.test(text) && /Empty it before it creases/.test(text) && /From Home Assistant/.test(text));
  check("a note with no source says it came from a service on the network", /From a service on your network/.test(text));
  check("unread notes are marked", (await page.locator("#bellPop .rss-item.new").count()) === 3);
  check("the connecting steps are folded away", (await page.locator("#bellPop details").evaluate((d) => d.open)) === false);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "bell_desktop.png") });
  await page.locator("#bellPop [data-bell-dismiss='n0000000000000002']").click();
  await page.waitForFunction(() => !/Front door open/.test(document.getElementById("bellPop").innerText));
  check("Dismiss removes one note", calls.some((c) => c[0] === "dismiss" && c[1] === "n0000000000000002"));
  await page.locator("#bellPop summary").click();
  const how = await page.locator("#bellPop").innerText();
  check("the fold explains the local address and the first messages to send", /ws:\/\/YOUR-SERVER-IP:8765\/api\/v1\/inbound\/ws/.test(how) && /"type":"auth"/.test(how) && /"type":"notify"/.test(how));
  await page.locator("#bellPop [data-bell-key]").click();
  await page.waitForSelector("#bellKey");
  check("making a key shows it once, ready to copy", (await page.locator("#bellKey").inputValue()) === "evq_TESTKEY-not-a-real-key" && /only once/.test(await page.locator("#bellPop").innerText()));
  check("the fold stayed open after making the key", (await page.locator("#bellPop details").evaluate((d) => d.open)) === true);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "bell_key_desktop.png") });
  await page.locator("[data-bell-close]").first().click();
  for (let i = 0; i < 40 && !calls.some((c) => c[0] === "read"); i++) await page.waitForTimeout(50);      // the request is sent a moment after the click
  check("closing the drop-down marks the notes as read", calls.some((c) => c[0] === "read"));
  await page.waitForFunction(() => document.querySelector("#bellBtn .rssbadge").textContent.trim() === "2");
  check("the badge keeps only the unread chat messages", true);
  await page.locator("#bellBtn").click();
  await page.waitForSelector("#bellPop:not([hidden])");
  check("the key is never shown again once the drop-down was closed", (await page.locator("#bellKey").count()) === 0);
  await page.locator("#bellPop summary").click();
  await page.locator("#bellPop [data-bell-key-remove]").click();
  await page.waitForFunction(() => /no key yet/.test(document.getElementById("bellPop").innerText));
  check("Remove my key takes the key away", calls.some((c) => c[0] === "key-remove"));
  await page.locator("#bellPop [data-bell-clear]").click();
  await page.waitForFunction(() => document.querySelectorAll("#bellPop [data-bell-dismiss]").length === 0);
  check("Clear the list empties the notes", calls.some((c) => c[0] === "clear"));
  await page.keyboard.press("Escape");
  check("Escape closes the drop-down", await page.locator("#bellPop").isHidden());
  await page.locator("#bellBtn").click();
  await page.mouse.click(300, 600);
  check("clicking elsewhere closes it on a computer", await page.locator("#bellPop").isHidden());
  check("no script errors", errors.length === 0);
  await context.close();
}

{
  // nothing new at all: the badge is gone and the list says so
  notes = []; chatUnread = 0;
  const { page, context, errors } = await run(1300, 900);
  await page.waitForSelector("#bellBtn:not([hidden])");
  check("with nothing new there is no badge", await page.locator("#bellBtn .rssbadge").isHidden());
  await page.locator("#bellBtn").click();
  await page.waitForSelector("#bellPop:not([hidden])");
  check("an empty list says so in plain words", /Nothing new/.test(await page.locator("#bellPop").innerText()));
  check("no script errors", errors.length === 0);
  await context.close();
}

{
  // On a phone the drop-down fills the screen with Close at the top and the buttons at the bottom
  notes = [{ id: "n0000000000000001", title: "Washer finished", message: "Empty it.", source: "Home Assistant", at: now - 90, unread: true }]; chatUnread = 1;
  const { page, context, errors } = await run(390, 800);
  await page.waitForSelector("#mBellBtn:not([hidden])");
  const mb = await page.locator("#mBellBtn").boundingBox();
  check("on a phone the bell is in the top bar, fully on the screen", mb.y < 56 && mb.x >= 0 && mb.x + mb.width <= 390);
  await page.locator("#mBellBtn").click();
  await page.waitForSelector("#bellPop:not([hidden]) .rss-item");
  const full = await page.locator("#bellPop").boundingBox();
  check("on a phone the notifications fill the whole screen", full.x <= 1 && full.y <= 1 && full.width >= 388 && full.height >= 798);
  const close = await page.locator("#bellPop .sf-top .sf-close").boundingBox(), done = await page.locator("#bellPop .sf-foot [data-bell-close]").boundingBox();
  check("Close is fixed at the top and Done at the bottom", close.y < 80 && done.y > 600 && done.y + done.height <= 801);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "bell_phone.png") });
  await page.locator("#bellPop summary").click();
  await page.locator("#bellPop [data-bell-key]").click();
  await page.waitForSelector("#bellKey");
  check("on a phone the key box is easy to use (large text)", (await page.locator("#bellKey").evaluate((e) => parseFloat(getComputedStyle(e).fontSize))) >= 16);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "bell_key_phone.png") });
  await page.locator("#bellPop .sf-foot [data-bell-close]").click();
  check("Done closes it", await page.locator("#bellPop").isHidden());
  check("no script errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
