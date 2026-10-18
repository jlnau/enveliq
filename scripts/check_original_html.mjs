// Browser check for "View original email" shown as the sender formatted it: the page is rebuilt by the real sanitiser (backend/mail/htmlview.py), shown in a locked frame
// with the policy the server sends, scripts do nothing, pictures from the internet wait for a button, links ask first, and plain text is one tap away.
// The page is loaded from a pretend Enveliq server (Playwright intercepts the requests), so this needs no Python.
//   node scripts/check_original_html.mjs [path/to/prototype/index.html]     (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = path.resolve(process.argv[2] || path.join(here, "..", "prototype", "index.html"));
const html = fs.readFileSync(target, "utf8");
const ORIGIN = "http://enveliq.test";
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const calls = [];
const features = { compose: true, address_book: true, sent: true, media: true, all_mail: false, shipping: false, subscriptions: false, travel: false, waiting: false, messages: false, write_help: false };
const here2 = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const EMAIL = `<html><head><style>.hello{color:rgb(200,30,30);font-size:28px}@import url(https://evil.example.invalid/x.css);</style></head><body bgcolor="#ffffff"><h1 class="hello">Spring sale</h1>
<table width="300" bgcolor="#ffeeaa"><tr><td>Cell one</td><td><a href="https://shop.example.com/sale?id=1">Shop now</a></td></tr></table>
<img src="https://tracker.example.invalid/p.gif" alt="pixel" width="1" height="1"><img id="logo" src="cid:logo@x" alt="logo" width="20" height="20">
<script>window.parent.__pwned = 1</script><img src="x" onerror="window.parent.__pwned = 2"><a href="javascript:window.parent.__pwned=3">bad link</a></body></html>`;
const TINY = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const build = (images) => JSON.parse(execFileSync("python3", ["-I", "-c", `
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("hv", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r = m.rebuild(sys.argv[2], {"logo@x": sys.argv[3]}, sys.argv[4] == "1")
print(json.dumps({"page": r.page, "csp": m.policy_header(sys.argv[4] == "1"), "blocked": r.blocked}))
`, path.join(here2, "backend", "mail", "htmlview.py"), EMAIL, TINY, images ? "1" : "0"], { encoding: "utf8" }));
const pages = { off: build(false), on: build(true) };
const mk = (id, subject) => ({ id, subject, sender_display: "Shop", sender_address: "shop@example.invalid", summary: "A sale.", priority: "normal", category: null, action_required: false, received_at: now - 60,
  reply_context: { reply_to: "shop@example.invalid", delivered_to: null, via_alias: null, message_id: `<${id}@x>`, references: [], cc: [], also_to: [] } });
const messages = [mk("m-html", "Spring sale"), mk("m-plain", "Plain note"), mk("m-broken", "Broken formatted")];
const orig = (extra) => ({ subject: "x", from: { name: "Shop", address: "shop@example.invalid" }, to: [], date: "2026-10-14", text: "Spring sale. Shop now: https://shop.example.com/sale?id=1", attachments: [], links: [{ url: "https://shop.example.com/sale?id=1", host: "shop.example.com", label: "", note: "", flagged: false }], remote_images: 0, ...extra });
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "admin" });
  if (p === "/api/v1/accounts") return json(200, [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton test", email_address: "me@example.invalid", server: "127.0.0.1", port: 1143, username: "me@example.invalid", settings: {} }]);
  if (p === "/api/v1/accounts/a1/messages") return json(200, messages);
  if (/\/messages\/m-html\/original$/.test(p)) return json(200, orig({ has_html: true, remote_images: pages.off.blocked }));
  if (/\/messages\/m-broken\/original$/.test(p)) return json(200, orig({ has_html: true }));
  if (/\/messages\/m-plain\/original$/.test(p)) return json(200, orig({ has_html: false }));
  if (/\/messages\/m-html\/original\/html$/.test(p)) { const on = u.searchParams.get("images") === "true"; calls.push(["html", on]); const r = on ? pages.on : pages.off; return route.fulfill({ status: 200, contentType: "text/html; charset=utf-8", headers: { "Content-Security-Policy": r.csp, "Cache-Control": "no-store" }, body: r.page }); }
  if (/\/original\/html$/.test(p)) { calls.push(["html-broken"]); return json(502, { detail: "The mailbox could not be reached." }); }
  if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: { ...features, address_book_auto: true } });
  if (p === "/api/v1/me/drafts") return json(200, { now: Date.now() / 1000, keep_days: 14, items: [] });
  if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "" });
  if (p === "/api/v1/me/contacts") return json(200, { items: [] });
  if (p === "/api/v1/me/tasks") return json(200, { today: "2026-10-14", tz: "UTC", now: Date.now() / 1000, tasks: [] });
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: {} });
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const open = async (width, height) => {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-view", JSON.stringify({ layout: "list" })); } catch (e) {} });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route(`${ORIGIN}/**`, handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForSelector("article.mail");
  return { page, context, errors };
};
const viewOriginal = async (page, subject) => {
  await page.locator("article.mail", { hasText: subject }).locator(".qmain").click();
  await page.locator("article.mail.open .summary-original-link, .reader .summary-original-link").first().click();
  await page.waitForSelector("#attachmentModal.open");
};

