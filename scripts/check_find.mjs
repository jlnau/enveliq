// Browser check for Find any email: the Search all my mail button, the results, View original, Summarise,
// the Found emails page, Reviewed, and the full-screen phone layout.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_find.mjs [path/to/prototype/index.html]
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

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, find_mail: opts.find_mail !== false };
  const msgs = [
    { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, state: "unread", received_at: now - 600, reply_context: ctx("m1"), attachment_summaries: [], tags: [], from_all_mail: false },
  ];
  const rows = [
    { token: "AAAAAAAAAAAA.0.aaaaaaaaaaaaaaaaaaaaaaaa", account_id: "a1", account: "me@example.invalid", from_name: "Dana", from_address: "dana@example.invalid", subject: "Canvas order", date: now - 3 * 86400, folder: "Archive", has_files: false },
    { token: "AAAAAAAAAAAA.1.bbbbbbbbbbbbbbbbbbbbbbbb", account_id: "a1", account: "me@example.invalid", from_name: "Sam", from_address: "sam@example.invalid", subject: "Old project", date: now - 400 * 86400, folder: "Archive", has_files: true },
  ];
  const state = { polls: 0, junk: false, kept: false };
  const progress = (done) => ({ id: "AAAAAAAAAAAA", done, cancelled: false, total: state.junk ? 3 : 2, listed: state.junk ? 3 : 2, include_junk: state.junk, mailboxes: [{ account_id: "a1", label: "me@example.invalid", state: done ? "done" : "searching", found: state.junk ? 3 : 2, message: "" }] });
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") {
      const out = [...msgs];
      if (state.kept) out.push({ id: "f1", subject: "Canvas order", sender_display: "Dana", sender_address: "dana@example.invalid", summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, state: "unread", received_at: now - 3 * 86400, reply_context: ctx("f1"), attachment_summaries: [], tags: [], from_all_mail: true, found_until: now + 60 * 86400 });
      return json(200, out);
    }
    if (p === "/api/v1/find/searches" && req.method() === "POST") { const b = JSON.parse(req.postData() || "{}"); calls.push(["start", b.query, b.include_junk]); state.junk = !!b.include_junk; state.polls = 0; return json(201, progress(false)); }
    if (p === "/api/v1/find/searches/AAAAAAAAAAAA/results") {
      state.polls++; const done = state.polls >= 2; const list = state.junk ? [...rows, { ...rows[1], token: "AAAAAAAAAAAA.2.cccccccccccccccccccccccc", subject: "Junk offer", folder: "Spam" }] : rows;
      return json(200, { ...progress(done), offset: 0, rows: list, more: false });
    }
    if (p === "/api/v1/find/searches/AAAAAAAAAAAA" && req.method() === "DELETE") { calls.push(["cancel"]); return route.fulfill({ status: 204 }); }
    if (/\/api\/v1\/find\/results\/[^/]+\/original$/.test(p)) { calls.push(["view"]); return json(200, { subject: "Canvas order", from: { name: "Dana", address: "dana@example.invalid" }, to: [{ name: "", address: "me@example.invalid" }], date: "Mon, 5 Oct 2026 10:00:00 +0000", text: "Your canvases are on the way.", truncated: false, attachments: [], file_count: 0, remote_images: 0, unsubscribe: null, links: [], warning: null, sender_check: null }); }
    if (/\/api\/v1\/find\/results\/[^/]+\/keep$/.test(p)) { calls.push(["keep"]); state.kept = true; return json(200, { already: false, account_id: "a1", message_id: "f1", found_until: now + 60 * 86400, summary_queued: true }); }
    if (p === "/api/v1/accounts/a1/messages/f1/resolve") { calls.push(["resolve", JSON.parse(req.postData() || "{}").outcome]); state.kept = false; return route.fulfill({ status: 204 }); }
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
async function open(server, { width = 1200, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) csp.push(m.text()); });
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.evaluate(() => { view.layout = "list"; applyView(); render(); });
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };

