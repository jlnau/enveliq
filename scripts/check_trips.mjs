// Browser check for Trips (v0.74): the menu entry (only when there is a trip), the Home card, the page, the buttons,
// the calendar switch, and that hostile text from an email is only text. Loaded from a pretend Enveliq server.
//
// Usage: node scripts/check_trips.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = process.env.TOUR ? "https://enveliq.test" : "http://enveliq.test";   // https hides the plain-http warning in the website pictures
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);
const ctx = (id) => ({ reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const iso = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const dayLong = (n) => new Date(iso(n) + "T00:00:00").toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "short" });

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, subscriptions: false, travel: opts.travel !== false };
  let calendar = true;
  const bk = (id, kind, extra) => ({ id: "v" + id.repeat(23), kind, status: "booked", provider: null, reference: null, detail: null, from: null, to: null, start: iso(5), end: null, start_time: null, end_time: null, nights: null, days_to_start: 5, ...extra });
  let trips = opts.empty ? [] : [
    { id: "v" + "c".repeat(23), title: "Trip to Rome", start: iso(-1), end: iso(2), days_to_start: -1, state: "now", cancelled: false, bookings: [
      bk("c", "stay", { provider: "Pensione Verde", to: "Rome", reference: "PV-1", start: iso(-1), end: iso(2), nights: 3, days_to_start: -1 })] },
    { id: "v" + "a".repeat(23), title: "Trip to Lisbon", start: iso(5), end: iso(13), days_to_start: 5, state: "soon", cancelled: false, bookings: [
      bk("a", "flight", { provider: "Qantas", reference: "QX7K2P", detail: "QF9", from: "Melbourne", to: "Lisbon", start: iso(5), end: iso(6), start_time: "10:45", end_time: "14:20" }),
      bk("b", "stay", { provider: "Hotel Aurora", to: "Lisbon", start: iso(6), end: iso(12), nights: 6, reference: "HA-5521", days_to_start: 6 }),
      bk("d", "car", { provider: "Hertz", from: "Lisbon airport", status: "cancelled", start: iso(6), end: iso(12), days_to_start: 6 }),
      bk("e", "flight", { provider: "Qantas", detail: "QF10", from: "Lisbon", to: "Melbourne", start: iso(13), end: iso(13), start_time: "09:00", days_to_start: 13 })] },
    { id: "v" + "f".repeat(23), title: "Trip to <img src=x onerror=window.__pwned=1>", start: iso(40), end: iso(41), days_to_start: 40, state: "soon", cancelled: false, bookings: [
      bk("f", "flight", { provider: "<b>Evil Air</b>", reference: "<script>window.__pwned=1</script>", from: "A", to: "B", start: iso(40), end: iso(41), days_to_start: 40 })] },
  ];
  const view = () => ({ enabled: features.travel, trips: features.travel ? trips : [], calendar, today: iso(0) });
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, [
      { id: "m1", subject: "Your booking", sender_display: "Qantas", sender_address: "bookings@example.invalid", summary: "Your flight is booked.", priority: "normal", category: "Travel", action_required: false, received_at: now - 600, reply_context: ctx("m1") },
    ]);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    if (p === "/api/v1/me/trips") { calls.push(["list"]); return json(200, view()); }
    if (p === "/api/v1/me/trips/settings" && req.method() === "PUT") { const b = JSON.parse(req.postData()); calls.push(["settings", b]); calendar = b.calendar; return json(200, view()); }
    const a = p.match(/^\/api\/v1\/me\/trips\/(v[0-9a-f]{23})\/remove$/);
    if (a && req.method() === "POST") {
      calls.push(["remove", a[1]]);
      for (const t of trips) t.bookings = t.bookings.filter((x) => x.id !== a[1]);
      trips = trips.filter((t) => t.bookings.length);
      return json(200, view());
    }
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