for (const [name, w, h] of [["computer", 1200, 900], ["phone", 390, 800]]) {
  calls.length = 0;
  const { page, context, errors } = await open(w, h);
  await viewOriginal(page, "Spring sale");
  const frame = page.locator("iframe.email-frame");
  check(`[${name}] the email is shown in a frame with no access to the page`, (await frame.count()) === 1 && (await frame.getAttribute("sandbox")) === "allow-scripts");
  const inner = page.frameLocator("iframe.email-frame");
  await inner.locator("h1.hello").waitFor();
  check(`[${name}] the sender's colours and sizes are kept`, await inner.locator("h1.hello").evaluate((e) => getComputedStyle(e).color === "rgb(200, 30, 30)" && parseFloat(getComputedStyle(e).fontSize) === 28));
  check(`[${name}] tables and their background colours are kept`, await inner.locator("table").evaluate((e) => getComputedStyle(e).backgroundColor === "rgb(255, 238, 170)"));
  await page.waitForFunction(() => document.querySelector("iframe.email-frame").offsetHeight > 150);
  check(`[${name}] the frame grows to the height of the email (one page, no inner scrolling)`, (await frame.evaluate((e) => e.offsetHeight)) > 150);
  check(`[${name}] a picture inside the email is shown`, await inner.locator("img[alt='logo']").evaluate((e) => e.complete && e.naturalWidth > 0));
  check(`[${name}] no script in the email ran`, (await page.evaluate(() => window.__pwned)) === undefined);
  check(`[${name}] the picture from the internet is held back, with a button to show it`, (await page.locator(".fmt-pics").count()) === 1 && (await inner.locator("img[data-blocked]").count()) >= 1);
  await inner.locator("a", { hasText: "Shop now" }).click();
  await page.waitForSelector("#linkAsk:not([hidden])");
  check(`[${name}] pressing a link asks first and names the website`, (await page.locator("#linkAskText").innerText()).includes("shop.example.com") && page.url().startsWith(ORIGIN));
  await page.locator("#linkAskNo").click();
  await inner.locator("a", { hasText: "bad link" }).click({ trial: true }).catch(() => {});
  if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, `original-html-${name}.png`) }); }
  await page.locator("[data-fmt-pics]").click();
  await page.waitForFunction(() => document.querySelector(".fmt-pics") && /shown for this email/.test(document.querySelector(".fmt-pics").textContent));
  check(`[${name}] Show pictures asks for the version with pictures`, calls.some((c) => c[0] === "html" && c[1] === true));
  await page.locator('[data-fmt="text"]').click();
  check(`[${name}] Plain text is one tap away`, (await page.locator("pre.email-text").isVisible()) && !(await frame.isVisible()));
  await page.locator('[data-fmt="html"]').click();
  check(`[${name}] and back to the formatted email`, await frame.isVisible());
  check(`[${name}] no script errors`, errors.length === 0);
  await context.close();
}
{
  const { page, context } = await open(1200, 900);
  await viewOriginal(page, "Plain note");
  check("an email with no HTML shows plain text only (no frame, no tabs)", (await page.locator("iframe.email-frame").count()) === 0 && (await page.locator(".fmt-tabs").count()) === 0 && (await page.locator("pre.email-text").isVisible()));
  await context.close();
}
{
  const { page, context } = await open(1200, 900);
  await viewOriginal(page, "Broken formatted");
  await page.waitForFunction(() => document.querySelector("pre.email-text") && document.querySelector("pre.email-text").offsetParent !== null, null, { timeout: 15000 });
  check("if the formatted email cannot be opened, the plain text is shown instead", await page.locator("pre.email-text").isVisible());
  await context.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
