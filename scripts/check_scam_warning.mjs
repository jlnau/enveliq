// Browser check for the "Be careful" flag: shown only for an email the server flagged, in plain words, as text; the Unsubscribe button of a
// flagged email asks once more before it offers the link.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_scam_warning.mjs [path/to/prototype/index.html]
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
const warn = { reasons: [
  { code: "link_mismatch", text: "A link says paypal.com but really goes to evil.example.", key: "a" },
  { code: "name_mismatch", text: "The sender's name says <img src=x onerror=window.__pwned=1>PayPal, but the email came from example.invalid.", key: "b" },
] };
const messages = [
  { ...base, id: "m-flag", subject: "Parcel waiting", sender_display: "Post", sender_address: "post@example.invalid", received_at: now - 100, reply_context: ctx("f"), scam_warning: warn,
    unsubscribe: { url: "https://news.example.invalid/u/9", mailto: null, subject: null, host: "news.example.invalid", source: "header" } },
  { ...base, id: "m-ok", subject: "Weekly news", sender_display: "News", sender_address: "news@example.invalid", received_at: now - 200, reply_context: ctx("o"),
    unsubscribe: { url: "https://news.example.invalid/u/42", mailto: null, subject: null, host: "news.example.invalid", source: "header" } },
  { ...base, id: "m-none", subject: "Dentist", sender_display: "Clinic", sender_address: "clinic@example.invalid", received_at: now - 300, reply_context: ctx("n") },
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
  if (/\/messages\/m-flag\/original$/.test(p)) return json(200, { subject: "Parcel waiting", from: { name: "Post", address: "post@example.invalid" }, to: [], date: "", text: "Pay a fee.", truncated: false, attachments: [], remote_images: 0, unsubscribe: null,
    warning: { reasons: [...warn.reasons, { code: "number_link", text: "A link goes to a number address instead of a website name.", key: "c" }] } });
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
  for (let i = 0; i < 10; i++) {
    const pressed = await page.evaluate(() => { const b = document.querySelector('.qtoggle[data-expand][aria-expanded="false"]'); if (!b) return false; b.click(); return true; });
    if (!pressed) break;
  }
}

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  const row = (id) => page.locator("article.mail", { hasText: id });
  check("only the flagged email has the Be careful label", (await page.locator(".scam-pill").count()) === 1 && (await row("Parcel waiting").locator(".scam-pill").count()) === 1);
  const note = row("Parcel waiting").locator(".scam-note");
  check("its card says what looks odd, in plain words", /Be careful with this one/.test(await note.innerText()) && /A link says paypal\.com but really goes to evil\.example\./.test(await note.innerText()));
  check("it does not call the email a scam or give an order", !/scam|fraud|phish|do not|must/i.test(await note.innerText()));
  check("the reasons are shown as text: a hostile reason runs nothing", (await note.locator("img").count()) === 0 && (await page.evaluate(() => window.__pwned)) === undefined);
  check("an ordinary email has no note at all", (await row("Weekly news").locator(".scam-note").count()) === 0 && (await row("Dentist").locator(".scam-note").count()) === 0);
  check("an ordinary newsletter keeps its plain Unsubscribe link", (await row("Weekly news").locator("a.unsub:visible").count()) === 1);
  const flagged = row("Parcel waiting");
  check("on the flagged email the link is not offered straight away", (await flagged.locator("a.unsub:visible").count()) === 0 && (await flagged.locator("button[data-careful]").count()) === 1);
  await flagged.locator("button[data-careful]").click();
  check("pressing Unsubscribe explains why, then offers Go anyway", /could tell the sender your address is real/.test(await flagged.locator(".unsub-sure").innerText()) && (await flagged.locator(".unsub-sure a.unsub:visible").getAttribute("href")) === "https://news.example.invalid/u/9");
  await shot(page, "scam-list");
  await flagged.locator("[data-open-email]").click();
  await page.waitForSelector("#attachmentModal.open .email-doc");
  check("View original shows the note from the whole email, with the extra reason found in its links", (await page.locator(".email-doc .scam-note li").count()) === 3 && /number address/.test(await page.locator(".email-doc .scam-note").innerText()) && /Pay a fee/.test(await page.locator(".email-doc").innerText()));
  await shot(page, "scam-viewer");
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 800);
  await expandAll(page);
  const pill = await page.locator(".scam-pill").first().boundingBox();
  check("on a phone the label fits on screen", pill !== null && pill.x >= 0 && pill.x + pill.width <= 390);
  check("nothing runs sideways on a phone", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot(page, "scam-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
