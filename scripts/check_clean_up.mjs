// Browser check for Clean up: the menu entry, the list of mailing lists, step-through mode, archive with its full-screen confirm, always archive, keep, undo, and the phone layout.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_clean_up.mjs [path/to/prototype/index.html]
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
const S1 = "s" + "1".repeat(20), S2 = "s" + "2".repeat(20), S3 = "s" + "3".repeat(20);

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, find_mail: false, junk_mail: false, clean_up: opts.clean_up !== false };
  const msgs = [
    { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, state: "unread", received_at: now - 600, reply_context: ctx("m1"), attachment_summaries: [], tags: [], from_all_mail: false },
  ];
  const all = [
    { id: S1, name: "Newsy", address: "news@example.com", count: 12, opened: 1, last: now - 86400, mailbox: "me@example.invalid", flagged: false, unsubscribe: { url: "https://news.example.com/u/abc", mailto: "leave@news.example.com", subject: "unsubscribe" } },
    { id: S2, name: "Shop", address: "shop@example.net", count: 5, opened: 0, last: now - 3 * 86400, mailbox: "me@example.invalid", flagged: false, unsubscribe: { url: null, mailto: "leave@shop.example.net", subject: "" } },
    { id: S3, name: "PayPal", address: "help@parcel-notice.example", count: 2, opened: 0, last: now - 5 * 86400, mailbox: "me@example.invalid", flagged: true, unsubscribe: null },
  ];
  let items = all.slice(), kept = 0, offer = null;
  const view = (extra = {}) => ({ senders: items, mailboxes: 1, kept, days: 60, problems: opts.problems || [], now, undo_offer: offer, ...extra });
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, msgs);
    if (p === "/api/v1/me/senders" && req.method() === "GET") { calls.push(["list", new URL(req.url()).search]); return json(200, view()); }
    if (p === "/api/v1/me/senders/undo") { calls.push(["undo"]); items = all.slice(); offer = null; return json(200, view({ restored: 12 })); }
    if (p === "/api/v1/me/senders/keep" && req.method() === "DELETE") { calls.push(["showkept"]); kept = 0; return json(200, view()); }
    const m = p.match(/^\/api\/v1\/me\/senders\/(s[0-9a-f]{20})\/(archive|always|keep)$/);
    if (m) {
      calls.push([m[2], m[1]]);
      const who = items.find((i) => i.id === m[1]);
      if (m[2] === "always") return json(200, view());
      items = items.filter((i) => i.id !== m[1]);
      if (m[2] === "keep") { kept += 1; return json(200, view()); }
      offer = { name: who.name };
      return json(200, view({ archived: who.count, more: false, left_for_tasks: 0, undo: "tok-" + "x".repeat(20), undo_seconds: 600, undo_offer: offer }));
    }
    if (p === "/api/v1/me/summary-queue") return json(200, { items: [], waiting: 0, writing: 0 });
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    return json(404, { detail: "not found: " + p });
  };
  return { handler, calls };
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


const goClean = async (page) => {
  await page.evaluate(() => { filter = "cleanup"; document.querySelectorAll(".nav[data-filter]").forEach((x) => x.classList.toggle("active", x.dataset.filter === "cleanup")); openCleanPage(); });
};

