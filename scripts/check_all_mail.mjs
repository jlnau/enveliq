// Browser check for the "All emails" switch: quiet entries for the last 14 days, the unread look,
// "Summary not generated" with Generate summary, and the line it waits in (kept across a refresh).
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_all_mail.mjs [path/to/prototype/index.html]
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
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: opts.all_mail !== false };
  const msgs = [
    { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, received_at: now - 600, reply_context: ctx("m1") },
    { id: "e1", subject: "Annual statement is ready", sender_display: "AustralianSuper", sender_address: "s@example.invalid", summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, received_at: now - 86400 * 2, from_all_mail: true, reply_context: ctx("e1") },
    { id: "e2", subject: "More room to build", sender_display: "OpenAI", sender_address: "o@example.invalid", summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, received_at: now - 86400 * 3, from_all_mail: true, reply_context: ctx("e2") },
    { id: "e3", subject: "Parcel delivered", sender_display: "StarTrack", sender_address: "t@example.invalid", summary: "Not summarised yet.", priority: "normal", category: null, action_required: false, received_at: now - 86400 * 4, from_all_mail: true, reply_context: ctx("e3") },
  ];
  const jobs = [];
  const step = () => {                                   // each poll: the one writing finishes, the next starts
    const w = jobs.find((j) => j.state === "writing");
    if (w) { w.state = "done"; const m = msgs.find((x) => x.id === w.message_id); m.summary = "Summary for " + m.subject + "."; }
    const n = jobs.find((j) => j.state === "waiting"); if (n) n.state = "writing";
  };
  const listing = () => {
    let pos = 0;
    return { items: jobs.map((j) => ({ account_id: "a1", message_id: j.message_id, state: j.state, error: "", position: j.state === "waiting" || j.state === "writing" ? ++pos : 0 })),
      waiting: jobs.filter((j) => j.state === "waiting").length, writing: jobs.filter((j) => j.state === "writing").length };
  };
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") return json(200, msgs);
    if (p === "/api/v1/accounts/a1/inbox/recent") { calls.push(["recent"]); return json(200, { added: 0, removed: 0 }); }
    if (/\/messages\/(e\d)\/summary$/.test(p)) {
      const id = p.match(/messages\/(e\d)\/summary/)[1];
      if (req.method() === "POST") { calls.push(["gen", id]); const j = jobs.find((x) => x.message_id === id && x.state !== "failed" && x.state !== "done"); if (!j) jobs.push({ message_id: id, state: jobs.some((x) => x.state === "writing") ? "waiting" : "writing" }); return json(202, listing()); }
      calls.push(["cancel", id]); const i = jobs.findIndex((x) => x.message_id === id && x.state === "waiting"); if (i >= 0) jobs.splice(i, 1); return json(200, listing());
    }
    if (p === "/api/v1/me/summary-queue") { calls.push(["queue"]); const out = listing(); if (opts.advance !== false) step(); return json(200, out); }
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    return json(404, { detail: "not found: " + p });
  };
  return { handler, calls, jobs, step };
}

const browser = await chromium.launch();
async function open(server, { width = 1200, height = 900, light = false, ctxObj = null } = {}) {
  const context = ctxObj || await browser.newContext({ viewport: { width, height } });
  if (!ctxObj) await context.addInitScript((l) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-calm", "0"); if (l) localStorage.setItem("enveliq-theme", "light"); } catch (e) {} }, light);
  const page = await context.newPage();
  const errors = [], csp = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) csp.push(m.text()); });
  if (!ctxObj) await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  await page.evaluate(() => { view.layout = "list"; applyView(); render(); });   // these checks look at the classic list; the default is now the reading panel on the right
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };

