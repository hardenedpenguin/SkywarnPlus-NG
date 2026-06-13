# Debian package install

Prebuilt `.deb` packages for **AllStar Link 3** nodes. Supported architectures: **amd64** and **arm64** only. Install skips `pip` and Hugging Face downloads on the node.

## Prerequisites

- **asl3-asterisk** already installed (package depends on it; does not install Asterisk for you)
- User **`asterisk`** present (from ASL3)
- Outbound Internet for NWS API

Runtime libraries are declared in the package (`libgomp1`, OpenBLAS, `libsndfile1`, `ffmpeg`, `sox`, etc.).

## Install (release assets)

From [GitHub Releases](https://github.com/hardenedpenguin/SkywarnPlus-NG/releases), pick your architecture:

**One-step (app + default Piper voice):**

```bash
sudo apt install ./skywarnplus-ng-all_1.2.0_amd64.deb
sudo systemctl status skywarnplus-ng
```

**Or install components separately:**

```bash
sudo apt install ./skywarnplus-ng_1.2.0_amd64.deb ./skywarnplus-ng-voice-en-us-amy-low_1.2.0_amd64.deb
```

Replace `amd64` with `arm64` on ARM nodes.

## Migrating from tarball (`install.sh`)

If SkywarnPlus-NG is already running from a release tarball, **stop the service before installing the deb**. The package refuses to configure while port 8100 is in use, and tarball installs are not stopped automatically by `apt`.

```bash
sudo systemctl stop skywarnplus-ng
sudo apt install ./skywarnplus-ng-all_1.2.0_amd64.deb
sudo systemctl enable --now skywarnplus-ng
```

You do **not** need to remove the old install, delete `config.yaml`, or wipe `/var/lib/skywarnplus-ng/data/`. The deb uses the same paths; config and alert history are preserved. Optional cleanup afterward: remove leftover `/var/lib/skywarnplus-ng/src/` from the tarball layout (the deb ships only the venv).

## Packages

| Package | Contents |
|---------|----------|
| `skywarnplus-ng` | Prebuilt venv, SOUNDS, scripts, systemd, logrotate, Apache proxy snippet |
| `skywarnplus-ng-voice-en-us-amy-low` | Piper `en_US-amy-low` model files |
| `skywarnplus-ng-all` | Metapackage: installs both of the above |

## Configuration

- Live config: `/etc/skywarnplus-ng/config.yaml` (created on first install from the example; **not** overwritten on upgrade)
- Example defaults: `/etc/skywarnplus-ng/config.yaml.example` (updated each package upgrade)
- Data/state: `/var/lib/skywarnplus-ng/data/` (not removed on upgrade or purge)

On first install, `config.yaml` is created from the shipped example. On upgrade, existing `config.yaml` is kept; check `.example` for new options.

## Upgrade

```bash
sudo apt install ./skywarnplus-ng-all_<new>_amd64.deb
```

The virtualenv is replaced; your config and data directory are kept.

## Remove

```bash
sudo apt remove skywarnplus-ng-all   # or skywarnplus-ng
```

`apt purge` removes packaged files. **`config.yaml` and data under `/var/lib/skywarnplus-ng/data/` are kept** unless you remove them manually.

## vs tarball + install.sh

| | Tarball `install.sh` | `.deb` |
|--|---------------------|--------|
| pip on node | Yes | No |
| Piper model | Download at install | Separate voice deb (or use `-all`) |
| Port 8100 check | Fails install if busy | Same (postinst) |
| Apache setup | With warnings | Same |
| ASL3 | Manual asterisk check | `Depends: asl3-asterisk` |

Tarball install remains supported for development and non-Debian systems.

## Build (maintainers)

Native **amd64** or **arm64** host:

```bash
sudo apt install devscripts debhelper build-essential python3 python3-pip python3-venv curl
./scripts/build_deb.sh
```

Output: `dist/debs/*.deb` (three packages per architecture).

Release tags build both architectures in CI and attach `.deb` files to GitHub Releases.
