// Browser check that a refresh keeps you where you are (the page and the open emails), and the Expand all / Collapse all link. Loaded from a pretend Enveliq server.
//
// Usage: node scripts/check_refresh.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "\u2713 " : "\u2717 ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);
const ctx = (id) => ({ reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });
const day = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);

function makeServer(opts = {}) {
  const calls = [];
  const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, waiting: opts.waiting !== false };
  const day = 86400;
  let days = 3;
  let notes = [
    { id: "w" + "a".repeat(23), account_id: "a1", to: ["Dana Example <dana@example.invalid>"], subject: "Quote for the fence", sent_at: now - 4 * day, ask: "Send me the quote by Friday.", state: "waiting", snooze_until: 0, closed_at: null, reason: null },
    { id: "w" + "b".repeat(23), account_id: "a1", to: ["Sam <sam@example.invalid>", "lee@example.invalid"], subject: "Lunch on Thursday?", sent_at: now - 1 * day, ask: "Tell me if Thursday works.", state: "waiting", snooze_until: 0, closed_at: null, reason: null },
    { id: "w" + "c".repeat(23), account_id: "a1", to: ["<img src=x onerror=window.__pwned=1>Evil <e@example.invalid>"], subject: "<script>window.__pwned=1</script>", sent_at: now - 9 * day, ask: "<b>reply</b> please", state: "waiting", snooze_until: 0, closed_at: null, reason: null },
    { id: "w" + "d".repeat(23), account_id: "a1", to: ["Kim <kim@example.invalid>"], subject: "Invoice 88", sent_at: now - 6 * day, ask: "Confirm you got it.", state: "replied", snooze_until: 0, closed_at: now - 100, reason: "reply" },
  ];
  const row = (n) => ({ ...n, age_days: Math.floor((now - n.sent_at) / day), due: n.state === "waiting" && now >= n.sent_at + days * day && now >= n.snooze_until });
  const out = () => ({ enabled: features.waiting, days, notes: features.waiting ? notes.map(row) : [], now });
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") { const base = { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, received_at: now - 600, reply_context: ctx("m1") }; return json(200, [base, { ...base, id: "m2", subject: "Second email" }, { ...base, id: "m3", subject: "Third email" }]); }
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    if (p === "/api/v1/me/shipping") return json(200, { enabled: false, orders: [], now });
    if (p === "/api/v1/accounts/a1/sent") {
      return json(200, { validity: 1, days: 14, more: false, items: [
        { uid: 5, to: [{ name: "Dana", address: "dana@example.invalid" }], subject: "Quote for the fence", date: now - 3 * day, follow: null },
        { uid: 6, to: [{ name: "Sam", address: "sam@example.invalid" }], subject: "Thanks for lunch", date: now - 2 * day, follow: null },
        { uid: 7, to: [{ name: "Kim", address: "kim@example.invalid" }], subject: "Invoice 88", date: now - 1 * day, follow: "waiting" },
      ] });
    }
    const f = p.match(/^\/api\/v1\/accounts\/a1\/sent\/1\/(\d+)\/follow$/);
    if (f && req.method() === "POST") {
      const force = JSON.parse(req.postData() || "{}").force === true;
      calls.push(["follow", Number(f[1]), force]);
      if (f[1] === "6" && !force) return json(200, { result: "not_waiting" });
      return json(200, { result: "added", ask: "Waiting for a reply." });
    }
    if (p === "/api/v1/me/waiting" && req.method() === "GET") { calls.push(["list"]); return json(200, out()); }
    if (p === "/api/v1/me/waiting/check") { calls.push(["check"]); return json(200, out()); }
    if (p === "/api/v1/me/waiting/settings") { days = JSON.parse(req.postData()).days; calls.push(["days", days]); return json(200, out()); }
    const a = p.match(/^\/api\/v1\/me\/waiting\/(w[0-9a-f]{23})\/(\w+)$/);
    if (a && req.method() === "POST") {
      calls.push([a[2], a[1]]);
      const n = notes.find((x) => x.id === a[1]);
      if (a[2] === "got_reply") { n.state = "replied"; n.closed_at = now; n.reason = "you"; }
      if (a[2] === "not_needed") { n.state = "done"; n.closed_at = now; n.reason = "not_needed"; }
      if (a[2] === "later") n.snooze_until = now + days * day;
      if (a[2] === "undo") { n.state = "waiting"; n.closed_at = null; n.reason = null; n.snooze_until = 0; }
      return json(200, out());
    }
    return json(404, { detail: "not found: " + p });
  };
  return { handler, calls };
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
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };


