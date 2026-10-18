# Install Enveliq with Portainer

[Portainer](https://www.portainer.io) is a popular control panel for Docker. This guide uses its **Stacks** page.

**You need:** Portainer up and running, and about 2 GB of free memory.

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

This is the install file. Select everything in the box below and copy it (on the website the box has a **Copy** button). You will paste it into the editor in the steps after it. If you read this on GitHub the box is not shown: open the [install file on GitHub](https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml) and press **Copy raw file** instead.

<!-- include: install/docker-compose.yml -->

1. Open Portainer and pick your Docker environment (usually called **local**).
2. In the left menu click **Stacks**, then **Add stack**.
3. In **Name** type `enveliq`. (Lower case, no spaces.)
4. Leave **Build method** on **Web editor**.
5. Copy the install file shown at the top of this step.
6. Back in Portainer, click inside the web editor and paste (Ctrl + V).
7. Change the lines marked `<-- CHANGE THIS` to your answers, including your vault key. Keep the quote marks.
8. Scroll down and press **Deploy the stack**.

**Tip:** under the editor Portainer has **Environment variables**. You can add `ENVELIQ_VAULT_KEY` there with your key instead of editing the file.

**Check:** you land on the Stacks list and `enveliq` shows as **running** (the first start downloads the images, so wait a few minutes). Click it: both `enveliq` and `enveliq-render` should be running.

## Step 3. Open Enveliq

Go to the address you chose in setting 1. For address **B** that is your server's number plus `:8765`, for example `http://192.168.1.50:8765`. You should see **Set up Enveliq**. Carry on with [First-time setup](after-install.md).

## Updating later

1. Open **Stacks**, click `enveliq`, then **Editor**.
2. Tick **Re-pull image and redeploy** (it is under the editor), and press **Update the stack**.

Your data is kept. More in [Maintenance](maintenance.md).

## If something goes wrong

[Troubleshooting](troubleshooting.md).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).

---

*These screens change as the programs are updated. If yours look different from this guide, please [open an issue](https://github.com/jlnau/enveliq/issues) and tell us which version you have.*
