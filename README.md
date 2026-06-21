# SkywarnPlus-NG

![GitHub total downloads](https://img.shields.io/github/downloads/hardenedpenguin/SkywarnPlus-NG/total?style=flat-square)

Weather alerts for Asterisk / app_rpt nodes — voice announcements, DTMF SkyDescribe, and a web dashboard.

<p align="center">
  <a href="SkywarnPlus-ng.png"><img src="SkywarnPlus-ng.png" alt="SkywarnPlus-NG Dashboard" width="400"></a>
  <a href="SkywarnPlus-ng-1.png"><img src="SkywarnPlus-ng-1.png" alt="SkywarnPlus-NG Dashboard" width="400"></a>
</p>

Modern rewrite of [SkywarnPlus](https://github.com/Mason10198/SkywarnPlus) by Mason Nelson (N5LSN/WRKF394). Release notes: [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases).

**Current release:** [v1.3.3](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/tag/v1.3.3)

> **Install and upgrades:** SkywarnPlus-NG is moving to the **Debian `.deb` package** for new installs and updates. Use the [hardenedpenguin APT repository](https://hardenedpenguin.github.io/hardenedpenguin-apt/) (`apt install skywarnplus-ng`) or install a `.deb` from [Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases). The release tarball **`install.sh`** flow is **deprecated** — it remains for legacy sites but is no longer supported. Tarball installs do not reliably deploy package-managed files (for example voice-install sudoers, systemd units, and Apache snippets). See **[docs/debian.md](docs/debian.md)**. Existing tarball installs should [migrate to apt](docs/debian.md#migrating-from-tarball-installsh-to-apt) rather than re-run `install.sh`.

## Install

**Prerequisites:** 64-bit Linux (**amd64** or **arm64**), **asl3-asterisk** with user **`asterisk`**, **asl3-tts**, outbound Internet for NWS.

### APT repository (recommended)

One-time setup adds the signing key and `sources.list` entry ([hardenedpenguin-apt](https://github.com/hardenedpenguin/hardenedpenguin-apt)). Supports **amd64** and **arm64**.

```bash
cd /tmp
curl -fsSLO https://hardenedpenguin.github.io/hardenedpenguin-apt/pool/main/h/hardenedpenguin-archive-keyring/hardenedpenguin-archive-keyring_1.0_all.deb
sudo apt install ./hardenedpenguin-archive-keyring_1.0_all.deb
sudo apt update
sudo apt install skywarnplus-ng
sudo systemctl enable --now skywarnplus-ng
```

**Or** download `skywarnplus-ng_*_<arch>.deb` from [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases) and install locally — see **[docs/debian.md](docs/debian.md)** for details.

```bash
sudo apt install ./skywarnplus-ng_*_amd64.deb
# or: sudo dpkg -i skywarnplus-ng_*_amd64.deb && sudo apt-get install -f
sudo systemctl enable --now skywarnplus-ng
```

Replace `amd64` with `arm64` on ARM nodes. Apache proxy is configured automatically on Apache nodes when present.

**Dashboard:** `http://<host>/skywarnplus-ng/` (default login **`admin`** / **`skywarn123`** — change under **Configuration** immediately).

**Config file:** `/etc/skywarnplus-ng/config.yaml` (UI saves here; restart after manual edits).

<details>
<summary><strong>Deprecated: release tarball + install.sh</strong></summary>

Not recommended for new deployments. May miss package-managed files (sudoers for voice install, systemd, Apache conf).

```bash
wget https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/download/v1.3.3/skywarnplus-ng-1.3.3.tar.gz
tar -xzf skywarnplus-ng-1.3.3.tar.gz
cd skywarnplus-ng-1.3.3
./install.sh
sudo systemctl enable --now skywarnplus-ng
```

> **Low disk on `/tmp`?** The installer uses **`/var/tmp`** for pip (override with **`SKYWARN_TMPDIR`** if needed).

</details>

## After install

1. Set a new dashboard password.
2. Add your [NWS county codes](CountyCodes.md) under **Configuration → Counties**.
3. Set **Asterisk node number(s)** and per-node counties if you run multiple nodes.
4. Pick **asl-tts** (local ASL3 Piper, default) or **gTTS** under **Audio / TTS**.
5. Save — the service reloads config from the UI.

The dashboard shows the **running version** so you can confirm what's live.

## Upgrade

**APT repository (recommended):** after the [one-time repo setup](#install) above:

```bash
sudo apt update
sudo apt install skywarnplus-ng
```

**Or** install a newer `.deb` from [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases):

```bash
sudo apt install ./skywarnplus-ng_*_amd64.deb
sudo systemctl restart skywarnplus-ng
```

Tarball sites should [migrate to apt](docs/debian.md#migrating-from-tarball-installsh-to-apt) instead of re-running `install.sh`.

<details>
<summary><strong>Deprecated: release tarball + install.sh</strong></summary>

Do not use on sites that can move to the `.deb`. Re-running `install.sh` runs `pip install` on the node and may skip new privileged scripts (for example `install-tts-voice.sh` and sudoers).

```bash
wget https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/download/v1.3.3/skywarnplus-ng-1.3.3.tar.gz
tar -xzf skywarnplus-ng-1.3.3.tar.gz
cd skywarnplus-ng-1.3.3
./install.sh
sudo systemctl restart skywarnplus-ng
```

</details>

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

The dashboard URL is **`http://<host>/skywarnplus-ng/`** — no port in the path. Default **`base_path`** is **`/skywarnplus-ng`**. On Apache nodes, the **`.deb`** installs **`config/apache/skywarnplus-ng-proxy.conf`** and runs **`a2enconf`**. For **nginx** or Nginx Proxy Manager, see **[nginx-proxy-manager-guide.md](nginx-proxy-manager-guide.md)**. For debugging without a proxy, the app listens on port **8100** locally (`http://127.0.0.1:8100/skywarnplus-ng/`); set **`base_path: ""`** if you expose **8100** directly.

## Documentation

| Topic | Guide |
|-------|--------|
| Debian / APT install, migrate from tarball | **[docs/debian.md](docs/debian.md)** |
| Push alerts, email, Discord, subscribers | **[docs/](docs/README.md)** |
| NWS county codes | [CountyCodes.md](CountyCodes.md) |
| nginx / NPM reverse proxy | [nginx-proxy-manager-guide.md](nginx-proxy-manager-guide.md) |

## Features

- NWS alert polling, voice announcements, tail messages, courtesy tones, ID changes
- Per-node counties, SkyDescribe DTMF (**841–849** by alert index), AlertScript
- Web dashboard with live status, health, logs, and configuration
- **PushOver** (global) and **Discord webhooks** (per-subscriber filters) on new alerts — see [docs/notifications-overview.md](docs/notifications-overview.md)
- Optional GPS mobile counties, quiet hours, NHC tropical cyclone advisories (1.1+)

## DTMF

**SkyDescribe:** codes **841–849** describe active alerts 1–9. Enable the menu paths on your node; DTMF only works for **currently active** alerts.

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
