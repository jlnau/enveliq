## What changed
<!-- In plain words. One topic per pull request. -->

## Why
<!-- What problem does this solve, or what did the maintainer ask for? -->

## What to check
<!-- What should the reviewer look at, run or click? -->

## Checklist
- [ ] Nothing real in it: no real mail, names, addresses, keys, tokens or anything from `data/`. Test data uses `example.com`, `.invalid` or `.example`.
- [ ] Backend changes have tests in `tests/`, and `python -m pytest -q` passes.
- [ ] Page changes have a browser check in `scripts/check_*.mjs` (new ones are added to `.github/workflows/ci.yml`), and I looked at screenshots.
- [ ] Anything people can see has a README entry, a `docs/CHANGELOG.md` entry under "Unreleased" (no version bump: the maintainer does that at release time), and the matching `docs/*.md` guide updated. Changes to data, sign-in or privacy have a `SECURITY.md` entry.
- [ ] The privacy promises still hold: raw email and attachments are not stored, secrets are never sent back to the browser or logged, and one person's data is never visible to another.
- [ ] Wording that normal users see is plain and kind.
