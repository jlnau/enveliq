// Draws the two inbox backdrops (night for dark mode, morning for light mode) and prints the CSS that holds them.
// Usage: node scripts/make_backdrops.mjs > backdrops.css     (the result is pasted into prototype/index.html)
// They are plain SVG pictures drawn in code, so they stay sharp on any screen and need no image downloads.
const W = 1800, H = 600;
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const ridge = (base, amp, freqs, phase, fill, extra = "") => {
  const pts = []; for (let x = 0; x <= W; x += 15) { let y = base; freqs.forEach(([f, a], i) => { y += Math.sin(x / W * Math.PI * 2 * f + phase + i * 1.7) * amp * a; }); pts.push([x, y]); }
  return `<path d="${pts.map((p, i) => (i ? "L" : "M") + p[0] + " " + p[1].toFixed(1)).join(" ")} L${W} ${H} L0 ${H} Z" fill="${fill}" ${extra}/>`;
};
const stars = (n, op) => { seed = 11; let s = ""; for (let i = 0; i < n; i++) { const x = rnd() * W, y = rnd() * H * 0.45, r = 0.5 + rnd() * 1.1; s += `<circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="${r.toFixed(1)}" fill="#fff" opacity="${(op * (0.3 + rnd() * 0.7)).toFixed(2)}"/>`; } return s; };
const mist = (cy, color, op, rx = 460, ry = 26) => [250, 700, 1150, 1560].map((x, i) => `<ellipse cx="${x}" cy="${cy + (i % 2 ? 10 : -6)}" rx="${rx - i * 40}" ry="${ry}" fill="${color}" opacity="${op}" filter="url(#bl)"/>`).join("");
const defs = (extra) => `<defs><filter id="bl" x="-30%" y="-200%" width="160%" height="500%"><feGaussianBlur stdDeviation="16"/></filter>${extra}</defs>`;
const svg = (inner) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMin slice">${inner}</svg>`;
const MX = 1060;   // where the moon or sun sits (in the middle of the picture on a laptop, so it stays between the heading and the buttons)

const dark = svg(`${defs(`<linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#06122a"/><stop offset=".45" stop-color="#10305f"/><stop offset=".8" stop-color="#2a5a93"/><stop offset="1" stop-color="#4a7fae"/></linearGradient><radialGradient id="m"><stop offset="0" stop-color="#fff6dd" stop-opacity=".95"/><stop offset=".3" stop-color="#f6e2b8" stop-opacity=".3"/><stop offset="1" stop-color="#f6e2b8" stop-opacity="0"/></radialGradient>`)}
<rect width="${W}" height="${H}" fill="url(#s)"/>${stars(110, 0.8)}
<circle cx="${MX}" cy="105" r="190" fill="url(#m)"/><circle cx="${MX}" cy="105" r="30" fill="#fbf0d4"/><circle cx="${MX + 11}" cy="98" r="30" fill="#14376a" opacity=".16"/>
${ridge(262, 34, [[1.8, 1], [4.4, .5], [8, .22]], 0.4, "#2c5a8d", 'opacity=".75"')}${mist(285, "#b9d4f2", .22)}
${ridge(322, 30, [[2.2, 1], [5.1, .45], [9, .2]], 2.1, "#1c426f", 'opacity=".92"')}${mist(345, "#a6c6ec", .2, 520)}
${ridge(385, 26, [[1.6, 1], [3.9, .5], [7.8, .25]], 4.0, "#12305a")}${mist(405, "#8fb5e4", .16, 560)}
${ridge(450, 20, [[2.5, 1], [5.9, .4]], 1.0, "#0b2347")}`);
const light = svg(`${defs(`<linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cfe6ff"/><stop offset=".5" stop-color="#e6f1ff"/><stop offset=".82" stop-color="#fde9d4"/><stop offset="1" stop-color="#fbd9bd"/></linearGradient><radialGradient id="m"><stop offset="0" stop-color="#fff3d6" stop-opacity="1"/><stop offset=".3" stop-color="#ffe2b3" stop-opacity=".55"/><stop offset="1" stop-color="#ffe2b3" stop-opacity="0"/></radialGradient>`)}
<rect width="${W}" height="${H}" fill="url(#s)"/>
<circle cx="${MX}" cy="125" r="240" fill="url(#m)"/><circle cx="${MX}" cy="125" r="34" fill="#ffe8bd"/>
<g filter="url(#bl)" opacity=".55"><ellipse cx="380" cy="70" rx="150" ry="16" fill="#fff"/><ellipse cx="800" cy="40" rx="190" ry="14" fill="#fff"/></g>
${ridge(266, 34, [[1.8, 1], [4.4, .5], [8, .22]], 0.4, "#c3d8f2", 'opacity=".9"')}${mist(290, "#fff", .55)}
${ridge(326, 30, [[2.2, 1], [5.1, .45], [9, .2]], 2.1, "#a9c5ea", 'opacity=".95"')}${mist(350, "#fff", .5, 520)}
${ridge(390, 26, [[1.6, 1], [3.9, .5], [7.8, .25]], 4.0, "#8cb0e0")}${mist(410, "#fff", .4, 560)}
${ridge(455, 20, [[2.5, 1], [5.9, .4]], 1.0, "#6f9bd3")}`);
const uri = (s) => 'url("data:image/svg+xml,' + s.replace(/\n/g, "").replace(/\s{2,}/g, " ").replace(/"/g, "'").replace(/#/g, "%23").replace(/</g, "%3C").replace(/>/g, "%3E") + '")';
console.log(`:root{--backdrop:${uri(dark)}}\nhtml[data-theme="light"]{--backdrop:${uri(light)}}`);
