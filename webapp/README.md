# KubeDeck Web

A small mobile-friendly dashboard that does what the desktop KubeDeck app
does for Kubernetes — SSH into a box that has `kubectl` configured, run
`kubectl` there, show the results — except from a phone browser instead
of a Qt window.

It's read-first with a few guarded actions: view pods, deployments,
services, nodes and events; tail a pod's logs; delete a pod, restart a
deployment, or scale one. Nothing more — no file manager, no terminal,
no arbitrary command execution.

## Setup

Run this on any machine that can already SSH into your cluster box
(your laptop, a small always-on server, etc — it does **not** need to
be the cluster box itself, just able to reach it over SSH):

```bash
cd webapp
pip install -r requirements.txt
cp .env.example .env
# edit .env: SSH_HOST / SSH_USER / SSH_KEY_PATH (or SSH_PASSWORD),
# and set APP_USERNAME / APP_PASSWORD to a real login for the dashboard
uvicorn app:app --host 0.0.0.0 --port 8000
```

Then, from your phone (same Wi-Fi network as the machine running this):

```
http://<that machine's LAN IP>:8000
```

You'll get a browser login prompt (HTTP Basic Auth) — use the
`APP_USERNAME` / `APP_PASSWORD` you set in `.env`. You can "Add to Home
Screen" on iOS/Android afterwards so it opens full-screen like an app.

## Using it away from home (optional)

Opening port 8000 directly to the internet is not recommended — do one
of these instead:

- **A personal VPN mesh** (Tailscale, ZeroTier, WireGuard): install it
  on the machine running this and on your phone, then just use the
  Tailscale/private IP instead of the LAN IP. This is the easiest and
  safest option and needs no changes to this app.
- **A reverse proxy with real TLS** (Caddy, nginx + Let's Encrypt, or a
  Cloudflare Tunnel) in front of `uvicorn`, so traffic is HTTPS instead
  of plain HTTP — HTTP Basic Auth sends credentials in a way that's only
  safe over TLS.

Either way, keep `APP_USERNAME`/`APP_PASSWORD` set to something real —
this dashboard can delete pods and restart deployments, so it should
never be reachable without a login.

## What it needs on the SSH target

Just `kubectl`, already configured (i.e. `kubectl get pods` already
works when you SSH in yourself). Nothing is installed or changed on
that box.

## Notes

- One SSH connection is kept open and reconnected automatically if it
  drops — fine for a single person checking their phone occasionally;
  this isn't built for concurrent multi-user load.
- All mutating actions (delete pod, restart/scale deployment) are
  `POST` requests behind the same login as everything else — there's
  no separate "read-only mode" here, so treat the login as a real
  credential.
- `SSH_HOST`/`SSH_KEY_PATH`/`APP_PASSWORD` all live in `.env`, which is
  already covered by the repo's `.gitignore` pattern for `.env` files —
  double-check it's not committed if you fork/copy this elsewhere.
