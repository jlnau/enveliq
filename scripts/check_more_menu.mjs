// Browser check for the three-dot menu on an email, Mute conversation, Mark unread, Print email / Save as PDF, and Conversation View.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_more_menu.mjs [path/to/prototype/index.html]
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
let messages, posts, prints;
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
  if (/\/original$/.test(p)) return json(200, { from: { name: "Alice", address: "alice@example.invalid" }, to: [{ address: "me@example.invalid" }], date: "Today", subject: "Trip plans", text: "Plain words of the original email.", links: [], has_html: false, remote_images: 0, attachments: [], truncated: false });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
async function open(width, height = 900) {
  messages = make(); posts = []; prints = 0;
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

for (const width of [1200, 390]) {
  const tag = width + "px wide: ";
  const { page, errors, context } = await open(width);
  await pick(page, "Electricity bill");
  const more = page.locator(".qmore").first();
  await page.waitForTimeout(500);
  const box = await more.boundingBox(), foot = await page.locator(".qfoot").first().boundingBox();
  check(tag + "the three-dot button sits at the far right of the action row", box && foot && Math.abs((foot.x + foot.width) - (box.x + box.width)) < 6);
  check(tag + "the old single buttons are gone from the row", (await page.locator(".qfoot [data-block-sender], .qfoot [data-junk-this], .qfoot [data-rule], .qfoot [data-important]").count()) === 0);
  check(tag + "Reply and Snooze stay in the row", (await page.locator(".qfoot [data-reply]").count()) === 1 && (await page.locator(".qfoot [data-snooze]").count()) === 1);
  await more.click();
  const menu = page.locator("#moreMenu");
  const items = (await menu.locator("[role=menuitem]").allInnerTexts()).join("|");
  check(tag + "the menu holds Reply, Snooze, Important, Always archive, Junk, Block, Mute, Print and Save as PDF", ["Reply", "Snooze", "Important person", "Always archive these", "Send to Junk", "Block sender", "Mute conversation", "Print email", "Save as PDF"].every((t) => items.includes(t)));
  const mb = await menu.boundingBox();
  check(tag + "the menu stays on the screen", mb && mb.x >= 0 && mb.y >= 0 && mb.x + mb.width <= width && mb.y + mb.height <= 900);
  await shot(page, "more-menu-" + width);
  await page.keyboard.press("Escape");
  check(tag + "Escape closes it", await menu.isHidden());
  await more.click();
  await menu.locator("[data-print]").click();
  await page.waitForFunction(() => window.__prints >= 1, null, { timeout: 12000 });
  // The browser lays the page out at paper width while the print window is open: that must not close the email being read.
  await page.setViewportSize({ width: 700, height: 900 }); await page.waitForTimeout(150); await page.setViewportSize({ width, height: 900 });
  await page.waitForTimeout(900);
  check(tag + "Print email prints the original and the email you were reading stays open", (await page.evaluate(() => window.__prints)) === 1 && (await page.evaluate(() => window.__printDoc)) && (await page.locator(".qmore").first().isVisible()) && !(await page.evaluate(() => document.getElementById("attachmentModal").classList.contains("open"))) && (await page.locator("#printDoc").count()) === 0 && (await page.evaluate(() => !document.body.classList.contains("printing-email"))));
  await pick(page, "Electricity bill");
  await page.locator(".qmore").first().click();
  await page.locator("#moreMenu [data-mute]").click();
  await page.waitForFunction(() => /Muted/.test(document.getElementById("toast").innerText));
  check(tag + "Mute conversation asks the server and says what happens", posts.some((x) => x[0] === "mute" && x[1] === "m-c") && /Archive/.test(await page.locator("#toast").innerText()));
  check(tag + "no sideways scroll", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check(tag + "no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(1200);
  await page.evaluate(() => document.querySelector('.nav[data-filter="reviewed"]').click());
  await page.waitForSelector("article.mail");
  await pick(page, "Already read one");
  const btn = page.locator("[data-unread]").first();
  check("a Reviewed email has a clear Mark unread button", (await btn.count()) > 0 && (await btn.innerText()) === "Mark unread");
  await btn.click();
  await page.waitForFunction(() => /back in your inbox/.test(document.getElementById("toast").innerText));
  check("it asks the server to restore the unread mark", posts.some((x) => x[0] === "unread" && x[1] === "m-r"));
  await page.evaluate(() => document.querySelector('.nav[data-filter="all"]').click());
  check("the email is back in the inbox list", (await page.locator("article.mail", { hasText: "Already read one" }).count()) === 1);
  check("no page errors", errors.length === 0);
  await context.close();
}

{
  const { page, errors, context } = await open(1200);
  check("Conversation View is off by default: every email has its own row", (await page.locator("article.mail").count()) === 3);
  await page.evaluate(() => setViewPanel(true));
  check("the Customise panel has a Conversation View switch, off", (await page.locator("#vConv").count()) === 1 && !(await page.locator("#vConv").isChecked()));
  await page.locator("#vConv").check();
  await page.waitForTimeout(200);
  check("switching it on groups the two emails of one conversation", (await page.locator("article.mail").count()) === 2 && /2 emails in this conversation/.test(await page.locator(".conv-bar").innerText()));
  await shot(page, "conversation-view");
  await page.locator("[data-conv]").click();
  check("Show lists the older email, with its own buttons", (await page.locator("article.mail").count()) === 3 && (await page.locator(".conv-kids article.mail .qic").count()) === 3);
  await page.evaluate(() => setViewPanel(true));   // clicking in the list closed the panel, so open it again
  await page.waitForTimeout(400);
  await page.locator("#vConv").uncheck();
  await page.waitForTimeout(200);
  check("switching it off puts every email back in its own row", (await page.locator("article.mail").count()) === 3 && (await page.locator(".conv-bar").count()) === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}
{
  const { page, errors, context } = await open(390);
  await page.evaluate(() => openNewMail());
  await page.waitForTimeout(300);
  await page.locator("#nmSubject").fill("Plans for Friday");
  await page.locator("#nmText").fill("Some words.");
  await page.goBack();
  await page.waitForSelector("#dkAsk.open");
  check("phone: Back asks whether to keep the new email as a draft", (await page.locator("#newMail.open").count()) === 1);
  await page.goBack();
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  check("phone: Back again saves it as a draft and closes it", posts.some((x) => x[0] === "draft" && x[2].subject === "Plans for Friday") && (await page.locator("#dkAsk.open").count()) === 0);
  await page.evaluate(() => openNewMail());
  await page.waitForTimeout(300);
  await page.goBack();
  await page.waitForFunction(() => !document.getElementById("newMail").classList.contains("open"));
  check("phone: Back on an empty new email just closes it", (await page.locator("#dkAsk.open").count()) === 0);
  check("no page errors", errors.length === 0);
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
