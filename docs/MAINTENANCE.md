# Looking after Enveliq (for the maintainer)

Enveliq is built on other people's software: the Python it runs on, the packages it uses, the Docker images, and the tools that build and host it. Those get security fixes over time. This page is the routine for keeping up with them, so Enveliq is not left alone until something breaks.

Nothing here changes anything on your server by itself. An update only reaches your household when you merge it, publish a release and press **Redeploy** in Arcane.

## What Enveliq relies on

| What | Where it comes from | How it gets updated |
| --- | --- | --- |
| The database | SQLite, one encrypted file (`vault.sqlite3`) read by the Python inside the Enveliq container. There is no separate database server. | With the Python base image, when the image is rebuilt. |
| Python and the base image | `python:3.13-slim` in `Dockerfile` and `Dockerfile.render` | Dependabot proposes newer images. Rebuilding also picks up fixes inside the same tag. |
| Python packages (FastAPI, cryptography and so on) | `requirements.txt`, every version pinned | Dependabot proposes updates weekly. |
| The PDF viewer container | `Dockerfile.render` (poppler) | Rebuilt with each release. |
| GitHub Actions that build and test | `.github/workflows/` | Dependabot proposes updates weekly. |
| The website's one package (`marked`) | `website/package.json` | Updated by hand when its advisory list changes. |
| Arcane, Docker and the host system | Your server | Updated on the host, not by Enveliq. |
| Proton Bridge, Microsoft, your AI provider | Outside services | Their own updates; Enveliq only changes if they change how they work. |

## The routine

**Every week (about 5 minutes).** Open the pull requests list. Dependabot may have opened one pull request called something like "python-small-updates". If its checks are green, read what changed and fold it into the current version pull request (or merge it into the branch). Anything GitHub marks as a **security** update goes first. A major version jump (for example 2.x to 3.x) comes as its own pull request: leave it until you have time to test it on the preview.

**With each release.** After publishing the release and redeploying, look at Administration, **Updates** and **Reporting** to confirm the new version is running and nothing is reporting errors.

**Every month.**
- Rebuild and redeploy even if no version changed, so fixes inside the base image arrive.
- Check that a backup actually restores: use Administration, **Backup and restore** on a spare copy and open it.
- Look at the repository's **Security** tab for open alerts (see below).

**Twice a year.**
- Update Arcane, Docker and the host operating system.
- Look at what is reachable from the internet (the public address, Cloudflare, Arcane) and remove anything you no longer use.
- Replace keys and tokens you have shared with other services, such as the AI key or API tokens.

**When someone reports a bug.** It goes into the current version pull request. A security problem goes first, and is released on its own if it cannot wait.

## Turn on GitHub's security alerts (one time)

Dependabot already proposes *updates* every week, but it only *warns you about a known vulnerability* if these are switched on. They are free. In the repository, open **Settings, Advanced Security** (or **Code security**) and switch on:

1. **Dependency graph**
2. **Dependabot alerts** (a warning when a package you use has a known security hole)
3. **Dependabot security updates** (it opens a pull request that fixes it)
4. **Secret scanning** and **Push protection** (stops a password or key being committed by accident)

Then, under your profile's notification settings, keep email on for "Dependabot alerts" so the warning reaches you.

## Pinning the build tools (why and how)

The checks workflow (`ci.yml`) names each GitHub Action by its exact version code, like `actions/checkout@3d3c42e…`. The preview workflow (`build-ui-preview.yml`) names them by a loose tag, like `docker/login-action@v3`. A tag can be moved by whoever owns that tool, so if the tool were ever tampered with, the preview build, which signs in to your container registry and pushes images, would run the changed version. An exact code cannot be moved. The fix is to give the preview workflow exact codes like the checks workflow has. Dependabot already knows how to keep exact codes up to date, so once they are in, they update themselves through the weekly pull request.

## If something looks wrong

- A package has a published security advisory: update it first, release, redeploy.
- A site or key may have been exposed: replace the key, redeploy, and tell the people it affects.
- Enveliq will not start after an update: redeploy the previous image in Arcane, then fix forward in the next version.
