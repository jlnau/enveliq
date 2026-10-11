// Browser check for the Unsubscribe button: shown for a newsletter, opens only a plain web link in a new tab, never for an unsafe one.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_unsub.mjs [path/to/prototype/index.html]
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
const base = { summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, state: "unread" };
const ctx = (id) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const messages = [
  { ...base, id: "m-url", subject: "Weekly news", sender_display: "News", sender_address: "news@example.invalid", received_at: now - 100, reply_context: ctx("u"),
    unsubscribe: { url: "https://news.example.invalid/u/42?id=7&x=%22y", mailto: null, subject: null, host: "news.example.invalid", source: "header" } },
  { ...base, id: "m-mail", subject: "Club notes", sender_display: "Club", sender_address: "club@example.invalid", received_at: now - 200, reply_context: ctx("m"),
    unsubscribe: { url: null, mailto: "leave@example.invalid", subject: "Please unsubscribe me", host: "example.invalid", source: "header" } },
  { ...base, id: "m-bad", subject: "Sneaky", sender_display: "Evil", sender_address: "evil@example.invalid", received_at: now - 300, reply_context: ctx("b"),
    unsubscribe: { url: "javascript:window.__pwned=1", mailto: null, subject: null, host: "evil.example.invalid", source: "header" } },
  { ...base, id: "m-none", subject: "Dentist", sender_display: "Clinic", sender_address: "clinic@example.invalid", received_at: now - 400, reply_context: ctx("n") },
];
const external = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) { external.push(req.url()); return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" }); }
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { cipher: "AES-256-GCM", kdf: "argon2id", initialized: true, unlocked: true, idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (/\/messages\/m-none\/original$/.test(p)) return json(200, { subject: "Dentist", from: { name: "Clinic", address: "clinic@example.invalid" }, to: [], date: "", text: "See you Monday.", truncated: false, attachments: [], remote_images: 0, unsubscribe: { url: "https://clinic.example.invalid/optout/5", mailto: null, subject: null, host: "clinic.example.invalid", source: "body" } });
  if (/\/messages\/[^/]+\/original$/.test(p)) return json(200, { subject: "x", from: { name: "", address: "x@example.invalid" }, to: [], date: "", text: "Hello", truncated: false, attachments: [], remote_images: 0, unsubscribe: null });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};

const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, errors, context };
}
async function expandAll(page) {
  // The row's own toggle is visually hidden (the whole row is the button), so press it from the page.
  for (let i = 0; i < 10; i++) {                       // opening one row redraws the list, so look again each time
    const pressed = await page.evaluate(() => { const b = document.querySelector('.qtoggle[data-expand][aria-expanded="false"]'); if (!b) return false; b.click(); return true; });
    if (!pressed) break;
  }
}

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  const links = page.locator(".qfoot a.unsub");
  check("the newsletter and the mailing-list email each get an Unsubscribe button", (await links.count()) === 2);
  const row = (id) => page.locator("article.mail", { hasText: id });
  const web = row("Weekly news").locator("a.unsub");
  check("the web link is the exact address, opens in a new tab, no referrer, no tracking hand-over",
    (await web.getAttribute("href")) === "https://news.example.invalid/u/42?id=7&x=%22y" && (await web.getAttribute("target")) === "_blank" && /noopener/.test(await web.getAttribute("rel")) && /noreferrer/.test(await web.getAttribute("rel")));
  check("it says which site it opens", /news\.example\.invalid/.test(await web.getAttribute("title")));
  const mail = row("Club notes").locator("a.unsub");
  check("an address-only newsletter gets a mailto link with its subject", (await mail.getAttribute("href")) === "mailto:leave@example.invalid?subject=Please%20unsubscribe%20me");
  check("a hostile javascript: link gets no button and runs nothing", (await row("Sneaky").locator("a.unsub").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined);
  check("an email with no link gets no button", (await row("Dentist").locator("a.unsub").count()) === 0);
  await shot(page, "unsub-list");

  const popup = context.waitForEvent("page");
  await web.click();
  const tab = await popup;
  check("pressing it opens the sender's own page in a new tab", tab.url().startsWith("https://news.example.invalid/u/42") && external.length >= 1);
  check("the opened tab cannot reach back into Enveliq", (await tab.evaluate(() => window.opener === null)) === true);
  await tab.close();

  await row("Dentist").locator("[data-open-email]").click();
  await page.waitForSelector("#attachmentModal.open .email-doc");
  check("View original finds a link in the body and shows it as a button too", (await page.locator("#viewerActions a.unsub").getAttribute("href")) === "https://clinic.example.invalid/optout/5");
  await shot(page, "unsub-viewer");
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 800);
  await expandAll(page);
  check("on a phone the button is there and big enough to tap", (await page.locator(".qfoot a.unsub").first().boundingBox()).height >= 34);
  await shot(page, "unsub-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
