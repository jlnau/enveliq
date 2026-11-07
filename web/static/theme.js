// Applies the light/dark choice made in the Enveliq app (kept in this browser
// only). Runs before the page is drawn so there is no flash of the other theme.
try {
  var c = localStorage.getItem("enveliq-theme");
  if (c === "light" || (c === "system" && matchMedia("(prefers-color-scheme: light)").matches)) document.documentElement.setAttribute("data-theme", "light");
} catch (e) { /* storage unavailable: stay dark */ }
// The dark colour scheme and the highlight colour chosen in Customise (also kept in this browser only).
try {
  var v = JSON.parse(localStorage.getItem("enveliq-view") || "null");
  if (v) {
    var sl = matchMedia("(prefers-color-scheme: light)").matches;
    if (v.scheme === "dark" || (v.scheme === "system" && !sl)) document.documentElement.setAttribute("data-scheme", "dark");
    if (v.scheme && v.scheme !== "standard" && /^(green|purple|orange|pink|teal)$/.test(v.highlight)) document.documentElement.setAttribute("data-hl", v.highlight);
  }
} catch (e) { /* storage unavailable: stay standard */ }
