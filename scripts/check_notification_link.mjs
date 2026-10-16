// Browser check that a notification link (/?open=<mailbox>:<email>) opens that exact email, that a tap on a notification while Enveliq is
// already open moves the page to the email (the service worker sends a message), and that a link to an email that is gone says so.
// Loaded from a pretend Enveliq server on localhost (a secure address, so the browser has a service worker object).
//
// Usage: node scripts/check_notification_link.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html")), "utf8");
const ORIGIN = "http://localhost:4173";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const now = Math.floor(Date.now() / 1000);
const ctx = (id) => ({ reply_to: "dana@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [] });

const embed = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(here, "..", "web", "static", n), "utf8")).join("\n");
const authCss = fs.readFileSync(path.join(here, "..", "web", "static", "auth.css"), "utf8");

function makeServer() {
  let extra = false;
  const saved = [];
  let mailSelection = null;
  const notificationChanges = [];
  const settings = { morning_on: true, morning_time: "08:00", due_on: true, repeat_hours: 2, repeat_max: 2, quiet_on: true, quiet_from: "21:00", quiet_to: "07:00", show_titles: true, mail_on: false, mail_details: false };
  const overview = () => ({ settings, tz: "Australia/Sydney", channels: [{ id: "browser", label: "This device (browser)", blurb: "A pop-up on this phone or computer, even when Enveliq is closed.", steps: ["Press Turn on for this device."], fields: [], enabled: false, allowed: true, configured: false, last_ok: null, last_error: null, devices: [] }] });                                 // a fourth email that "arrives" after the page loaded
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, waiting: false };
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
    if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
    if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "u", settings: {} }]);
    if (p === "/api/v1/accounts/a1/messages") {
      const base = { id: "m1", subject: "Update on refund", sender_display: "Amazon", sender_address: "a@example.invalid", summary: "Your refund was processed.", priority: "normal", category: "Information", action_required: false, received_at: now - 600, reply_context: ctx("m1") };
      const list = [base, { ...base, id: "m2", subject: "Second email" }, { ...base, id: "m3", subject: "Third email" }];
      if (extra) list.unshift({ ...base, id: "m4", subject: "Fourth email", received_at: now - 5 });
      return json(200, list);
    }
    if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
    if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: authCss });
    if (p === "/api/v1/me/notifications") return json(200, overview());
    if (p === "/api/v1/me/notifications/settings" && req.method() === "PUT") {
      const changes = JSON.parse(req.postData());Object.assign(settings,changes);notificationChanges.push(changes);saved.push(changes);return json(200,overview());
    }
    if (p === "/api/v1/me/notifications/settings" && req.method() === "PUT") { const b = JSON.parse(req.postData()); saved.push(b); Object.assign(settings, b); return json(200, overview()); }
    if (p === "/api/v1/me/mail-context" && req.method() === "GET") return json(200, { selection: mailSelection });
    if (p === "/api/v1/me/mail-context" && req.method() === "PUT") { mailSelection = JSON.parse(req.postData()); if (!mailSelection.account_id) mailSelection = null; return json(200, { selection: mailSelection }); }
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: { a1: { ok: true, at: now } } });
    if (p === "/api/v1/me/outbox") return json(200, { now: Date.now() / 1000, items: [] });
    if (p === "/api/v1/me/shipping") return json(200, { enabled: false, orders: [], now });
    return json(404, { detail: "not found: " + p });
  };
  return { handler, saved, notificationChanges, selection: () => mailSelection, arrive: () => { extra = true; } };
}

