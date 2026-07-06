# Debian package install

Prebuilt `.deb` packages for **AllStar Link 3** nodes. Supported architectures: **amd64** and **arm64** only. Install skips `pip` on the node.

New installs and upgrades should use the **hardenedpenguin APT repository** or a `.deb` from [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases). The release tarball **`install.sh`** flow is **deprecated** — see [Migrating from tarball](#migrating-from-tarball-installsh-to-apt).

## Prerequisites

- **asl3-asterisk** and **asl3-tts** (the package declares both as dependencies)
- User **`asterisk`** present (from ASL3)
- Piper voice models under **`/var/lib/piper-tts`** (installed by asl3-tts, supermon-ng, or the dashboard voice catalog)
- Outbound Internet for NWS API

### Debian suite packages (Bookworm vs Trixie)

AllStar Link 3 supports **Debian 12 Bookworm** and **Debian 13 Trixie**. Each release ships **two `.deb` variants** per architecture (ASL3-style revision tags):

| Package revision | Debian | Python runtime | Install when |
|------------------|--------|----------------|--------------|
| `*.deb12_*` | Bookworm (12) | 3.11 / `libpython3.11` | Raspberry Pi / nodes on Bookworm |
| `*.deb13_*` | Trixie (13) | 3.13 / `libpython3.13` | Nodes on Trixie |

Example filenames: `skywarnplus-ng_1.6.0-1.deb12_arm64.deb`, `skywarnplus-ng_1.6.0-1.deb13_amd64.deb`.

Install the variant that matches your OS. Bookworm nodes **cannot** install the `.deb13` package (apt requires `libpython3.13`, which is not in Bookworm). Trixie nodes should use `.deb13`.

Runtime libraries are declared in the package (`libpython3.11` or `libpython3.13`, `libsndfile1`, `ffmpeg`, `sox`, `wget`, etc.). The bundled venv uses a copied Python binary that requires the matching system **`libpython`** shared library.

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

Download the `.deb` that matches your **Debian suite** and architecture from [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases):

- **Bookworm (Debian 12):** `skywarnplus-ng_*_deb12_<arch>.deb`
- **Trixie (Debian 13):** `skywarnplus-ng_*_deb13_<arch>.deb`

```bash
# Bookworm example (arm64 Pi):
sudo apt install ./skywarnplus-ng_*_deb12_arm64.deb

# Trixie example (amd64):
sudo apt install ./skywarnplus-ng_*_deb13_amd64.deb
sudo systemctl status skywarnplus-ng
```

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

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Depends: libpython3.13` but Bookworm has only 3.11 | Install the **`.deb12`** package (Bookworm build), not `.deb13`. See [Debian suite packages](#debian-suite-packages-bookworm-vs-trixie). |
| `libpython3.13.so.1.0: cannot open shared object file` | Wrong package variant for your OS, or missing runtime: `sudo apt install libpython3.13` (Trixie) / `libpython3.11` (Bookworm), then restart. |
| `skywarnplus-ng: bad interpreter` (CI path in shebang) | Upgrade to a package built with `fix-venv-paths.sh`, or use `venv/bin/python -m skywarnplus_ng.cli` (same as systemd). |

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

Native **amd64** or **arm64** host. Build one suite or both:

```bash
sudo apt install devscripts debhelper build-essential python3 python3-pip python3-venv curl

# Bookworm package (Python 3.11, revision .deb12):
SKYWARN_DEB_SUITE=bookworm ./scripts/build_deb.sh bookworm

# Trixie package (Python 3.13, revision .deb13):
./scripts/build_deb.sh trixie

# Both suites:
./scripts/build_debs_all.sh
```

Requires **python3.11** on the builder for Bookworm packages and **python3.13** for Trixie (CI uses `actions/setup-python`).

Output: `dist/debs/skywarnplus-ng_*_deb12_<arch>.deb` and/or `*_deb13_<arch>.deb`.

Release tags build all four combinations in CI (amd64/arm64 × bookworm/trixie) and attach `.deb` files to GitHub Releases.
