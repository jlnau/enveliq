# Enveliq UI preview

This folder describes the separate Docker preview stack originally used to test the interface redesign. The redesign is now merged into `main` for v0.87. The preview stack remains a useful place to test changes separately, but its images are not the versioned production release images.

## Safety

* Deploying the **preview stack** does not replace a running production stack. Merging code into `main` also does not publish or deploy a GitHub Release.
* Do not point the preview at the production Docker volume or reuse production vault keys.
* Do not connect your everyday mailbox until duplicate syncs and reminders have been assessed.
* Use a dedicated test mailbox or the bundled demonstration data first.
* The isolated preview images are separate from the tagged production release images. Confirm the source branch and successful preview workflow before using them.

## Running separately using Arcane

1. Confirm the isolated preview images are available from a successful **Build UI Preview** workflow before deploying. This workflow builds preview images and does not publish a production version.
2. In Arcane, create another project called `enveliq-preview`. Keep the existing production project running.
3. Paste the complete contents of `preview/docker-compose.yml` into the new project's Compose editor.
4. Set the preview project environment variables: `ENVELIQ_PREVIEW_SETUP_CODE` must be unique and at least 20 characters; `ENVELIQ_PREVIEW_PUBLIC_URL` must match the address used by the browser. The default is `http://localhost:8767` and is accessible only from the Docker host.
5. Deploy. The two preview containers must show healthy. For a remote browser, use a separate HTTPS reverse proxy hostname forwarding to port `8767` on the Docker host and set `ENVELIQ_PREVIEW_PUBLIC_URL` to that HTTPS address before deployment.
6. Open the preview address and finish first time setup with the test setup code. Configure test mailboxes only.

To update an existing preview after its image source changes, wait for a successful preview image build and then redeploy only the preview project in Arcane. Do not redeploy the production project as part of preview testing.

## Interface changes

* Calm mode starts enabled unless a browser has explicitly turned it off.
* Desktop receives a compact landscape header while mobile keeps the existing navigation without an extra banner.
* The original task system supplies Start here, remaining tasks due today and Later; no tasks are copied or deleted by the UI.
* Attachment paperclips are displayed directly beside their timestamps, without an extra vertical line.
* All backend, reminder, vault and mailbox logic remains unchanged.

## Validation

Review the branch's existing CI checks and the image publishing workflow before deploying.
Perform a hands on review in both themes on desktop and mobile, with Calm mode on and off.
Verify task actions, filters, attachments, snoozing, compose and mailbox operations using a test account.
