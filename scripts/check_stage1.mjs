// Browser check for Stage 1: Mark as read / Mark as unread in the three-dot menu (Reviewed is no longer a button or a swipe),
// next / previous email arrows, Show email headers, Download .eml, "Send with high importance" and "Mark as read when I send".
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_stage1.mjs [path/to/prototype/index.html]
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
const features = { compose: true, address_book: true, sent: true, media: true };
const now = Math.floor(Date.now() / 1000);
const ctx = (id, refs = []) => ({ reply_to: "x@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: refs });
const base = { summary: "A short summary.", priority: "normal", category: "Information", action_required: false, state: "unread", snoozed_until: null };
const make = () => [
  { ...base, id: "m-a", subject: "Trip plans", sender_display: "Alice", sender_address: "alice@example.invalid", received_at: now - 300, reply_context: ctx("a2", ["<a1@x>"]) },
  { ...base, id: "m-b", subject: "Re: Trip plans", sender_display: "Bob", sender_address: "bob@example.invalid", received_at: now - 900, reply_context: ctx("a1") },
  { ...base, id: "m-c", subject: "Electricity bill", sender_display: "Northside Power", sender_address: "bills@example.invalid", received_at: now - 1200, reply_context: ctx("c") },
  { ...base, id: "m-r", subject: "Already read one", sender_display: "Cara", sender_address: "cara@example.invalid", received_at: now - 5000, state: "reviewed", resolved_at: now - 100, reply_context: ctx("r") },
];
let messages, posts, prints, sent;
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (p === "/api/v1/me/mail-view") return json(200, m === "GET" ? { view: null } : { view: JSON.parse(req.postData() || "{}") });
  if (/\/api\/v1\/accounts\/a1\/messages\/[^/]+\/(mute|unread|resolve)$/.test(p) && m === "POST") {
    posts.push([p.split("/").pop(), p.split("/")[6], JSON.parse(req.postData() || "{}")]);
    return route.fulfill({ status: p.endsWith("/mute") ? 200 : 204, contentType: "application/json", body: p.endsWith("/mute") ? JSON.stringify({ muted: true, id: "q0123456789abcdef" }) : "" });
  }
  if (p === "/api/v1/me/drafts" && m === "POST") { posts.push(["draft", "", JSON.parse(req.postData() || "{}")]); return json(200, { id: "d0123456789abcdef", items: [] }); }
  if (p === "/api/v1/me/drafts") return json(200, { items: [] });
  if (/\/original\/headers$/.test(p)) return json(200, { headers: "From: Alice <alice@example.invalid>\nSubject: Trip plans\nReceived: from mx.example.invalid" });
  if (/\/original\/eml$/.test(p)) return route.fulfill({ status: 200, contentType: "message/rfc822", headers: { "Content-Disposition": 'attachment; filename="email.eml"' }, body: "Subject: Trip plans\r\n\r\nHello" });
  if (/\/messages\/[^/]+\/(reply|forward)$/.test(p) && m === "POST") { sent.push([p.split("/").pop(), JSON.parse(req.postData() || "{}")]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/accounts\/a1\/send$/.test(p) && m === "POST") { sent.push(["send", JSON.parse(req.postData() || "{}")]); return json(200, { sent: true, from: "me@example.invalid" }); }
  if (/\/original$/.test(p)) return json(200, { from: { name: "Alice", address: "alice@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Today", subject: "Trip plans", text: "Plain words of the original email.", links: [], has_html: false, remote_images: 0, attachments: [], truncated: false });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height = 900) {
  messages = make(); posts = []; prints = 0; sent = [];
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} window.print = () => { window.__prints = (window.__prints || 0) + 1; window.__printDoc = !!document.getElementById("printDoc") && document.getElementById("printDoc").textContent.includes("Plain words"); dispatchEvent(new Event("beforeprint")); setTimeout(() => dispatchEvent(new Event("afterprint")), 700); }; });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.waitForTimeout(300);
  return { page, errors, context };
}
const pick = async (page, title) => { if (await page.locator(".qmore").first().isVisible().catch(() => false)) return; await page.locator("article.mail", { hasText: title }).locator(".qmain, .qtoggle").first().click(); await page.waitForSelector(".qmore"); };
const menuTexts = async (page) => (await page.locator("#moreMenu [role=menuitem]").allInnerTexts()).map((x) => x.trim());

