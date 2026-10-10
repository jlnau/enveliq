# Install Enveliq on Proxmox

Proxmox runs virtual computers. The simplest, most reliable way to run Enveliq is inside a small Linux virtual machine. This guide makes one, and then you follow the Linux guide inside it.

**You need:** Proxmox VE up and running, and about 4 GB of memory and 20 GB of disk to spare.

## Option 1: a virtual machine (recommended)

1. In the Proxmox web page, upload a **Debian** or **Ubuntu Server** installer: select your storage, **ISO Images**, **Download from URL** (or **Upload**).
2. Click **Create VM** (top right). Give it a name such as `enveliq`. On **OS** choose the ISO. Accept the defaults, except: **Disk** 20 GB, **CPU** 2 cores, **Memory** 4096 MB.
3. Start the VM, open its **Console**, and install the system. When it asks what to install, choose the **SSH server** and the **standard system utilities**. Make a user and password.
4. When it finishes and restarts, log in. Find its number with `hostname -I`.
5. Follow [Install Enveliq with Docker Compose on Linux](docker-compose.md) from the top, inside this VM.

## Option 2: an LXC container (smaller, for people who know Proxmox)

Docker inside LXC works but is not an official Proxmox feature. If you choose it:

1. Create an unprivileged **Debian** container with 2 cores, 4096 MB memory and 20 GB disk.
2. Before you start it: select the container, **Options**, **Features**, and tick **Nesting** and **keyctl**.
3. Start it, open its **Console**, and follow [Install Enveliq with Docker Compose on Linux](docker-compose.md).

If Docker will not start in the container, use Option 1.

## Opening Enveliq

The VM or container has its own network number. Use it for address **B**, or run Tailscale inside it for address **C**. See [Choose your settings](choose-settings.md).

## Next

[First-time setup](after-install.md).
