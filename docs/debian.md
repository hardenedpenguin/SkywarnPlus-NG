# Debian package install

Prebuilt `.deb` packages for **AllStar Link 3** nodes. Supported architectures: **amd64** and **arm64** only. Install skips `pip` on the node.

New installs and upgrades should use the **hardenedpenguin APT repository** or a `.deb` from [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases). The release tarball **`install.sh`** flow is **deprecated** — see [Migrating from tarball](#migrating-from-tarball-installsh-to-apt).

## Prerequisites

- **asl3-asterisk** and **asl3-tts** (the package declares both as dependencies)
- User **`asterisk`** present (from ASL3)
- Piper voice models under **`/var/lib/piper-tts`** (installed by asl3-tts, supermon-ng, or the dashboard voice catalog)
- Outbound Internet for NWS API

Runtime libraries are declared in the package (`libsndfile1`, `ffmpeg`, `sox`, `wget`, etc.).

## APT repository

Published packages are in the [hardenedpenguin APT repository](https://hardenedpenguin.github.io/hardenedpenguin-apt/) (`stable`, **amd64** / **arm64**). New releases are published there automatically when a `v*` tag is pushed.

One-time setup:

```bash
cd /tmp
curl -fsSLO https://hardenedpenguin.github.io/hardenedpenguin-apt/pool/main/h/hardenedpenguin-archive-keyring/hardenedpenguin-archive-keyring_1.0_all.deb
sudo apt install ./hardenedpenguin-archive-keyring_1.0_all.deb
sudo apt update
```

The `hardenedpenguin-archive-keyring` package installs the GPG key and `/etc/apt/sources.list.d/hardenedpenguin.list`.

Install or upgrade:

```bash
sudo apt install skywarnplus-ng
sudo systemctl enable --now skywarnplus-ng
```

## Install from GitHub Releases

Download `skywarnplus-ng_*_<arch>.deb` from [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases):

```bash
sudo apt install ./skywarnplus-ng_*_amd64.deb
sudo systemctl status skywarnplus-ng
```

Replace `amd64` with `arm64` on ARM nodes.

## Migrating from tarball (`install.sh`) to apt

Do **not** mix re-running `install.sh` and `dpkg` upgrades on the same tree. To move from a tarball install:

1. **Back up** config and data (optional but recommended):

   ```bash
   sudo tar -czf /root/skywarnplus-ng-pre-apt-backup.tar.gz \
     /etc/skywarnplus-ng/config.yaml \
     /var/lib/skywarnplus-ng/data
   ```

2. **Stop** the service so port 8100 is free (the package refuses to configure while it is in use):

   ```bash
   sudo systemctl stop skywarnplus-ng
   ```

3. **Add the APT repository** if not already configured (see [APT repository](#apt-repository) above), then **install** the package:

   ```bash
   sudo apt install skywarnplus-ng
   ```

   Or install a `.deb` from [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases) with `sudo apt install ./skywarnplus-ng_*_arm64.deb`.

4. **Restore** is rarely needed — paths match the tarball layout. If something went wrong:

   ```bash
   sudo tar -xzf /root/skywarnplus-ng-pre-apt-backup.tar.gz -C /
   ```

5. **Enable and start:**

   ```bash
   sudo systemctl enable --now skywarnplus-ng
   ```

You do **not** need to remove the old tarball tree under `$HOME` or wipe `/var/lib/skywarnplus-ng/data/`. Config and alert history under `/etc/skywarnplus-ng/` and `/var/lib/skywarnplus-ng/data/` are preserved.

## Configuration

- Live config: `/etc/skywarnplus-ng/config.yaml` (created on first install from the example; **not** overwritten on upgrade)
- Example defaults: `/etc/skywarnplus-ng/config.yaml.example` (updated each package upgrade)
- Data/state: `/var/lib/skywarnplus-ng/data/` (not removed on upgrade or purge)

On first install, `config.yaml` is created from the shipped example. On upgrade, existing `config.yaml` is kept; check `.example` for new options.

## Upgrade

**APT repository:**

```bash
sudo apt update
sudo apt install skywarnplus-ng
```

**Or** a newer `.deb` from Releases:

```bash
sudo apt install ./skywarnplus-ng_<new>_<arch>.deb
```

The virtualenv is replaced; your config and data directory are kept.

## Remove

```bash
sudo apt remove skywarnplus-ng
```

`apt purge` removes packaged files. **`config.yaml` and data under `/var/lib/skywarnplus-ng/data/` are kept** unless you remove them manually.

## vs tarball + install.sh

| | Tarball `install.sh` (deprecated) | `.deb` |
|--|-----------------------------------|--------|
| pip on node | Yes | No |
| TTS | asl3-tts + `/var/lib/piper-tts` | `Depends: asl3-tts` |
| Voice install sudoers | Not reliably updated | Shipped in package |
| Port 8100 check | Fails install if busy | Same (postinst) |
| Apache setup | With warnings | Same |
| ASL3 | Manual asterisk check | `Depends: asl3-asterisk` |

Tarball `install.sh` remains in the repo for developers and non-Debian systems only.

## Build (maintainers)

Native **amd64** or **arm64** host:

```bash
sudo apt install devscripts debhelper build-essential python3 python3-pip python3-venv curl
./scripts/build_deb.sh
```

Output: `dist/debs/skywarnplus-ng_*_<arch>.deb` (one package per architecture).

Release tags build both architectures in CI and attach `.deb` files to GitHub Releases.
