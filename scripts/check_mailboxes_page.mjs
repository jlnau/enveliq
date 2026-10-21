// Browser check for the Mailboxes page: a row for each mailbox, an Edit page whose checkboxes save at once,
// no Save buttons, and a phone layout. The page is loaded from a pretend Enveliq server (Playwright intercepts the
// requests), so this needs no Python.   node scripts/check_mailboxes_page.mjs      (SHOTS=<dir> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.join(here, "..", "web");
const ORIGIN = "http://enveliq.test";
const SHOTS = process.env.SHOTS;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const now = Math.floor(Date.now() / 1000);
const accounts = [
  { id: "a1", provider: "Proton Mail", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton", email_address: "morgan@example.com", server: "192.168.1.20", port: 1143, settings: { ai_summaries: true, waiting: true } },
  { id: "a2", provider: "Gmail", auth_method: "imap", owner_user_id: "u1", display_name: "Gmail", email_address: "morgan@gmail.example", server: "imap.example.invalid", port: 993, settings: { color: "red", ai_summaries: true, waiting: true } },
];
const patches = [];
const syncAccounts = { a1: { ok: true, at: now - 120, added: 0 }, a2: { ok: false, at: now - 60, error: "login failed" } };
const handler = async (route) => {
  const req = route.request(), p = new URL(req.url()).pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (p === "/mailboxes") return route.fulfill({ status: 200, contentType: "text/html", body: fs.readFileSync(path.join(web, "auth.html"), "utf8") });
  if (p.startsWith("/static/")) return route.fulfill({ status: 200, contentType: p.endsWith(".css") ? "text/css" : "application/javascript", body: fs.readFileSync(path.join(web, p)) });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "user", session: { state: "full" } });
  if (p === "/api/v1/accounts" && req.method() === "GET") return json(200, accounts);
  if (p.startsWith("/api/v1/accounts/") && req.method() === "PATCH") {
    const a = accounts.find(x => p.endsWith("/" + x.id)); const body = JSON.parse(req.postData() || "{}");
    if (body.settings && body.settings.fail) return json(500, { detail: "nope" });
    patches.push(body); if (body.settings) a.settings = body.settings; if (body.display_name) a.display_name = body.display_name;
    return json(200, a);
  }
  if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, now: Date.now() / 1000, accounts: syncAccounts });
  if (p === "/api/v1/ai/status") return json(200, { configured: true, model: "llama3.1:8b" });
  if (p === "/api/v1/mail/providers") return json(200, [{ id: "proton", label: "Proton Mail", blurb: "Through Proton Bridge", kind: "bridge", status: "ready" }]);
  return json(404, { detail: "not found" });
};
const browser = await chromium.launch();
const csp = [];
async function open(width, height) {
  const ctx = await browser.newContext({ viewport: { width, height } });
  await ctx.route(ORIGIN + "/**", handler);
  const page = await ctx.newPage();
  page.on("console", m => { if (/Content Security Policy/i.test(m.text())) csp.push(m.text()); });
  await page.goto(ORIGIN + "/mailboxes");
  await page.waitForSelector(".mbrow");
  return page;
}

const page = await open(1200, 800);
check("each mailbox is a row in one list", (await page.locator(".mbrow").count()) === 2);
check("a mailbox row opens that mailbox and has no buttons of its own", (await page.locator(".mbrow").first().locator("button").count()) === 0 && (await page.locator(".mbrow").first().evaluate(e => e.tagName)) === "BUTTON");
check("none of the old long row of buttons is on the list", (await page.locator("button:has-text('Turn automatic sync'), button:has-text('Rename'), button:has-text('Diagnostics'), button:has-text('Remove')").count()) === 0);
check("a mailbox that failed its last check says it needs you", (await page.locator(".mbrow").nth(1).getAttribute("aria-label")).includes("Needs you") || (await page.locator(".mbrow").nth(1).getAttribute("aria-label")).includes("login failed"));
check("the rows are in one grouped card", await page.evaluate(() => { const r = [...document.querySelectorAll(".mbrow")]; return r[0].parentElement === r[1].parentElement && r[1].getBoundingClientRect().top > r[0].getBoundingClientRect().bottom - 2; }));
check("the add form is folded away when a mailbox exists", await page.locator("#mb_add").isHidden());
await page.getByRole("button", { name: "Add a mailbox" }).click();
check("the Add a mailbox row opens the form", await page.locator("#mb_add").isVisible());
if (SHOTS) await page.screenshot({ path: `${SHOTS}/mailboxes-add.png` });
await page.getByRole("link", { name: /Mailboxes/ }).first().click().catch(() => {});
await page.goto(ORIGIN + "/mailboxes");
await page.waitForSelector(".mbrow");
if (SHOTS) await page.screenshot({ path: `${SHOTS}/mailboxes-list.png` });

