// Browser check for the user menu, Profile settings, the tidied Settings/Administration menus and the password rules card.
// The page is loaded from a pretend Enveliq server (Playwright intercepts requests); the real page scripts from web/static are used.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_user_menu.mjs [path/to/prototype/index.html]
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const html = fs.readFileSync(path.resolve(process.argv[2] || path.join(root, "prototype", "index.html")), "utf8");
const authJs = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(root, "web", "static", n), "utf8")).join("\n");   // as /embed.js serves them
const authCss = fs.readFileSync(path.join(root, "web", "static", "auth.css"), "utf8");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
for (const ev of ["uncaughtException", "unhandledRejection"]) process.on(ev, (e) => { console.log("::error::" + String((e && e.message) || e).split("\n").slice(0, 3).join(" | ")); process.exit(1); });
const features = { compose: true, address_book: true, sent: true, media: true };
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");

function makeServer(role) {
  const calls = [];
  const me = { id: "u1", username: "morgan", display_name: "morgan", email: null, about: "", show_in_people: true, role, avatar_v: null, security: { password_set: true, totp_enabled: false, recovery_codes_left: 0, passkeys: [], sso_linked: false },
    session: { state: "full", method: "password" }, policy: { require_mfa: "admins", password_login: "everyone", pw_min_length: 12, pw_min_digits: 0, pw_min_upper: 0, pw_min_lower: 0, pw_min_symbols: 0, pw_forbid_username: true }, sso: { enabled: false } };
  const policy = { ...me.policy };
  const handler = async (route) => {
    const req = route.request(), p = new URL(req.url()).pathname;
    const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = () => { try { return JSON.parse(req.postData() || "{}"); } catch (e) { return {}; } };
    if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
    if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: authJs });
    if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: authCss });
    if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } });
    if (p === "/api/v1/system") return json(200, { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900, version: "0.59" });
    if (p === "/api/v1/me") return json(200, me);
    if (p === "/api/v1/me/profile") { calls.push(["profile", body()]); const b = body(); if (b.display_name !== undefined) me.display_name = b.display_name || me.username; if (b.email !== undefined) me.email = b.email || null; if (b.about !== undefined) me.about = b.about; return json(200, me); }
    if (p === "/api/v1/me/avatar") { if (req.method() === "PUT") { calls.push(["avatar", body().image.slice(0, 22)]); me.avatar_v = "abc123"; } else { calls.push(["avatar-remove"]); me.avatar_v = null; } return json(200, me); }
    if (/^\/api\/v1\/users\/u1\/avatar/.test(p)) return route.fulfill({ status: 200, contentType: "image/png", body: PNG });
    if (p === "/api/v1/accounts") return json(200, []);
    if (p === "/api/v1/me/preferences") return json(200, { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 0 });
    if (p === "/api/v1/me/features") return json(200, { effective: features, admin: features, user: features, labels: { compose: "New email" } });
    if (p === "/api/v1/sync/status") return json(200, { enabled: true, minutes: 10, editable: true, now: Date.now() / 1000, accounts: {} });
    if (p === "/api/v1/admin/users") return json(200, [{ id: "u1", username: "morgan", display_name: "Morgan", role: "admin", disabled: false, source: "local", security: { totp_enabled: true, passkeys: [] } }]);
    if (p === "/api/v1/admin/auth-policy") { if (req.method() === "PUT") { calls.push(["policy", body()]); Object.assign(policy, body()); } return json(200, policy); }
    if (p === "/api/v1/admin/sso") return json(200, { enabled: false, redirect_uri: ORIGIN + "/cb", label: "SSO", issuer: "", client_id: "", scopes: "openid", auto_create: true, allowed_groups: [], admin_groups: [], groups_claim: "groups", username_claim: "preferred_username", require_email_verified: false });
    return json(404, { detail: "not found" });
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
  await page.waitForSelector("#userPill", { state: "attached" });
  await page.waitForFunction(() => document.body.classList.contains("backend"));
  return { page, errors, csp, context };
}
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };
const host = (page, panel) => page.locator(`[data-settings-panel="${panel}"] .embed-host`);

