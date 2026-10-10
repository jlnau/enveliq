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

You will make a small text file called `docker-compose.yml` inside that folder.

1. Open <https://github.com/jlnau/enveliq/blob/main/install/docker-compose.yml> in your browser.
2. Press the **Copy raw file** button (two overlapping squares, top right of the file).
3. Now save it as a file:
   - **Windows:** open **Notepad**. Paste. Choose **File**, **Save as**. Go to the `enveliq` folder. Click **Save as type** and choose **All files**. Type the name `docker-compose.yml` and press **Save**.
   - **Mac:** open **TextEdit**. Choose **Format**, **Make Plain Text**. Paste. Choose **File**, **Save**. Name it `docker-compose.yml`, choose the `enveliq` folder, and when it asks about `.yml`, press **Use .yml**. (If it offers "If no extension is provided, use .txt", untick it.)
4. **Check:** in the folder the file is called `docker-compose.yml`, not `docker-compose.yml.txt`. (On Windows, in File Explorer press **View**, **Show**, **File name extensions** to see the full name.)

## Step 4. Change the three lines

1. Open [Choose your settings](choose-settings.md) and decide your answers. If you only want to try Enveliq on this computer, you can change **just the setup code** and leave the rest.
2. Open the file you saved (right-click, **Open with**, Notepad or TextEdit) and edit the lines marked `<-- CHANGE THIS`. Keep the quote marks.
3. Save the file.

## Step 5. Start Enveliq

1. Open a terminal in the `enveliq` folder:
   - **Windows:** in File Explorer open the `enveliq` folder. Click the address bar at the top, type `cmd` and press Enter. A black window opens.
   - **Mac:** open **Terminal** (press Command + Space, type `Terminal`, press Enter). Type `cd ` (the letters c, d and a space), then drag the `enveliq` folder from Finder into the Terminal window, then press Enter.
2. Type this and press Enter:

   ```
   docker compose up -d
   ```

3. Wait. The first time it downloads Enveliq, which can take a few minutes. You will see lines scroll by.
4. **Check:** it ends with two lines that say `Started` (or `Running`). Docker Desktop's **Containers** page now lists `enveliq` and `enveliq-render` as running.

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
