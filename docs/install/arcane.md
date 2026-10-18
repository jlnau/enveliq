# Install Enveliq with Arcane

[Arcane](https://getarcane.app) is a friendly control panel for Docker. If you already have it, installing Enveliq takes about five minutes.

**You need:** Arcane up and running, and about 2 GB of free memory.

## Step 1. Decide your settings

Open [Choose your settings](choose-settings.md), decide your answers, and come back. Have your **setup code** ready.

### Make your vault key (required)

The vault key is a long secret that locks everything Enveliq keeps. Enveliq will not finish setup without one. Make it now, **before** you start Enveliq. Use whichever way is easiest:

- **In a terminal** (on Mac or Linux): `openssl rand -hex 32`
- **In a terminal anywhere Docker runs, including Windows:**

  ```
  docker run --rm alpine sh -c "head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; echo"
  ```

- **No terminal?** In your password manager (Bitwarden, 1Password and others) make a new password that is **64 characters, letters and numbers only**.

Either way you get one long line of letters and numbers. **Save it in your password manager right now.** If your install file is ever lost, this key is the only way to open your data again. Then, when you edit the install file below, paste the key between the quote marks on the line `ENVELIQ_VAULT_KEY: "PASTE-YOUR-VAULT-KEY-HERE"`.

## Step 2. Create the project

1. Open Arcane. In the left menu click **Projects**.
2. Click **Create Project**.
3. In **Name** type `enveliq`.
4. Open <https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml> in another tab and press **Copy raw file** (two overlapping squares, top right of the file).
5. Back in Arcane, click in the large compose editor, select everything in it (Ctrl + A), and paste (Ctrl + V).
6. Change the lines marked `<-- CHANGE THIS` to your answers, including your vault key. Keep the quote marks.
7. Click **Create Project**. Arcane saves it and starts it.

**Check:** the project `enveliq` shows two services, `enveliq` and `enveliq-render`, both running. The first start downloads the images and can take a few minutes. If a service is red, open the project and look at its logs, then see [Troubleshooting](troubleshooting.md).

## Step 3. Open Enveliq

Go to the address you chose in setting 1, for example `http://localhost:8765` or `http://192.168.1.50:8765` (the computer that runs Arcane, with `:8765` on the end). You should see **Set up Enveliq**. Carry on with [First-time setup](after-install.md).

Arcane runs Enveliq on the same machine as Arcane itself. If you chose address **A** (`localhost`), "localhost" means **that machine**. To open it from your own computer, choose address **B** or **C**.

## Updating later

Open the project in Arcane and press **Redeploy**. It downloads the newest Enveliq and restarts it. Your data is kept. More in [Maintenance](maintenance.md).

## If something goes wrong

[Troubleshooting](troubleshooting.md).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).

---

*These screens change as the programs are updated. If yours look different from this guide, please [open an issue](https://github.com/jlnau/enveliq/issues) and tell us which version you have.*
