# SkywarnPlus-NG

![GitHub total downloads](https://img.shields.io/github/downloads/hardenedpenguin/SkywarnPlus-NG/total?style=flat-square)

Modern weather alert system for Asterisk/app_rpt nodes with DTMF integration.

<p align="center">
  <a href="SkywarnPlus-ng.png"><img src="SkywarnPlus-ng.png" alt="SkywarnPlus-NG Dashboard" width="400"></a>
  <a href="SkywarnPlus-ng-1.png"><img src="SkywarnPlus-ng-1.png" alt="SkywarnPlus-NG Dashboard" width="400"></a>
</p>

*Click the thumbnails above to view full-size dashboard screenshots*

## About

SkywarnPlus-NG is a complete rewrite of the original [SkywarnPlus](https://github.com/Mason10198/SkywarnPlus) project by [Mason Nelson (N5LSN/WRKF394)](https://github.com/Mason10198). This rewrite modernizes the codebase, adds a web dashboard, and improves maintainability while preserving the core concept and functionality of the original project. We extend our gratitude to Mason Nelson for the original idea and implementation that inspired this project.

### What's New in 1.0.5

- **Dashboard login**: bcrypt password handling (including `$2y$` hashes for supermon-ng/PHP compatibility); plaintext passwords are not written to config.
- **Dashboard**: Built-in Tailwind CSS (no production CDN), clearer WebSocket behavior behind reverse proxies, version shown on the main dashboard.
- **Security**: Rate limits on login and config API; subscriber webhook URLs validated (HTTPS, no private/loopback hosts).

## Before you install (read this first)

These trip people up most often:

| Topic | What to know |
|--------|----------------|
| **Asterisk user** | The installer expects the **`asterisk`** user to exist (standard on AllStar / Asterisk nodes). Install Asterisk first, or the script will exit with an error. |
| **Do not run `install.sh` as root** | Run it as a normal user; the script uses `sudo` where needed. |
| **Python** | **Python 3.11 or newer** is required. Debian 13 ships **Python 3.13**, which is what we test most. |
| **Release tarball** | Use a [GitHub release](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases) tarball. The repo includes a pre-built `tailwind.css`; if you build from a **minimal** git checkout without that file, the installer will warn you—run `npm install && npm run build:css` (see [Web dashboard CSS](#web-dashboard-css-for-developers)) and copy `src/` again, or use an official release. |

## Quick Start

```bash
# Download the release tarball (replace version if newer)
wget https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/download/v1.0.5/skywarnplus-ng-1.0.5.tar.gz

# Optional: verify checksum from the release page
sha256sum skywarnplus-ng-1.0.5.tar.gz

# Extract and run the installer (will prompt for sudo where required)
tar -xzf skywarnplus-ng-1.0.5.tar.gz
cd skywarnplus-ng-1.0.5
./install.sh

# Enable and start the service
sudo systemctl enable skywarnplus-ng
sudo systemctl start skywarnplus-ng
sudo systemctl status skywarnplus-ng
```

**Then open the dashboard** (on the machine or remotely if the firewall allows it):

- URL: **`http://<host>:8100`** (default port **8100**)
- Default login: **`admin`** / **`skywarn123`** — **change this immediately** under Configuration.

> **Firewall:** For remote access, allow the dashboard port, e.g. `sudo ufw allow 8100/tcp`.

> **Configuration file:** The live config is **`/etc/skywarnplus-ng/config.yaml`**. The UI saves changes there; advanced users can edit YAML directly (restart the service after manual edits if needed).

## Where things live (reference)

| Item | Typical path |
|------|----------------|
| Application code | `/var/lib/skywarnplus-ng/src/` |
| Python virtualenv | `/var/lib/skywarnplus-ng/venv/` |
| Config | `/etc/skywarnplus-ng/config.yaml` |
| Data (state, tail audio, etc.) | `/var/lib/skywarnplus-ng/data/` |
| Application log file | `/var/log/skywarnplus-ng/skywarnplus-ng.log` |
| systemd unit | `skywarnplus-ng.service` |
| DTMF / SkyDescribe fragment | `/etc/asterisk/custom/rpt/skydescribe.conf` |
| Sounds (installed) | `/var/lib/skywarnplus-ng/SOUNDS/` |

**CLI (after install):** the `skywarnplus-ng` console script is installed into the venv. Examples:

```bash
sudo -u asterisk /var/lib/skywarnplus-ng/venv/bin/skywarnplus-ng --help
# Describe first active alert (same idea as DTMF describe)
sudo -u asterisk /var/lib/skywarnplus-ng/venv/bin/skywarnplus-ng describe 1
```

Day-to-day operation uses **`systemctl`**; the service runs `skywarnplus_ng.cli run` with your config.

## Requirements

- 64-bit Linux ( **Debian 13** is the reference platform )
- **Python 3.11+** with `python3-venv`, `python3-dev`
- GCC toolchain (`build-essential` or `gcc` / `g++`)
- Packages the installer pulls on Debian: `ffmpeg`, `sox`, `libsndfile1`, `libopenblas0`, `libgomp1`, `libffi-dev`, `libssl-dev`, `libasound2-dev`, `portaudio19-dev`, `curl`, etc.
- **`asterisk` user** (install Asterisk / ASL first)
- Outbound Internet (NWS API; optional gTTS, Pushover, webhooks)

On other distributions, install the equivalent packages, then run `./install.sh`.

## Installation steps (detail)

1. **Download** the `.tar.gz` for your version from [Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases). Verify **SHA256** on the release page if you use checksums.

2. **Extract and install**
   ```bash
   tar -xzf skywarnplus-ng-1.0.5.tar.gz
   cd skywarnplus-ng-1.0.5
   ./install.sh
   ```
   This creates directories, copies `src/` and `pyproject.toml`, creates the venv, installs the package, seeds **`/etc/skywarnplus-ng/config.yaml`** from `config/default.yaml` **only if** that file does not exist, generates `skydescribe.conf`, installs systemd + logrotate, and tries to free port **8100** if something else is using it.

3. **Start the service**
   ```bash
   sudo systemctl enable skywarnplus-ng
   sudo systemctl start skywarnplus-ng
   ```

4. **Configure** — see [First-time dashboard configuration](#first-time-dashboard-configuration) below.

### Reinstall / upgrade from a newer tarball

- Extract a **new** release directory and run `./install.sh` again.
- If **`/etc/skywarnplus-ng/config.yaml` already exists**, the installer **keeps** your config and writes an updated example to **`config.yaml.example`** for comparison.
- After upgrading, restart: **`sudo systemctl restart skywarnplus-ng`**.

## First-time dashboard configuration

1. Open **`http://<hostname>:8100`** (or your HTTPS reverse-proxy URL).
2. Log in with **`admin` / `skywarn123`**, then go to **Configuration** and set a **new password** (stored as a bcrypt hash).
3. **Counties:** Add or enable the [NWS county codes](CountyCodes.md) you need. Example codes in the default YAML are placeholders—replace with your area.
4. **Asterisk:** Set your **node number(s)** and, if you use multiple nodes with different areas, per-node counties (see [Multi-node](#multi-node-deployments)).
5. **Audio / TTS:** Choose **gTTS** (default) or **Piper** if you installed the Piper model during setup.
6. **Alerts & filtering:** Tune tail message, courtesy tones, ID change, blocked events, etc., as needed.
7. **Save** from the UI; changes go to **`/etc/skywarnplus-ng/config.yaml`**.

The main dashboard shows the **running app version** (from the installed package) so you can confirm what build is live.

## Configuration (concepts that confuse people)

### Dashboard auth

- Auth is **on** by default (`monitoring.http_server.auth` in YAML).
- Passwords in config are **bcrypt** hashes; the UI hashes new passwords for you.
- **Session** duration is configurable (e.g. `session_timeout_hours`).

### `base_path` and reverse proxies

If the app is served at **`https://example.com/skywarnplus-ng/`** (not at the domain root):

1. Set **`monitoring.http_server.base_path`** to **`/skywarnplus-ng`** (leading slash, **no** trailing slash) in **`config.yaml`** or the Configuration UI.
2. Your proxy must **strip** that prefix when forwarding to the app (so the app still sees paths like `/`, `/ws`, `/api/...`).
3. **WebSockets** must be proxied (Upgrade headers). **Nginx** often needs long **`proxy_read_timeout` / `proxy_send_timeout`** for `/ws` or the browser will reconnect in a loop.

Step-by-step for **Nginx Proxy Manager**: see **[nginx-proxy-manager-guide.md](nginx-proxy-manager-guide.md)** (includes rewrite + WebSocket + timeout snippet).

After changing **`base_path` or proxy settings**, restart: **`sudo systemctl restart skywarnplus-ng`**.

### Polling and NWS

- **`poll_interval`** (seconds) controls how often alerts are fetched (default **60** in `default.yaml`).
- The app identifies itself to api.weather.gov with a **`User-Agent`**; do not use a generic placeholder that violates NWS policy.

### Email notifications (Gmail)

Use a Google **App Password**, not your normal Gmail password. Enable **2-Step Verification**, then create an App Password under **Security** and paste it into the dashboard email settings.

### Piper TTS (optional)

The installer downloads **en_US-amy** (low quality by default) under **`/var/lib/skywarnplus-ng/piper/`**. For **medium** quality: `PIPER_QUALITY=medium ./install.sh`. In the UI, select **Piper** and leave model path empty to use the default install path.

### Multi-node deployments

Configure which counties each Asterisk node monitors so one server can serve different regions:

- **Web UI:** Configuration → Asterisk → per-node counties.
- **YAML:** See commented examples in **`config/default.yaml`**.

## Features

- **Weather Alerts**: Real-time NWS alert monitoring and voice announcements
- **Per-Node Counties**: Different county sets per node (multi-site from one server)
- **SkyDescribe DTMF**: On-demand descriptions for active alerts (`841`–`849` by index, plus configurable `*1`–`*5` style codes in config)
- **Web Dashboard**: Responsive UI, live updates, health/metrics/logs/database views
- **Tail Messages**, **Courtesy Tones**, **ID Changes**, **AlertScript**, **County Audio**
- **Notifications**: Email, Pushover, webhooks (with HTTPS / SSRF-safe URL rules for subscriber webhooks)

## DTMF Commands

SkyDescribe maps **841–849** to describe active alerts **by index (1–9)**. Those codes are written to **`/etc/asterisk/custom/rpt/skydescribe.conf`** during install; you still enable the menu paths on your node (e.g. ASL-menu).

**CLI alternative:**

```bash
skywarnplus-ng describe 1                    # 1st active alert by index
skywarnplus-ng describe "Tornado Warning"    # All alerts with this title
```

> **Important:** DTMF only describes **currently active** alerts. Ensure SkywarnPlus-NG is running, counties are configured, and SkyDescribe is enabled for your node.

## Service management & logs

```bash
sudo systemctl restart skywarnplus-ng
sudo systemctl status skywarnplus-ng
journalctl -u skywarnplus-ng -f
```

File logging (if enabled) is under **`/var/log/skywarnplus-ng/`** per `logging.file` in config.

## Common issues

| Symptom | Things to check |
|---------|------------------|
| **`install.sh` fails: asterisk user missing** | Install Asterisk / ASL so user **`asterisk` exists**. |
| **Port 8100 in use** | The installer tries to clear it; otherwise run `sudo ss -tulpn` and find the process on 8100, or change **`monitoring.http_server.port`** in config. |
| **404 or wrong paths behind nginx** | **`base_path`** must match the public URL prefix; proxy must **strip** the prefix; see [nginx-proxy-manager-guide.md](nginx-proxy-manager-guide.md). |
| **Dashboard reconnects / many `/ws` lines in logs** | Add long **`proxy_*_timeout`** for the WebSocket location and ensure **`base_path`** matches; the app sends protocol-level WebSocket pings to help idle proxies. |
| **Cannot log in after editing YAML** | Password must be a **bcrypt** hash if set manually; easiest fix is to set password again from the UI or restore from backup. |
| **“Dashboard stylesheet missing” during install** | Use an official release tarball or run **`npm install && npm run build:css`** before packaging (see below). |

## Web dashboard CSS (for developers)

The dashboard ships with a pre-built Tailwind stylesheet at **`src/skywarnplus_ng/web/static/tailwind.css`** (no runtime CDN). If you change HTML under **`src/skywarnplus_ng/web/templates/`**, rebuild:

```bash
npm install
npm run build:css
```

## License

MIT License - see LICENSE file for details.
