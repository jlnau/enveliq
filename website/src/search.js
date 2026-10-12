(function () {
  var box = document.getElementById("results"), q = document.getElementById("q");
  if (!box || !q) return;
  var term = new URLSearchParams(location.search).get("q") || "";
  q.value = term;
  function esc(t) { return t.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  fetch("/search-index.json").then(function (r) { return r.json(); }).then(function (all) {
    var words = term.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) { box.innerHTML = "<p>Type a word above, such as <em>backup</em> or <em>passkey</em>.</p>"; return; }
    var hits = all.map(function (p) {
      var t = p.t.toLowerCase(), d = p.d.toLowerCase(), b = p.b.toLowerCase(), score = 0;
      for (var i = 0; i < words.length; i++) {
        var w = words[i];
        if (t.indexOf(w) < 0 && d.indexOf(w) < 0 && b.indexOf(w) < 0) return null;
        score += (t.indexOf(w) >= 0 ? 10 : 0) + (d.indexOf(w) >= 0 ? 4 : 0) + Math.min(b.split(w).length - 1, 5);
      }
      if (/^\/docs\/(changelog|version-history)\//.test(p.u)) score = Math.floor(score / 4);      // old release notes should not outrank the guides
      var at = b.indexOf(words[0]), from = Math.max(0, at - 60);
      return { p: p, score: score, snip: at < 0 ? p.d : (from ? "…" : "") + p.b.slice(from, from + 170) + "…" };
    }).filter(Boolean).sort(function (a, b) { return b.score - a.score; }).slice(0, 15);
    if (!hits.length) { box.innerHTML = "<p>Nothing found for <strong>" + esc(term) + "</strong>. Try a shorter word, or browse the <a href=\"/docs/\">list of guides</a>.</p>"; return; }
    box.innerHTML = "<p class=\"count\">" + hits.length + " guide" + (hits.length > 1 ? "s" : "") + " found</p><ol class=\"hits\">" + hits.map(function (h) {
      return "<li><a href=\"" + h.p.u + "\">" + esc(h.p.t) + "</a><p>" + esc(h.snip) + "</p></li>";
    }).join("") + "</ol>";
  }).catch(function () { box.innerHTML = "<p>Search could not load. Browse the <a href=\"/docs/\">list of guides</a> instead.</p>"; });
})();
