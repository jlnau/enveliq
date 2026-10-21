// Browser check for the one list look: every page under Settings and Administration opens from its list, every row opens a page
// with a blue back link, nothing is drawn the old way (cards of boxes, tables, folded channel cards), a switch is always a switch,
// the pages fit a phone, and the buttons that finish a form stay at the bottom of a phone screen. Light and dark. The server is pretended.
//
// Usage (needs Playwright and a Chromium build):
//   node scripts/check_settings_list.mjs        (SHOTS=<dir> also saves a picture of every page)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "..");
const html = fs.readFileSync(path.join(root, "prototype", "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "static", "auth.css"), "utf8");
const embed = ["welcome.js", "auth.js"].map((n) => fs.readFileSync(path.join(root, "web", "static", n), "utf8")).join("\n");
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };

const unknown = [];
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname, m = req.method();
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.fulfill({ status: 200, contentType: "text/html", body: "<title>elsewhere</title>" });
  if (p === "/") return route.fulfill({ status: 200, contentType: "text/html", body: html });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
  if (p === "/embed.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: embed });
  if (m !== "GET") return json(200, {});
  const api = p.replace("/api/v1", "");
  const D = {
    "/status": { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } },
    "/system": { cipher: "AES-256-GCM", kdf: "Argon2id", idle_lock_seconds: 900 },
    "/me": { id: "u1", username: "morgan", display_name: "Morgan", role: "admin", email: "morgan@example.com", session: { state: "full" }, security: { totp_enabled: true, password_set: true, recovery_codes_left: 8, passkeys: [{ id: "k1", name: "Pixel phone", created_at: 1759000000 }] }, source: "local" },
    "/accounts": [{ id: "a1", provider: "proton", auth_method: "proton_bridge", owner_user_id: "u1", display_name: "Proton", email_address: "morgan@example.com", server: "172.30.0.1", port: 1144, username: "morgan", settings: {} }, { id: "a2", provider: "gmail", auth_method: "app_password", owner_user_id: "u1", display_name: "Gmail", email_address: "morgan@gmail.example", server: "imap.gmail.com", port: 993, username: "morgan", settings: { color: "#c8453c" } }],
    "/admin/users": [{ id: "u1", username: "morgan", display_name: "Morgan", role: "admin", source: "local", disabled: false, security: { totp_enabled: true, passkeys: [] } }],
    "/admin/auth-policy": { require_mfa: "admins", password_login: "everyone", min_length: 12, require_number: true, require_upper: true, require_lower: false, require_symbol: false, pw_min_length: 12, pw_min_digits: 1, pw_min_upper: 1, pw_min_lower: 0, pw_min_symbols: 0, pw_forbid_username: true },
    "/admin/sso": { enabled: false, label: "Sign in", issuer: "", client_id: "", scopes: "openid", auto_create: true, allowed_groups: [], admin_groups: [], groups_claim: "groups", username_claim: "preferred_username", has_secret: false },
    "/me/preferences": { keep_reviewed: true, keep_archived: true, keep_days: 7, max_days: 14, instructions: "", undo_send_seconds: 10 },
    "/me/features": { effective: { find_mail: true }, admin: { compose: true, find_mail: true, sent: true, media: true, messages: true }, user: { compose: true, find_mail: true, sent: true, media: true, messages: true }, labels: { compose: "New email", find_mail: "Find any email (search all your mail)", sent: "Sent (last 4 months)", media: "Pictures and attachment previews", messages: "Messages (write to the other people here)" } },
    "/admin/features": { flags: { compose: true, find_mail: true, sent: true, media: true, messages: true }, labels: { compose: "New email", find_mail: "Find any email (search all your mail)", sent: "Sent (last 4 months)", media: "Pictures and attachment previews", messages: "Messages (write to the other people here)" } },
    "/admin/backups": { backups: [], settings: { daily: false, keep_days: 7 }, folder: "backups", last_error: null, max_keep_days: 60, confirm_word: "RESTORE" },
    "/sync/status": { minutes: 5, editable: true },
    "/admin/review-settings": { max_days: 14, instructions: "" },
    "/find/fast": { mailboxes: [] },
    "/admin/notifications": { labels: { ntfy: "ntfy", gotify: "Gotify", homeassistant: "Home Assistant", telegram: "Telegram" }, channels: { ntfy: true, gotify: true, homeassistant: true, telegram: false }, local_hosts: ["192.168.1.0/24"], from_environment: [] },
    "/admin/google": { enabled: false, redirect_uri: "https://enveliq.example.com/api/v1/me/sync/google/callback", client_id: "", client_secret_set: false },
    "/admin/agent": { mode: "plain", who: "all", name: "Agent", url: "", model: "", has_key: false },
    "/admin/check-address": { accounts: [{ id: "a1", email: "check@example.com", name: "Check" }], account_id: null, allowed: ["alex@example.com"], set_elsewhere: false, automatic_sync_on: true, last: null },
    "/admin/attachment-ai": { enabled: true, cloud: false },
    "/admin/ai-prompt": { in_use: false, default: "You write short, calm summaries of emails for a busy family. Say what the email is, what is asked of the reader, and any date or amount.", custom: "", fixed: "Reply only as JSON with the fields summary, category, priority and suggested_task.", min: 100, max: 4000 },
    "/ai/config": { provider: "custom", url: "http://192.168.1.20:11434/v1/chat/completions", model: "llama3.1:8b", has_key: false, source: "saved" },
    "/ai/providers": [{ id: "custom", label: "Other server on my network", cloud: false, url_example: "http://192.168.1.20:11434/v1/chat/completions", model_example: "llama3.1:8b", steps: [] }, { id: "anthropic", label: "Claude (Anthropic)", cloud: true, company: "Anthropic", url: "https://api.anthropic.com/v1/messages", key_url: "https://console.anthropic.com/", models_url: "https://docs.anthropic.com/", model_example: "claude-sonnet-5-5", steps: [] }],
    "/admin/reporting": { enabled: false, kind: "none", url: "", has_token: false, interval: 60, sinks: {} },
    "/me/important": { items: [{ address: "beth@example.com", name: "Beth Harris" }, { address: "school@example.org", name: "Town Primary School" }] },
    "/me/saved": { signature: "Thanks, Morgan", replies: [{ id: "r0000000000000001", title: "On my way", text: "Thanks, I'm on my way." }], limits: { signature: 1000, replies: 30, title: 60, text: 3000 } },
    "/me/rules": { rules: [{ id: "u0000000000000001", sender: "news@example.com", subject: "", action: "archived" }], actions: { archived: "Archive it", reviewed: "Mark it reviewed" }, max: 50 },
    "/me/notifications": { settings: { quiet_from: "22:00", quiet_to: "07:00", enabled: true }, tz: "Australia/Sydney", channels: [{ id: "browser", label: "This device (browser)", blurb: "A pop-up on this phone or computer, even when Enveliq is closed.", steps: ["Press Turn on for this device."], fields: [], enabled: false, allowed: true, configured: false, last_ok: null, last_error: null, devices: [] }] },
    "/me/sync": { feed: { on: false }, google: { available: true, connected: false, enabled: false }, titles: true, caldav: { configured: false, enabled: false }, todo: { configured: false, enabled: false } },
    "/ai/status": { configured: true, model: "llama3.1:8b" },
    "/mail/providers": [{ id: "proton", label: "Proton Mail", blurb: "Through Proton Bridge", kind: "bridge", status: "ready" }],
    "/admin/microsoft": { enabled: false, client_id: "", tenant: "common", has_secret: false, redirect_uri: "https://enveliq.example.com/api/v1/mail/microsoft/callback", ready: false },
    "/admin/update-notice": { enabled: true, current: "0.94", update: null },
    "/me/write-help": { available: true, enabled: true, instructions: "" },
  };
  D["/sync/status"] = { enabled: true, minutes: 5, editable: true, accounts: { a1: { ok: true, at: Date.now() / 1000 - 120, added: 0 }, a2: { ok: true, at: Date.now() / 1000 - 300, added: 2 } } };
  D["/me/away"] = { enabled: true, start: "2026-11-02", end: "2026-11-13", body: "Thank you for your email. I am away until 13 November and will reply when I am back.", state: "scheduled", answered: 0, limits: { body: 2000 }, today: "2026-10-21" };
  D["/auth/devices"] = { items: [{ id: "d1", label: "Chrome on Windows", current: true, signed_in_at: 1760000000 }, { id: "d2", label: "Pixel phone", signed_in_at: 1759000000 }] };
  D["/me/muted"] = { items: [{ id: "m1", subject: "Re: Netball roster", muted_at: 1760000000, count: 3 }, { id: "m2", subject: "School trip forms", muted_at: 1759000000, count: 0 }], max: 300 };
  D["/me/features"].effective.address_book = true; D["/me/features"].admin.address_book = true; D["/me/features"].user.address_book = true; D["/me/features"].user.address_book_auto = true;
  D["/me/contacts"] = { total: 3, items: [{ name: "Beth Harris", address: "beth@example.com", count: 12 }, { name: "", address: "school@example.org", count: 0 }, { name: "Alex Moore", address: "alex@example.net", count: 2 }] };
  D["/admin/reporting"] = {"config": {"instance": "enveliq", "label_mode": "id", "categories": {"activity": true, "security": true}, "prometheus": {"enabled": false, "has_token": false}, "logs": {"enabled": false}, "loki": {"enabled": false, "url": "", "auth": "none", "username": "", "has_secret": false, "tenant": "", "labels": {}}, "webhook": {"enabled": false, "url": "", "has_secret": false}, "otlp": {"enabled": false, "url": "", "auth": "none", "username": "", "has_secret": false, "interval": 60}, "grafana": {"enabled": false, "url": "", "has_secret": false, "folder": "Enveliq", "prometheus_uid": "", "loki_uid": "", "annotations": true, "dashboard_url": ""}}, "status": {"logs": {"sent": 0, "last_ok": null, "last_error": null, "dropped": 0}, "loki": {"sent": 0, "last_ok": null, "last_error": null, "dropped": 0}, "webhook": {"sent": 0, "last_ok": null, "last_error": null, "dropped": 0}, "otlp": {"sent": 0, "last_ok": null, "last_error": null, "dropped": 0}, "grafana": {"sent": 0, "last_ok": null, "last_error": null, "dropped": 0}, "dashboard": {"sent": 0, "last_ok": null, "last_error": null, "dropped": 0}}, "mailboxes": [{"label": "mailbox-1", "name": "Proton"}], "metrics_path": "/metrics", "allowed_hosts_set": false};
  if (api in D) return json(200, D[api]);
  unknown.push(api);
  return json(404, { detail: "not found" });
};


