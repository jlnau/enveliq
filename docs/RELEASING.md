# Making a release (for the maintainer)

Merging a pull request into `main` publishes nothing. Enveliq's images are built and published only when you publish a **GitHub Release**. Several merged pull requests can go out together as one release.

GitHub has no built-in "release template" that pre-fills the form. What it does have is the **Generate release notes** button, which fills in the description from the pull requests merged since the last release. This repository sets that up in `.github/release.yml`. The text to paste into the title and description is below.

## Before you click "Create a new release"

1. Everything you want in this release is merged, and the checks on `main` are green.
2. Ask Claude: "prepare release v0.86" (use the next number). It opens a pull request that does only three things: sets `backend/version.py`, sets "Current version" in `README.md`, and renames "Unreleased" in `docs/CHANGELOG.md` to that version and today's date.
3. You review and merge that pull request. The version in `backend/version.py` is now the number you will tag.

## Create the release

1. On the repository's front page, press **Create a new release** (right-hand side, under "Releases").
2. **Choose a tag:** type the version with a `v` in front, for example `v0.86`, then choose **Create new tag: v0.86 on publish**. The tag must match `backend/version.py` exactly, or the publish step stops on purpose.
3. **Target:** leave it on `main`.
4. **Release title:** `Enveliq v0.86` (same number as the tag).
5. **Description:** press **Generate release notes**, then add the two short parts from the template below at the top. (On the very first release the button is greyed out, because there is no earlier tag to compare with. Write the notes by hand.)
6. Leave **Set as the latest release** ticked. Leave "pre-release" unticked.
7. Press **Publish release**.
8. Open the **Actions** tab and watch **Checks**. When **Publish images** shows a green tick, the new images are ready.
9. In Arcane, press **Redeploy**.

## Template for the description

Copy this above the generated list and fill in the brackets.

```
## In short
[One or two plain sentences: what is better for people in this version.]

## Before you update
[Delete this section if there is nothing to do. Otherwise say what to do, for example "Nothing to do: update as usual."]

(Press "Generate release notes" and the full list of changes appears below this line.)
```

The longer, plain-words version of each change is in `docs/CHANGELOG.md` under the same version number.

## If something goes wrong

- **Publish images was skipped or stopped:** the tag and `backend/version.py` do not match. Delete the release and its tag on GitHub, fix the version, and create the release again.
- **A check failed:** nothing is published. Fix it in a pull request, merge, then edit the release (or make a new one) and publish again.
- **Labels:** pull requests with labels `feat`, `fix`, `security` or `docs` are grouped in the generated notes. Unlabelled ones still appear, under "Other changes".
