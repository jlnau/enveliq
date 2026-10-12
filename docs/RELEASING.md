# Making a release (for the maintainer)

Merging a pull request into `main` publishes nothing. Enveliq's images are built and published only when you publish a **GitHub Release**. Several merged pull requests can go out together as one release.

GitHub has no built-in "release template" that pre-fills the form. What it does have is the **Generate release notes** button, which fills in the description from the pull requests merged since the last release. This repository sets that up in `.github/release.yml`. The text to paste into the title and description is below.

## Before you click "Create a new release"

1. Merge the feature pull requests for this release and wait for the required checks on `main` to pass.
2. Open **Actions → Prepare Release → Run workflow**, leave the branch on `main`, enter the next number without `v` (for example `0.83`), and click **Run workflow**.
3. The workflow generates release notes from PRs merged since the previous released tag when the Unreleased changelog section is empty. If that section already contains manually prepared notes, those are preserved instead. It then uses `scripts/prepare_release.py` to update `backend/version.py`, the README and the changelog and creates a PR.
4. Review and merge the preparation PR once all required checks pass. Only then create the GitHub Release tag. Do not run Prepare Release again for an already prepared version.

No terminal commands or manual changelog edits are needed for the normal release process. The workflow stops safely if the previous release tag is missing, there are no new merged PRs, or the new release branch or tag already exists.

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

## Important: preparing a version is not publishing it

The preparation script changes files locally only. Commit the three changes in a pull request and merge it before creating a tag. A release tag captures a particular commit: updating `main` after creating the tag does not change the existing release. If a release was already published using the wrong version, do not simply rerun its failed workflow. First prepare and merge the version changes, then deliberately replace the incorrect tag and release, or publish a newly numbered release, after reviewing the impact on users and images.

## If something goes wrong

- **Publish images was skipped or stopped:** the tag and `backend/version.py` do not match. Delete the release and its tag on GitHub, fix the version, and create the release again.
- **A check failed:** nothing is published. Fix it in a pull request, merge, then edit the release (or make a new one) and publish again.
- **Labels:** pull requests with labels `feat`, `fix`, `security` or `docs` are grouped in the generated notes. Unlabelled ones still appear, under "Other changes".
