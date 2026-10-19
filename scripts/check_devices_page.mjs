// Browser check for the Your devices section on the Sign-in & security page.
// The pages are served from the real files; the server is pretended (Playwright intercepts requests).
//
// Usage (needs Playwright and a Chromium build):  node scripts/check_devices_page.mjs
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...p) => fs.readFileSync(path.join(root, ...p), "utf8");
const ORIGIN = "http://enveliq.test";
const CHALLENGE = "A".repeat(43);
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };

let devices = [
  { id: "d1", label: "This computer", signed_in_at: 1760000000, method: "password", remembered: false, current: true },
  { id: "d2", label: "Pixel phone", signed_in_at: 1760100000, method: "password", remembered: true, current: false },
];
let signedOut = null;
const handler = async (route) => {
  const req = route.request(), u = new URL(req.url()), p = u.pathname;
  const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (u.origin !== ORIGIN) return route.abort();
  if (p === "/account" || p === "/login") return route.fulfill({ status: 200, contentType: "text/html", body: read("web", "auth.html") });
  if (p.startsWith("/static/") && p.endsWith(".js")) return route.fulfill({ status: 200, contentType: "text/javascript", body: read("web", p) });
  if (p === "/static/auth.css") return route.fulfill({ status: 200, contentType: "text/css", body: read("web", "static", "auth.css") });
  if (p === "/api/v1/status") return json(200, { initialized: true, unlocked: true, setup_required: false, sign_in: { password: true, passkeys: false, remember: false, sso: { enabled: false, label: null } } });
  if (p === "/api/v1/me") return json(200, { id: "u1", username: "morgan", display_name: "Morgan", role: "user", session: { state: "full" }, security: { totp_enabled: false, passkeys: [], password_set: true, recovery_codes_left: 0 }, policy: {}, sso: { enabled: false } });
  if (p === "/api/v1/auth/devices" && req.method() === "GET") return json(200, { items: devices });
  if (p.startsWith("/api/v1/auth/devices/") && req.method() === "DELETE") { signedOut = p.split("/").pop(); devices = devices.filter(d => d.id !== signedOut); return route.fulfill({ status: 204, body: "" }); }
  return route.fulfill({ status: 404, body: "" });
};

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 390, height: 780 } })).newPage();
await page.route("**/*", handler);
await page.goto(`${ORIGIN}/account`);
await page.waitForSelector("#devices .item");
const text = await page.locator("#devices").innerText();
check("the section lists both devices", text.includes("This computer") && text.includes("Pixel phone"));
check("this device is marked and has no sign-out button", text.includes("(this one)") && (await page.locator("#devices .item").first().locator("button").count()) === 0);
await page.locator("#devices .item", { hasText: "Pixel phone" }).locator("button").click();
await page.waitForFunction(() => !document.querySelector("#devices").innerText.includes("Pixel phone"));
check("signing the other device out asks the server and removes it", signedOut === "d2");
check("no sideways scroll on a phone", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
await browser.close();
process.exit(failed ? 1 : 0);