{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server);
  check("the Trips entry is available under More when there is a trip", await page.locator("#moreItems #tripNav").count() === 1 && await page.locator("#tripNav").getAttribute("hidden") === null);
  if (!(await page.locator("#tripNav").isVisible())) await page.locator("#moreToggle").click();
  check("expanding More makes Trips visible", await page.locator("#tripNav").isVisible());
  check("the badge counts the trips that are not over (3)", (await page.locator("#tripBadge").innerText()).trim() === "3");
  const home = await page.locator("#tripBars").innerText();
  check("Home shows a trip under way and one starting within a week", home.includes("Trip to Rome") && home.includes("Under way") && home.includes("Trip to Lisbon") && home.includes("Starts in 5 days"));
  check("Home does not show a trip that is far away", !/Evil|onerror/.test(home));
  await shot(page, "trip-home");

  await page.click("#tripNav");
  await page.waitForSelector("#tripPage .tripitem");
  const txt = await page.locator("#tripPage").innerText();
  check("the page lists all three trips and hides the email list and Home cards", (await page.locator("#tripPage .tripitem").count()) === 3 && await page.locator("#list").isHidden() && await page.locator("#tripBars").isHidden());
  check("a flight shows its route, number, airline, day and times", txt.includes("Melbourne → Lisbon · QF9 · Qantas") && txt.includes(`${dayLong(5)}, 10:45`) && txt.includes("14:20"));
  check("a stay shows its nights and booking reference", txt.includes("Hotel Aurora, Lisbon") && txt.includes("(6 nights)") && txt.includes("Booking reference HA-5521"));
  check("a cancelled booking is marked", txt.includes("Hire car · Cancelled") && await page.locator(".tripbook.cancelled").count() === 1);
  check("a trip under way says so", txt.includes("Under way · until"));
  check("the page says the AI copies and Enveliq works out the dates", txt.includes("The AI copies what each email says. Enveliq works out the dates"));
  check("hostile text is shown as text, not run", !(await page.evaluate(() => window.__pwned)) && (await page.locator("#tripPage img").count()) === 0 && (await page.locator("#tripPage script").count()) === 0 && txt.includes("<b>Evil Air</b>") && txt.includes("<script>"));
  check("there are no links to airlines, hotels or anyone else", (await page.locator("#tripPage a").count()) === 0);
  check("the calendar switch starts on", await page.locator("#tripCal").isChecked());
  await shot(page, "trip-page");

  await page.locator("#tripCal").uncheck();
  await page.waitForFunction(() => !document.querySelector("#tripCal").checked);
  check("switching the calendar off is sent to the server", JSON.stringify(server.calls.filter((c) => c[0] === "settings")) === JSON.stringify([["settings", { calendar: false }]]));

  const before = await page.locator("#tripPage .tripbook").count();
  await page.locator("[data-trip-remove]").first().click();
  await page.waitForFunction((n) => document.querySelectorAll("#tripPage .tripbook").length === n - 1, before);
  check("'This is not my booking' removes it", server.calls.some((c) => c[0] === "remove"));
  check("no script or style was blocked", csp.length === 0 && errors.length === 0);
  await context.close();
}

{
  const server = makeServer({ empty: true });
  const { page, errors, context } = await open(server);
  check("with no trip the entry stays hidden and Home shows no card", await page.locator("#tripNav").isHidden() && await page.locator("#tripBars").isHidden() && await page.locator("#trackLabel").isHidden());
  check("nothing went wrong", errors.length === 0);
  await context.close();
}

{
  const server = makeServer({ travel: false });
  const { page, errors, context } = await open(server);
  check("with the feature off there is no entry, no card and the list is not asked for", await page.locator("#tripNav").isHidden() && await page.locator("#tripBars").isHidden() && !server.calls.some((c) => c[0] === "list"));
  check("nothing went wrong", errors.length === 0);
  await context.close();
}

{
  const server = makeServer();
  const { page, errors, context } = await open(server, { width: 390, height: 800 });
  await page.waitForSelector("#tripBars .triprow");
  check("on a phone the Home card fits the screen", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await shot(page, "trip-home-phone");
  await page.evaluate(() => { document.getElementById("tripNav").click(); });
  await page.waitForSelector("#tripPage .tripitem");
  check("on a phone the page fits the screen", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await shot(page, "trip-page-phone");
  check("nothing went wrong", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("Trips check passed.");
