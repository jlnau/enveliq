// Browser check for phone width: an email opened full screen never makes the page wider than the screen (the cause of the page looking zoomed in).
// Uses long unbreakable words, a long address, tags and a task on the email, at the narrowest phone widths. The page is loaded from a pretend Enveliq server.
//   node scripts/check_phone_width.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
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
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, tags: true, rss: true, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const mk = (id, subject, name, n) => ({ id, subject, sender_display: name, sender_address: "do-not-reply-" + "x".repeat(45) + "@notifications.example.invalid", summary: "Reminder https://example.invalid/" + "a".repeat(120) + " and " + "b".repeat(70) + " for families", tags: ["SFX", "A rather long tag name for testing", "kids sport"], suggested_task: { title: "Bring a hat and water bottle to PE classes " + "c".repeat(60), due: "2026-10-14", detail: "d".repeat(100) }, priority: "normal", category: null, action_required: false, received_at: now - n,
  reply_context: { reply_to: name.toLowerCase() + "@example.invalid", delivered_to: null, via_alias: null, message_id: "<" + id + "@x>", references: [], cc: [], also_to: [] } });
const proton = { id: "a1", provider: "Proton Mail", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } };
const gmail = { id: "a2", provider: "Gmail", auth_method: "imap", owner_user_id: "u1", display_name: "Gmail test", email_address: "me2@example.invalid", server: "imap.example.invalid", port: 993, username: "me2@example.invalid", settings: { provider_id: "gmail", smtp_port: 465, send_identities: [], ai_summaries: true } };
let accounts = [proton, gmail];
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, accounts);
  if (p === "/api/v1/accounts/a1/messages") return json(200, [mk("m-proton", "From the Proton mailbox", "Bob", 120)]);
  if (p === "/api/v1/accounts/a2/messages") return json(200, [mk("m-gmail", "From the Gmail mailbox", "Cara", 180)]);
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const run = async (width, height, layout = "list") => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript((l) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: l })); } catch (e) {} }, layout);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const rowOf = (page, subject) => page.locator("article.mail", { hasText: subject });
const widths = () => ({ vw: innerWidth, doc: document.documentElement.scrollWidth, rbody: document.querySelector(".rbody") ? document.querySelector(".rbody").scrollWidth : 0, rbodyClient: document.querySelector(".rbody") ? document.querySelector(".rbody").clientWidth : 0 });
for (const w of [320, 360, 390, 412]) {
  const { page, context, errors } = await run(w, 800);
  await page.evaluate(() => { document.getElementById("syncBtn").hidden = false; document.getElementById("mSyncBtn").hidden = false; });
  check(`${w}px: every button in the top bar is fully on the screen, Sync included`, await page.evaluate(() => { const bs = [...document.querySelectorAll("#mTop .mbtn")].filter((b) => !b.hidden && b.getBoundingClientRect().width > 0); return bs.length >= 3 && bs.every((b) => { const r = b.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; }) && !!bs.find((b) => b.id === "mSyncBtn"); }));
  check(`${w}px: New email and News feeds are not in the top bar`, (await page.locator("#mNewBtn, #mRssBtn").count()) === 0);
  await page.click("#menuBtn");
  check(`${w}px: the menu has New email and News feeds`, (await page.locator("#newMailBtn").isVisible()) && (await page.locator("#sideRss").isVisible()));
  await page.click("#menuBtn");
  const list = await page.evaluate(widths);
  check(`${w}px: the list is not wider than the screen`, list.doc <= list.vw);
  await rowOf(page, "Proton mailbox").locator(".qmain").click();
  await page.waitForSelector(".reader .qside");
  await page.waitForTimeout(250);
  const r = await page.evaluate(widths);
  check(`${w}px: the open email is not wider than the screen (page ${r.doc}, email ${r.rbody}, screen ${r.vw})`, r.doc <= r.vw && r.rbody <= r.rbodyClient + 1);
  check(`${w}px: nothing in the open email runs off the right edge`, await page.evaluate(() => [...document.querySelectorAll(".reader *")].every((e) => { const b = e.getBoundingClientRect(); return b.width === 0 || b.right <= innerWidth + 1; })));
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `phone_width_${w}.png`) });
  check(`${w}px: no script errors`, errors.length === 0);
  await context.close();
}
{
  const { page, context } = await run(390, 800);
  check("double-tap zoom is switched off on the page (pinching still works)", await page.evaluate(() => getComputedStyle(document.documentElement).touchAction === "manipulation"));
  check("the browser is told not to enlarge text by itself", await page.evaluate(() => { const s = getComputedStyle(document.documentElement); return (s.webkitTextSizeAdjust || s.textSizeAdjust) === "100%"; }));
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