const browser = await chromium.launch();
async function open(server, query = "", { width = 1200, height = 900 } = {}) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); sessionStorage.removeItem("enveliq-open"); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, server.handler);
  await page.goto(`${ORIGIN}/${query}`);
  await page.waitForSelector("article.mail");
  await page.evaluate(() => { if (innerWidth > 700) { view.layout = "list"; applyView(); render(); } });   // the desktop part looks at the classic list; the default is now the reading panel on the right
  await page.waitForTimeout(300);
  return { page, errors, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
const openSubjects = (page) => page.evaluate(() => [...document.querySelectorAll("article.mail.open .subject")].map((e) => e.textContent.trim()));

{
  const server = makeServer();
  const { page, context } = await open(server, "", { width: 1200, height: 800 });
  await page.waitForSelector("article.mail");
  await page.locator("article.mail").nth(1).click();
  await page.waitForTimeout(400);
  check("selected email is stored in per-user context", server.selection()?.message_id === "m2" || server.selection()?.message_id === "m1");
  const selected = server.selection()?.message_id;
  await page.reload();
  await page.waitForSelector("article.mail");
  await page.waitForTimeout(250);
  check("selected email restores after refresh", await page.evaluate(() => paneId != null));
  check("refresh retains the same selected message", server.selection()?.message_id === selected);
  await page.close();await context.close();
}

{
  const server = makeServer();
  const { page, context, errors } = await open(server);
  await page.evaluate(() => openSettings("settings","mailalerts"));
  await page.waitForSelector('#mailAlertAccounts input[data-mail-alert-account]');
  check("email alerts are in the existing personal Settings",await page.locator('[data-settings-tab="mailalerts"].active').count()===1);
  check("all new emails is the default mode", await page.locator('input[name="mailAlertMode"][value="all"]').isChecked());
  await page.locator('input[name="mailAlertMode"][value="action"]').check();
  await page.waitForFunction(() => document.getElementById("mailAlertStatus").textContent === "Saved");
  check("action-only mode is saved to the notification endpoint",server.notificationChanges.some(x=>x.mail_filter==="action"));
  await page.locator('#mailAlertAccounts input[data-mail-alert-account]').uncheck();
  await page.waitForFunction(() => document.getElementById("mailAlertStatus").textContent === "Saved");
  check("disabling notifications for one mailbox does not disable the channel",server.notificationChanges.some(x=>Array.isArray(x.mail_muted_accounts)&&x.mail_muted_accounts.includes("a1")));
  await page.evaluate(() => loadMailAlertPrefs());
  await page.waitForTimeout(150);
  check("saved filter and mailbox mute restore in Settings",await page.locator('input[name="mailAlertMode"][value="action"]').isChecked()&&!(await page.locator('#mailAlertAccounts input[data-mail-alert-account]').isChecked()));
  check("no script errors in email alert preferences",errors.length===0);
  await page.close();await context.close();
}

{
  const { page, errors, context } = await open(makeServer());
  check("the page links the install manifest", (await page.locator('link[rel="manifest"]').getAttribute("href")) === "/manifest.webmanifest");
  check("with no link nothing is opened for you", (await openSubjects(page)).length === 0);
  await page.close(); await context.close();
}

{
  const { page, errors, context } = await open(makeServer(), "?open=a1:m2");
  check("a link to one email opens exactly that email", JSON.stringify(await openSubjects(page)) === JSON.stringify(["Second email"]));
  check("the link is taken off the address so a refresh does not open it again", (await page.evaluate(() => location.search)) === "");
  await shot(page, "notification-link-desktop");
  check("no script errors", errors.length === 0);
  await page.close(); await context.close();
}

{
  const { page, context } = await open(makeServer(), "?open=a1:gone");
  check("a link to an email that is gone opens nothing and says so", (await openSubjects(page)).length === 0 && /no longer in your list/.test(await page.locator("#toast, .toast").first().innerText().catch(() => "")));
  await page.close(); await context.close();
}

{
  const { page, context } = await open(makeServer(), "?open=other:m1");
  check("a link naming another mailbox opens nothing", (await openSubjects(page)).length === 0);
  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, context } = await open(server);
  check("a service worker object exists on a secure address", await page.evaluate(() => "serviceWorker" in navigator));
  await page.evaluate((u) => navigator.serviceWorker.dispatchEvent(new MessageEvent("message", { data: { type: "enveliq-open", url: u } })), `${ORIGIN}/?open=a1:m3`);
  await page.waitForFunction(() => document.querySelectorAll("article.mail.open").length === 1);
  check("a tap on a notification while Enveliq is open moves to that email", JSON.stringify(await openSubjects(page)) === JSON.stringify(["Third email"]));
  server.arrive();
  await page.evaluate((u) => navigator.serviceWorker.dispatchEvent(new MessageEvent("message", { data: { type: "enveliq-open", url: u } })), `${ORIGIN}/?open=a1:m4`);
  await page.waitForFunction(() => [...document.querySelectorAll("article.mail.open .subject")].some((e) => e.textContent.trim() === "Fourth email"), null, { timeout: 5000 });
  check("an email that arrived since the list was read is found by reading the list again", (await openSubjects(page)).includes("Fourth email"));
  await page.evaluate(() => navigator.serviceWorker.dispatchEvent(new MessageEvent("message", { data: { type: "enveliq-open", url: "https://evil.example/?open=a1:m1" } })));
  await page.evaluate(() => navigator.serviceWorker.dispatchEvent(new MessageEvent("message", { data: { type: "other", url: "/?open=a1:m1" } })));
  await page.waitForTimeout(300);
  check("a link to another website, or any other message, is ignored", !(await openSubjects(page)).includes("Update on refund"));
  await page.close(); await context.close();
}

