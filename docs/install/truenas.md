# Install Enveliq on TrueNAS SCALE

TrueNAS SCALE 24.10 and newer can run a Docker Compose file as a **custom app**.

**You need:** TrueNAS SCALE with **Apps** set up (a pool chosen for apps), and about 2 GB of free memory.

## Step 1. Decide your settings

Open [Choose your settings](choose-settings.md), decide your answers, and come back. On TrueNAS you open Enveliq from other devices, so you will most likely choose address **B** (home Wi-Fi) or **C** (Tailscale). Have your **setup code** ready.

## Step 2. Prepare the install file

1. Open <https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml> on your computer and press **Copy raw file**.
2. Paste it into a plain text editor (Notepad, TextEdit in plain text mode, or any code editor) so you can edit it comfortably. TrueNAS is strict about indentation, so do not change the spaces at the start of lines.
3. Change the lines marked `<-- CHANGE THIS` to your answers. The port line already says `- "8765:8765"`, so other devices on your network can open Enveliq.

## Step 3. Install it as a custom app

1. In TrueNAS open **Apps**, then **Discover Apps**.
2. Click the **three dots** (⋮) at the top right, then **Install via YAML**.
3. **Application Name:** `enveliq` (lower case letters and numbers only).
4. Paste your edited file into **Custom Config**.
5. Press **Save**.

TrueNAS now downloads and starts Enveliq. This can take several minutes.

**Check:** on **Apps**, **Installed**, `enveliq` shows as **Running**.

## Step 4. Open Enveliq

On any device on your home network go to `http://YOUR-TRUENAS-NUMBER:8765`, for example `http://192.168.1.50:8765`. You should see **Set up Enveliq**. Carry on with [First-time setup](after-install.md).

## Updating later

In **Apps**, **Installed**, open `enveliq`, press **Edit**, then **Save** again. The install file asks Docker for the newest version. Check the version number under the Enveliq logo (top left) afterwards. Your data is kept in the `enveliq-data` volume. More in [Maintenance](maintenance.md).

## If something goes wrong

[Troubleshooting](troubleshooting.md).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).

---

*These screens change as the programs are updated. If yours look different from this guide, please [open an issue](https://github.com/jlnau/enveliq/issues) and tell us which version you have.*
