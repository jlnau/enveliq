# Install Enveliq on Unraid

Unraid can run Docker Compose projects with a free add-on called **Docker Compose Manager**.

**You need:** Unraid 6.12 or newer with Docker switched on, and about 2 GB of free memory.

## Step 1. Decide your settings

Open [Choose your settings](choose-settings.md), decide your answers, and come back. This includes a **vault key**, which is required: make it now with [Setting 4: the vault key](choose-settings.md#setting-4-the-vault-key-required) and save a copy in your password manager. On Unraid you open Enveliq from other devices, so you will most likely choose address **B** (home Wi-Fi) or **C** (Tailscale). Have your **setup code** ready.

## Step 2. Install Docker Compose Manager

1. In Unraid open the **Apps** tab.
2. Search for **Docker Compose Manager** and press **Install**.
3. **Check:** on the **Docker** tab, scroll to the bottom. A **Compose** section is there.

## Step 3. Add the stack

1. On the **Docker** tab scroll to the bottom and click **Add New Stack**.
2. Type the name `enveliq` and press **OK**.
3. Click the **cog** beside `enveliq` and choose **Edit Stack**.
4. Open <https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml> on your computer and press **Copy raw file**. Paste it into the editor.
5. Change the lines marked `<-- CHANGE THIS` to your answers. The port line already says `- "8765:8765"`, so other devices on your network can open Enveliq.
6. Press **Save Changes**.

## Step 4. Start it

1. Beside `enveliq` press **Compose Pull**. Wait for it to finish (it downloads Enveliq).
2. Press **Compose Up**.

**Check:** `enveliq` and `enveliq-render` appear in the Docker list as started.

## Step 5. Open Enveliq

On any device on your home network go to `http://YOUR-UNRAID-NUMBER:8765`, for example `http://192.168.1.50:8765`. You should see **Set up Enveliq**. Carry on with [First-time setup](after-install.md).

## Updating later

Press **Compose Pull**, then **Compose Up** again. Your data is kept. More in [Maintenance](maintenance.md).

## If something goes wrong

[Troubleshooting](troubleshooting.md).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).

---

*These screens change as the programs are updated. If yours look different from this guide, please [open an issue](https://github.com/jlnau/enveliq/issues) and tell us which version you have.*
