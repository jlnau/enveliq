// Browser check for "Search everywhere": the one search box also shows matches in Reviewed, Archived and Snoozed emails, tasks, orders and
// waiting notes, using only what the page already holds. Matches are shown as text and lead to the right place.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_search_everywhere.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = process.env.TOUR ? "https://enveliq.test" : "http://enveliq.test";
const NOW = new Date("2026-10-14T10:00:00+11:00");   // https hides the plain-http warning in the website pictures
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const features = { compose: true, address_book: true, sent: true, media: true, shipping: true, waiting: true };
const nowS = Math.floor(NOW.getTime() / 1000);
const base = { priority: "normal", category: "Information", action_required: false, state: "unread", snoozed_until: null };
const ctx = (id) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const messages = [
  { ...base, id: 101, subject: "Dentist on Monday", sender_display: "Brightwater Dental", sender_address: "clinic@example.invalid", received_at: nowS - 300, reply_context: ctx("a"), summary: "Reminds you of a check-up on Monday at 10:30." },
  { ...base, id: 102, subject: "Your electricity bill", sender_display: "Northside Power", sender_address: "bills@example.invalid", received_at: nowS - 90000, reply_context: ctx("b"), summary: "Your bill is ready and due in two weeks.", state: "reviewed", resolved_at: nowS - 3600 },
  { ...base, id: 103, subject: "Photos from the trip", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: nowS - 200000, reply_context: ctx("c"), summary: "Shares the holiday photos and asks about dinner.", state: "archived", resolved_at: nowS - 7200 },
  { ...base, id: 104, subject: "Book club", sender_display: "Kim", sender_address: "kim@example.invalid", received_at: nowS - 400, reply_context: ctx("d"), summary: "Asks which book to read next.", snoozed_until: Math.floor(Date.now() / 1000) + 86400 },
  { ...base, id: 105, subject: "<img src=x onerror=window.__pwned=1>Offer", sender_display: "Odd Sender", sender_address: "odd@example.invalid", received_at: nowS - 500, reply_context: ctx("e"), summary: "A <b>special</b> offer for the trip.", state: "reviewed", resolved_at: nowS - 100 },
];
const tasks = { today: "2026-10-14", tasks: [
  { id: "t1", title: "Ring to confirm the check-up", state: "open", due: "2026-10-15", days: 1, priority: "normal", sender: "Brightwater Dental", received: nowS - 300, account_id: "a1", message_id: 101 },
  { id: "t2", title: "Buy a trip insurance policy", state: "open", due: "2026-10-20", days: 6, priority: "normal", sender: "Alice", received: nowS - 200, account_id: "a1", message_id: "gone" },
] };
const orders = [
  { id: "s" + "a".repeat(23), shop: "Northside Audio", order_number: "NA-20481", carrier: "SwiftPost", tracking: "SP4471002318AU", items: "Studio headphones for the trip", status: "shipped", expected: "2026-10-16", expected_text: "Fri 16 Oct", prev_expected: null, delayed: false, delivered_at: null, ack: null, unsure: false, needs_confirm: false, events: [] },
];
const notes = [
  { id: "w" + "a".repeat(23), to: ["Dana <dana@example.invalid>"], subject: "Quote for the fence", ask: "Waiting for the price.", state: "waiting", due: false, age_days: 1, reason: null, snooze_until: 0 },
];
const external = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) { external.push(req.url()); return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" }); }
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/me/tasks") return json(200, tasks);
  if (p === "/api/v1/me/shipping") return json(200, { enabled: true, orders, now: nowS, carriers: { fixed: [], shared: [] } });
  if (p === "/api/v1/me/waiting") return json(200, { enabled: true, days: 3, notes });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: nowS } } });
  if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