{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server);
  check("Clean up is in the left menu", await page.locator("#cleanNav").isVisible() && (await page.locator("#cleanNav .nav-label").innerText()) === "Clean up");
  await page.click("#cleanNav");
  await page.waitForFunction(() => document.querySelectorAll(".cl-card").length === 3);
  check("opening the page asks the server once", server.calls.filter((c) => c[0] === "list").length === 1);
  check("the page title says Clean up and the inbox list is hidden", (await page.locator(".top-left h2").innerText()) === "Clean up" && await page.locator("#cleanPage").isVisible() && !(await page.locator("#list").isVisible()));
  const first = await page.locator(".cl-card").first().innerText();
  check("each card says how many emails, how many were opened and when", first.includes("12 emails") && first.includes("you opened 1") && first.includes("yesterday"));
  check("a sender that looks odd has no Unsubscribe and says why", (await page.locator(".cl-card").nth(2).locator(".unsub").count()) === 0 && (await page.locator(".cl-card").nth(2).innerText()).includes("looks odd"));
  check("the others offer Unsubscribe as a plain link or a plain address", (await page.locator(".cl-card .unsub, .cl-card [data-unsub]").count()) >= 1 || (await page.locator(".cl-card").first().innerText()).includes("Unsubscribe"));
  check("every card has Archive, Always archive and Keep", (await page.locator("[data-clean-archive]").count()) === 3 && (await page.locator("[data-clean-always]").count()) === 3 && (await page.locator("[data-clean-keep]").count()) === 3);
  await shot(page, "clean-desktop");

  await page.locator(`[data-clean-always="${S2}"]`).click();
  await page.waitForFunction(() => document.body.innerText.includes("New email from them is now archived"));
  check("Always archive makes a rule and says where to change it", server.calls.some((c) => c[0] === "always" && c[1] === S2));

  await page.locator(`.cl-card [data-clean-archive="${S1}"]`).click();
  await page.waitForSelector("[data-clean-confirm]");
  check("Archive asks first and says nothing is deleted", (await page.locator("[data-clean-confirm]").innerText()).includes("Nothing is deleted") && !server.calls.some((c) => c[0] === "archive"));
  await shot(page, "clean-confirm");
  await page.locator(".sf-foot [data-clean-cancel]").click();
  check("Cancel closes it without archiving", !(await page.locator("[data-clean-confirm]").count()) && !server.calls.some((c) => c[0] === "archive"));
  await page.locator(`.cl-card [data-clean-archive="${S1}"]`).click();
  await page.waitForSelector("[data-clean-confirm]");
  await page.locator("[data-clean-confirm] button[type=submit]").click();
  await page.waitForSelector(".cl-undo");
  check("archiving removes the card and offers Undo", server.calls.some((c) => c[0] === "archive" && c[1] === S1) && (await page.locator(".cl-card").count()) === 2 && (await page.locator(".cl-undo").innerText()).includes("Newsy"));
  await page.locator("[data-clean-undo]").click();
  await page.waitForFunction(() => document.querySelectorAll(".cl-card").length === 3);
  check("Undo puts them back", server.calls.some((c) => c[0] === "undo") && !(await page.locator(".cl-undo").count()));

  await page.locator(`[data-clean-keep="${S3}"]`).click();
  await page.waitForFunction(() => document.querySelectorAll(".cl-card").length === 2);
  check("Keep removes the card and offers to show kept ones again", server.calls.some((c) => c[0] === "keep" && c[1] === S3) && (await page.locator("[data-clean-showkept]").count()) === 1);
  await page.locator("[data-clean-showkept]").click();
  await page.waitForFunction(() => document.querySelectorAll(".cl-card").length >= 2 && !document.querySelector("[data-clean-showkept]"));
  check("Show kept again clears the keep list", server.calls.some((c) => c[0] === "showkept"));

  await page.click('.nav[data-filter="all"]');
  check("going back to the inbox shows the inbox", await page.locator("#list").isVisible() && !(await page.locator("#cleanPage").isVisible()));
  check("no script errors and nothing blocked by the page policy", errors.length === 0 && csp.length === 0);
  if (errors.length || csp.length) console.log(errors.concat(csp).join("\n"));
  await context.close();
}

{
  const server = makeServer({ clean_up: false });
  const { page, context } = await open(server);
  check("with Clean up switched off there is no menu entry", await page.locator("#cleanNav").isHidden());
  await context.close();
}

{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800, touch: true });
  await goClean(page);
  await page.waitForSelector(".cl-card");
  check("phone: it opens one at a time with a way to see the whole list", (await page.locator(".cl-card").count()) === 1 && (await page.locator("[data-clean-mode]").innerText()) === "See the whole list");
  check("phone: nothing scrolls sideways", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  const heights = await page.locator(".cl-card .jk-acts .btn, .cl-card .jk-acts .unsub").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
  check("phone: buttons are at least 44px tall", heights.length >= 3 && heights.every((h) => h >= 44));
  check("phone: the card fits the screen", await page.locator(".cl-card").evaluate((e) => e.getBoundingClientRect().right <= window.innerWidth + 1));
  await shot(page, "clean-phone");
  await page.locator("[data-clean-skip]").click();
  check("phone: Skip for now moves to the next sender", (await page.locator(".cl-card").first().innerText()).includes("Shop"));
  await page.locator("[data-clean-archive]").first().click();
  await page.waitForSelector("[data-clean-confirm]");
  const box = await page.locator("[data-clean-confirm]").boundingBox();
  check("phone: the confirm opens full screen", box.width >= 388 && box.height >= 780);
  const top = await page.locator(".cl-confirm .sf-top").boundingBox(), foot = await page.locator(".cl-confirm .sf-foot").boundingBox();
  check("phone: Close is fixed at the top and the buttons at the bottom", top.y <= 2 && foot.y + foot.height >= 798 && await page.locator(".cl-confirm .sf-close").isVisible() && await page.locator(".cl-confirm .sf-foot button[type=submit]").isVisible());
  await shot(page, "clean-phone-confirm");
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
