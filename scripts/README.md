# SkywarnPlus-NG Scripts

Development and utility scripts. Run from the project root unless noted.

## Packaging / Debian

| Script | Purpose |
|--------|---------|
| `scripts/build_deb.sh` / `build_debs_all.sh` | Build `.deb` packages |
| `scripts/debian/*` | Suite prep, venv staging, `base_path` migration, changelog sync |

## Asterisk / DTMF

### `generate_dtmf_conf.py`

Generates Asterisk custom DTMF include files (used by the Debian postinst).

```bash
python3 scripts/generate_dtmf_conf.py --help
```

### `test_asterisk_integration.py`

Checks config, sound files, and DTMF-related wiring.

```bash
python3 scripts/test_asterisk_integration.py
```

Service restarts use systemd: `sudo systemctl restart skywarnplus-ng`.

## Notifications

### `test_pushover.py`

```bash
python3 scripts/test_pushover.py <API_TOKEN> <USER_KEY>
```

Create an application at https://pushover.net/apps/build. You can also configure PushOver in the dashboard under **Monitoring → PushOver**.

## Other

| Script | Purpose |
|--------|---------|
| `parse_county_codes.py` | County code list helpers |
| `set_config_asl_tts.py` | Point TTS at asl-tts / Piper |
| `test_asl_tts.py` | TTS smoke test |
| `custom_alertscript.py` | Example AlertScript |
| `install-tts-voice.sh` | Privileged Piper voice install helper |

## Notes

- Prefer configuration via the web dashboard and `/etc/skywarnplus-ng/config.yaml` on packaged installs.
- Ensure `skywarnplus-ng` is on `PATH` for the `asterisk` user when testing DTMF from the node.
