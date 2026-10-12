# Install Enveliq on a Synology NAS

For Synology NAS models that run **Container Manager** (DSM 7.2 or newer). It is a Docker program you add from Package Center.

**You need:** a Synology with an **Intel or AMD** processor (most "Plus" models, shown as `+` in the name, for example DS920+) and at least 2 GB of memory. Models with ARM processors need the [build method](raspberry-pi.md) instead. Not sure? Search your model number on Synology's website for "CPU".

## Step 1. Decide your settings

Open [Choose your settings](choose-settings.md), decide your answers, and come back. On a NAS you open Enveliq from other devices, so you will most likely choose address **B** (home Wi-Fi) or **C** (Tailscale). Have your **setup code** ready.

## Step 2. Install Container Manager

1. In DSM open **Package Center**.
2. Search for **Container Manager** and press **Install**.
3. **Check:** Container Manager appears in your main menu.

## Step 3. Make a folder

1. Open **File Station**.
2. Open the shared folder called **docker**. (If it does not exist, make a shared folder named `docker` in **Control Panel**, **Shared Folder**.)
3. Inside it, make a folder called `enveliq`.

## Step 4. Create the project

1. Open **Container Manager**, click **Project** in the left menu, then **Create**.
2. **Project name:** `enveliq`.
3. **Path:** press **Set Path** and choose `docker/enveliq`.
4. **Source:** choose **Create docker-compose.yml**.
5. Open <https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml> on your computer and press **Copy raw file**. Paste it into the box (Ctrl + V).
6. Change the lines marked `<-- CHANGE THIS` to your answers. The port line already says `- "8765:8765"`, so other devices on your network can open Enveliq.
7. Press **Next**. If it offers **Set up web portal via Web Station**, leave it off. Press **Next**, then **Done**.

Container Manager now downloads and starts Enveliq. This can take several minutes the first time.

**Check:** in **Project**, `enveliq` shows as **Running**.

## Step 5. Open Enveliq

On any device on your home network go to `http://YOUR-NAS-NUMBER:8765` (the number is the NAS's address, for example `http://192.168.1.50:8765`). You should see **Set up Enveliq**. Carry on with [First-time setup](after-install.md).

## Updating later

In **Container Manager**, **Project**, click `enveliq`, press **Action**, then **Build**. The install file asks Docker for the newest version each time. Check the version number under the Enveliq logo (top left) afterwards; if it did not change, press **Action**, **Clean**, then **Action**, **Build** again. Your data is kept. More in [Maintenance](maintenance.md).

## If something goes wrong

- **"Port already in use":** another app is using 8765. Change the first number in the port line, for example `- "8766:8765"`, and use 8766 in the address.
- Otherwise see [Troubleshooting](troubleshooting.md).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).

---

*These screens change as the programs are updated. If yours look different from this guide, please [open an issue](https://github.com/jlnau/enveliq/issues) and tell us which version you have.*
