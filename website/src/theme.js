(function () {
  var d = document.documentElement, key = "enveliq-site-theme", saved = null;
  try { saved = localStorage.getItem(key); } catch (e) {}
  if (saved !== "light" && saved !== "dark") saved = null;
  var mq = window.matchMedia ? matchMedia("(prefers-color-scheme: light)") : null;
  function current() { return saved || (mq && mq.matches ? "light" : "dark"); }
  function apply() { d.setAttribute("data-theme", current()); }
  apply();
  document.addEventListener("DOMContentLoaded", function () {
    var b = document.getElementById("themeToggle");
    if (!b) return;
    b.hidden = false;
    function label() {
      var light = current() === "light";
      b.setAttribute("aria-label", light ? "Switch to dark mode" : "Switch to light mode");
      b.title = light ? "Switch to dark mode" : "Switch to light mode";
    }
    label();
    b.addEventListener("click", function () {
      saved = current() === "light" ? "dark" : "light";
      try { localStorage.setItem(key, saved); } catch (e) {}
      apply(); label();
    });
    if (mq && mq.addEventListener) mq.addEventListener("change", function () { if (!saved) { apply(); label(); } });
  });
})();