{
  const { page, context } = await open(makeServer(), "", { width: 390, height: 800 });
  const original = await page.evaluate(() => ({ filter, paneId }));
  await page.evaluate((url) => navigator.serviceWorker.dispatchEvent(new MessageEvent("message", { data: { type: "enveliq-open", url } })), `${ORIGIN}/?open=a1:m2`);
  await page.waitForSelector(".reader");
  check("notification can open an email while the phone inbox is running", await page.locator(".reader").count() === 1);
  await page.goBack();
  await page.waitForTimeout(300);
  check("Back from notification returns to the original phone inbox", await page.evaluate(({f,p}) => !document.body.classList.contains("reader-open") && filter === f && paneId === p, { f: original.filter, p: original.paneId }));
  await page.close();await context.close();
}

{
  const { page, context } = await open(makeServer(), "?open=a1:m1", { width: 390, height: 800 });
  check("on a phone the link opens the email too (full screen)", await page.evaluate(() => (document.querySelector(".reader h3")?.textContent || "").trim()) === "Update on refund");
  await shot(page, "notification-link-phone");
  await page.goBack();
  await page.waitForTimeout(300);
  check("Back from a fresh phone notification returns to the inbox without leaving Enveliq",
    (await page.locator(".reader").count()) === 0 &&
    (await page.locator("article.mail").count()) > 0 &&
    new URL(page.url()).pathname === "/");

  await page.close(); await context.close();
}

{
  const server = makeServer();
  const { page, errors, context } = await open(server);
  await page.click("#userPill");
  await page.click("#settingsBtn");
  await page.click('[data-settings-tab="reminders"]');
  await page.waitForTimeout(800);
  const text = await page.evaluate(() => { return [...document.querySelectorAll("#settings *")].map((e) => e.shadowRoot ? e.shadowRoot.textContent : "").join(" "); });
  check("Settings > Notifications offers the new-email switch, off to begin with", /When new email arrives/.test(text));
  check("it also offers the sender and subject switch, in the privacy section", /Show who a new email is from and its subject/.test(text));
  const state = await page.evaluate(() => {
    const roots = [...document.querySelectorAll("#settings *")].filter((e) => e.shadowRoot).map((e) => e.shadowRoot);
    const q = (id) => { for (const r of roots) { const el = r.querySelector("#" + id); if (el) return el; } return null; };
    return { mail: q("rs_mail") && q("rs_mail").checked, details: q("rs_maildetails") && q("rs_maildetails").checked };
  });
  check("both start switched off", state.mail === false && state.details === false);
  await shot(page, "reminders-settings");
  check("the tab and page are called Notifications", /Notifications/.test(await page.locator("[data-settings-tab=reminders]").innerText()) && !/Reminders/.test(await page.locator("[data-settings-tab=reminders]").innerText()));
  await page.evaluate(() => {
    const roots = [...document.querySelectorAll("#settings *")].filter((e) => e.shadowRoot).map((e) => e.shadowRoot);
    for (const r of roots) { const el = r.querySelector("#rs_mail"); if (el) { el.click(); r.querySelector("form button[type=submit]").click(); } }
  });
  await page.waitForTimeout(600);
  check("saving sends the new settings", server.saved.length === 1 && server.saved[0].mail_on === true && server.saved[0].mail_details === false);
  check("no script errors in Settings", errors.length === 0);
  await page.close(); await context.close();
}

await browser.close();
process.exit(failed ? 1 : 0);
