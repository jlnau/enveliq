# Troubleshooting

Find your problem, try the fix, and if it still does not work, [open an issue](https://github.com/jlnau/enveliq/issues) and tell us what you see.

- [The page does not open](#the-page-does-not-open)
- [It says "Invalid host header"](#it-says-invalid-host-header)
- [Docker says "denied" or "unauthorized" when pulling](#docker-says-denied-or-unauthorized-when-pulling)
- [Docker says "no matching manifest" or "exec format error"](#docker-says-no-matching-manifest-or-exec-format-error)
- [I do not know the setup code](#i-do-not-know-the-setup-code)
- [Enveliq says it is locked after a restart](#enveliq-says-it-is-locked-after-a-restart)
- [I forgot my password or lost my phone](#i-forgot-my-password-or-lost-my-phone)
- [Port 8765 is already in use](#port-8765-is-already-in-use)
- ["permission denied" when I type a docker command](#permission-denied-when-i-type-a-docker-command)
- [Passkeys or "Sign in with Microsoft" do not work](#passkeys-or-sign-in-with-microsoft-do-not-work)
- [How do I see what Enveliq is doing?](#how-do-i-see-what-enveliq-is-doing)
- [Start again from scratch](#start-again-from-scratch)

## The page does not open

Work down this list.

1. **Is it running?** Type `docker compose ps` in the folder with your install file (or look in your control panel). Both `enveliq` and `enveliq-render` should say `Up` or `running`. If not, type `docker compose up -d`, then `docker compose logs enveliq` to see why.
2. **Is Docker running?** On Windows and Mac, Docker Desktop must be open and show **Engine running**.
3. **Are you using the exact address from setting 1?** `http://localhost:8765` and `http://127.0.0.1:8765` are different addresses to Enveliq. Use exactly what you set in `ENVELIQ_PUBLIC_URL`. See [It says "Invalid host header"](#it-says-invalid-host-header).
4. **Are you on the right computer?** `localhost` always means the computer you are typing on. To open Enveliq from another device, you need address B or C in [Choose your settings](choose-settings.md), and the port line changed to `- "8765:8765"`.
5. **A firewall?** On Linux with `ufw`, allow the port: `sudo ufw allow from 192.168.1.0/24 to any port 8765` (change the network to match yours). Do not open it to the whole internet.

## It says "Invalid host header"

The address in your browser is not the one you put in `ENVELIQ_PUBLIC_URL`. Enveliq refuses other names on purpose. Either type the address you set, or change `ENVELIQ_PUBLIC_URL` to the address you want to use, save, and redeploy (`docker compose up -d`).

## Docker says "denied" or "unauthorized" when pulling

Docker could not download Enveliq.

- Check that the image names in your install file are exactly as in [`install/docker-compose.yml`](../../install/docker-compose.yml), and that the computer is online.
- **If you still see this:** open an issue. Meanwhile, use the build method in the [Raspberry Pi guide](raspberry-pi.md), which works on any computer.

## Docker says "no matching manifest" or "exec format error"

Your computer is not an ordinary 64-bit Intel or AMD one (for example a Raspberry Pi, or an ARM NAS). Use the [build method](raspberry-pi.md). On an Apple-silicon Mac, Docker Desktop normally runs the ordinary image anyway; if yours does not, use the build method.

## I do not know the setup code

The code is whatever you put in `ENVELIQ_SETUP_CODE`. If you forgot it, or you left the placeholder and Enveliq made one, read it from the container:

```
docker exec enveliq cat /data/setup-code.txt
```

In **Portainer**: **Containers**, click `enveliq`, **Console**, **Connect**, then type `cat /data/setup-code.txt`. In **Arcane**, **Dockge** and other panels, look for the container's **Terminal** or **Console** button and type the same.

The code stops existing once setup is finished.

## Enveliq says it is locked after a restart

You did not set a vault key, so Enveliq waits for your **vault passphrase**. Open `/unlock` on your Enveliq address (for example `http://localhost:8765/unlock`), type the passphrase, then sign in. To make Enveliq unlock by itself, set a vault key: [Unlocking by itself](../VAULT_KEY.md).

**If you have lost the passphrase (or key), your data cannot be recovered.** That is what encryption means. You can [start again](#start-again-from-scratch).

## I forgot my password or lost my phone

- **Lost your phone:** sign in with one of the **recovery codes** you saved during setup. Each works once. Then set up the authenticator app again in **Settings**, **Sign-in & security**.
- **Forgot the password of another person:** an administrator opens **Administration**, **People** and gives them a new temporary password.
- **The only administrator forgot their password and has no recovery codes:** open an issue. Do not delete anything first.

## Port 8765 is already in use

Another program uses that port. In the port line of your install file, change the **first** number, for example `- "8766:8765"`, then use `8766` in your address and in `ENVELIQ_PUBLIC_URL`. Redeploy.

## "permission denied" when I type a docker command

On Linux: you are not in the `docker` group yet. Run `sudo usermod -aG docker $USER`, then **log out and back in**.

## Passkeys or "Sign in with Microsoft" do not work

Both need a secure `https://` address (or `localhost`). With plain `http://192.168...` they cannot work. Use [Tailscale or a reverse proxy](../ACCESS.md) to get `https`.

## How do I see what Enveliq is doing?

```
docker compose logs enveliq
```

In a control panel, open the `enveliq` container and press **Logs**. Logs never contain your email, passwords or keys.

## Start again from scratch

This **deletes all your Enveliq data**. Only do it if you want a clean start.

```
docker compose down
docker volume rm enveliq-data
docker compose up -d
```