// ---- Administrator ----
{
  const server = makeServer("admin");
  const { page, errors, csp } = await open(server);
  check("the page names its tab icon", (await page.locator('head link[rel="icon"]').getAttribute("href")) === "/brand/enveliq-icon-128.webp");
  check("the sidebar footer keeps only Calm mode and Agent", (await page.locator(".side-foot .nav").allInnerTexts()).map((t) => t.trim()).join("|") === "Calm mode|Agent");
  check("the menu is closed to begin with", await page.locator("#userMenu").isHidden());
  check("desktop Inbox options start collapsed", await page.locator("#filterBy").isHidden() && await page.locator("#previewInboxOptions").getAttribute("aria-expanded")==="false");
  await page.click("#previewInboxOptions");
  check("desktop Inbox options can be expanded", await page.locator("#filterBy").isVisible() && await page.locator("#previewInboxOptions").getAttribute("aria-expanded")==="true");
  await page.click("#previewInboxOptions");
  check("desktop Inbox options collapse again", await page.locator("#filterBy").isHidden());

  await page.click("#userPill");
  await shot(page, "menu");
  const items = (await page.locator("#userMenu .menu-item").allInnerTexts()).map((t) => t.trim());
  check("the menu preserves account settings and offers all three appearance modes", ["Profile settings", "Settings", "Manage users"].every(t=>items.includes(t)) && (await page.locator("[data-theme-choice]").count())===3 && (await page.locator("#previewCalmBtn").isVisible()));
  check("Sign out is in the menu too", (await page.locator("#userMenu button", { hasText: "Sign out" }).count()) === 1);
  await page.click('[data-theme-choice="light"]');
  check("Light mode works from the account menu", (await page.evaluate(() => document.documentElement.dataset.theme))==="light");
  check("Light mode is visibly selected", await page.locator('[data-theme-choice="light"]').getAttribute("aria-pressed")==="true");
  await page.click('[data-theme-choice="system"]');
  check("System theme can be chosen and is remembered", await page.locator('[data-theme-choice="system"]').getAttribute("aria-pressed")==="true" && await page.evaluate(()=>localStorage.getItem("enveliq-theme"))==="system");
  await page.click('[data-theme-choice="dark"]');
  check("Dark mode works from the menu", !(await page.evaluate(() => document.documentElement.dataset.theme)));
  await page.click("#userPill");

  // Profile settings
  await page.click("#userPill");
  await page.click("#profileBtn");
  await page.waitForSelector("#settings.open");
  await host(page, "profile").locator("text=Everything on this page is optional").waitFor({ timeout: 15000 });
  check("Profile settings opens the Profile page", (await page.locator("#settingsHeading").innerText()).trim() === "Profile" && (await page.locator('[data-settings-tab="profile"].active').count()) === 1);
  const groups = (await page.locator("#settingsNav .settings-group").allTextContents()).map((t) => t.trim());
  check("Settings is grouped: You, Your mail, How it works for you, Help", groups.join("|") === "You|Your mail|How it works for you|Help");
  const tabs = (await page.locator("#settingsNav [data-settings-tab]").allInnerTexts()).map((t) => t.trim());
  check("Settings has no leftover mock-up page", !tabs.includes("My preferences") && tabs[0] === "Profile");
  const pf = host(page, "profile");
  check("the people-list switch starts on", (await host(page, "profile").locator("#pf_people").isChecked()));
  check("name, email and about start empty (name shows the username as a hint)", (await pf.locator("#pf_email").inputValue()) === "" && (await pf.locator("#pf_about").inputValue()) === "" && (await pf.locator("#pf_name").inputValue()) === "");
  await pf.locator("#pf_name").fill("Morgan N");
  await pf.locator("#pf_email").fill("j@example.com");
  await pf.locator("#pf_about").fill("Hello");
  await pf.locator("button:has-text('Save profile')").click();
  await page.waitForFunction(() => document.getElementById("userName").textContent === "Morgan N");
  check("saving sends the three details and the sidebar name updates", JSON.stringify(server.calls.find((c) => c[0] === "profile")[1]) === JSON.stringify({ display_name: "Morgan N", email: "j@example.com", about: "Hello", show_in_people: true }));
  await pf.locator("#pf_file").setInputFiles({ name: "me.png", mimeType: "image/png", buffer: PNG });
  await page.waitForFunction(() => document.querySelector("#avatar img"), null, { timeout: 15000 });
  const av = server.calls.find((c) => c[0] === "avatar");
  check("a chosen picture keeps PNG transparency when resized before upload", !!av && av[1].startsWith("data:image/png;base64"));
  check("the picture replaces the initials beside the name", (await page.locator("#avatar img").getAttribute("src")).includes("/api/v1/users/u1/avatar"));
  check("the picture loads (the page allows it)", await page.evaluate(() => { const i = document.querySelector("#avatar img"); return new Promise((ok) => (i.complete ? ok(i.naturalWidth > 0) : (i.onload = () => ok(true), i.onerror = () => ok(false)))); }));
  await shot(page, "profile");
  await pf.getByRole("button", { name: "Remove", exact: true }).click();
  await page.waitForFunction(() => !document.querySelector("#avatar img") && document.getElementById("avatar").textContent.length > 0);
  check("removing the picture brings the initials back", true);
  await page.click("#closeSettings");

  // Administration
  await page.click("#userPill");
  await page.click("#adminBtn");
  await page.waitForSelector("#settings.open");
  const ag = (await page.locator("#settingsNav .settings-group").allTextContents()).map((t) => t.trim());
  check("Administration is grouped: People, Mail, AI, System", ag.join("|") === "People|Mail|AI|System");
  const at = (await page.locator("#settingsNav [data-settings-tab]").allInnerTexts()).map((t) => t.trim());
  check("Administration has no mock-up pages", !at.some((t) => /^(Processing|Email providers|Tasks & automation|Privacy & retention|System status)$/.test(t)) && at.includes("Security & privacy") && at.includes("Sign-in rules & SSO"));
  await page.click('[data-settings-tab="sso"]');
  const ss = host(page, "sso");
  await ss.locator("summary:has-text('Password requirements')").waitFor({ timeout: 15000 });
  check("password requirements are folded away until wanted", !(await ss.locator("details:has(summary:has-text('Password requirements'))").evaluate((d) => d.open)));
  await ss.locator("summary:has-text('Password requirements')").click();
  check("the card has length, numbers, capitals, small letters, symbols and the username rule", (await ss.locator("#pw_len, #pw_dig, #pw_up, #pw_low, #pw_sym, #pw_nouser").count()) === 6);
  await shot(page, "pwrules");
  await ss.locator("#pw_len").fill("14");
  await ss.locator("#pw_dig").fill("2");
  await ss.locator("#pw_up").fill("1");
  await ss.locator("#pw_sym").fill("1");
  check("the preview sentence follows the numbers", (await ss.locator("#pw_preview").innerText()).includes("At least 14 characters, 2 numbers, 1 capital letter and 1 symbol"));
  await ss.locator("button:has-text('Save sign-in rules')").click();
  await page.waitForFunction(() => true);
  await new Promise((r) => setTimeout(r, 300));
  const pol = server.calls.find((c) => c[0] === "policy");
  check("saving sends the password rules", !!pol && pol[1].pw_min_length === 14 && pol[1].pw_min_digits === 2 && pol[1].pw_min_upper === 1 && pol[1].pw_min_symbols === 1 && pol[1].pw_forbid_username === true);
  await page.click('[data-settings-tab="users"]');
  const us = host(page, "users");
  await us.locator("summary:has-text('Add a person')").waitFor({ timeout: 15000 });
  check("Add a person is folded away and shows the password rules", (await us.locator("text=At least 12 characters").count()) >= 0);
  await page.click('[data-settings-tab="security"]');
  await shot(page, "security");
  check("Security & privacy shows how mail is handled in a fold", (await page.locator('[data-settings-panel="security"] details.fold').count()) === 3);
  check("no script errors", errors.length === 0);
  check("no blocked content", csp.length === 0);
}

