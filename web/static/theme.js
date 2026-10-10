// Applies the light/dark choice made in the Enveliq app (kept in this browser
// only). Runs before the page is drawn so there is no flash of the other theme.
try {
  if (localStorage.getItem("enveliq-theme") === "light") document.documentElement.setAttribute("data-theme", "light");
} catch (e) { /* storage unavailable: stay dark */ }
