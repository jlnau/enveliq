// Browser check for Junk Mail: the menu entry, the list with the AI's answers, the safe viewer, Not Junk, and the phone layout.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_junk.mjs [path/to/prototype/index.html]
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
const ctx = (id) => ({ reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const J1 = "j" + "1".repeat(23), J2 = "j" + "2".repeat(23), J3 = "j" + "3".repeat(23);

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, find_mail: false, junk_mail: opts.junk_mail !== false };
  const msgs = [
    { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, state: "unread", received_at: now - 600, reply_context: ctx("m1"), attachment_summaries: [], tags: [], from_all_mail: false },
  ];
  const items = [
    { id: J1, mailbox: "me@example.invalid", subject: "You have won a prize", sender_display: "Prize Team", sender_address: "win@example.invalid", received_at: now - 3600, verdict: null, summary: "", reason: "", failed: false, has_files: false },
    { id: J2, mailbox: "me@example.invalid", subject: "Your March invoice", sender_display: "Billing", sender_address: "billing@example.com", received_at: now - 7200, verdict: null, summary: "", reason: "", failed: false, has_files: false },
    { id: J3, mailbox: "me@example.invalid", subject: "Cheap watches", sender_display: null, sender_address: "x@example.invalid", received_at: now - 9000, verdict: null, summary: "", reason: "", failed: false, has_files: false },
  ];
  const view = () => ({ items, total: items.length, pending: items.filter((i) => !i.verdict).length, needs_review: items.filter((i) => i.verdict === "review").length, junk: items.filter((i) => i.verdict === "junk").length, ai: true, problems: opts.problems || [] });
  const state = {};
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, msgs);
    if (p === "/api/v1/junk" && req.method() === "GET") return json(200, view());
    if (p === "/api/v1/junk/refresh") { calls.push(["refresh"]); return json(200, view()); }
    if (p === "/api/v1/junk/check") {
      calls.push(["check"]);
      const next = items.find((i) => !i.verdict);
      if (next) Object.assign(next, next.id === J2 ? { verdict: "review", summary: "An invoice for March from a company you may deal with.", reason: "Looks like a real bill." } : { verdict: "junk", summary: "A prize offer asking you to click a link.", reason: "Classic prize scam." });
      return json(200, view());
    }
    if (p === `/api/v1/junk/${J1}/original`) { calls.push(["view"]); return json(200, { subject: "You have won a prize", from: { name: "Prize Team", address: "win@example.invalid" }, to: [{ name: "", address: "me@example.invalid" }], date: "Mon, 5 Oct 2026 09:00:00 +0000", text: "Claim at http://prizes.example.invalid/now", truncated: false, attachments: [], file_count: 0, remote_images: 0, has_html: true, unsubscribe: null, links: [], warning: null, sender_check: null }); }
    if (p === `/api/v1/junk/${J1}/original/html`) return route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><html><body><p>Claim your prize now</p></body></html>" });
    if (/\/api\/v1\/junk\/j[0-9a-f]{23}\/not-junk$/.test(p)) { const id = p.split("/")[4]; calls.push(["notjunk", id]); const i = items.findIndex((x) => x.id === id); if (i >= 0) items.splice(i, 1); return json(200, view()); }
    if (p === "/api/v1/me/summary-queue") return json(200, { items: [], waiting: 0, writing: 0 });
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    return json(404, { detail: "not found: " + p });
  };
  return { handler, calls, state };
}