{
  const server = makeServer();
  const { page, context } = await open(server);
  await page.waitForSelector("article.mail");
  check("the expand link starts as Expand all", (await page.locator("#expandAll").innerText()) === "Expand all" && await page.locator("#expandAll").isVisible());

  // Expand all / Collapse all
  await page.click("#expandAll");
  await page.waitForFunction(() => document.querySelectorAll("article.mail.open").length === 3);
  check("Expand all opens every email and the link turns into Collapse all", (await page.locator("#expandAll").innerText()) === "Collapse all");
  await page.click("#expandAll");
  await page.waitForFunction(() => document.querySelectorAll("article.mail.open").length === 0);
  check("Collapse all closes them again", (await page.locator("#expandAll").innerText()) === "Expand all");
  check("the link is small and quiet (12px text, not a button box)", await page.evaluate(() => { const c = getComputedStyle(document.getElementById("expandAll")); return parseFloat(c.fontSize) <= 13 && c.borderTopWidth === "0px" && c.backgroundColor === "rgba(0, 0, 0, 0)"; }));

  // While emails are selected the selection bar needs the room, so the link steps aside
  await page.locator("article.mail .check").nth(0).check();
  await page.locator("article.mail .check").nth(1).check();
  check("the link steps aside while two or more emails are selected, and returns after", await page.locator("#expandAll").isHidden());
  await page.click("#clear");
  await page.waitForFunction(() => !document.getElementById("expandAll").hidden);
  check("clearing the selection brings it back", await page.locator("#expandAll").isVisible());

  // An open email stays open after a refresh
  await page.locator("article.mail .subject", { hasText: "Second email" }).click();
  await page.waitForFunction(() => document.querySelectorAll("article.mail.open").length === 1);
  await page.reload();
  await page.waitForSelector("article.mail");
  await page.waitForFunction(() => document.querySelectorAll("article.mail.open").length === 1);
  check("after a refresh the same email is still open", (await page.locator("article.mail.open .subject").innerText()) === "Second email" && (await page.locator("article.mail").count()) === 3);
  await shot(page, "refresh-open");
  await page.locator("article.mail.open .subject").click();
  await page.reload();
  await page.waitForSelector("article.mail");
  check("an email closed before the refresh stays closed", (await page.locator("article.mail.open").count()) === 0);

  // The page you were on
  for (const [nav, sel, hash, what] of [["#shipNav", "#shipPage", "#/shipping", "Shipping"], ["#waitNav", "#waitPage", "#/waiting", "Waiting for reply"], ['.nav[data-filter="tasks"]', "#tasksPage", "#/tasks", "Tasks"], ['.nav[data-filter="reviewed"]', "#list", "#/reviewed", "Reviewed"], ["#sentNav", "#sentList", "#/sent", "Sent"]]) {
    if (hash === "#/shipping" || hash === "#/waiting") continue;                     // those switches are off in this mock; covered in their own checks
    await page.click(nav);
    check(`${what}: the address shows where you are`, (await page.evaluate(() => location.hash)) === hash);
    await page.reload();
    await page.waitForSelector(".nav.active");
    await page.waitForTimeout(400);
    check(`${what}: after a refresh you are still there`, (await page.evaluate(() => location.hash)) === hash && (await page.locator(`.nav.active`).getAttribute("data-filter")) === hash.slice(2) && (hash !== "#/sent" ? true : await page.locator(".srow").first().isVisible()));
  }
  await page.click('.nav[data-filter="all"]');
  check("the inbox has no hash", (await page.evaluate(() => location.hash)) === "");
  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, context } = await open(server);
  await page.click("#userPill");
await page.click("#settingsBtn");
  await page.click('[data-settings-tab="general"]');
  check("Settings: the address shows the open section", (await page.evaluate(() => location.hash)) === "#/settings/general");
  await page.reload();
  await page.waitForSelector("#settings.open");
  await page.waitForTimeout(500);
  check("Settings: after a refresh the same section is open", (await page.locator("#settings.open").count()) === 1 && (await page.locator("[data-settings-tab].active").getAttribute("data-settings-tab")) === "general");
  await page.click("#closeSettings");
  check("closing Settings clears the address", (await page.evaluate(() => location.hash)) === "");
  await page.close(); await context.close();
}

{
  const server = makeServer({ waiting: true });
  const { page, context } = await open(server);
  await page.click("#waitNav");
  await page.reload();
  await page.waitForSelector(".nav.active");
  await page.waitForTimeout(400);
  check("Waiting for reply: after a refresh you are still there", (await page.evaluate(() => location.hash)) === "#/waiting" && await page.locator("#waitPage").isVisible());
  await page.close(); await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
