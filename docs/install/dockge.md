# Install Enveliq with Dockge

[Dockge](https://github.com/louislam/dockge) is a simple control panel for Docker Compose files. Enveliq's install file is one, so it fits right in.

**You need:** Dockge up and running (see Dockge's own page if you need to install it), and about 2 GB of free memory.

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

Either way you get one long line of letters and numbers. **Save it in your password manager right now.** If your install file is ever lost, this key is the only way to open your data again. Then, when you edit the install file below, put it in the line `ENVELIQ_VAULT_KEY: "${ENVELIQ_VAULT_KEY:-}"`: replace `${ENVELIQ_VAULT_KEY:-}` with your key and keep the quote marks (or, if your panel has an environment box, set `ENVELIQ_VAULT_KEY` there).

## Step 2. Create the stack

1. Open Dockge (usually on port 5001 of your server, for example `http://192.168.1.50:5001`) and sign in.
2. Click **Compose** (top left).
3. In the stack **name** box type `enveliq`. (Lower case.)
4. Open <https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml> in another tab and press **Copy raw file** (two overlapping squares, top right of the file).
5. Back in Dockge, click in the editor, select everything (Ctrl + A) and paste (Ctrl + V).
6. Change the lines marked `<-- CHANGE THIS` to your answers, including your vault key. Keep the quote marks.
7. Click **Deploy**.

**Check:** Dockge shows the stack with `enveliq` and `enveliq-render` running. The first start downloads the images, so wait a few minutes.

## Step 3. Open Enveliq

Go to the address you chose in setting 1, for example `http://192.168.1.50:8765` for address **B**. You should see **Set up Enveliq**. Carry on with [First-time setup](after-install.md).

## Updating later

Open the stack in Dockge and press **Update** (it pulls the newest images and restarts the stack). Your data is kept. More in [Maintenance](maintenance.md).

## If something goes wrong

[Troubleshooting](troubleshooting.md).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).

---

*These screens change as the programs are updated. If yours look different from this guide, please [open an issue](https://github.com/jlnau/enveliq/issues) and tell us which version you have.*
