// Browser check for the fixed top of the inbox on a computer: the search / Sync mail / name bar and the "Recent emails" bar stay in view
// while the emails scroll, and the picture behind the top shows until the page has moved. Phones keep their own top bar.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_sticky_header.mjs [path/to/prototype/index.html]
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
const features = { compose: true, address_book: true, sent: true, media: true };
const base = { summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, state: "unread" };
const ctx = (id) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const TOUR = !!process.env.TOUR;            // TOUR=1 gives tidy example text for the website pictures; the checks themselves use a hostile one
const warn = { reasons: [
  { code: "name_mismatch", text: "The sender's name says Royal Mail, but the email came from parcel-help.example.", key: "a" },
  { code: "link_mismatch", text: "A link says royalmail.com but really goes to parcel-help.example.", key: "b" },
] };
const hostile = { code: "name_mismatch", text: "The sender's name says <img src=x onerror=window.__pwned=1>PayPal, but the email came from example.invalid.", key: "c" };
const messages = [
  { ...base, id: "m-flag", subject: "Your parcel is on hold", sender_display: "Parcel Service", sender_address: "notice@parcel-help.example", received_at: now - 100, reply_context: ctx("f"), scam_warning: warn,
    summary: "Says a parcel is on hold and asks you to pay a small fee through a link.", category: "Information",
    unsubscribe: { url: "https://parcel-help.example/u/9", mailto: null, subject: null, host: "parcel-help.example", source: "header" } },
  { ...base, id: "m-ok", subject: "Weekly news", sender_display: "Northside News", sender_address: "news@example.invalid", received_at: now - 200, reply_context: ctx("o"),
    summary: "This week's local news: roadworks on Elm Street and a new library timetable.", category: "Information",
    unsubscribe: { url: "https://news.example.invalid/u/42", mailto: null, subject: null, host: "news.example.invalid", source: "header" } },
  { ...base, id: "m-none", subject: "Dentist on Monday", sender_display: "Brightwater Dental", sender_address: "clinic@example.invalid", received_at: now - 300, reply_context: ctx("n"),
    summary: "Reminds you of a check-up on Monday at 10:30.", category: "Information" },
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
  if (/\/messages\/m-flag\/original$/.test(p)) return json(200, { subject: "Your parcel is on hold", from: { name: "Parcel Service", address: "notice@parcel-help.example" }, to: [], date: "", text: "Your parcel could not be delivered. Pay a small fee to release it.", truncated: false, attachments: [], remote_images: 0, unsubscribe: null,
    warning: { reasons: [...warn.reasons, TOUR ? { code: "number_link", text: "A link goes to a number address instead of a website name.", key: "d" } : hostile] } });
  if (/\/messages\/[^/]+\/original$/.test(p)) return json(200, { subject: "x", from: { name: "", address: "x@example.invalid" }, to: [], date: "", text: "Hello", truncated: false, attachments: [], remote_images: 0, unsubscribe: null });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};

const people = [["Northside Power", "Your electricity bill"], ["Brightwater Dental", "Dentist on Monday"], ["Streamly", "Your receipt"], ["Qantas", "Your booking"], ["Northside News", "Weekly news"], ["Amazon", "Update on refund"]];
messages.length = 0;
for (let i = 0; i < 40; i++) { const [s, sub] = people[i % people.length]; messages.push({ ...base, id: "m" + i, subject: sub, sender_display: s, sender_address: `s${i}@example.invalid`, received_at: now - 100 - i * 700, reply_context: ctx("x" + i), summary: "Made-up text for the check.", category: "Information" }); }
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height, theme) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript((t) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-theme", t); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} }, theme);
  const page = await context.newPage();
  const errors = []; page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`); await page.waitForSelector("article.mail"); await page.waitForTimeout(500);
  return { page, errors, context };
}
const rect = (page, sel) => page.evaluate((s) => { const r = document.querySelector(s).getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height) }; }, sel);

for (const theme of ["dark", "light"]) {
  const { page, errors, context } = await open(1200, 800, theme);
  const bar0 = await rect(page, "#previewToolbar");
  const bg0 = await page.evaluate(() => getComputedStyle(document.querySelector("#previewToolbar")).backgroundColor);
  check(`${theme}: at the top the bar is see-through, so the picture behind shows`, bg0 === "rgba(0, 0, 0, 0)" || bg0 === "transparent");
  await page.evaluate(() => window.scrollTo(0, 900)); await page.waitForTimeout(250);
  const bar = await rect(page, "#previewToolbar"), head = await rect(page, "#previewListHeading");
  check(`${theme}: the search / name bar stays at the top while scrolled (top ${bar.top})`, bar.top === 0 && bar.bottom > 40);
  check(`${theme}: the Recent emails bar stays right under it (top ${head.top}, bar bottom ${bar.bottom})`, Math.abs(head.top - (bar.bottom + 8)) <= 2);
  const bg1 = await page.evaluate(() => getComputedStyle(document.querySelector("#previewToolbar")).backgroundColor);
  check(`${theme}: once scrolled the bar is solid so emails do not show through`, bg1 !== "rgba(0, 0, 0, 0)" && bg1 !== "transparent");
  const first = await page.evaluate((hb) => { const rows = [...document.querySelectorAll("article.mail")].filter((a) => a.getBoundingClientRect().bottom > hb); return rows.length ? Math.round(rows[0].getBoundingClientRect().top) : null; }, head.bottom);
  check(`${theme}: the emails scroll under the bars (first row at ${first})`, first !== null);
  const clicked = await page.evaluate(() => { const b = document.querySelector("#search"); b.focus(); return document.activeElement === b; });
  check(`${theme}: the search box can still be used while scrolled`, clicked);
  await shot(page, `sticky-${theme}`);
  await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(250);
  const back = await rect(page, "#previewToolbar");
  check(`${theme}: back at the top the bar is where it started (top ${back.top})`, back.top === bar0.top);
  check(`${theme}: no page errors`, errors.length === 0);
  await context.close();
}
{
  const { page, errors, context } = await open(390, 800, "dark");
  const pos = await page.evaluate(() => getComputedStyle(document.querySelector("#previewListHeading")).position);
  check("phone: the Recent emails bar scrolls as before (not fixed)", pos !== "sticky");
  check("phone: no page errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
console.log("Sticky header check passed.");
