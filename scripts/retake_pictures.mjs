// Retake every picture used by the guides, the README and the website, in the current design.
// Runs the existing browser checks with SHOTS (made-up mail, no server) once per theme, then
// scripts/place_pictures.py copies the right ones into docs/images (dark, PNG) and website/src/images (dark and light, WebP).
// Usage: node scripts/retake_pictures.mjs <output folder>
import { spawn } from "node:child_process"; import fs from "node:fs"; import path from "node:path";
const out = path.resolve(process.argv[2] || "pictures");
const checks = ["check_shipping", "check_subscriptions", "check_trips", "check_snooze", "check_writehelp", "check_scam_warning", "check_link_check", "check_sender_check", "check_check_address", "check_backup", "check_search_everywhere", "check_email_features"];
const jobs = []; for (const theme of (process.env.THEMES || "dark,light").split(",")) for (const c of checks) jobs.push([theme, c]);
let next = 0, failed = 0;
async function worker() {
  while (next < jobs.length) {
    const [theme, c] = jobs[next++]; const dir = path.join(out, theme); fs.mkdirSync(dir, { recursive: true });
    await new Promise((res) => {
      const p = spawn("node", ["--import", "./scripts/_shot_prefs.mjs", `scripts/${c}.mjs`], { env: { ...process.env, THEME: theme, CALM: "0", TOUR: "1", SHOTS: dir }, stdio: "ignore" });
      p.on("exit", (code) => { console.log(`${code === 0 ? "ok  " : "FAIL"} ${theme} ${c}`); if (code) failed++; res(); });
    });
  }
}
await Promise.all([worker(), worker(), worker(), worker()]);
console.log(failed ? `${failed} check(s) failed` : "all pictures taken");
