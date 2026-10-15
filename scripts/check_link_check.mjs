// Browser check for "Where does this link go?": View original lists each link with the website it really goes to, and a link opens only after
// the person has chosen it and been shown where it goes. Links that cannot be opened safely are listed but have no way to open.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_link_check.mjs [path/to/prototype/index.html]
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
  if (/\/messages\/m-ok\/original$/.test(p)) return json(200, orig("Your order receipt", "Northside Audio", "orders@example.invalid", "Thanks for your order.", okLinks));
  if (/\/messages\/m-bad\/original$/.test(p)) return json(200, orig("Your parcel is on hold", "Parcel Service", "notice@parcel-help.example", "Pay a small fee to release it.", badLinks,
    { reasons: [{ code: "link_mismatch", text: "A link says royalmail.com but really goes to parcel-help.example.", key: "a" }, { code: "number_link", text: "A link goes to a number address instead of a website name.", key: "ip" }] }));
  if (/\/messages\/m-none\/original$/.test(p)) return json(200, orig("Dinner on Friday", "Alice", "alice@example.invalid", "See you at 7.", []));
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
  // The current default layout can collapse the email rows. Use the expanded
  // list so the link checks exercise the original-email viewer itself.
  await page.evaluate(() => { view.layout = "list"; view.rows = "open"; applyView(); render(); });
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

{
  const { page, errors, context } = await open(1200, 900);
  await expandAll(page);
  await openOriginal(page, "Your order receipt");
  const list = page.locator(".link-list");
  check("the links are listed with the website each one really goes to", /orders\.example\.com/.test(await list.innerText()) && /tracking\.example\.net/.test(await list.innerText()));
  check("what the email calls the link is shown too", /The email calls it “View your order”/.test(await list.innerText()));
  check("the rest of the address (tokens, paths) is not shown", !/token|ABC/.test(await list.innerText()));
  check("nothing is a link until the person chooses Open", (await page.locator(".link-list a").evaluateAll((a) => a.filter((x) => x.offsetParent !== null).length)) === 0);
  await page.locator("[data-link-ask]").first().click();
  const sure = page.locator(".link-sure:not([hidden])");
  check("Open asks first and says where it goes", (await sure.count()) === 1 && /This goes to orders\.example\.com\. Open it in a new tab\?/.test(await sure.innerText()));
  const a = sure.locator("a");
  check("the link opens in a new tab with no referrer", (await a.getAttribute("target")) === "_blank" && /noopener/.test(await a.getAttribute("rel")) && /noreferrer/.test(await a.getAttribute("rel")));
  check("a calm email says Open it, not Open anyway", /^Open it$/.test((await a.innerText()).trim()));
  await shot(page, "links-ask");
  await page.locator("[data-link-ask]").nth(1).click();
  check("only one question is open at a time", (await page.locator(".link-sure:not([hidden])").count()) === 1);
  await closeViewer(page);

  await openOriginal(page, "Your parcel is on hold");
  const text = await page.locator(".link-list").innerText();
  check("an odd link says why, in words", /royalmail\.com but really goes to parcel-help\.example/.test(text));
  check("a link that cannot be opened is listed with no way to open it", /Not opened from here/.test(text) && (await page.locator(".link-row", { hasText: "192.168.1.9" }).locator("a, [data-link-ask]").count()) === 0);
  await page.locator(".link-row", { hasText: "parcel-help.example" }).locator("[data-link-ask]").click();
  const careful = await page.locator(".link-sure:not([hidden])").innerText();
  check("on a flagged email the question is firmer", /This email looked odd/.test(careful) && /Open anyway/.test(careful));
  check("it never calls anything a scam", !/scam|fraud|fake|danger/i.test(await page.locator(".link-list").innerText() + careful));
  await shot(page, "links-careful");
  await closeViewer(page);

  await openOriginal(page, "Dinner on Friday");
  check("an email with no links shows no list", (await page.locator(".link-list").count()) === 0);
  check("the page never contacted another website", external.length === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(390, 800);
  // On a phone an email now opens full screen (see check_phone_reader.mjs). This part checks sizes and fit inside an open email row, so it keeps the row layout.
  await page.evaluate(() => { lay = () => view.layout; render(); });
  await expandAll(page);
  await openOriginal(page, "Your parcel is on hold");
  await page.locator(".link-row", { hasText: "parcel-help.example" }).locator("[data-link-ask]").click();
  check("on a phone the list fits and the page does not scroll sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1 && document.querySelector(".link-list").scrollWidth <= document.querySelector(".link-list").clientWidth + 1));
  await shot(page, "links-phone");
  check("no page errors on a phone", errors.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All checks passed");