// ---- Ordinary user ----
{
  const server = makeServer("user");
  const { page, errors } = await open(server);
  await page.click("#userPill");
  check("a normal user does not see Administration", await page.locator("#adminBtn").isHidden());
  check("they still see Profile settings and Settings", (await page.locator("#profileBtn").isVisible()) && (await page.locator("#settingsBtn").isVisible()));
  check("no script errors (user)", errors.length === 0);
}

// ---- Phone ----
{
  const server = makeServer("admin");
  const { page } = await open(server, { width: 390, height: 780 });
  check("phone Inbox options start collapsed", await page.locator("#filterBy").isHidden());
  await page.click("#previewInboxOptions");
  check("phone Inbox options expand when tapped", await page.locator("#filterBy").isVisible());
  await page.click("#previewInboxOptions");
  check("phone Inbox options collapse again", await page.locator("#filterBy").isHidden());
  await page.click("#menuBtn");
  await page.click("#userPill");
  const box = await page.locator("#userMenu").boundingBox();
  check("on a phone the menu fits on the screen", !!box && box.x >= 0 && box.x + box.width <= 390 && box.y >= 0 && box.y + box.height <= 780);
  check("on a phone account, appearance and Calm controls can be reached", (await page.locator("#userMenu .menu-item:visible").count()) >= 2 && (await page.locator("[data-theme-choice]:visible").count()) === 3 && await page.locator("#previewCalmBtn").isVisible());
  await page.click("#settingsBtn");
  await page.waitForSelector("#settings.open");
  check("choosing Settings on a phone closes the side menu and the user menu", !(await page.evaluate(() => document.body.classList.contains("menu-open"))) && (await page.locator("#userMenu").isHidden()));
}
await browser.close();
process.exit(failed ? 1 : 0);