const browser = await chromium.launch();
async function open(server, { width = 1200, height = 900, touch = false } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: touch });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} });
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
  check("Junk Mail is in the left menu", await page.locator("#junkNav").isVisible() && (await page.locator("#junkNav .nav-label").innerText()) === "Junk Mail");
  await page.click("#junkNav");
  await page.waitForFunction(() => document.querySelectorAll(".jk-card").length === 3 && !document.querySelector(".jk-chip.wait"));
  check("opening the page reads the junk folders then asks the AI about each email", server.calls[0][0] === "refresh" && server.calls.filter((c) => c[0] === "check").length === 3);
  check("the page title says Junk Mail", (await page.locator(".top-left h2").innerText()) === "Junk Mail" && await page.locator("#junkPage").isVisible() && !(await page.locator("#list").isVisible()));
  const chips = await page.locator(".jk-card .jk-chip").allInnerTexts();
  check("each email is either 'Yes, it's junk' or 'Needs review'", chips.filter((c) => c === "Yes, it's junk").length === 2 && chips.filter((c) => c === "Needs review").length === 1);
  check("emails that need review come first", (await page.locator(".jk-card").first().innerText()).includes("Your March invoice"));
  check("each shows a summary, why, and says the AI wrote it", (await page.locator(".jk-card").first().innerText()).includes("An invoice for March") && (await page.locator(".jk-card").first().innerText()).includes("Why: Looks like a real bill.") && (await page.locator(".jk-card").first().innerText()).includes("Checked by the AI"));
  check("every card has View original email and Not Junk", (await page.locator("[data-junk-view]").count()) === 3 && (await page.locator(".jk-card [data-junk-not]").count()) === 3);
  check("the menu badge counts emails that need review", (await page.locator("#junkBadge").innerText()) === "1");
  await shot(page, "junk-desktop");

  await page.locator(`[data-junk-view="${J1}"]`).click();
  await page.waitForSelector("#attachmentModal.open");
  check("View original email opens the viewer and says links, pictures and scripts are off", (await page.locator("#viewerStrip").innerText()).includes("Links are switched off") && (await page.locator("#viewerStrip").innerText()).includes("Pictures from the internet are switched off"));
  check("the viewer offers no links list, unsubscribe, reply or attachment buttons", (await page.locator("#attachmentViewer .link-list, #attachmentViewer .att-title, #viewerActions .unsub, #viewerActions [data-reply]").count()) === 0);
  check("the plain text shows the address as text only, never as a clickable link", (await page.locator("#attachmentViewer [data-inline-link], #attachmentViewer .email-text a").count()) === 0 && (await page.locator("#attachmentViewer .email-text").innerText()).includes("prizes.example.invalid"));
  check("the formatted email loads from the Junk Mail address, in a frame", ((await page.locator("#attachmentViewer iframe.email-frame").getAttribute("src")) || "").includes(`/api/v1/junk/${J1}/original/html`));
  check("the viewer has a Not Junk button", (await page.locator("#viewerActions [data-junk-not]").count()) === 1);
  await shot(page, "junk-viewer");
  await page.locator("#viewerActions [data-junk-not]").click();
  await page.waitForFunction(() => document.querySelectorAll(".jk-card").length === 2);
  check("Not Junk in the viewer moves it, closes the viewer and removes the card", server.calls.some((c) => c[0] === "notjunk" && c[1] === J1) && !(await page.locator("#attachmentModal.open").count()));
  await page.locator(`[data-junk-not="${J3}"]`).first().click();
  await page.waitForFunction(() => document.querySelectorAll(".jk-card").length === 1);
  check("Not Junk on a card removes it from the list", server.calls.some((c) => c[0] === "notjunk" && c[1] === J3));
  await page.click('.nav[data-filter="all"]');
  check("going back to the inbox shows the inbox again", await page.locator("#list").isVisible() && !(await page.locator("#junkPage").isVisible()));
  check("no script errors and nothing blocked by the page policy", errors.length === 0 && csp.length === 0);
  if (errors.length || csp.length) console.log(errors.concat(csp).join("\n"));
  await context.close();
}

{
  const server = makeServer({ junk_mail: false });
  const { page, context } = await open(server);
  check("with Junk Mail switched off there is no menu entry", await page.locator("#junkNav").isHidden());
  await context.close();
}

{
  const server = makeServer({ problems: ["me@example.invalid: Enveliq could not find this mailbox's Junk or Spam folder."] });
  const { page, context } = await open(server, { width: 390, height: 800, touch: true });
  await page.evaluate(() => { filter = "junk"; document.querySelectorAll(".nav[data-filter]").forEach((x) => x.classList.toggle("active", x.dataset.filter === "junk")); openJunkPage(); });
  await page.waitForFunction(() => document.querySelectorAll(".jk-card").length === 3 && !document.querySelector(".jk-chip.wait"));
  check("phone: a mailbox problem is explained in plain words", (await page.locator(".jk-bad").first().innerText()).includes("could not find this mailbox's Junk"));
  check("phone: nothing scrolls sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  const heights = await page.locator(".jk-acts button").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
  check("phone: buttons are at least 44px tall", heights.length === 6 && heights.every((h) => h >= 44));
  const fits = await page.locator(".jk-card").evaluateAll((els) => els.every((e) => e.getBoundingClientRect().right <= window.innerWidth + 1));
  check("phone: each card fits the screen", fits);
  await shot(page, "junk-phone");
  await page.locator(`[data-junk-view="${J1}"]`).click();
  await page.waitForSelector("#attachmentModal.open");
  const box = await page.locator("#attachmentModal").boundingBox();
  check("phone: the viewer opens full screen with Not Junk reachable", box.width >= 388 && box.height >= 780 && await page.locator("#viewerActions [data-junk-not]").isVisible());
  await shot(page, "junk-phone-viewer");
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
