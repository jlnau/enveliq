// Preload for taking documentation pictures: node --import ./scripts/_shot_prefs.mjs scripts/check_x.mjs
// Sets the theme (THEME=dark|light) and Calm mode (CALM=0|1) in every browser the check opens, and hides the
// "page is not encrypted" notice that only appears because the checks run over plain http.
import { chromium } from "playwright";
const theme = process.env.THEME || "dark", calm = process.env.CALM || "0";
const orig = chromium.launch.bind(chromium);
chromium.launch = async (...a) => {
  const br = await orig(...a), nc = br.newContext.bind(br);
  br.newContext = async (o) => {
    const c = await nc(o);
    await c.addInitScript(([t, k]) => {
      try { localStorage.setItem("enveliq-theme", t); localStorage.setItem("enveliq-calm", k); localStorage.setItem("enveliq-welcome-seen", "1"); } catch {}
      document.addEventListener("DOMContentLoaded", () => { const s = document.createElement("style"); s.textContent = "#httpBanner,.demo-banner{display:none!important}"; document.head.appendChild(s); });
    }, [theme, calm]);
    return c;
  };
  return br;
};
