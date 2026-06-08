# SkywarnPlus-NG

![GitHub total downloads](https://img.shields.io/github/downloads/hardenedpenguin/SkywarnPlus-NG/total?style=flat-square)

Weather alerts for Asterisk / app_rpt nodes — voice announcements, DTMF SkyDescribe, and a web dashboard.

<p align="center">
  <a href="SkywarnPlus-ng.png"><img src="SkywarnPlus-ng.png" alt="SkywarnPlus-NG Dashboard" width="400"></a>
  <a href="SkywarnPlus-ng-1.png"><img src="SkywarnPlus-ng-1.png" alt="SkywarnPlus-NG Dashboard" width="400"></a>
</p>

Modern rewrite of [SkywarnPlus](https://github.com/Mason10198/SkywarnPlus) by Mason Nelson (N5LSN/WRKF394). Release notes: [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases).

## Install

**Prerequisites:** 64-bit Linux, **Python 3.11+**, Asterisk with user **`asterisk`**, outbound Internet. Run **`install.sh` as a normal user** (not root) — it uses `sudo` where needed. Use an [official release tarball](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases) (includes pre-built dashboard CSS).

```bash
wget https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/download/v1.1.0/skywarnplus-ng-1.1.0.tar.gz
tar -xzf skywarnplus-ng-1.1.0.tar.gz
cd skywarnplus-ng-1.1.0
./install.sh

sudo systemctl enable --now skywarnplus-ng
sudo systemctl status skywarnplus-ng
```

**Dashboard:** `http://<host>/skywarnplus-ng/` when Apache is installed (installer enables the proxy automatically), or `http://<host>:8100/skywarnplus-ng/` direct. Default login **`admin`** / **`skywarn123`** — change under **Configuration** immediately.

**Config file:** `/etc/skywarnplus-ng/config.yaml` (UI saves here; restart after manual edits).

> **Low disk on `/tmp`?** The installer uses **`/var/tmp`** for pip (override with **`SKYWARN_TMPDIR`** if needed).

## After install

1. Set a new dashboard password.
2. Add your [NWS county codes](CountyCodes.md) under **Configuration → Counties**.
3. Set **Asterisk node number(s)** and per-node counties if you run multiple nodes.
4. Pick **Piper** (local, default) or **gTTS** under **Audio / TTS**.
5. Save — the service reloads config from the UI.

The dashboard shows the **running version** so you can confirm what's live.

## Upgrade

Extract a newer release tarball and run **`./install.sh`** again in the new directory. Your existing **`/etc/skywarnplus-ng/config.yaml`** is kept; an updated example is written to **`config.yaml.example`**. Then:

```bash
sudo systemctl restart skywarnplus-ng
```

## Paths & CLI

| Item | Path |
|------|------|
| Config | `/etc/skywarnplus-ng/config.yaml` |
| Data / state | `/var/lib/skywarnplus-ng/data/` |
| Virtualenv | `/var/lib/skywarnplus-ng/venv/` |
| Log | `/var/log/skywarnplus-ng/skywarnplus-ng.log` |
| DTMF fragment | `/etc/asterisk/custom/rpt/skydescribe.conf` |

```bash
sudo -u asterisk /var/lib/skywarnplus-ng/venv/bin/skywarnplus-ng describe 1
journalctl -u skywarnplus-ng -f
```

## Reverse proxy

Default **`base_path`** is **`/skywarnplus-ng`**. On Apache nodes, **`install.sh`** installs **`config/apache/skywarnplus-ng-proxy.conf`** and runs **`a2enconf`**. For **nginx** or Nginx Proxy Manager, see **[nginx-proxy-manager-guide.md](nginx-proxy-manager-guide.md)**. For direct access on port 8100 only, set **`base_path: ""`** in config.

## Features

- NWS alert polling, voice announcements, tail messages, courtesy tones, ID changes
- Per-node counties, SkyDescribe DTMF (**841–849** by alert index), AlertScript
- Web dashboard with live status, health, logs, and configuration
- Email, Pushover, and HTTPS webhooks (configure under **Configuration → Subscribers**)
- Optional GPS mobile counties, quiet hours, NHC tropical cyclone advisories (1.1+)

## DTMF & webhooks

**SkyDescribe:** codes **841–849** describe active alerts 1–9. Enable the menu paths on your node; DTMF only works for **currently active** alerts.

**Webhooks:** add a subscriber with an **HTTPS** URL and enable the webhook delivery method. The server POSTs JSON (`title`, `message`, `timestamp`, `source`) from the node — test with **DEV → Test alert injection** and `journalctl -u skywarnplus-ng -f`. Private/local URLs are blocked by design.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `asterisk` user missing | Install Asterisk / ASL first |
| Port 8100 in use | Change **`monitoring.http_server.port`** or free the port |
| 404 / broken UI behind nginx | Check **`base_path`** and proxy prefix stripping — [guide](nginx-proxy-manager-guide.md) |
| WebSocket reconnect loop | Long proxy timeouts + correct **`base_path`** |
| pip: no space left on device | Check **`df -h /var/tmp`** or set **`SKYWARN_TMPDIR`** |
| Stylesheet missing on install | Use a release tarball, or run `npm install && npm run build:css` |

## Development

```bash
python -m pip install -e ".[dev]"
ruff check src tests && pytest tests/ -v
```

After editing dashboard templates, rebuild CSS: `npm install && npm run build:css`.

## License

GNU General Public License v3.0 or later — see **[LICENSE](LICENSE)**.
