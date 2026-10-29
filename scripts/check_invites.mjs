// Browser check for calendar invitations: an open email that carries an invitation shows a card with Accept, Maybe, Decline and Propose new time.
// The answers go to the server (which sends the email and writes the calendar); on a phone the "Propose a new time" form fills the screen with
// its title and Close at the top and its buttons at the bottom. The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_invites.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://enveliq.test";
const NOW = new Date("2026-10-30T10:00:00+11:00");
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const features = { compose: true, address_book: true, sent: true, media: true };
const nowS = Math.floor(NOW.getTime() / 1000);
const start = Math.floor(new Date("2026-11-03T14:00:00+11:00").getTime() / 1000);
const base = { summary: "Sam invites you to a catch-up.", priority: "normal", category: "Information", action_required: false, state: "unread", has_attachments: true, attachment_count: 1 };
const ctx = (id) => ({ reply_to: "sam@example.com", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const messages = [
  { ...base, id: "m-a", subject: "Invitation: Project catch-up", sender_display: "Sam Example", sender_address: "sam@example.com", received_at: nowS - 300, reply_context: ctx("a") },
  { ...base, id: "m-b", subject: "Invitation: Odd one", sender_display: "Pat", sender_address: "pat@elsewhere.invalid", received_at: nowS - 600, reply_context: ctx("b") },
  { ...base, id: "m-c", subject: "Plain email", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: nowS - 900, reply_context: ctx("c"), has_attachments: false, attachment_count: 0 },
];
const card = (over) => ({ method: "REQUEST", summary: "Project catch-up", location: "Video call", description: "", start, end: start + 2700, all_day: false, start_day: "", end_day: "", tz: "Australia/Sydney", repeats: false, cancelled: false,
  organizer: { name: "Sam Example", email: "sam@example.com" }, people: 2, can_answer: true, can_add: true, organizer_differs: false, mine: "me@example.invalid", calendar: "Google Calendar", answer: null, ...over });
const cards = { "m-a": card({}), "m-b": card({ summary: "Odd one", organizer_differs: true, organizer: { name: "", email: "boss@other.invalid" } }) };
const posted = [];
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
  const iv = /\/messages\/(m-[a-c])\/invite(?:\/(answer|propose|calendar))?$/.exec(p);
  if (iv) {
    if (!iv[2]) return cards[iv[1]] ? json(200, cards[iv[1]]) : json(404, { detail: "This email has no calendar invitation." });
    const body = JSON.parse(req.postData() || "{}");
    posted.push({ id: iv[1], what: iv[2], ...body });
    if (iv[2] === "answer") { cards[iv[1]] = { ...cards[iv[1]], answer: { response: body.response, calendar: "Google Calendar", calendar_problem: "" } }; return json(200, { sent: true, from: "me@example.invalid" }); }
    return json(200, { sent: true, from: "me@example.invalid" });
  }
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: nowS } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height) {
  const context = await browser.newContext({ viewport: { width, height }, timezoneId: "Australia/Sydney", locale: "en-AU" });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.evaluate(() => { view.layout = "list"; view.rows = "open"; applyView(); render(); });
  return { page, errors, context };
}
async function expandAll(page) {
  for (let i = 0; i < 10; i++) {
    const pressed = await page.evaluate(() => { const b = document.querySelector('.qtoggle[data-expand][aria-expanded="false"]'); if (!b) return false; b.click(); return true; });
    if (!pressed) break;
  }
}
const row = (page, subject) => page.locator("article.mail", { hasText: subject });

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  const a = row(page, "Project catch-up").locator("section[data-invite]");
  await a.waitFor({ state: "visible" });
  const text = await a.innerText();
  check("the card names the meeting, the place and who it is from", /Project catch-up/.test(text) && /Video call/.test(text) && /Sam Example/.test(text));
  check("the time is shown in the person's own time zone", /Tue,? 3 Nov/.test(text) && /2:00\s?pm/i.test(text) && /2:45\s?pm/i.test(text) && /your time/.test(text));
  check("the four choices are there", (await a.locator(".iv-btns button").allInnerTexts()).join("|") === "Accept|Maybe|Decline|Propose new time");
  check("it says where an accepted meeting will go", /adds the meeting to Google Calendar/.test(text));
  check("an email without an invitation shows no card", (await row(page, "Plain email").locator("section[data-invite]").count()) === 0);
  await shot(page, "invite-card");
  await a.locator('[data-invite-act="accepted"]').click();
  await page.waitForTimeout(300);
  check("Accept asks the server to accept, without the organiser box", posted.length === 1 && posted[0].what === "answer" && posted[0].response === "accepted" && posted[0].confirm_organizer === false);
  check("the card then says You accepted and that it is in the calendar", /You accepted/.test(await a.innerText()) && /It is in Google Calendar/.test(await a.innerText()));
  await a.locator('[data-invite-act="declined"]').click();
  await page.waitForTimeout(300);
  check("Decline is sent the same way", posted[1].response === "declined");

  const b = row(page, "Odd one").locator("section[data-invite]");
  await b.waitFor({ state: "visible" });
  check("an organiser who is not the sender gets a warning and a box", /Be careful/.test(await b.innerText()) && (await b.locator("input[data-invite-ok]").count()) === 1);
  const before = posted.length;
  await b.locator('[data-invite-act="accepted"]').click();
  await page.waitForTimeout(200);
  check("nothing is sent until the box is ticked", posted.length === before);
  await b.locator("input[data-invite-ok]").check();
  await b.locator('[data-invite-act="accepted"]').click();
  await page.waitForTimeout(300);
  check("then the answer goes with the person's agreement", posted[posted.length - 1].confirm_organizer === true);

  await a.locator('[data-invite-act="propose"]').click();
  const sheet = page.locator("#invProp");
  check("Propose new time opens a form with the day, times and a note", (await sheet.locator("#ivpDay").inputValue()) === "2026-11-03" && (await sheet.locator("#ivpStart").inputValue()) === "14:00" && (await sheet.locator("#ivpEnd").inputValue()) === "14:45");
  await sheet.locator("#ivpDay").fill("2026-11-04");
  await sheet.locator("#ivpNote").fill("Wednesday suits me better.");
  await shot(page, "invite-propose-desktop");
  await sheet.locator("#ivpSend").click();
  await page.waitForTimeout(300);
  const prop = posted.find((x) => x.what === "propose");
  check("the suggestion is sent with Unix times and the person's zone", prop && prop.start === Math.floor(new Date("2026-11-04T14:00:00+11:00").getTime() / 1000) && prop.end - prop.start === 2700 && prop.zone === "Australia/Sydney" && prop.note === "Wednesday suits me better.");
  check("the form closes", (await page.locator("#invProp").count()) === 0);
  check("the page never contacted another website", external.length === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 844);
  await row(page, "Project catch-up").click();               // on a phone a tap opens the email
  const a = page.locator("section[data-invite]").first();
  await a.waitFor({ state: "visible" });
  await a.locator('[data-invite-act="propose"]').scrollIntoViewIfNeeded();
  await a.locator('[data-invite-act="propose"]').click();
  const box = await page.locator("#invProp").boundingBox();
  check("on a phone the form fills the whole screen", box && box.x === 0 && box.y === 0 && Math.round(box.width) === 390 && Math.round(box.height) === 844);
  const top = await page.locator("#invProp .sf-top").boundingBox(), foot = await page.locator("#invProp .sf-foot").boundingBox();
  check("its title and Close are fixed at the top and its buttons at the bottom", top.y === 0 && Math.round(foot.y + foot.height) === 844 && (await page.locator("#invProp .sf-close").isVisible()));
  check("every button is at least 44 pixels tall", (await page.locator("#invProp button").evaluateAll((bs) => bs.every((b) => b.getBoundingClientRect().height >= 44))));
  await shot(page, "invite-propose-phone");
  await page.locator("#invProp .sf-close").click();
  check("Close puts the email back", (await page.locator("#invProp").count()) === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
