// Browser check for Snooze: an email can be set aside until Later today, Tomorrow, This weekend, Next week or a chosen date. The page works out
// the time in the person's own time zone and sends a Unix time; the email leaves the inbox, shows under Snoozed, and comes back at the top.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_snooze.mjs [path/to/prototype/index.html]
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
let failNext = false;
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
  const sn = /\/messages\/(m-[a-c])\/snooze$/.exec(p);
  if (sn && req.method() === "POST") {
    if (failNext) { failNext = false; return json(422, { detail: "Pick a time between now and 366 days away." }); }
    const until = JSON.parse(req.postData() || "{}").until;
    posted.push({ id: sn[1], until });
    messages.find((m) => m.id === sn[1]).snoozed_until = until;
    return json(200, { snoozed_until: until });
  }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: nowS } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height) {
  const context = await browser.newContext({ viewport: { width, height }, timezoneId: "Australia/Melbourne", locale: "en-AU" });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  messages.forEach((m) => { m.snoozed_until = null; });
  await page.clock.install({ time: new Date(NOW.getTime() - 5000) });
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.clock.pauseAt(NOW);              // time stands still at 10:00 until a check moves it
  return { page, errors, context };
}
async function expandAll(page) {
  for (let i = 0; i < 10; i++) {
    const pressed = await page.evaluate(() => { const b = document.querySelector('.qtoggle[data-expand][aria-expanded="false"]'); if (!b) return false; b.click(); return true; });
    if (!pressed) break;
  }
}
const row = (page, subject) => page.locator("article.mail", { hasText: subject });
const utc = (iso) => Math.floor(new Date(iso).getTime() / 1000);
const badge = (page, id) => page.locator("#" + id).innerText();

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  check("with nothing snoozed there is no Snoozed entry in the left menu", await page.locator("#snoozeNav").isHidden());
  await row(page, "Dentist on Monday").locator("[data-snooze]").click();
  const menu = page.locator("#snoozeMenu");
  const labels = (await menu.locator("[data-snooze-pick] span").allInnerTexts()).join("|");
  check("the menu offers Later today, Tomorrow, This weekend and Next week", labels === "Later today|Tomorrow|This weekend|Next week");
  check("each choice shows the day and time it means, in the person's own time", /tomorrow 8:00\s?am/i.test(await menu.innerText()) && /Sat, 17 Oct/.test(await menu.innerText()) && /Mon, 19 Oct/.test(await menu.innerText()));
  await shot(page, "snooze-menu");
  await menu.locator("[data-snooze-pick]", { hasText: "Tomorrow" }).click();
  await page.waitForTimeout(200);
  check("Tomorrow sends 8 am tomorrow, Melbourne time, as a Unix time", posted.length === 1 && posted[0].id === "m-a" && posted[0].until === utc("2026-10-15T08:00:00+11:00"));
  check("the email leaves the inbox list", (await row(page, "Dentist on Monday").count()) === 0 && (await row(page, "Your electricity bill").count()) === 1);
  check("the inbox count goes down and Snoozed appears with a count of 1", (await badge(page, "allBadge")) === "2" && (await page.locator("#snoozeNav").isVisible()) && (await badge(page, "snoozeBadge")) === "1");
  await expandAll(page);
  await row(page, "Your electricity bill").locator("[data-snooze]").click();
  await menu.locator("[data-snooze-pick]", { hasText: "Later today" }).click();
  await page.waitForTimeout(200);
  check("Later today is three hours on, to the next half hour", posted[1].until === utc("2026-10-14T13:00:00+11:00"));
  await expandAll(page);
  await row(page, "Book club").locator("[data-snooze]").click();
  await menu.locator("[data-snooze-pick]", { hasText: "This weekend" }).click();
  await page.waitForTimeout(200);
  check("This weekend is Saturday 8 am", posted[2].until === utc("2026-10-17T08:00:00+11:00"));

  await page.locator("#snoozeNav").click();
  await expandAll(page);
  check("the Snoozed view lists all three, each saying when it comes back", (await page.locator("article.mail").count()) === 3 && /Snoozed until tomorrow 8:00\s?am/i.test(await row(page, "Dentist on Monday").innerText()));
  await shot(page, "snooze-list");
  await row(page, "Dentist on Monday").locator("[data-unsnooze]").click();
  await page.waitForTimeout(200);
  check("Wake now sends no time and the email leaves the Snoozed view", posted[3].id === "m-a" && posted[3].until === null && (await row(page, "Dentist on Monday").count()) === 0);
  await page.locator('.nav[data-filter="all"]').click();
  check("it is back in the inbox", (await row(page, "Dentist on Monday").count()) === 1);
  check("the page never contacted another website", external.length === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  await row(page, "Book club").locator("[data-snooze]").click();
  const menu = page.locator("#snoozeMenu");
  check("a date can be picked, and only from tomorrow on", (await menu.locator("#snzDate").getAttribute("min")) === "2026-10-15");
  await menu.locator("#snzDate").fill("2026-10-20");
  await menu.locator("[data-snooze-date]").click();
  await page.waitForTimeout(200);
  check("a picked date means 8 am that day, Melbourne time", posted[posted.length - 1].until === utc("2026-10-20T08:00:00+11:00"));
  await context.close();
}

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  failNext = true;
  await row(page, "Book club").locator("[data-snooze]").click();
  await page.locator("#snoozeMenu [data-snooze-pick]", { hasText: "Tomorrow" }).click();
  await page.waitForTimeout(300);
  check("if the server says no, the email stays and a plain message is shown", (await row(page, "Book club").count()) === 1 && /Pick a time between now/.test(await page.locator("#toast").innerText()));
  await page.keyboard.press("Escape");
  await context.close();
}

{
  // coming back: the email returns at the top when its time passes
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  await row(page, "Book club").locator("[data-snooze]").click();
  await page.locator("#snoozeMenu [data-snooze-pick]", { hasText: "Later today" }).click();
  await page.waitForTimeout(200);
  check("before its time it is out of sight", (await row(page, "Book club").count()) === 0);
  await page.clock.fastForward("03:10:00");
  await page.waitForTimeout(300);
  const first = await page.locator("article.mail").first().innerText();
  check("when its time comes it returns at the top and says so", /Book club/.test(first) && /Back from snooze/.test(first));
  check("the Snoozed entry goes away when nothing is snoozed", await page.locator("#snoozeNav").isHidden());
  await shot(page, "snooze-back");
  check("no page errors when it wakes", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 800);
  await expandAll(page);
  await row(page, "Dentist on Monday").locator("[data-snooze]").click();
  const box = await page.locator("#snoozeMenu").boundingBox();
  check("on a phone the menu sits inside the screen", box && box.x >= 0 && box.x + box.width <= 390 && box.y >= 0 && box.y + box.height <= 800);
  check("its choices are easy to tap", (await page.locator("#snoozeMenu [data-snooze-pick]").evaluateAll((b) => b.every((x) => x.getBoundingClientRect().height >= 44))));
  check("the page does not scroll sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot(page, "snooze-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