const browser = await chromium.launch();
const LANDINGS = [["settings", "account"], ["settings", "people"], ["settings", "rules"], ["settings", "alerts"], ["admin", "sync"], ["admin", "llm"], ["admin", "adminbackup"]].filter(([, t]) => !process.env.ONLY || process.env.ONLY.split(",").includes(t));
const SINGLES = [["settings", "accounts"], ["settings", "general"], ["settings", "setup"], ["admin", "users"], ["admin", "adminfeatures"], ["admin", "adminreminders"]].filter(([, t]) => !process.env.ONLY || process.env.ONLY.split(",").includes(t));
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, name + ".png") }); };

// What is on the page the person can see right now: the title, how many rows, and anything drawn the old way.
const look = (page) => page.evaluate(() => {
  const host = [...document.querySelectorAll(".embed-host")].find((h) => h.offsetParent && h.shadowRoot);
  if (!host) return null;
  const r = host.shadowRoot, vis = (e) => e && e.getClientRects().length > 0;
  const scope = [...r.querySelectorAll(".ios-pane, .ios-list")].find(vis) || r;
  return {
    title: (scope.querySelector("h1") || {}).textContent || "",
    rows: [...scope.querySelectorAll(".li")].filter(vis).length,
    go: [...scope.querySelectorAll(".li.go")].filter(vis).length,
    back: !!([...scope.querySelectorAll(".back")].find(vis)),
    old: [...r.querySelectorAll("details.chan, table.table, label.check, .featgrid, .grid2 .field, .avatar-edit, section.section > h2")].filter(vis).length,
    oldWhat: [...r.querySelectorAll("details.chan, table.table, label.check, .featgrid, .grid2 .field, .avatar-edit, section.section > h2")].filter(vis).map((e) => e.outerHTML.slice(0, 160)),
    plainSave: [...scope.querySelectorAll("button.btn")].filter(vis).length,
    sideways: document.querySelector("#settings").scrollWidth > document.querySelector("#settings").clientWidth + 2,
    ios: !!r.querySelector(".ios"),
  };
});
const clickRow = (page, index) => page.evaluate((i) => {
  const host = [...document.querySelectorAll(".embed-host")].find((h) => h.offsetParent && h.shadowRoot);
  const scope = [...host.shadowRoot.querySelectorAll(".ios-pane, .ios-list")].find((e) => e.getClientRects().length) || host.shadowRoot;
  const rows = [...scope.querySelectorAll(".li.go")].filter((e) => e.getClientRects().length);
  if (!rows[i]) return null;
  const name = rows[i].textContent.trim().slice(0, 40); rows[i].click(); return name;
}, index);
const clickBack = (page) => page.evaluate(() => {
  const host = [...document.querySelectorAll(".embed-host")].find((h) => h.offsetParent && h.shadowRoot);
  const b = [...host.shadowRoot.querySelectorAll(".back")].find((e) => e.getClientRects().length); if (b) b.click(); return !!b;
});

