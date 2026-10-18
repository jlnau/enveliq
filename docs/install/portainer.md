# Install Enveliq with Portainer

[Portainer](https://www.portainer.io) is a popular control panel for Docker. This guide uses its **Stacks** page.

**You need:** Portainer up and running, and about 2 GB of free memory.

## Step 1. Decide your settings

Open [Choose your settings](choose-settings.md), decide your answers, and come back. This includes a **vault key**, which is required: make it now with [Setting 4: the vault key](choose-settings.md#setting-4-the-vault-key-required) and save a copy in your password manager. Have your **setup code** ready.

## Step 2. Create the stack

1. Open Portainer and pick your Docker environment (usually called **local**).
2. In the left menu click **Stacks**, then **Add stack**.
3. In **Name** type `enveliq`. (Lower case, no spaces.)
4. Leave **Build method** on **Web editor**.
5. Open <https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml> in another tab and press **Copy raw file** (two overlapping squares, top right of the file).
6. Back in Portainer, click inside the web editor and paste (Ctrl + V).
7. Change the lines marked `<-- CHANGE THIS` to your answers. Keep the quote marks.
8. Scroll down and press **Deploy the stack**.

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