await page.locator(".mbrow").first().click();
await page.waitForSelector("#mb_ai_a1");
check("the mailbox page has three ticked switches", (await page.locator(".li input[type=checkbox]:checked").count()) === 3);
check("it has no Save button", (await page.getByRole("button", { name: "Save", exact: true }).count()) === 0);
check("Remove sits on its own row, as a red centred row", (await page.locator(".li.danger", { hasText: "Remove this mailbox" }).count()) === 1);
if (SHOTS) await page.screenshot({ path: `${SHOTS}/mailbox-edit.png` });
await page.uncheck("#mb_ai_a1", { force: true });
await page.waitForTimeout(150);
check("switching saves at once", patches.length === 1 && patches[0].settings.ai_summaries === false);
check("the other choices are kept in the same save", patches[0].settings.waiting === true);
await page.uncheck("#mb_auto_a1", { force: true });
await page.waitForTimeout(150);
check("automatic checking saves too", patches.length === 2 && patches[1].settings.auto_sync === false);
await page.check("#mb_ai_a1", { force: true });
await page.waitForTimeout(150);
check("switching on again saves too", patches.length === 3 && patches[2].settings.ai_summaries === true);
await page.getByRole("button", { name: /^Name/ }).click();
await page.fill("input[aria-label='Mailbox name']", "Home Proton");
await page.keyboard.press("Tab");
await page.waitForSelector("h1.pg-title:has-text('Home Proton')", { state: "attached" });
check("the name saves when you leave the box", patches[patches.length - 1].display_name === "Home Proton");
await page.locator(".ios-pane:visible .back").first().click();
check("Diagnostics is a row you open", (await page.getByRole("button", { name: /Diagnostics/ }).count()) === 1);
await page.getByRole("button", { name: /Remove this mailbox/ }).click();
await page.locator("button:has-text('Remove Home Proton')").click();
check("Remove asks a question and does not remove yet", (await page.locator("text=Yes, delete").count()) + (await page.locator("button.danger").count()) >= 2);
await page.goto(ORIGIN + "/mailboxes");
await page.waitForSelector(".mbrow");
check("the list is back", (await page.locator(".mbrow").count()) === 2);

const phone = await open(390, 844);
check("rows stack on a phone", await phone.evaluate(() => { const c = [...document.querySelectorAll(".mbrow")].map(e => e.getBoundingClientRect()); return c[1].top > c[0].bottom - 2; }));
check("no sideways scrolling on a phone", await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
check("rows are easy to tap", await phone.evaluate(() => [...document.querySelectorAll(".mbrow")].every(b => b.getBoundingClientRect().height >= 44)));
if (SHOTS) await phone.screenshot({ path: `${SHOTS}/mailboxes-phone.png` });
await phone.locator(".mbrow").first().click();
await phone.waitForSelector("#mb_ai_a1");
check("the mailbox page fits a phone and its rows are large", await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1 && [...document.querySelectorAll(".li")].filter(r => r.offsetParent).every(r => r.getBoundingClientRect().height >= 44)));
if (SHOTS) await phone.screenshot({ path: `${SHOTS}/mailbox-edit-phone.png`, fullPage: true });
check("no Content Security Policy violations", csp.length === 0);
await browser.close();
process.exit(failed ? 1 : 0);
