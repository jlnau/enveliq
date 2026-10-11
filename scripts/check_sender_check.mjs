// Browser check for "Is this really from them?": the Sender line in View original says, in plain words, whether the email provider confirmed
// the sender, and nothing at all when it cannot tell. Also checks the Reply-To note and the phone layout.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_sender_check.mjs [path/to/prototype/index.html]
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
const orig = (subject, name, address, text, sender_check, replyTo, warning = null) => ({ subject, from: { name, address }, to: [], date: "", text, truncated: false, attachments: [], remote_images: 0, unsubscribe: null, sender_check, warning, replyTo });
const messages = [
  { ...base, id: "m-ok", subject: "Your order receipt", sender_display: "Northside Audio", sender_address: "orders@example.invalid", received_at: now - 100, reply_context: ctx("o"), summary: "A receipt for your headphone order.", category: "Information" },
  { ...base, id: "m-bad", subject: "Your parcel is on hold", sender_display: "Parcel Service", sender_address: "notice@parcel-help.example", received_at: now - 200, reply_context: { ...ctx("b"), reply_to: "help@mailbox.example" }, summary: "Says a parcel is on hold and asks you to pay a small fee.", category: "Information" },
  { ...base, id: "m-unk", subject: "Dentist on Monday", sender_display: "Brightwater Dental", sender_address: "clinic@example.invalid", received_at: now - 300, reply_context: ctx("u"), summary: "Reminds you of a check-up on Monday at 10:30.", category: "Information" },
];
const TOUR = !!process.env.TOUR;
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
  if (/\/messages\/m-ok\/original$/.test(p)) return json(200, orig("Your order receipt", "Northside Audio", "orders@example.invalid", "Thanks for your order.", { result: "confirmed", detail: "spf=pass, dkim=pass, dmarc=pass", reply_differs: false }));
  if (/\/messages\/m-bad\/original$/.test(p)) return json(200, orig("Your parcel is on hold", "Parcel Service", "notice@parcel-help.example", "Pay a small fee to release it.", { result: "not_confirmed", detail: "spf=fail, dkim=none, dmarc=fail", reply_differs: true }, "help@mailbox.example",
    { reasons: [{ code: "link_mismatch", text: "A link says royalmail.com but really goes to parcel-help.example.", key: "a" }, { code: "not_confirmed", text: "Your email provider could not confirm who really sent this.", key: "dmarc" }] }));
  if (/\/messages\/m-unk\/original$/.test(p)) return json(200, orig("Dentist on Monday", "Brightwater Dental", "clinic@example.invalid", "See you Monday at 10:30.", { result: "unknown", detail: "", reply_differs: false }));
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
async function openOriginal(page, subject) {
  await page.locator("article.mail", { hasText: subject }).locator("[data-open-email]").click();
  await page.waitForSelector("#attachmentModal.open .email-doc");
}
const senderLine = (page) => page.locator(".email-head dt", { hasText: /^Sender$/ });

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  await openOriginal(page, "Your order receipt");
  check("a confirmed email says so, in words", /Your email provider confirmed this came from that address\./.test(await page.locator(".email-head").innerText()));
  check("the confirmed line is green", (await page.locator(".email-head dd.ok").count()) === 1);
  await shot(page, "sender-confirmed");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#attachmentModal.open", { state: "hidden" }).catch(() => {});
  await openOriginal(page, "Your parcel is on hold");
  check("an unconfirmed email says so, calmly", /could not confirm this came from that address\./.test(await page.locator(".email-head").innerText()) && (await page.locator(".email-head dd.warn").count()) === 1);
  check("it does not shout or call anything a scam", !/scam|fraud|fake|danger/i.test(await page.locator(".email-head").innerText()));
  check("a Reply-To on another website is pointed out", /Reply-To/.test(await page.locator(".email-head").innerText()) && /a different website from the sender/.test(await page.locator(".email-head").innerText()));
  await shot(page, "sender-not-confirmed");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#attachmentModal.open", { state: "hidden" }).catch(() => {});
  await openOriginal(page, "Dentist on Monday");
  check("when the provider cannot tell, nothing is said at all", (await senderLine(page).count()) === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 800);
  await expandAll(page);
  await openOriginal(page, "Your parcel is on hold");
  check("on a phone the sender line fits and the page does not scroll sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1 && document.querySelector(".email-head").scrollWidth <= document.querySelector(".email-head").clientWidth + 1));
  await shot(page, "sender-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
