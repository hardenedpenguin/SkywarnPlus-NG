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

Per-version changes are described on [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases) (generated release notes and assets).

## Before you install (read this first)

These trip people up most often:

| Topic | What to know |
|--------|----------------|
| **Asterisk user** | The installer expects the **`asterisk`** user to exist (standard on AllStar / Asterisk nodes). Install Asterisk first, or the script will exit with an error. |
| **Do not run `install.sh` as root** | Run it as a normal user; the script uses `sudo` where needed. |
| **Python** | **Python 3.11 or newer** is required. Debian 13 ships **Python 3.13**, which is what we test most. |
| **`/var/tmp` and pip temp space** | **`install.sh`** sets **`TMPDIR`** to **`/var/tmp`** (overridable with **`SKYWARN_TMPDIR`**) while creating the venv and running **pip**, so large wheels (e.g. **numpy** / **piper** deps) do not fill a small **`/tmp`** tmpfs. **`/var/tmp`** should be **disk-backed** and have enough free space. If **`/var/tmp`** is tmpfs or too small, set e.g. **`SKYWARN_TMPDIR=/var/lib/skywarnplus-ng/tmp`** and create that directory before installing. |
| **Release tarball** | Use a [GitHub release](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases) tarball. The repo includes a pre-built `tailwind.css`; if you build from a **minimal** git checkout without that file, the installer will warn you—run `npm install && npm run build:css` (see [Web dashboard CSS](#web-dashboard-css-for-developers)) and copy `src/` again, or use an official release. |

## Quick Start

```bash
# Download the release tarball (replace version if newer)
wget https://github.com/hardenedpenguin/SkywarnPlus-NG/releases/download/v1.1.0/skywarnplus-ng-1.1.0.tar.gz

# Optional: verify checksum from the release page
sha256sum skywarnplus-ng-1.1.0.tar.gz

# Extract and run the installer (will prompt for sudo where required)
tar -xzf skywarnplus-ng-1.1.0.tar.gz
cd skywarnplus-ng-1.1.0
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
| Installed Python package (what the service runs) | `/var/lib/skywarnplus-ng/venv/lib/python3.*/site-packages/skywarnplus_ng/` (printed at end of `install.sh`) |
| Source copy (reference / dev) | `/var/lib/skywarnplus-ng/src/` |
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
- Outbound Internet (NWS API; optional cloud gTTS if you use it, Pushover, webhooks)

On other distributions, install the equivalent packages, then run `./install.sh`.

## Installation steps (detail)

**Filesystem / temp:** **`install.sh`** uses **`TMPDIR=${SKYWARN_TMPDIR:-/var/tmp}`** for **pip** and the venv so downloads are not written to a tiny **`/tmp`** tmpfs (common on ARM/ASL nodes). Use a disk-backed, spacious **`/var/tmp`**, or override **`SKYWARN_TMPDIR`**. See the table in [Before you install](#before-you-install-read-this-first).

1. **Download** the `.tar.gz` for your version from [Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases). Verify **SHA256** on the release page if you use checksums.

2. **Extract and install**
   ```bash
   tar -xzf skywarnplus-ng-1.1.0.tar.gz
   cd skywarnplus-ng-1.1.0
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
- **`install.sh`** runs **`pip install --upgrade --upgrade-strategy eager .`** so existing virtualenvs pick up **newer dependency releases** that still match **`pyproject.toml`**, not only the minimum versions that already satisfied the old install.
- The running service loads Python from the **venv site-packages** path printed at the end of install—not from **`/var/lib/skywarnplus-ng/src/`** alone. Hotfixes must update that package or re-run **`pip install`** from the install directory.
- If **`/etc/skywarnplus-ng/config.yaml` already exists**, the installer **keeps** your config and writes an updated example to **`config.yaml.example`** for comparison.
- After upgrading, restart: **`sudo systemctl restart skywarnplus-ng`**.

## First-time dashboard configuration

1. Open **`http://<hostname>:8100`** (or your HTTPS reverse-proxy URL).
2. Log in with **`admin` / `skywarn123`**, then go to **Configuration** and set a **new password** (stored as a bcrypt hash).
3. **Counties:** Add or enable the [NWS county codes](CountyCodes.md) you need. Example codes in the default YAML are placeholders—replace with your area.
4. **Asterisk:** Set your **node number(s)** and, if you use multiple nodes with different areas, per-node counties (see [Multi-node](#multi-node-deployments)).
5. **Audio / TTS:** Default is **Piper** (local). Use **gTTS** in the UI if you prefer cloud synthesis.
6. **Alerts & filtering:** Tune tail message, courtesy tones, ID change, blocked events, etc., as needed.
7. **Save** from the UI; changes go to **`/etc/skywarnplus-ng/config.yaml`**.

The main dashboard shows the **running app version** (from the installed package) so you can confirm what build is live.

**Release notices (on by default):** In **Configuration → Monitoring → Software updates (advisory)**, **Check GitHub for newer releases** is enabled by default. The app contacts the public GitHub API (at most about once per day by default), compares your installed version to the latest release, and shows a **banner on the dashboard** if a newer version exists. **Uncheck** the option to opt out. It does **not** download or install anything; upgrade steps stay the same as [Reinstall / upgrade from a newer tarball](#reinstall--upgrade-from-a-newer-tarball) above.

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
- **Failed NWS fetch:** If a poll cannot reach the API (network error, timeout, etc.), the app **keeps the previous alert list** and logs a warning. The dashboard shows an **NWS feed warning** banner with the time of the failure until the next **successful** fetch. Check **`journalctl -u skywarnplus-ng`** for details.
- **`alerts.time_type`:** With **`onset`**, an alert’s active window uses **`onset`** … **`ends`** (if present) else **`expires`**. With **`effective`**, the window uses **`effective`** … **`expires`**. The UI may show an **Expires** time that differs from **`ends`**; cancellation products with **`urgency: Past`** (or “cancelled” in the headline) are **dropped immediately** and are not held until **`ends`**.

### Email notifications (Gmail)

Use a Google **App Password**, not your normal Gmail password. Enable **2-Step Verification**, then create an App Password under **Security** and paste it into the dashboard email settings.

### Webhooks (how they work, how to configure, how to test)

SkywarnPlus-NG can send **outbound HTTP callbacks** (webhooks) when an alert is generated. This is useful for:

- **Discord / Slack / Teams**: post a message into a channel
- **Home automation**: call Node-RED / Home Assistant / custom endpoints
- **Logging/monitoring**: ship “an alert happened” events to another system

Important details that often confuse people:

- **Webhooks are outbound**: SkywarnPlus-NG makes an HTTPS `POST` request *from the server* to your URL.
- **Webhooks are per-subscriber**: you add a subscriber and (optionally) give them a `webhook_url`. The subscriber must also have the **Webhook** delivery method enabled in their preferences.
- **HTTPS is required** for subscriber webhooks. The server rejects `http://...` and blocks obvious local/private targets (e.g. `localhost`, `192.168.x.x`, `10.x.x.x`) to reduce SSRF risk.

#### Configure a webhook (recommended approach)

1. Go to **Configuration → Subscribers**.
2. **Add Subscriber** (name + email are required; the email is just an identifier).
3. Paste your **Webhook URL** into the subscriber’s **Webhook URL** field.
4. In that subscriber’s methods, **enable “webhook”** (and optionally disable email if you only want webhook delivery).
5. (Optional) Set per-county filtering on the subscriber so they only get the counties you care about.
6. Save.

> Discord note: This project treats Discord as “a webhook URL you POST JSON to”. The simplest setup is still via **Subscribers** so you can filter per-county and avoid duplicates.

#### What gets sent

Subscriber webhooks use a **generic JSON payload** (content-type `application/json`). Your endpoint should accept a JSON `POST` and return HTTP **200** or **204**.

At minimum, expect fields like:

- `title`: notification title
- `message`: notification body (text)
- `timestamp`: ISO8601 UTC time
- `source`: `SkywarnPlus-NG`

#### Test your webhook end-to-end (works on any system)

The key is to test **from the SkywarnPlus-NG server**, because *that* is where the outbound request originates.

1. **Get a temporary capture URL**
   - Use a service like `webhook.site` (or any “request bin”) to get a unique HTTPS URL.
2. **Paste that URL** into a Subscriber’s **Webhook URL** and enable the webhook method.
3. **Generate a test alert**
   - Easiest: enable **DEV → Test alert injection** (Configuration → DEV / Test Injection) and wait for the next poll; the app will generate a fake “Tornado Warning”.
4. **Verify delivery**
   - In the request-bin UI, you should see an incoming `POST` from your server.
   - Also watch logs:

```bash
sudo journalctl -u skywarnplus-ng -f
```

If you don’t see requests arriving:

- **URL rejected immediately**: the log will mention the webhook URL was rejected (common causes: `http://` instead of `https://`, `localhost`, private IPs).
- **Firewall / outbound blocked**: ensure the server can reach the Internet on TCP 443.
- **Reverse proxy / local endpoints**: if your webhook target is on your LAN, you must expose it via a **public HTTPS** endpoint (or a proper tunnel) because private targets are blocked by design.

#### Test your endpoint directly (payload acceptance)

If you own the webhook receiver (Node-RED / custom API), you can also test it with `curl`:

```bash
curl -i -X POST "https://YOUR-WEBHOOK-URL-HERE" \
  -H "Content-Type: application/json" \
  -d '{"test":true,"message":"SkywarnPlus-NG manual webhook test"}'
```

For SkywarnPlus-NG delivery to count as success, your endpoint should respond with **HTTP 200 or 204**.

### Piper TTS (default)

The installer downloads **en_US-amy** (low quality by default) under **`/var/lib/skywarnplus-ng/piper/`**. For **medium** quality: `PIPER_QUALITY=medium ./install.sh` and set **`audio.tts.model_path`** to the matching **`.onnx`** file (or pick it in the UI). In the UI, you can leave the Piper model path empty to use the default install path.

More Piper voices (many languages) are published in **[rhasspy/piper-voices on Hugging Face](https://huggingface.co/rhasspy/piper-voices/tree/main)**. Download the **`.onnx`** and matching **`.onnx.json`** for a voice into your Piper directory, then reload the dashboard configuration page so the new model appears in the list.

### Multi-node deployments

Configure which counties each Asterisk node monitors so one server can serve different regions:

- **Web UI:** Configuration → Asterisk → per-node counties.
- **YAML:** See commented examples in **`config/default.yaml`**.

### AlertScript (BASH / DTMF)

- **BASH** commands run as **`/bin/bash -c`**. Placeholders **`{alert_title}`**, **`{alert_id}`**, **`{alert_event}`**, **`{alert_area}`**, **`{alert_counties}`** are filled from NWS data using **shell quoting**, so strange characters in alert text cannot break out of the substituted argument (command injection from CAP text is mitigated). Your **static** command text is still trusted—only insert placeholders where you intend NWS content.
- **DTMF** commands are sent to Asterisk **`rpt fun`**. After substitution, the string must match **digits and DTMF letters only** (`0-9`, `*`, `#`, `A`–`D`); longer or shell-like strings are **skipped** with a log line. Use **fixed** DTMF sequences in config; do not rely on **`{alert_event}`** for DTMF unless the substituted value is a safe sequence.

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
| **pip: No space left on device during install** | Often **`/tmp`** is a small tmpfs while **`df /`** looks fine. **`install.sh`** directs pip to **`/var/tmp`** via **`TMPDIR`**; confirm **`df -h /var/tmp`** (or set **`SKYWARN_TMPDIR`** to a directory on a large disk). |

## Development

From a git checkout (with **pip** and Python **3.11+**):

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pytest tests/ -v
```

CI runs **Ruff** (lint + format check), **mypy** on a small typed subset, and **pytest** on **Python 3.11–3.13** for pushes and pull requests to **`main`**.

Optional: install **[pre-commit](https://pre-commit.com/)** and run **`pre-commit install`** in this repo to run **Ruff** before each commit (see **`.pre-commit-config.yaml`**).

## Web dashboard CSS (for developers)

The dashboard ships with a pre-built Tailwind stylesheet at **`src/skywarnplus_ng/web/static/tailwind.css`** (no runtime CDN). If you change HTML under **`src/skywarnplus_ng/web/templates/`**, rebuild:

```bash
npm install
npm run build:css
```

## License

SkywarnPlus-NG is licensed under the **GNU General Public License v3.0 or later**. See the **[LICENSE](LICENSE)** file for the full text.
