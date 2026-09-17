# KubeDeck Web

KubeDeck Web is the mobile-friendly companion dashboard built into the
KubeDeck desktop application.

## How it works

When KubeDeck starts, it starts the web server automatically in a background
thread. The web server does **not** create another SSH connection and does
not need SSH credentials of its own. It reuses the live SSH connection already
owned by KubeDeck and opens managed SSH session channels for Kubernetes
commands and pod logs.

Web login credentials are configured in:

**KubeDeck → Settings → Web App**

The credentials are read dynamically, so changing them does not require a
KubeDeck restart.

## Open the web app

Keep KubeDeck running, connect to the VM as usual, then open:

```text
http://<KubeDeck-machine-LAN-IP>:8000
```

The web app is bound to `0.0.0.0:8000` by default so a phone on the same
network can reach it.

## Configuration

The `.env` file no longer contains SSH host/user/key/password settings or web
login credentials. The example file only documents optional web-server host
and port overrides.

For packaged KubeDeck builds, the web UI also has a Python-embedded fallback
so the page remains available when the PyInstaller bundle does not include the
source `static/` directory.

## Security

The dashboard can delete pods and restart/scale deployments. Keep it on a
trusted LAN/VPN or put HTTPS/TLS in front of it before exposing it outside a
trusted network.
