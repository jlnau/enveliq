// Browser check for the email and attachment windows: they grow with the browser window (and stay inside it), web addresses in the text of an
// email can be clicked but only open after the person is shown where they go, and PDF pages use the room they are given.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_viewer_size.mjs [path/to/prototype/index.html]
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
const orig = (subject, name, address, text, links, warning = null) => ({ subject, from: { name, address }, to: [], date: "", text, truncated: false, attachments: [], remote_images: 0, unsubscribe: null, sender_check: { result: "unknown", detail: "", reply_differs: false }, links, warning });
const messages = [
  { ...base, id: "m-ok", subject: "Your order receipt", sender_display: "Northside Audio", sender_address: "orders@example.invalid", received_at: now - 100, reply_context: ctx("o"), summary: "A receipt for your headphone order.", category: "Information" },
  { ...base, id: "m-bad", subject: "Your parcel is on hold", sender_display: "Parcel Service", sender_address: "notice@parcel-help.example", received_at: now - 200, reply_context: ctx("b"), summary: "Says a parcel is on hold and asks you to pay a small fee.", category: "Information" },
  { ...base, id: "m-none", subject: "Dinner on Friday", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: now - 300, reply_context: ctx("n"), summary: "Asks if you can come to dinner at seven.", category: "Information" },
];
const okLinks = [
  { label: "View your order", host: "orders.example.com", url: "https://orders.example.com/o/1?token=ABC", note: "", flagged: false },
  { label: "", host: "tracking.example.net", url: "https://tracking.example.net/x", note: "", flagged: false },
];
const badLinks = [
  { label: "www.royalmail.com/track", host: "parcel-help.example", url: "https://parcel-help.example/pay?id=77", note: "A link says royalmail.com but really goes to parcel-help.example.", flagged: true },
  { label: "Track my parcel", host: "192.168.1.9", url: null, note: "A link goes to a number address instead of a website name.", flagged: true },
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
  if (/\/messages\/m-ok\/original$/.test(p)) return json(200, orig("Your order receipt", "Northside Audio", "orders@example.invalid", "Thanks for your order.\nTrack it here: https://orders.example.com/o/1?token=ABC.\nAlso https://tracking.example.net/x, and http://not-checked.example/pay for the rest.", okLinks));
  if (/\/messages\/m-bad\/original$/.test(p)) return json(200, orig("Your parcel is on hold", "Parcel Service", "notice@parcel-help.example", "Pay a small fee to release it: https://parcel-help.example/pay?id=77", badLinks,
    { reasons: [{ code: "link_mismatch", text: "A link says royalmail.com but really goes to parcel-help.example.", key: "a" }, { code: "number_link", text: "A link goes to a number address instead of a website name.", key: "ip" }] }));
  if (/\/messages\/m-none\/original$/.test(p)) return json(200, orig("Dinner on Friday", "Alice", "alice@example.invalid", "See you at 7. Menu: https://menu.example.org/", [{ label: "", host: "menu.example.org", url: "https://menu.example.org/", note: "", flagged: false }]));
  if (/\/attachments\/0\/view$/.test(p)) return json(200, { kind: "pdf", total: 1, shown: 1, pages: ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="] });
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
const closeViewer = async (page) => { await page.keyboard.press("Escape"); await page.waitForSelector("#attachmentModal.open", { state: "hidden" }).catch(() => {}); };


const box = (page, sel) => page.locator(sel).evaluate((e) => { const r = e.getBoundingClientRect(); return { w: r.width, h: r.height, top: r.top, bottom: r.bottom, left: r.left, right: r.right, vh: innerHeight, vw: innerWidth }; });

{
  const { page, errors, context } = await open(1800, 1600);
  const popups = []; context.on("page", (p) => popups.push(p));
  await expandAll(page);
  await openOriginal(page, "Your order receipt");
  const big = await box(page, "#attachmentModal");
  check("on a tall, wide screen the email window is much bigger than the old 960 by 820 limit", big.h > 1300 && big.w > 1100);
  check("and it stays inside the browser window with room round it", big.top >= 0 && big.bottom <= big.vh && big.left >= 0 && big.right <= big.vw && big.h < big.vh);
  check("the email itself stays a readable column, not stretched across the window", (await box(page, ".email-doc")).w <= 770);
  const links = page.locator(".email-text .inline-link");
  check("web addresses the server checked are clickable in the text", (await links.count()) === 2 && /orders\.example\.com/.test(await links.first().innerText()));
  check("the full stop after an address is not part of the link", !/\.$/.test(await links.first().innerText()));
  check("an address nobody checked stays plain text", /not-checked\.example\/pay/.test(await page.locator(".email-text").innerText()) && (await page.locator('.email-text .inline-link', { hasText: "not-checked" }).count()) === 0);
  check("nothing in the text is a real link that opens by itself", (await page.locator(".email-text a").count()) === 0 && (await page.locator("#linkAsk").isHidden()));
  await links.first().click();
  const ask = page.locator("#linkAsk");
  check("clicking a link asks first and says where it goes", (await ask.isVisible()) && /This goes to orders\.example\.com\. Open it in a new tab\?/.test(await ask.innerText()));
  check("nothing opened by itself", popups.length === 0);
  const open_ = page.locator("#linkAskOpen");
  check("only the Open it button leads away, in a new tab with no referrer", (await open_.getAttribute("href")) === "https://orders.example.com/o/1?token=ABC" && (await open_.getAttribute("target")) === "_blank" && /noopener/.test(await open_.getAttribute("rel")) && /noreferrer/.test(await open_.getAttribute("rel")));
  check("a calm email says Open it", /^Open it$/.test((await open_.innerText()).trim()));
  await shot(page, "viewer-big");
  await page.locator("#linkAskNo").click();
  check("Not now closes the question", await ask.isHidden());
  await links.nth(1).focus(); await page.keyboard.press("Enter");
  check("a link can be chosen with the keyboard too", (await ask.isVisible()) && /tracking\.example\.net/.test(await ask.innerText()));
  await closeViewer(page);
  check("closing the window also closes the question", await ask.isHidden());

  await openOriginal(page, "Your parcel is on hold");
  check("a flagged email gets no clickable web addresses in its text", (await page.locator(".email-text .inline-link").count()) === 0 && /parcel-help\.example\/pay\?id=77/.test(await page.locator(".email-text").innerText()));
  await closeViewer(page);

  await openOriginal(page, "Dinner on Friday");
  await page.locator(".email-text .inline-link").first().click();
  check("a calm email with a link works the same way", /menu\.example\.org/.test(await ask.innerText()));
  await closeViewer(page);

  // the attachment window (PDF pages) also follows the window
  await page.evaluate(() => openDoc("/api/v1/accounts/a1/messages/m-ok/attachments", { index: 0, filename: "invoice.pdf", size_bytes: 12345 }));
  await page.waitForSelector("#docStage img.doc-page");
  const card = await box(page, "#docBox .pic-card"), stage = await box(page, "#docStage");
  check("the attachment window is wider than the old 900 pixels on a wide screen", card.w > 1000 && card.w <= 1201 && card.h <= card.vh);
  const stageMax = await page.locator("#docStage").evaluate((e) => parseFloat(getComputedStyle(e).maxHeight));
  check("and the pages area gets the extra height (much more than the old 62 percent of the window)", stageMax > 0.7 * 1600);
  const pageW = (await box(page, "#docStage img.doc-page")).w;
  check("a PDF page fits the width it is given instead of a small fixed size", pageW > 700 && pageW <= stage.w);
  await shot(page, "viewer-attachment-big");
  await page.evaluate(() => closeDoc());
  check("no page errors", errors.length === 0);
  check("the page never contacted another website", external.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(1200, 700);
  await expandAll(page);
  await openOriginal(page, "Your order receipt");
  const small = await box(page, "#attachmentModal");
  check("on a short window the email window still fits inside it", small.h <= small.vh * 0.93 && small.top >= 0 && small.bottom <= small.vh);
  await shot(page, "viewer-small");
  check("no page errors on the small window", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 800);
  await expandAll(page);
  await openOriginal(page, "Your order receipt");
  const ph = await box(page, "#attachmentModal");
  check("on a phone the window still fills the screen and nothing scrolls sideways", ph.w >= ph.vw - 1 && (await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)));
  await page.locator(".email-text .inline-link").first().click();
  check("on a phone the question shows and fits", (await page.locator("#linkAsk").isVisible()) && (await page.evaluate(() => document.querySelector("#linkAsk").getBoundingClientRect().right <= innerWidth + 1)));
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
