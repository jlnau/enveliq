// Browser check: a new install must be given a vault key. With none, the setup page explains how to make one and shows no setup form;
// with one, the setup form has no passphrase boxes. The pages are served from the real files; the server is pretended.
// Usage: node scripts/check_vault_key_setup.mjs   (SHOTS=<folder> saves screenshots)
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...p) => fs.readFileSync(path.join(root, ...p), "utf8");
const files = { "/setup": ["text/html", read("web", "auth.html")], "/static/auth.css": ["text/css", read("web", "static", "auth.css")], "/static/auth.js": ["text/javascript", read("web", "static", "auth.js")],
  "/static/welcome.js": ["text/javascript", read("web", "static", "welcome.js")], "/static/theme.js": ["text/javascript", read("web", "static", "theme.js")] };
const ORIGIN = "http://enveliq.test";
let failed = false;
const check = (label, good) => { console.log((good ? "✓ " : "✗ ") + label); if (!good) { failed = true; console.log("::error::" + label); } };
const shots = process.env.SHOTS; if (shots) fs.mkdirSync(shots, { recursive: true });
const b = await chromium.launch();

for (const [name, vp] of [["desktop", { width: 1100, height: 800 }], ["phone", { width: 390, height: 780 }]]) {
  for (const needed of [true, false]) {
    const p = await b.newPage({ viewport: vp }); const errors = [];
    p.on("pageerror", (e) => errors.push(String(e)));
    await p.route("**/*", (route) => {
      const u = new URL(route.request().url());
      if (u.origin !== ORIGIN) return route.fulfill({ status: 404, body: "" });
      if (u.pathname === "/api/v1/status") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ initialized: false, unlocked: false, setup_required: true, auto_unlock: !needed, auto_unlock_problem: null, vault_key_needed: needed, sign_in: { password: true, passkeys: true, sso: { enabled: false, label: null } } }) });
      const f = files[u.pathname]; if (f) return route.fulfill({ status: 200, contentType: f[0], body: f[1] });
      return route.fulfill({ status: 404, body: "" });
    });
    await p.goto(ORIGIN + "/setup"); await p.waitForTimeout(500);
    const text = await p.locator("main").innerText(); const tag = `${name}, ${needed ? "no key yet" : "key given"}`;
    if (needed) {
      check(`${tag}: it says a vault key is needed first`, text.includes("a vault key") && text.includes("openssl rand -hex 32") && text.includes("ENVELIQ_VAULT_KEY=") && text.includes("docker compose up -d"));
      check(`${tag}: it says to save a copy somewhere safe`, text.includes("Save a copy in your password manager"));
      check(`${tag}: there is no setup form to fill in`, (await p.locator("form").count()) === 0);
    } else {
      check(`${tag}: the setup form asks for no passphrase`, (await p.locator("#passphrase").count()) === 0 && (await p.locator("#username").count()) === 1 && text.includes("Enveliq unlocks itself"));
    }
    check(`${tag}: no sideways scrolling`, await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    check(`${tag}: no script errors`, errors.length === 0);
    if (shots) await p.screenshot({ path: path.join(shots, `vault-key-${name}-${needed ? "needed" : "given"}.png`), fullPage: true });
    await p.close();
  }
}
await b.close();
process.exit(failed ? 1 : 0);
