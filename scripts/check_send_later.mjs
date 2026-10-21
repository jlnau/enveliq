// Browser check for Send later: a new email can be kept by the server and sent at Later today, Tomorrow, This weekend or Next week. The page sends a
// Unix time and the person's words to /me/scheduled, closes the writing window, lists the waiting email under Sent and can take it back.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_send_later.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = process.env.TOUR ? "https://enveliq.test" : "http://enveliq.test";
const NOW = new Date("2026-10-14T10:00:00+11:00");   // a Wednesday morning in Melbourne   // https hides the plain-http warning in the website pictures
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const features = { compose: true, address_book: true, sent: true, media: true };
const base = { summary: "Not summarised yet.", priority: "normal", category: "Information", action_required: false, state: "unread" };
const ctx = (id) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const nowS = Math.floor(NOW.getTime() / 1000);
const messages = [
  { ...base, id: "m-a", subject: "Dentist on Monday", sender_display: "Brightwater Dental", sender_address: "clinic@example.invalid", received_at: nowS - 300, reply_context: ctx("a"), summary: "Reminds you of a check-up on Monday at 10:30.", snoozed_until: null },
  { ...base, id: "m-b", subject: "Your electricity bill", sender_display: "Northside Power", sender_address: "bills@example.invalid", received_at: nowS - 600, reply_context: ctx("b"), summary: "Your bill is ready and due in two weeks.", snoozed_until: null },
  { ...base, id: "m-c", subject: "Book club", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: nowS - 900, reply_context: ctx("c"), summary: "Asks which book to read next.", snoozed_until: null },
];
const posted = [];
const waiting = [];
let deleted = null;
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/accounts/a1/sent") return json(200, { items: [], more: false });
  if (p === "/api/v1/me/scheduled" && req.method() === "POST") {
    const b = JSON.parse(req.postData() || "{}");
    posted.push(b);
    waiting.push({ id: "s0123456789abcdef", kind: b.kind, account_id: b.account_id, subject: b.subject, to: b.to[0], people: b.to.length, send_at: b.send_at, state: "pending", error: null, _b: b });
    return json(201, waiting[waiting.length - 1]);
  }
  if (p === "/api/v1/me/scheduled" && req.method() === "GET") return json(200, { now: nowS, max_days: 30, items: waiting });
  if (p.startsWith("/api/v1/me/scheduled/") && req.method() === "DELETE") {
    deleted = p.split("/").pop();
    const w = waiting.pop();
    return json(200, { ...w, body: w._b.body, to_list: w._b.to, cc_list: [], bcc_list: [], from_address: w._b.from_address });
  }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: nowS } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
for (const [width, height] of [[1200, 900], [390, 780]]) {
  const context = await browser.newContext({ viewport: { width, height }, timezoneId: "Australia/Melbourne", locale: "en-AU" });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  posted.length = 0; waiting.length = 0; deleted = null;
  await page.clock.install({ time: new Date(NOW.getTime() - 5000) });
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.clock.pauseAt(NOW);
  const tag = width + "px wide: ";
  await page.evaluate(() => openNewMail());
  check(tag + "the writing window has Send later in the menu next to Send", await page.locator("#nmMore").isVisible() && (await page.locator("#nmLater").count()) === 1);
  check(tag + "a reply window can attach files and has Send later", (await page.locator("#cmAttach").count()) === 1 && (await page.locator("#composeLater").count()) === 1);
  await page.locator("#nmTo input").fill("dana@example.invalid");
  await page.locator("#nmTo input").press("Enter");
  await page.locator("#nmSubject").fill("Later on");
  await page.locator("#nmText").fill("Some words to send later.");
  await page.locator("#nmMore").click();
  await page.locator("#nmLater").click();
  const menu = page.locator("#laterMenu");
  const labels = (await menu.locator("[data-later-pick] span").allInnerTexts()).join("|");
  check(tag + "the menu offers the same times as Snooze", labels === "Later today|Tomorrow|This weekend|Next week");
  const box = await menu.boundingBox();
  check(tag + "the menu stays on the screen", box && box.x >= 0 && box.y >= 0 && box.x + box.width <= width);
  await shot(page, "send-later-" + width);
  await menu.locator("[data-later-pick]", { hasText: "Tomorrow" }).click();
  await page.waitForTimeout(300);
  check(tag + "Tomorrow sends 8 am tomorrow, Melbourne time, with the person's words and no files", posted.length === 1 && posted[0].kind === "new" && posted[0].send_at === Math.floor(new Date("2026-10-15T08:00:00+11:00").getTime() / 1000) && posted[0].to[0].includes("dana@example.invalid") && posted[0].body.includes("Some words") && !posted[0].files);
  check(tag + "the writing window closes", !(await page.locator("#newMail.open").count()));
  await page.evaluate(() => document.querySelector('.nav[data-filter="sent"]').click());
  await page.waitForSelector("#sentWaiting button");
  const note = await page.locator("#sentWaiting").innerText();
  check(tag + "the email is listed as waiting, with its time and a way to take it back", /Waiting to send: Later on/.test(note) && /Take it back/.test(note));
  await page.locator("#sentWaiting button").click();
  await page.waitForTimeout(300);
  check(tag + "taking it back asks the server and puts the words back in a writing window", deleted === "s0123456789abcdef" && (await page.evaluate(() => document.getElementById("nmText").value)).includes("Some words"));
  check(tag + "no sideways scroll", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
