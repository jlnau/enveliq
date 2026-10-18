# Install Enveliq with Docker Desktop (Windows or Mac)

The easiest way to try Enveliq. Docker Desktop is a free program that runs Enveliq on your own computer.

**Good to know:** Enveliq only works while Docker Desktop is running and the computer is awake. For a household that wants Enveliq always available, a small always-on computer or a NAS is better. See [Install Enveliq](README.md) for the other guides.

**You need:** a Windows 10 or 11 PC, or a Mac, with about 4 GB of free memory, and about 15 minutes.

## Step 1. Install Docker Desktop

1. Open <https://www.docker.com/products/docker-desktop/> and press the download button for your computer (Windows, Mac with Apple chip, or Mac with Intel chip). If you do not know which Mac you have, click the Apple menu, **About This Mac**: it says **Chip**.
2. Open the file you downloaded and follow the installer. Accept the defaults. On Windows it may ask to restart the computer: do that.
3. Start **Docker Desktop**. Tick the box to accept the terms. If it asks you to sign in, you can press **Skip**.
4. **Check:** wait until the bottom-left of the Docker Desktop window shows a green **Engine running**.

## Step 2. Make a folder for Enveliq

1. Open your **Documents** folder.
2. Make a new folder called `enveliq`.

## Step 3. Get the install file

This is the install file. Select everything in the box below and copy it (on the website the box has a **Copy** button). You will paste it into the editor in the steps after it. If you read this on GitHub the box is not shown: open the [install file on GitHub](https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml) and press **Copy raw file** instead.

<!-- include: install/docker-compose.yml -->

You will make a small text file called `docker-compose.yml` inside that folder.

1. Copy the install file shown at the top of this step.
2. Now save it as a file:
   - **Windows:** open **Notepad**. Paste. Choose **File**, **Save as**. Go to the `enveliq` folder. Click **Save as type** and choose **All files**. Type the name `docker-compose.yml` and press **Save**.
   - **Mac:** open **TextEdit**. Choose **Format**, **Make Plain Text**. Paste. Choose **File**, **Save**. Name it `docker-compose.yml`, choose the `enveliq` folder, and when it asks about `.yml`, press **Use .yml**. (If it offers "If no extension is provided, use .txt", untick it.)
3. **Check:** in the folder the file is called `docker-compose.yml`, not `docker-compose.yml.txt`. (On Windows, in File Explorer press **View**, **Show**, **File name extensions** to see the full name.)

## Step 4. Open a terminal in the folder

- **Windows:** in File Explorer open the `enveliq` folder. Click the address bar at the top, type `powershell` and press Enter. A blue window opens.
- **Mac:** open **Terminal** (press Command + Space, type `Terminal`, press Enter). Type `cd ` (the letters c, d and a space), then drag the `enveliq` folder from Finder into the Terminal window, then press Enter.

## Step 5. Make your vault key and start Enveliq

The vault key is a long secret that locks everything Enveliq keeps. Enveliq will not finish setup without one. Paste the block for your computer and press Enter. It makes the key, saves it in a file called `.env` next to the install file (Docker reads it by itself), and starts Enveliq.

**Windows (PowerShell)**

```
$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
"ENVELIQ_VAULT_KEY=" + (($b | ForEach-Object { $_.ToString("x2") }) -join "") | Out-File -Encoding ascii .env
docker compose up -d
```

**Mac**

```
echo "ENVELIQ_VAULT_KEY=$(openssl rand -hex 32)" > .env
docker compose up -d
```

1. Wait. The first time it downloads Enveliq, which can take a few minutes. You will see lines scroll by.
2. **Check:** it ends with two lines that say `Started` (or `Running`). Docker Desktop's **Containers** page now lists `enveliq` and `enveliq-render` as running.
3. **Save a copy of your vault key in your password manager now:** run `type .env` (Windows) or `cat .env` (Mac) and copy the line. If that file is ever lost, the key is the only way to open your data again.

## Step 6. Open Enveliq

Open your browser and go to the address you chose in setting 1. If you kept the default, that is <http://localhost:8765>.

You should see a **Set up Enveliq** page asking for a setup code. Carry on with [First-time setup](after-install.md).

## Keep it running

- Docker Desktop must be running. In Docker Desktop open **Settings**, **General**, and tick **Start Docker Desktop when you sign in to your computer**.
- Enveliq starts again by itself whenever Docker Desktop starts.

## If something goes wrong

See [Troubleshooting](troubleshooting.md). The usual ones: [the page will not open](troubleshooting.md#the-page-does-not-open), [the image will not download](troubleshooting.md#docker-says-denied-or-unauthorized-when-pulling), and [I do not know the setup code](troubleshooting.md#i-do-not-know-the-setup-code).

## Next

[First-time setup](after-install.md), then [connect your email](after-install.md#step-4-connect-your-email).
