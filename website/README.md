# The Enveliq website

A small static site for https://enveliq.app: a front page plus the guides, built from the files in `docs/` and `SECURITY.md`. It loads nothing from other websites. It runs two small scripts from the site itself. The guide search (`src/search.js`): a box on the guides pages opens `/search/`, which reads `/search-index.json` (built from the guides at build time) and lists matches in the visitor's browser. And the light or dark switch (`src/theme.js`): a button in the top bar that remembers the visitor's choice in their own browser (without it the site follows the device setting). Nothing is sent anywhere. Without scripts the search page says so and points to the list of guides. The security policy allows scripts from the site itself only (`script-src 'self'`).

## Build it on your own computer

```
cd website
npm install
npm run build     # writes the site into website/dist
npm run check     # every link and picture resolves, only the search runs a script, strict headers
```

Open `website/dist/index.html` in a browser, or serve the folder with `python -m http.server -d dist`.

## What lives where

- `src/home.html` is the front page. `src/style.css` is the only stylesheet. `src/images/` holds the pictures.
- `build.mjs` turns every guide into a page, builds the side menu, fixes links between guides and writes `_headers`, `robots.txt` and `sitemap.xml`.
- Edit a guide in `docs/` and the website follows. There is nothing to copy.

## Publish on Cloudflare (one time)

1. In Cloudflare, go to Workers & Pages, create a project and connect the GitHub repository.
2. Root directory `website`. Build command `npm install && npm run build`. Output directory `dist`.
3. Add the custom domain `enveliq.app`.

Each merge to `main` publishes again.

## Search engines

- Every page gets its own title, description, address (canonical), share picture and Twitter card. The share picture is `src/images/share.png` (1200 x 630).
- The front page carries data that tells search engines it is a free application. Guide pages carry a breadcrumb trail. These are inert JSON blocks, not scripts.
- Pages for people building Enveliq (see `NOINDEX` in `build.mjs`) stay on the site but are kept out of search results and the sitemap.
- Long titles are shortened in `SHORT_TITLE`. Descriptions are cut at a sentence or word, at most 160 characters.
- The sitemap adds "last changed" dates when the repository has real history. A shallow copy gives every page the same date, so the dates are left out then.
- `npm run check` fails if a page loses its title, description, canonical address, share tags or heading, or if the sitemap lists a hidden page.

## Light and dark, and the pictures

- The colours are set in `src/style.css` as two sets (dark, matching the app's night-sky look, and light). `src/theme.js` sets `data-theme` on the page before it is drawn.
- Every picture has a dark version and a light twin named `NAME-light.webp` (guide pictures: `NAME-light.png`). The build shows the right one automatically. A picture with no twin is shown in both themes.
- To retake all the pictures in the current design: `node scripts/retake_pictures.mjs <folder>` (runs the browser checks with made-up mail, once for dark and once for light), then `python scripts/place_pictures.py <folder>` puts them in `docs/images` and `website/src/images`.

## Also in the build

- `src/tour.html` is the screenshot tour at `/tour/`. Every screenshot uses made-up example mail. The "Be careful" pictures come from `TOUR=1 SHOTS=<dir> node scripts/check_scam_warning.mjs` (then saved as .webp).
- `src/favicon.ico` and the icons in `src/images/` (`apple-touch-icon.png`, `icon-192.png`, `icon-512.png`) are for browsers and phone home screens.
- `/.well-known/security.txt` points researchers at the private security report form. Its "Expires" date is set at each build, so publishing renews it.
- `node audit-contrast.mjs` (needs Playwright) checks text colour against its background in dark and light, on desktop and phone.

## Cloudflare settings that are not in the repository

- **www:** redirect `www.enveliq.app` to `enveliq.app` (Rules, then Redirect Rules, or a Bulk Redirect).
- **Visitor numbers:** use the domain's own Analytics page. Do not switch on "Web Analytics" for the Pages project, because it adds a script to every page, which this site's security policy blocks.
- **Search engines:** add the site to Google Search Console and Bing Webmaster Tools, verify with a DNS record, and submit `https://enveliq.app/sitemap.xml`.