for (const theme of ["dark", "light"]) for (const width of [1200, 390]) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  await context.addInitScript((t) => { try { localStorage.setItem("enveliq-welcome-seen", "1"); localStorage.setItem("enveliq-theme", t); } catch (e) {} }, theme);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await context.route("**/*", handler);
  await page.goto(`${ORIGIN}/`);
  await page.waitForTimeout(700);
  if (theme === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  const open = async (mode, tab) => {
    await page.evaluate((m) => openSettings(m), mode);
    await page.waitForTimeout(250);
    await page.evaluate((t) => document.querySelector(`#settingsNav [data-settings-tab~="${t}"]`).click(), tab);
    await page.waitForTimeout(1400);
  };
  const L = `${theme} ${width}px`;
  for (const [mode, tab] of LANDINGS) {
    await open(mode, tab);
    const top = await look(page);
    check(`${L} ${tab}: the list has a title and rows that open pages`, !!top && top.ios && top.title.length > 0 && top.go >= 2 && !top.back);
    await shot(page, `list-${tab}-${theme}-${width}`);
    for (let i = 0; i < (top ? top.go : 0); i++) {
      const name = await clickRow(page, i);
      await page.waitForTimeout(1300);
      const inner = await look(page);
      if (inner && inner.old) console.log("   OLD", name, JSON.stringify(inner.oldWhat));
      check(`${L} ${tab} > ${name}: opens with a title and a back link, nothing drawn the old way`, !!inner && inner.ios && inner.title.length > 0 && inner.back && inner.old === 0 && !inner.sideways);
      if (inner && width === 1200 && i === 0) await shot(page, `list-${tab}-${i}-${theme}-${width}`);
      // a row that opens one more level (a drill) is followed once, then we come back
      if (inner && inner.go > 0 && inner.back) {
        const deeper = await clickRow(page, 0);
        await page.waitForTimeout(900);
        const d2 = await look(page);
        check(`${L} ${tab} > ${name} > ${deeper}: opens`, !!d2 && d2.title.length > 0 && d2.back && d2.old === 0);
        await clickBack(page); await page.waitForTimeout(500);
      }
      if (!(await clickBack(page))) break;
      await page.waitForTimeout(900);
    }
  }
  for (const [mode, tab] of SINGLES) {
    await open(mode, tab);
    const v = await look(page);
    check(`${L} ${tab}: one list, a title, nothing drawn the old way, nothing sideways`, !!v && v.ios && v.title.length > 0 && v.old === 0 && !v.sideways);
    await shot(page, `single-${tab}-${theme}-${width}`);
  }
  // every tick box is a switch
  await open("settings", "general");
  const sw = await page.evaluate(() => { const h = [...document.querySelectorAll(".embed-host")].find((x) => x.offsetParent && x.shadowRoot); return [...h.shadowRoot.querySelectorAll("input[type=checkbox]")].every((c) => getComputedStyle(c).appearance === "none" && (!c.offsetParent || c.offsetWidth >= 40)); });
  check(`${L}: every tick box is drawn as a switch`, sw);
  // on a phone the buttons that finish a form stay at the bottom of the screen
  if (width === 390) {
    await open("settings", "people");
    await page.evaluate(() => { const h = [...document.querySelectorAll(".embed-host")].find((x) => x.offsetParent && x.shadowRoot); [...h.shadowRoot.querySelectorAll(".li.go")].find((e) => /Signature/.test(e.textContent)).click(); });
    await page.waitForTimeout(1300);
    await page.evaluate(() => { const h = [...document.querySelectorAll(".embed-host")].find((x) => x.offsetParent && x.shadowRoot); [...h.shadowRoot.querySelectorAll(".li")].find((e) => /Add a saved reply/.test(e.textContent)).click(); });
    await page.waitForTimeout(900);
    const act = await page.evaluate(() => {
      const h = [...document.querySelectorAll(".embed-host")].find((x) => x.offsetParent && x.shadowRoot);
      const g = [...h.shadowRoot.querySelectorAll(".grp-wrap.act")].find((e) => e.getClientRects().length);
      if (!g) return null;
      const r = g.getBoundingClientRect(); return { bottom: r.bottom, height: innerHeight, sticky: getComputedStyle(g).position };
    });
    check(`${L}: the Save button of a form is fixed at the bottom of the phone screen`, !!act && act.sticky === "sticky" && act.bottom <= act.height + 1);
    await shot(page, `phone-form-${theme}`);
  }
  check(`${L}: no script errors`, errors.length === 0);
  if (errors.length) console.log("   " + errors.join(" | ").slice(0, 300));
  await context.close();
}
await browser.close();
if (unknown.length) console.log("note: not pretended:", [...new Set(unknown)].join(", "));
if (failed) process.exit(1);
console.log("The one list look holds on every Settings and Administration page.");