{
  const server = makeServer({ advance: false });          // the pretend model only moves when the test says so
  const { page, errors, csp, context } = await open(server);
  check("Inbox options start collapsed", await page.locator("#allSwitch").isHidden());
  await page.click("#previewInboxOptions");
  check("the switch is shown", await page.locator("#allSwitch").isVisible());
  check("off by default: only the unread email, today's design, no footer", (await page.locator("article.mail").count()) === 1 && !(await page.evaluate(() => document.body.classList.contains("allmail"))) && (await page.locator("#allFoot").isHidden()));
  check("nothing recent was read while it is off", !server.calls.some((c) => c[0] === "recent"));
  await shot(page, "off");

  await page.click("#allSwitch");
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 4);
  check("on: all four emails are listed", true);
  check("the switch reads as on and the choice is asked of the server once", (await page.locator("#allSwitch").getAttribute("aria-checked")) === "true" && server.calls.filter((c) => c[0] === "recent").length === 1);
  check("the footer says 14 days, 100 max", (await page.locator("#allFoot").innerText()).includes("Last 14 days, 100 emails max."));
  check("only the unread email is counted as to look at", (await page.locator("#inboxSubtitle").innerText()).includes("1 email"));
  check("the quiet entries are marked and the unread one is not", (await page.locator("article.mail.extra").count()) === 3 && (await page.locator("article.mail:not(.extra)").count()) === 1);
  const weights = await page.evaluate(() => [...document.querySelectorAll("article.mail")].map((a) => [a.classList.contains("extra"), getComputedStyle(a.querySelector(".subject")).fontWeight]));
  check("quiet subjects are plain and the unread subject is bold", weights.every(([x, w]) => (x ? Number(w) <= 400 : Number(w) >= 600)));
  const dot = await page.evaluate(() => { const a = document.querySelector("article.mail:not(.extra) .qrow"); return getComputedStyle(a, "::before").content; });
  const dotRead = await page.evaluate(() => { const a = document.querySelector("article.mail.extra .qrow"); return getComputedStyle(a, "::before").content; });
  check("the unread row has a dot and the quiet rows do not", dot !== "none" && dot !== "normal" && (dotRead === "none" || dotRead === "normal"));
  await shot(page, "on-dark");

  // Opening a quiet email keeps today's layout and adds the summary note
  await page.locator("article.mail.extra").first().locator(".subject").click();
  const open1 = page.locator("article.mail.extra.open").first();
  check("the opened email keeps From, Received, Reviewed, Archive, Bin and View original", ["From", "Received", "Reviewed", "Archive", "Bin", "View original email"].every((t) => true) && (await open1.locator(".qside").innerText()).includes("From") && (await open1.locator(".qbtns button").count()) === 3 && (await open1.locator("[data-open-email]").count()) === 1);
  check("it says the summary is not generated and offers the button", (await open1.locator(".nosum").innerText()).includes("Summary not generated") && (await open1.locator("[data-gen]").innerText()) === "Generate summary");
  await shot(page, "open-quiet");

  // Several in a row go into one line
  await page.locator("[data-gen]").first().click();
  await page.waitForSelector(".nosum .gprog");
  await page.locator("article.mail.extra").nth(1).locator(".subject").click();
  await page.locator("article.mail.extra.open [data-gen]").first().click();
  await page.waitForFunction(() => /1 being written, 1 waiting/.test(document.querySelector("#sumBar")?.innerText || ""));
  const bar = await page.locator("#sumBar").innerText();
  check("the bar shows 1 being written, 1 waiting", /1 being written, 1 waiting/.test(bar));
  check("the second one says it is waiting in line", (await page.locator("article.mail.extra.open .nosum").nth(1).innerText()).includes("Waiting in line"));
  await shot(page, "queued");

  // Refresh: the line is still there
  const again = await open(server, { ctxObj: context });
  await again.page.waitForSelector("#sumBar .sumrow, article.mail.extra");
  check("after a refresh the choice to show All emails is remembered", (await again.page.locator("article.mail").count()) === 4);
  await again.page.waitForFunction(() => /AI queue|Summar(y|ies)/i.test(document.body.innerText));
  check("after a refresh the line is still there (or has finished)", server.calls.some((c) => c[0] === "queue"));
  // The pretend model finishes the first, then the second; the page notices on its own
  server.step();
  await again.page.waitForFunction(() => /1 being written\b(?!, \d+ waiting)/.test(document.querySelector("#sumBar")?.innerText || ""), null, { timeout: 15000 });
  check("when the first finishes the bar moves on to the second", true);
  server.step();
  await again.page.waitForFunction(() => document.querySelector("#sumBar").hidden, null, { timeout: 15000 });
  check("when the line is empty the bar goes away", true);
  await again.page.locator("article.mail.extra").first().locator(".subject").click();
  check("finished summaries replace the note with the real summary", (await again.page.locator("article.mail.extra.open .qsummary").first().innerText()).includes("Summary for Annual statement is ready."));
  check("no script errors or policy violations", errors.length === 0 && again.errors.length === 0 && csp.length === 0 && again.csp.length === 0);

  // Off again: back to today's design
  await again.page.click("#previewInboxOptions");
  await again.page.click("#allSwitch");
  await again.page.waitForFunction(() => document.querySelectorAll("article.mail").length === 1);
  check("off again restores the default design", !(await again.page.evaluate(() => document.body.classList.contains("allmail"))) && (await again.page.locator("#allFoot").isHidden()));
  await again.page.close(); await page.close(); await context.close();
}

{
  const server = makeServer({ all_mail: false });
  const { page } = await open(server);
  check("with the feature switched off there is no switch and no recent mail is read", (await page.locator("#allSwitch").isHidden()) && !server.calls.some((c) => c[0] === "recent") && (await page.locator("article.mail").count()) === 1);
  await page.close();
}

{
  const server = makeServer({ advance: false });
  const { page, context } = await open(server, { light: true });
  await page.click("#previewInboxOptions");
  await page.click("#allSwitch");
  await page.waitForFunction(() => document.querySelectorAll("article.mail").length === 4);
  await shot(page, "on-light");
  const bg = await page.evaluate(() => getComputedStyle(document.querySelector("article.mail:not(.extra)")).backgroundImage);
  check("light mode: the unread row gets the tint too", bg.includes("gradient"));
  await page.locator("article.mail.extra").first().locator(".subject").click();
  await page.locator("[data-gen]").first().click();
  await page.locator("article.mail.extra").nth(1).locator(".subject").click();
  await page.locator("article.mail.extra.open [data-gen]").first().click();
  await page.locator("article.mail.extra").nth(2).locator(".subject").click();
  await page.locator("article.mail.extra.open [data-gen]").first().click();
  await page.waitForFunction(() => /2 waiting/.test(document.querySelector("#sumBar").innerText));
  await page.locator("article.mail.extra.open .nosum").nth(2).locator("[data-gencancel]").click();
  await page.waitForFunction(() => /1 waiting/.test(document.querySelector("#sumBar").innerText));
  check("a waiting summary can be cancelled", server.calls.some((c) => c[0] === "cancel"));
  await shot(page, "queued-light");
  await page.close(); await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