{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server);
  check("no Found emails entry while nothing is kept", await page.locator("#foundNav").isHidden());
  await page.fill("#search", "v");
  check("one letter does not offer a search of all mail", (await page.locator("[data-find-open]").count()) === 0);
  await page.fill("#search", "canvas");
  check("two or more letters offer Search all my mail", await page.locator("[data-find-open]").isVisible());
  await page.click("[data-find-open]");
  await page.waitForSelector("#findPop:not([hidden]) .find-row");
  check("the results open in a pop-up with the search words shown", (await page.locator("#findPop").innerText()).includes("canvas"));
  await page.waitForFunction(() => /^2 emails/.test(document.querySelector("#findPop .find-total")?.innerText || ""));
  check("the total and each mailbox are shown", (await page.locator("#findPop .find-mbx").innerText()).includes("2 found"));
  check("two rows, newest first, with folder and date", (await page.locator(".find-row").count()) === 2 && (await page.locator(".find-row b").first().innerText()) === "Canvas order" && (await page.locator(".find-row .fr-meta").first().innerText()).includes("Archive"));
  check("a row with files says so", (await page.locator(".find-row .fr-meta").nth(1).innerText()).includes("has files"));
  check("each row has View original email and Summarise", (await page.locator(".find-row [data-find-view]").count()) === 2 && (await page.locator(".find-row [data-find-keep]").count()) === 2);
  check("nothing is shown that could name a message number or folder path", !(await page.locator("#findPop").innerHTML()).includes("source_locator"));
  await shot(page, "results");

  await page.check("[data-find-junk]");
  await page.waitForFunction(() => document.querySelectorAll(".find-row").length === 3);
  check("Include Spam and Bin searches again and adds the extra result", server.calls.some((c) => c[0] === "start" && c[2] === true) && (await page.locator(".find-row").nth(2).innerText()).includes("Spam"));
  await page.uncheck("[data-find-junk]");
  await page.waitForFunction(() => document.querySelectorAll(".find-row").length === 2);

  await page.locator("[data-find-view]").first().click();
  await page.waitForSelector("#attachmentModal.open");
  check("View original email shows the email and puts the results aside", (await page.locator("#attachmentModal").innerText()).includes("canvases are on the way") && (await page.locator("#findPop").isHidden()));
  await page.evaluate(() => closeAttachmentViewer());
  await page.waitForSelector("#findPop:not([hidden]) .find-row");
  check("closing the email brings the results back", (await page.locator(".find-row").count()) === 2);

  await page.locator("[data-find-keep]").first().click();
  await page.waitForFunction(() => /Added to Found emails/.test(document.querySelector("#findPop")?.innerText || ""));
  check("Summarise says it was added and for how long", (await page.locator(".find-row .fr-note").first().innerText()).includes("60 days"));
  check("the button cannot be pressed twice", await page.locator("[data-find-keep]").first().isDisabled());
  await shot(page, "kept");
  await page.click("[data-find-close]");
  check("closing leaves the pop-up hidden", await page.locator("#findPop").isHidden());
  await page.fill("#search", "");
  await page.waitForSelector("#foundNav:not([hidden])");
  check("Found emails appears in the menu with a count", (await page.locator("#foundBadge").innerText()) === "1");
  check("the kept email is not in the normal inbox list", (await page.locator("article.mail").count()) === 1);
  await page.click("#foundNav");
  await page.waitForFunction(() => document.querySelector(".top-left h2")?.textContent === "Found emails");
  check("Found emails lists it, and says how long it is kept", (await page.locator("article.mail").count()) === 1 && (await page.locator("#inboxSubtitle").innerText()).includes("60 days"));
  await page.locator("article.mail .subject").first().click();
  check("a found email offers Reviewed but not Archive or Bin", (await page.locator("article.mail.open [data-status=reviewed]").first().isVisible()) && !(await page.locator("article.mail.open [data-status=archived]").first().isVisible()) && !(await page.locator("article.mail.open [data-status=trashed]").first().isVisible()));
  await shot(page, "found");
  await page.locator("article.mail.open [data-status=reviewed]").first().click();
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 0);
  check("Reviewed asks the server and removes it from the page", server.calls.some((c) => c[0] === "resolve" && c[1] === "reviewed"));
  check("no script errors or policy violations", errors.length === 0 && csp.length === 0);
  await context.close();
}

{
  const server = makeServer({ find_mail: false });
  const { page, errors, csp, context } = await open(server);
  await page.fill("#search", "canvas");
  check("with the switch off there is no Search all my mail", (await page.locator("[data-find-open]").count()) === 0);
  check("no errors with the switch off", errors.length === 0 && csp.length === 0);
  await context.close();
}

{
  const server = makeServer();
  const { page, errors, csp, context } = await open(server, { width: 390, height: 780 });
  await page.evaluate(() => { document.body.classList.add("msearch"); });
  await page.fill("#search", "canvas");
  await page.click("[data-find-open]");
  await page.waitForSelector("#findPop:not([hidden]) .find-row");
  const box = await page.evaluate(() => {
    const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { t: b.top, l: b.left, w: b.width, h: b.height, b: b.bottom }; };
    return { pop: r("#findPop"), top: r("#findPop .sf-top"), foot: r("#findPop .sf-foot"), vh: innerHeight, vw: innerWidth, overflow: getComputedStyle(document.querySelector("#findPop .sf-body")).overflowY };
  });
  check("on a phone the search opens full screen", box.pop.l === 0 && box.pop.t === 0 && Math.round(box.pop.w) === box.vw && Math.round(box.pop.h) === box.vh);
  check("the title and Close stay at the top and the buttons at the bottom", box.top.t === 0 && Math.round(box.foot.b) === box.vh && box.overflow === "auto");
  check("the Close button is easy to press", (await page.locator("#findPop .sf-close").first().boundingBox()).height >= 44);
  await shot(page, "phone-results");
  check("no sideways scrolling on the phone", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  check("no errors on the phone", errors.length === 0 && csp.length === 0);
  await context.close();
}

await browser.close();
if (failed) process.exit(1);
console.log("All Find any email checks passed.");
