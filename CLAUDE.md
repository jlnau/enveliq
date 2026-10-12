# CLAUDE.md

Project: **Enveliq** ("Turn email into clarity."), a private, self-hosted email-review app for a household, run in Docker. Backend: FastAPI in `backend/` (mail in `backend/mail/`, sign-in in `backend/auth/`). Main page: `prototype/index.html`. Settings and Administration pages: `web/auth.html`, `web/static/auth.js`, `auth.css`. Everything a normal user sees must be calm, plain and friendly.

## Read first
- `README.md` (what exists) and `SECURITY.md` (what Enveliq promises and how)
- `docs/ARCHITECTURE.md`, then the guide for whatever area you touch (`docs/*.md`)
- `docs/CHANGELOG.md` (the change log, newest first)

## Non-negotiables
- Raw email bodies and attachments are never stored. Only encrypted summaries and structured results are kept, inside the encrypted vault. Secrets (passwords, tokens, API keys) are write-only from the browser: never sent back, never logged.
- One person's data is never visible to another person. The server decides who may read, from the signed-in session; the page never gets to choose. Administrators run Enveliq; they do not read other people's mail or messages. A record you may not open answers "not found".
- Email text is untrusted input. The AI is told to treat it as data, gets no tools, and never calculates or decides. Anything an AI wrote is labelled as such.
- Strict Content-Security-Policy and no third-party requests when a page is viewed. No inline secrets, no remote fonts or scripts.
- Passwords use Argon2id; sign-in rules (two-factor, passkeys, single sign-on, password requirements) are enforced on the server, never only in the page.
- Test data is synthetic: use example domains (`example.com`, `.invalid`, `.example`) and private-range addresses like `192.168.1.x`. Never commit real mail, addresses, keys or tokens. Never commit anything from `data/`.
- Wording for normal users is plain and kind, with no jargon. Administration may be more technical. Long or rarely used options fold away behind a "Show" fold.

## Working rules
- Do not change the version number. Leave `backend/version.py` and "Current version" in `README.md` alone, and do not put a version number in pull request titles. The maintainer bumps the version once, right before a release.
- Every change people can see must be documented in the matching `docs/*.md` guide, and in `SECURITY.md` when it touches data, sign-in or privacy. Describe the user-visible change clearly in the pull request so release notes can be generated from merged pull requests. Do not edit the README recent-changes list or the shared `docs/CHANGELOG.md` Unreleased section in ordinary feature pull requests. Those shared release summaries are updated together when preparing a release. Update other README sections only when needed to keep existing instructions factually correct.
- Write backend tests for backend changes (`tests/`). Write or update a browser check (`scripts/check_*.mjs`) for page changes, and add new ones to `.github/workflows/ci.yml`.
- Do not invent requirements, options or behaviour that was not asked for. Do not remove features while tidying; move or fold them.

## Branches and pull requests
- Never push to `main`. Work on a feature branch (`feat/...`, `fix/...`, `docs/...`, `chore/...`) and open a pull request into `main`. The maintainer reviews and merges.
- One topic per pull request. The description says what changed, why, and what to check, in plain words.
- When the maintainer requests several independent changes, create one independent branch and pull request per change. Fetch the latest remote `main` before creating EACH branch, and base each branch directly on that commit; never branch from another feature branch unless the maintainer explicitly asks for dependent changes. Do not mix the changes into one branch.
- Parallel pull requests are expected. Keep each PR limited to files needed for that feature and its targeted tests and guide. Shared application files may legitimately overlap; do not suppress necessary changes just to avoid conflicts. Before declaring a PR ready, fetch the latest `main`, check whether the PR is mergeable, and update it safely if required. Never force-push, discard others' changes or blindly accept one side of a conflict.
- A passing CI result alone does not establish merge readiness. Check that the PR is conflict-free, its required checks are passing against the current base, and any merge-queue requirements are satisfied. After another PR merges, remaining open PRs may need a fresh check or safe integration with the new `main`.
- If more than one PR changes the same code, coordinate their integration and rerun all relevant tests; some semantic conflicts cannot be prevented by documentation conventions or automation.

- Merging into `main` publishes nothing. Images are built and published only when the maintainer publishes a GitHub Release whose tag (for example `v0.86`) matches `backend/version.py`, and only after every check passes.
- When asked to prepare a release: set `backend/version.py` and "Current version" in `README.md` to the new number, and rename the "Unreleased" heading in `docs/CHANGELOG.md` to that version and today's date. Nothing else.

## Before opening a pull request, run and pass
- `python -m pytest -q` (needs `requirements-dev.txt`)
- `node scripts/check_*.mjs` for every page you changed (the full list is in `.github/workflows/ci.yml`), plus `node --check web/static/auth.js` after editing it
- `scripts/run_signin_e2e.sh`, `python scripts/mailbox_e2e.py` and `python scripts/welcome_e2e.py` when sign-in, Settings, Administration or setup pages changed (they need the full dev requirements and Playwright)
- Look at screenshots of any page you changed (`SHOTS=<dir> node scripts/check_...mjs`) before saying it looks right

Personal and deployment-specific rules live in `CLAUDE.local.md`, which is not committed.
