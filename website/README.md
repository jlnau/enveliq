# The Enveliq website

A small static site for https://enveliq.app: a front page plus the guides, built from the files in `docs/` and `SECURITY.md`. It ships no scripts and loads nothing from other websites.

## Build it on your own computer

```
cd website
npm install
npm run build     # writes the site into website/dist
npm run check     # every link and picture resolves, no scripts, strict headers
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