// For the website pictures (TOUR=1) the made-up hostile test email is shown with a friendly subject, so the picture reads well. Only what is drawn changes, not what the check tests.
const shot = async (page, name) => {
  if (!process.env.SHOTS) return;
  if (process.env.TOUR) await page.evaluate(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); for (let n = w.nextNode(); n; n = w.nextNode()) if (n.nodeValue.includes("<img src=x onerror=")) n.nodeValue = n.nodeValue.replace("<img src=x onerror=window.__pwned=1>", ""); });
  await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") });
};
async function open(width, height) {
  const context = await browser.newContext({ viewport: { width, height }, timezoneId: "Australia/Melbourne", locale: "en-AU" });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  // Check opening a search result in the expanded email list, regardless of
  // the user preference that is currently chosen by default.
  await page.evaluate(() => { view.layout = "list"; view.rows = "open"; applyView(); render(); });
  await page.waitForTimeout(500);
  return { page, errors, context };
}
const type = async (page, text) => { await page.locator("#search").fill(text); await page.waitForTimeout(150); };
const more = (page) => page.locator(".srch-more");

{
  const { page, errors, context } = await open(1200, 900);
  await type(page, "electricity");
  let t = await more(page).innerText();
  check("a Reviewed email is found from the inbox, and says where it is", /Your electricity bill/.test(t) && /Reviewed · Northside Power/.test(t));
  await type(page, "check-up");
  check("a task is found, with when it is due", /Tasks/.test(await more(page).innerText()) && /Ring to confirm the check-up/.test(await more(page).innerText()));
  check("an email already shown in the list is not repeated below", !/Dentist on Monday/.test(await more(page).innerText()));
  await type(page, "trip");
  t = await more(page).innerText();
  check("Archived and Snoozed emails, tasks and orders are all found", /Photos from the trip/.test(t) && /Archived/.test(t) && /Buy a trip insurance policy/.test(t) && /Northside Audio · NA-20481/.test(t) && /Orders/.test(t));
  await shot(page, "search-everywhere");
  await type(page, "fence");
  check("a waiting note is found", /Waiting for a reply/.test(await more(page).innerText()) && /Quote for the fence/.test(await more(page).innerText()) && /To Dana/.test(await more(page).innerText()));
  await type(page, "book");
  check("a Snoozed email is found and says so", /Book club/.test(await more(page).innerText()) && /Snoozed · Kim/.test(await more(page).innerText()));
  await type(page, "e");
  check("one letter does not start a search everywhere", (await more(page).count()) === 0);
  await type(page, "zzzz");
  check("when nothing matches nothing extra is shown", (await more(page).count()) === 0);
  await type(page, "onerror");
  const hostile = await more(page).innerText();
  check("hostile text from an email is shown as plain text, never run", /<img src=x onerror=window.__pwned=1>Offer/.test(hostile) && (await more(page).locator("img").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined);

  await type(page, "electricity");
  await more(page).locator("[data-search-open]").first().click();
  await page.waitForTimeout(200);
  check("choosing an email opens the list it is in, with the search cleared and the email open", (await page.locator("#search").inputValue()) === "" && (await page.locator('.nav[data-filter="reviewed"].active').count()) === 1 && (await page.locator("article.mail.open", { hasText: "Your electricity bill" }).count()) === 1);
  await page.locator('.nav[data-filter="all"]').click();
  await type(page, "fence");
  await more(page).locator("[data-search-go]").first().click();
  await page.waitForTimeout(200);
  check("choosing a waiting note opens that page", (await page.locator('.nav[data-filter="waiting"].active').count()) === 1 && /Quote for the fence/.test(await page.locator("#waitPage").innerText()));
  await type(page, "trip");
  check("on that page the extra panel is not shown", (await more(page).count()) === 0);
  check("the page never contacted another website", external.length === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 800);
  await page.locator("#mSearchBtn").click();
  await type(page, "trip");
  const box = await more(page).boundingBox();
  check("on a phone the results fit and the page does not scroll sideways", box && box.x >= 0 && box.x + box.width <= 390 && (await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)));
  check("each result is easy to tap", await more(page).locator(".srch-hit").evaluateAll((b) => b.length > 0 && b.every((x) => x.getBoundingClientRect().height >= 40)));
  await shot(page, "search-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
