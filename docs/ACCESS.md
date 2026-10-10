# How should I open Enveliq?

Enveliq is a web page that runs on your own machine. You choose how your browser reaches it. Pick
the first option that fits. Every option except the last gives you **https**, which Enveliq needs
for passkeys and for Outlook, Hotmail and Microsoft 365 sign-in.

| You want | Use | Needs a domain | Open to the internet |
|---|---|---|---|
| Just me and my family, on our own phones and laptops, from anywhere | [Tailscale](#tailscale-the-easiest) | No | No |
| A normal web address, and I already run Nginx Proxy Manager | [Nginx Proxy Manager](#nginx-proxy-manager) | Yes | Your choice |
| A normal web address, and no open ports at home | [Cloudflare Tunnel](#cloudflare-tunnel) | Yes | Yes, through Cloudflare |
| I already run Caddy, Traefik or Nginx | [Caddy, Traefik, Nginx](#caddy-traefik-and-nginx) | Yes | Your choice |
| A quick look on my home network | [Plain http](#plain-http-on-your-home-network-for-a-quick-look) | No | No |

## The same four rules for every proxy

1. **Tell Enveliq its own address first.** Set `ENVELIQ_PUBLIC_URL` to exactly what people type in the
   browser, for example `https://enveliq.example.com` (no path, no trailing slash). Set it **before** anyone
   registers a passkey: passkeys and single sign-on are tied to that address.
2. **Send traffic to port 8765 over plain http.** The proxy handles https; Enveliq listens on 8765.
3. **Keep the Host header.** The proxy must pass the original host name through (all the ones below do by
   default). Enveliq refuses a request whose host is not in `ENVELIQ_PUBLIC_URL`.
4. **Let the proxy reach the port.** By default Enveliq only listens on the machine it runs on
   (`127.0.0.1`). A proxy on the same machine, outside Docker, can use `127.0.0.1:8765`. A proxy in
   another container, or on another machine, cannot. For those, put the machine's own network address
   in `ENVELIQ_PUBLISH` (for example `ENVELIQ_PUBLISH=192.168.1.50`), so Enveliq listens on that
   address only, and keep that port closed to everything except the proxy.

Settings go in the `.env` file next to `docker-compose.yml` (in Arcane: the project's environment
variables). After changing them, update and redeploy:

```
cd /opt/enveliq-app && git pull && docker build -t enveliq:local . && docker build -f Dockerfile.render -t enveliq-render:local .
```

Or skip building altogether: [Install Enveliq](install/README.md) uses ready-made images.

Then press Redeploy in Arcane, or run `docker compose up -d`.

If syncing many emails ever ends in a 504 or "timeout", raise the proxy's read timeout to 120 seconds.

## Tailscale, the easiest

Tailscale makes a private network between your own devices. Nothing is opened to the internet, you
need no domain, and it gives Enveliq a real https address that only your devices can reach.

1. Make a free Tailscale account and install Tailscale on the machine that runs Enveliq and on every
   phone or laptop that will use it. Sign in to the same account on all of them.
2. In the Tailscale admin page, open DNS, turn on MagicDNS, and under HTTPS Certificates press Enable.
3. On the Enveliq machine, run:

   ```
   tailscale serve --bg 8765
   tailscale serve status
   ```

   The status shows an address like `https://enveliq-host.tail1234.ts.net`.
4. Put that address in `.env` and redeploy:

   ```
   ENVELIQ_PUBLIC_URL=https://enveliq-host.tail1234.ts.net
   ```
5. Open that address on any device signed in to your Tailscale account.

Tailscale on the same machine reaches `127.0.0.1:8765`, so you do not need `ENVELIQ_PUBLISH`. To let a
family member in, share the machine from the Tailscale admin page.

## Nginx Proxy Manager

1. In Nginx Proxy Manager open Hosts, Proxy Hosts, Add Proxy Host.
2. Details tab:
   - Domain Names: `enveliq.example.com`
   - Scheme: `http`
   - Forward Hostname / IP: the address of the machine that runs Enveliq (for example `192.168.1.50`).
     Do not use `127.0.0.1` or `localhost`: inside Nginx Proxy Manager's own container that means
     itself.
   - Forward Port: `8765`
   - Turn on Block Common Exploits. Websockets Support is not needed.
3. SSL tab: SSL Certificate, Request a new SSL Certificate (Let's Encrypt), turn on Force SSL and
   HTTP/2 Support, accept the terms, Save.
4. In Enveliq's `.env`:

   ```
   ENVELIQ_PUBLIC_URL=https://enveliq.example.com
   ENVELIQ_PUBLISH=192.168.1.50
   ```

   Use the same machine address as in step 2. If Nginx Proxy Manager runs on the same machine, this
   still applies, because it runs in its own container.
5. If you reach it from outside your home, make sure the domain points to your public address and ports
   80 and 443 forward to Nginx Proxy Manager. Do not forward 8765.

## Cloudflare Tunnel

A tunnel means you open no ports at home: a small program called `cloudflared` on your machine calls out
to Cloudflare, and Cloudflare serves your domain. You need a domain whose DNS is on Cloudflare.

1. In the Cloudflare dashboard open Zero Trust, Networks, Tunnels, Create a tunnel, choose Cloudflared,
   and name it. Follow the shown command to install and start `cloudflared` on the machine that runs
   Enveliq (or on any machine that can reach it).
2. Add a Public hostname:
   - Subdomain and Domain: `enveliq` and `example.com`
   - Service Type: `HTTP`
   - URL: `localhost:8765` if `cloudflared` runs directly on the same machine, or
     `192.168.1.50:8765` if it runs in a container or elsewhere
3. In Enveliq's `.env`:

   ```
   ENVELIQ_PUBLIC_URL=https://enveliq.example.com
   ```

   Add `ENVELIQ_PUBLISH=192.168.1.50` only if `cloudflared` is not directly on the same machine.
4. **Put Cloudflare Access in front of it.** Otherwise anyone on the internet can reach the sign-in
   page. In Zero Trust open Access, Applications, Add an application, Self-hosted, use the same
   hostname, and add a policy that allows only your email addresses. Enveliq's own sign-in and
   two-factor still apply after that.

One thing to know: a tunnel ends https at Cloudflare's servers, so Cloudflare can technically see the
traffic. Mail stays encrypted in Enveliq's storage, but what you read in the browser passes through
Cloudflare. If that matters to you, use Tailscale instead.

## Caddy, Traefik and Nginx

**Caddy** (gets its own certificate). In the `Caddyfile`:

```
enveliq.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

Use the machine's address instead of `127.0.0.1` if Caddy runs in a container, and set `ENVELIQ_PUBLISH`
as in rule 4.

**Traefik** (dynamic file, with a certificate resolver you already use):

```yaml
http:
  routers:
    enveliq:
      rule: Host(`enveliq.example.com`)
      entryPoints: [websecure]
      tls:
        certResolver: letsencrypt
      service: enveliq
  services:
    enveliq:
      loadBalancer:
        servers:
          - url: "http://192.168.1.50:8765"
```

**Nginx** (with a certificate from certbot or your own):

```nginx
server {
    listen 443 ssl http2;
    server_name enveliq.example.com;
    ssl_certificate     /etc/letsencrypt/live/enveliq.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/enveliq.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_read_timeout 120s;
    }
}
```

**Anything else** (Synology, QNAP, OPNsense, HAProxy, a router's reverse proxy): forward
`https://your-name` to `http://machine-address:8765` and keep the Host header. The four rules above are
the whole list.

In every case, set `ENVELIQ_PUBLIC_URL` to the https address and nothing else is needed.

## Plain http on your home network, for a quick look

If you only want to try Enveliq on a network you trust, you can open `http://machine-address:8765`
with no proxy. It is off until you switch it on, and it has real limits: passwords and the sign-in
cookie are not encrypted on the network, and passkeys and Outlook sign-in will not work. Steps and
details: [NETWORK_ACCESS.md](NETWORK_ACCESS.md). The inbox shows a warning while you use it this way.

## If it does not work

- **"Bad Request" or an invalid host message:** the address in the browser is not the one in
  `ENVELIQ_PUBLIC_URL`. They must match exactly, including `https://`.
- **Bad gateway (502):** the proxy cannot reach port 8765. Check rule 4: a proxy in a container must use
  the machine's address, and `ENVELIQ_PUBLISH` must be that address (or `0.0.0.0`).
- **Passkey or Microsoft sign-in says the address is wrong:** you are on http, or the address changed after
  you set it up. Use the https address, and register passkeys again if you changed it.
