// Browser check for Waiting for reply (v0.52): the page, the amber Home card, the buttons, the nudge, and that
// hostile text from an email is shown as text only. Loaded from a pretend Enveliq server.
//
// Usage: node scripts/check_waiting.mjs [path/to/prototype/index.html]
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
    if (p === "/api/v1/accounts/a1/messages") return json(200, [
    { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, received_at: now - 600, reply_context: ctx("m1") },
    ]);
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
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); } catch (e) {} });
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
  check("the Waiting entry is shown when the feature is on", await page.locator("#waitNav").isVisible() && await page.locator("#shipNav").isHidden());
  check("the sidebar shows how many are being waited on (3; the answered one is not counted)", (await page.locator("#waitBadge").innerText()).trim() === "3");
  check("the number turns blue because two are due", await page.locator("#waitBadge.hot").count() === 1);
  check("Home shows the amber card with the due notes only", (await page.locator("#waitBars .waitrow").count()) === 2 && !(await page.locator("#waitBars").innerText()).includes("Lunch on Thursday"));
  check("it says who, what and for how long", /Dana/.test(await page.locator("#waitBars").innerText()) && /Sent 4 days ago\. No reply yet\./.test(await page.locator("#waitBars").innerText()));
  await shot(page, "wait-home");

  await page.click("#waitNav");
  await page.waitForSelector("#waitPage .wcard");
  check("the page lists due, waiting and closed notes", (await page.locator("#waitPage .wcard").count()) === 4 && (await page.locator("#waitPage .wcard.due").count()) === 2 && (await page.locator("#waitPage .wcard.closed").count()) === 1 && await page.locator("#list").isHidden());
  const txt = await page.locator("#waitPage").innerText();
  check("shows the ask, the time left, and why a note was closed", txt.includes("Waiting: Send me the quote by Friday.") && /Reminder after 3 days/.test(txt) && txt.includes("Replied"));
  check("hostile text is shown as text, not run", !(await page.evaluate(() => window.__pwned)) && (await page.locator("#waitPage img, #waitPage script").count()) === 0 && txt.includes("<script>window.__pwned=1</script>"));
  check("buttons are at least 44px tall", await page.evaluate(() => [...document.querySelectorAll("#waitPage .wbtn")].every((b) => b.getBoundingClientRect().height >= 43)));
  await shot(page, "wait-page");

  await page.selectOption("#waitDays", "5");
  await page.waitForFunction(() => document.querySelector("#waitDays").value === "5" && document.querySelectorAll("#waitPage .wcard.due").length === 1);
  check("changing the days is sent to the server and the due notes follow (the four-day one is no longer due)", server.calls.some((c) => c[0] === "days" && c[1] === 5) && (await page.locator("#waitPage .wcard.due").count()) === 1);
  await page.selectOption("#waitDays", "3");
  await page.waitForFunction(() => document.querySelectorAll("#waitPage .wcard.due").length === 2);

  await page.locator('#waitPage .wcard', { hasText: "Quote for the fence" }).locator('[data-wait-nudge]').click();
  await page.waitForSelector("#newMail.open");
  check("Write a nudge opens New email to that person, with the subject and a short message", (await page.locator("#nmSubject").inputValue()) === "Re: Quote for the fence" && (await page.locator("#nmTo").innerText()).includes("Dana") && (await page.locator("#nmText").inputValue()).includes("Send me the quote by Friday"));
  await page.locator("#nmCancel").click(); await page.locator("#nmCancel").click();
  await page.waitForFunction(() => !document.querySelector("#newMail.open"));

  await page.locator('#waitPage .wcard', { hasText: "Quote for the fence" }).locator('[data-wait="later"]').click();
  await page.waitForFunction(() => document.querySelectorAll("#waitPage .wcard.due").length === 1);
  check("Ask again moves it out of the due list", server.calls.some((c) => c[0] === "later"));
  await page.locator('#waitPage .wcard', { hasText: "Lunch on Thursday" }).locator('[data-wait="got_reply"]').click();
  await page.waitForFunction(() => document.querySelectorAll("#waitPage .wcard.closed").length === 2);
  check("Got a reply closes it", server.calls.some((c) => c[0] === "got_reply"));
  await page.locator('#waitPage .wcard.closed', { hasText: "Lunch on Thursday" }).locator('[data-wait="undo"]').click();
  await page.waitForFunction(() => document.querySelectorAll("#waitPage .wcard.closed").length === 1);
  check("Undo puts it back", server.calls.some((c) => c[0] === "undo"));
  await page.locator('#waitPage [data-wait="not_needed"]').first().click();
  await page.waitForFunction(() => document.querySelectorAll("#waitPage .wcard.closed").length === 2);
  check("Not needed closes it", server.calls.some((c) => c[0] === "not_needed"));
  check("no script errors or policy violations", errors.length === 0 && csp.length === 0);
  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, errors, context } = await open(server);
  if (!(await page.locator("#sentNav").isVisible())) await page.locator("#moreToggle").click();
  await page.click("#sentNav");
  await page.waitForSelector(".srow");
  const rows = page.locator(".srow");
  await rows.nth(0).locator(".shead").click();
  check("an opened sent email has a Follow for a reply button", (await rows.nth(0).locator(".sent-follow, .sbody").locator("button", { hasText: "Follow for a reply" }).count()) === 1);
  await rows.nth(2).locator(".shead").click();
  check("one that is already followed says so and cannot be pressed", await rows.nth(2).locator("button", { hasText: "Following for a reply" }).isDisabled());
  await shot(page, "sent-follow");
  await rows.nth(0).locator("button", { hasText: "Follow for a reply" }).click();
  await rows.nth(0).locator("button", { hasText: "Following for a reply" }).waitFor();
  check("pressing it follows that email and says where to see it", server.calls.some((c) => c[0] === "follow" && c[1] === 5 && c[2] === false) && (await rows.nth(0).innerText()).includes("See Waiting for reply"));
  await rows.nth(1).locator(".shead").click();
  await rows.nth(1).locator("button", { hasText: "Follow for a reply" }).click();
  await rows.nth(1).locator("button", { hasText: "Follow it anyway" }).waitFor();
  check("when the AI finds nothing asked it says so and offers Follow it anyway", (await rows.nth(1).innerText()).includes("did not find a question or request"));
  await rows.nth(1).locator("button", { hasText: "Follow it anyway" }).click();
  await rows.nth(1).locator("button", { hasText: "Following for a reply" }).waitFor();
  check("Follow it anyway sends force", server.calls.some((c) => c[0] === "follow" && c[1] === 6 && c[2] === true));
  check("no script errors", errors.length === 0);
  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, context } = await open(server);
  await page.locator('#waitBars [data-wait="got_reply"]').first().click();
  await page.waitForFunction(() => document.querySelectorAll("#waitBars .waitrow").length === 1);
  check("a button on the Home card works without opening the page", server.calls.some((c) => c[0] === "got_reply"));
  await page.close(); await context.close();
}

{
  const server = makeServer({ waiting: false });
  const { page, context } = await open(server);
  check("with the feature off there is no menu entry, no Home card and no request", await page.locator("#waitNav").isHidden() && await page.locator("#waitBars").isHidden() && !server.calls.some((c) => c[0] === "list"));
  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, context } = await open(server, { width: 390, height: 800 });
  check("phone: the Home card fits the screen", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  check("phone: its buttons are at least 44px tall", await page.evaluate(() => [...document.querySelectorAll("#waitBars .wbtn")].every((b) => b.getBoundingClientRect().height >= 43)));
  await shot(page, "wait-home-phone");
  await page.close(); await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
