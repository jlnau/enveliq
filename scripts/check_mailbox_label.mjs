// Browser check for the mailbox label: with more than one mailbox connected, every email in the list, and the open email, says which mailbox it came from.
// With one mailbox there is no label. The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_mailbox_label.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html"));
const html = fs.readFileSync(target, "utf8");
const ORIGIN = "http://enveliq.test";
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const features = { compose: true, address_book: true, sent: true, media: false, all_mail: false, shipping: false, rss: false, tags: false, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const mk = (id, subject, name, n) => ({ id, subject, sender_display: name, sender_address: name.toLowerCase() + "@example.invalid", summary: "A summary.", priority: "normal", category: null, action_required: false, received_at: now - n,
  reply_context: { reply_to: name.toLowerCase() + "@example.invalid", delivered_to: null, via_alias: null, message_id: "<" + id + "@x>", references: [], cc: [], also_to: [] } });
const proton = { id: "a1", provider: "Proton Mail", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "172.30.0.1", port: 1144, username: "bridge", settings: { smtp_port: 1026, send_identities: [], ai_summaries: true } };
const gmail = { id: "a2", provider: "Gmail", auth_method: "imap", owner_user_id: "u1", display_name: "Gmail test", email_address: "me2@example.invalid", server: "imap.example.invalid", port: 993, username: "me2@example.invalid", settings: { provider_id: "gmail", smtp_port: 465, send_identities: [], ai_summaries: true } };
let accounts = [proton, gmail];
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, accounts);
  if (p === "/api/v1/accounts/a1/messages") return json(200, [mk("m-proton", "From the Proton mailbox", "Bob", 120)]);
  if (p === "/api/v1/accounts/a2/messages") return json(200, [mk("m-gmail", "From the Gmail mailbox", "Cara", 180)]);
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const run = async (width, height, layout = "list") => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript((l) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: l })); } catch (e) {} }, layout);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const rowOf = (page, subject) => page.locator("article.mail", { hasText: subject });

{
  const { page, context, errors } = await run(1300, 900);
  check("with two mailboxes each email in the list says which one it came from", (await rowOf(page, "Proton mailbox").locator(".qmain .mbox").innerText()).trim() === "Proton test" && (await rowOf(page, "Gmail mailbox").locator(".qmain .mbox").innerText()).trim() === "Gmail test");
  check("the two mailboxes get different colours", await page.evaluate(() => { const a = [...document.querySelectorAll(".qmain .mbox")].map((e) => e.style.getPropertyValue("--bh")); return a.length === 2 && a[0] !== a[1]; }));
  check("a mailbox with no chosen colour gets an automatic one that is a number", await page.evaluate(() => /^\d+$/.test(document.querySelector(".qmain .mbox").style.getPropertyValue("--bh").trim())));
  check("the label's hover text names the provider and the address", /Gmail/.test(await rowOf(page, "Gmail mailbox").locator(".mbox").getAttribute("title")) && /me2@example.invalid/.test(await rowOf(page, "Gmail mailbox").locator(".mbox").getAttribute("title")));
  await rowOf(page, "Gmail mailbox").locator(".qmain").click();
  await page.waitForSelector("article.mail.open .qside");
  check("inside the open email there is a Mailbox line with the same label", /Mailbox/.test(await page.locator("article.mail.open .qside").innerText()) && (await page.locator("article.mail.open .qside .mbox").innerText()).trim() === "Gmail test");
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "mailbox_label_desktop.png") });
  check("no script errors", errors.length === 0);
  await context.close();
}
{
  const { page, context, errors } = await run(390, 800);
  check("on a phone the list shows the label too", (await page.locator("article.mail .qmain .mbox").count()) === 2);
  await rowOf(page, "Proton mailbox").locator(".qmain").click();
  await page.waitForSelector(".reader .qside");
  check("on a phone the full-screen email shows which mailbox it came from", (await page.locator(".reader .qside .mbox").innerText()).trim() === "Proton test");
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "mailbox_label_phone.png") });
  check("no script errors", errors.length === 0);
  await context.close();
}
{
  gmail.settings = { ...gmail.settings, color: "red" };
  proton.settings = { ...proton.settings, color: "teal" };
  const { page, context, errors } = await run(1300, 900);
  const hues = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll("article.mail")].map((a) => [a.innerText.includes("Gmail mailbox") ? "gmail" : "proton", a.querySelector(".qmain .mbox").style.getPropertyValue("--bh").trim()])));
  check("a colour chosen on the Mailboxes page is the one the label uses (red 0, teal 180)", hues.gmail === "0" && hues.proton === "180");
  check("no script errors", errors.length === 0);
  await context.close();
  delete gmail.settings.color; delete proton.settings.color;
}
{
  accounts = [proton];
  const { page, context, errors } = await run(1300, 900);
  check("with one mailbox there is no label", (await page.locator(".mbox").count()) === 0);
  await rowOf(page, "Proton mailbox").locator(".qmain").click();
  await page.waitForSelector("article.mail.open .qside");
  check("and no Mailbox line in the open email", !/Mailbox/.test(await page.locator("article.mail.open .qside").innerText()));
  check("no script errors", errors.length === 0);
  await context.close();
}
await browser.close();
if (failed) process.exit(1);