for (const width of [1200, 390]) {
  const tag = width + "px wide: ";
  const { page, errors, context } = await open(width);
  await pick(page, "Electricity bill");
  await page.waitForTimeout(400);
  check(tag + "there is no Reviewed button on the email", (await page.locator("article.mail.open .action.reviewed, article.mail.open [data-status=reviewed]").count()) === 0);
  check(tag + "Archive and Bin are still there", (await page.locator(".action.archive").count()) >= 1 && (await page.locator(".action.trash").count()) >= 1);
  await page.locator(".qmore").first().click();
  const items = await menuTexts(page);
  check(tag + "the three-dot menu has Mark as read, Show email headers and Download this email", ["Mark as read", "Show email headers", "Download this email (.eml)"].every((w) => items.some((i) => i === w)));
  await shot(page, "stage1-menu-" + width);
  await page.locator("#moreMenu [data-headers]").click();
  await page.waitForSelector("#hdrBox:not([hidden])");
  check(tag + "Show email headers opens the header lines", /Subject: Trip plans/.test(await page.locator("#hdrText").innerText()));
  await shot(page, "stage1-headers-" + width);
  await page.keyboard.press("Escape");
  check(tag + "Escape closes the headers", await page.locator("#hdrBox").isHidden());
  await page.locator(".qmore").first().click();
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 8000 }), page.locator("#moreMenu [data-eml]").click()]);
  check(tag + "Download this email saves a .eml file", dl.suggestedFilename() === "email.eml");
  await page.locator(".qmore").first().click();
  await page.locator("#moreMenu [data-markread]").click();
  await page.waitForSelector("#undoBar:not([hidden])");
  check(tag + "Mark as read shows an Undo bar that says Marked as read", /Marked as read/.test(await page.locator("#undoBar").innerText()));
  check(tag + "no sideways scroll", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => document.querySelector('.nav[data-filter="reviewed"]').click());
  await page.waitForSelector("article.mail");
  await pick(page, "Already read one");
  await page.locator(".qmore").first().click();
  const items = await menuTexts(page);
  check("a read email offers Mark as unread (and not Mark as read)", items.includes("Mark as unread") && !items.includes("Mark as read"));
  await page.locator("#moreMenu [data-unread]").click();
  await page.waitForFunction(() => /back in your inbox/.test(document.getElementById("toast").innerText));
  check("Mark as unread asks the server", posts.some((x) => x[0] === "unread" && x[1] === "m-r"));
  check("no page errors", errors.length === 0);
  await context.close();
}

for (const width of [1200, 390]) {
  const tag = "reading layout, " + width + "px wide: ";
  const { page, errors, context } = await open(width);
  if (width > 800) {
    await page.click("#viewTab"); await page.waitForTimeout(300);
    await page.click('#viewPanel [data-view="layout"][data-val="right"]'); await page.waitForTimeout(400);
    await page.mouse.click(600, 500); await page.waitForTimeout(300);
    await page.locator("article.mail .qmain").first().click();
  } else {
    await page.locator("article.mail .qmain").first().click();
  }
  await page.waitForSelector("[data-nav-mail]");
  const title = () => page.evaluate(() => (document.querySelector(".reading h3, .rl-head h3, .reader h3, .reading .qsubject") || {}).innerText || paneId);
  check(tag + "the open email has Previous and Next arrows", (await page.locator("[data-nav-mail='-1']").count()) >= 1 && (await page.locator("[data-nav-mail='1']").count()) >= 1);
  const first = await title();
  await page.locator("[data-nav-mail='-1']").first().click(); await page.waitForTimeout(300);
  check(tag + "Previous on the first email says it is the first and stays put", /first email/.test(await page.locator("#toast").innerText()) && (await title()) === first);
  await page.locator("[data-nav-mail='1']").first().click(); await page.waitForTimeout(500);
  const second = await title();
  check(tag + "Next opens the next email in the list", second !== first);
  await shot(page, "stage1-arrows-" + width);
  await page.locator("[data-nav-mail='-1']").first().click(); await page.waitForTimeout(500);
  check(tag + "Previous goes back to the one before", (await title()) === first);
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(1200);
  await pick(page, "Electricity bill");
  await page.locator(".qfoot [data-reply]").first().click();
  await page.waitForSelector("#compose.open");
  check("the reply window has More options, closed", (await page.locator("#cmOptions").count()) === 1 && !(await page.locator("#cmOptions").evaluate((e) => e.open)));
  await page.locator("#cmOptions summary").click();
  check("More options holds Mark as read when I send and Send with high importance, both unticked", (await page.locator("#cmMarkRead").isVisible()) && (await page.locator("#cmImportant").isVisible()) && !(await page.locator("#cmMarkRead").isChecked()) && !(await page.locator("#cmImportant").isChecked()));
  await page.locator("#composeText").click();
  await page.keyboard.type("Thanks, got it.");
  await page.locator("#cmImportant").check();
  await page.locator("#cmMarkRead").check();
  await shot(page, "stage1-reply-options");
  await page.locator("#composeSend").click();
  await page.waitForTimeout(1200);
  const rep = sent.find((x) => x[0] === "reply");
  check("the reply is sent with important: true", rep && rep[1].important === true);
  check("Mark as read when I send puts the email on the Undo bar", /Marked as read/.test(await page.locator("#undoBar").innerText().catch(() => "")));
  await page.locator("article.mail", { hasText: "Trip plans" }).first().locator(".qmain, .qtoggle").first().click().catch(() => {});
  await page.locator(".qfoot [data-reply]").first().click();
  await page.waitForSelector("#compose.open");
  check("the ticks are cleared for the next reply", !(await page.locator("#cmImportant").isChecked()) && !(await page.locator("#cmMarkRead").isChecked()));
  await page.keyboard.press("Escape");
  check("no page errors", errors.length === 0);
  await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
