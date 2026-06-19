"""
Config and county restore API handlers mixin.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from aiohttp.web import Request, Response

from ...audio.tts_voices import build_voices_payload, list_voice_models
from ..auth_security import incoming_sets_non_default_password
from ..setup_status import is_dashboard_configured
from ..config_merge import (
    deep_merge_dict,
    model_dump_for_merge,
    redact_config_for_api,
    resolve_config_path,
)

if TYPE_CHECKING:
    from ...core.config import AppConfig

logger = logging.getLogger(__name__)


def _sanitize_counties_list(raw: Any) -> list[dict[str, Any]]:
    """Drop null/invalid county entries; accept list or dict-with-numeric-keys from bad clients."""
    if raw is None:
        return []
    if isinstance(raw, dict):

        def _sort_key(k: object) -> tuple[int, int | str]:
            s = str(k)
            return (0, int(s)) if s.isdigit() else (1, s)

        raw = [raw[k] for k in sorted(raw.keys(), key=_sort_key)]
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if code is None:
            continue
        code_s = str(code).strip()
        if not code_s:
            continue
        name = item.get("name")
        name_s = str(name).strip() if name is not None else ""
        audio = item.get("audio_file")
        audio_s = str(audio).strip() if audio is not None else ""
        enabled = item.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("true", "1", "on", "yes")
        out.append(
            {
                "code": code_s,
                "name": name_s or None,
                "enabled": bool(enabled),
                "audio_file": audio_s or None,
            }
        )
    return out


def _list_piper_onnx_models(piper_dir: Path) -> list[str]:
    """Legacy alias: return absolute paths for voice basenames in piper_dir."""
    return [str(piper_dir / name) for name in list_voice_models(piper_dir)]


def _tts_voices_dir(config: Any) -> Path:
    tts = getattr(getattr(config, "audio", None), "tts", None)
    if tts and getattr(tts, "voices_dir", None):
        return Path(str(tts.voices_dir))
    return Path("/var/lib/piper-tts")


def _collect_runtime_warnings(config: Any) -> list[str]:
    """User-visible warnings for TTS/runtime dependencies."""
    warnings: list[str] = []
    tts = getattr(getattr(config, "audio", None), "tts", None)
    if not tts:
        return warnings

    engine = str(getattr(tts, "engine", "") or "").lower().replace("_", "-")
    if engine in ("asl-tts", "asltts", "piper"):
        binary = str(getattr(tts, "asl_tts_binary", "asl-tts") or "asl-tts")
        if not Path(binary).is_file() and not shutil.which(binary):
            warnings.append(
                f"asl-tts binary not found ({binary}). Install the asl3-tts package."
            )
        voices_dir = _tts_voices_dir(config)
        voice = str(getattr(tts, "voice", "") or "en_US-amy-low.onnx")
        if not (voices_dir / voice).is_file():
            warnings.append(
                f"Piper voice not found: {voices_dir / voice}. "
                "Install voices via asl3-tts or add .onnx + .onnx.json under "
                f"{voices_dir}."
            )

    return warnings


class ConfigApiMixin:
    def _reload_config_from_disk(self) -> Path:
        """Reload AppConfig from the configured YAML path into app + dashboard."""
        from ...core.config import AppConfig

        config_path = resolve_config_path(self.config)
        new_config = AppConfig.from_yaml(config_path)
        self.config = new_config
        if self.app:
            self.app.apply_runtime_config(new_config)
        return config_path

    def _write_config_yaml(self, updated_config: "AppConfig", config_path: Path) -> None:
        """Serialize AppConfig to YAML on disk (hash auth password, preserve quotes)."""
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.default_flow_style = False
        yaml.preserve_quotes = True
        yaml.width = 4096

        def convert_paths_for_yaml(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: convert_paths_for_yaml(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert_paths_for_yaml(item) for item in obj]
            if hasattr(obj, "__fspath__"):
                return str(obj)
            return obj

        serializable_config = convert_paths_for_yaml(updated_config.model_dump())

        try:
            pwd = getattr(
                getattr(getattr(updated_config.monitoring, "http_server", None), "auth", None),
                "password",
                "",
            )
            if isinstance(pwd, str) and pwd and not self._is_bcrypt_hash(pwd):
                pwd = self._hash_password(pwd)
                updated_config.monitoring.http_server.auth.password = pwd
            mon = serializable_config.setdefault("monitoring", {})
            http = mon.setdefault("http_server", {})
            auth = http.setdefault("auth", {})
            auth["password"] = pwd if isinstance(pwd, str) else ""
        except Exception as e:
            logger.warning("Could not set hashed auth password for write: %s", e)

        try:
            from ruamel.yaml.scalarstring import DoubleQuotedScalarString

            mon = serializable_config.get("monitoring")
            if isinstance(mon, dict):
                http = mon.get("http_server")
                if isinstance(http, dict):
                    auth = http.get("auth")
                    if isinstance(auth, dict) and isinstance(auth.get("password"), str):
                        auth["password"] = DoubleQuotedScalarString(auth["password"])
        except Exception:
            pass

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(serializable_config, f)

    def _serialize_asterisk_nodes(self, raw_nodes):
        """Convert asterisk.nodes (int | NodeConfig) to JSON-serializable list."""
        out = []
        for n in raw_nodes or []:
            if isinstance(n, int):
                out.append(n)
            elif hasattr(n, "model_dump"):
                out.append(n.model_dump())
            elif isinstance(n, dict):
                out.append(n)
            elif hasattr(n, "number"):
                out.append({"number": n.number, "counties": getattr(n, "counties", None)})
            else:
                continue
        return out

    async def api_config_get_handler(self, request: Request) -> Response:
        """Handle API config get endpoint."""
        try:
            # Convert config to dict and handle Path objects
            config_dict = self.config.model_dump()

            # Convert Path objects to strings for JSON serialization
            def convert_paths(obj):
                if isinstance(obj, dict):
                    return {k: convert_paths(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_paths(item) for item in obj]
                elif hasattr(obj, "__fspath__"):  # Path-like object
                    return str(obj)
                else:
                    return obj

            serializable_config = convert_paths(config_dict)

            # Ensure asterisk.nodes is JSON-serializable (NodeConfig -> dict)
            if "asterisk" in serializable_config and "nodes" in serializable_config["asterisk"]:
                raw = serializable_config["asterisk"]["nodes"]
                serializable_config["asterisk"]["nodes"] = self._serialize_asterisk_nodes(
                    raw if isinstance(raw, list) else [raw]
                )

            # asl-tts voice catalog for configuration UI
            voices_dir = _tts_voices_dir(self.config)
            tts = self.config.audio.tts
            default_voice = str(getattr(tts, "voice", "en_US-amy-low.onnx"))
            voices_payload = build_voices_payload(
                voices_dir=voices_dir,
                default_voice=default_voice,
            )
            serializable_config["tts_voices"] = voices_payload
            serializable_config["tts_voices_dir"] = voices_payload["voices_dir"]
            serializable_config["tts_default_voice"] = voices_payload["default"]
            serializable_config["tts_available_voices"] = list_voice_models(voices_dir)
            serializable_config["tts_voice_regions"] = voices_payload["regions"]
            serializable_config["piper_available_models"] = [
                str(voices_dir / name) for name in serializable_config["tts_available_voices"]
            ]
            serializable_config["piper_default_model_path"] = str(voices_dir / default_voice)

            # Suggest asl-tts node from first configured Asterisk node
            nodes = getattr(getattr(self.config, "asterisk", None), "nodes", None) or []
            default_node = getattr(tts, "node_number", None)
            if default_node is None and nodes:
                first = nodes[0]
                if isinstance(first, int):
                    default_node = first
                elif isinstance(first, dict):
                    default_node = first.get("number")
                elif hasattr(first, "number"):
                    default_node = first.number
            serializable_config["tts_default_node_number"] = default_node or 1

            serializable_config["runtime_warnings"] = _collect_runtime_warnings(self.config)
            serializable_config["auth_uses_default_password"] = (
                self.config.monitoring.http_server.auth.enabled
                and self._uses_default_dashboard_password()
            )
            serializable_config["is_configured"] = is_dashboard_configured(
                self.config, self._verify_password
            )

            return web.json_response(redact_config_for_api(serializable_config))
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_config_update_handler(self, request: Request) -> Response:
        """Handle API config update endpoint."""
        try:
            client_ip = self._client_ip(request)
            allowed, retry_after = await self._config_rate_limit.check(client_ip)
            if not allowed:
                headers = {}
                if retry_after is not None:
                    headers["Retry-After"] = str(max(1, int(retry_after) + 1))
                return web.json_response(
                    {"error": "Too many configuration saves. Try again later."},
                    status=429,
                    headers=headers,
                )

            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"error": "JSON body must be an object"}, status=400)

            if (
                self.config.monitoring.http_server.auth.enabled
                and self._uses_default_dashboard_password()
            ):
                if not incoming_sets_non_default_password(data, self._is_bcrypt_hash):
                    return web.json_response(
                        {
                            "error": (
                                "Change the default admin password "
                                "(Monitoring → Authentication) before saving other settings."
                            )
                        },
                        status=403,
                    )

            # Hash dashboard auth password if present and plaintext (so we never persist plaintext)
            self._ensure_auth_password_hashed_in_dict(data)

            # Dashboard may send sparse counties arrays (null holes) after row removal.
            if "counties" in data:
                data["counties"] = _sanitize_counties_list(data.get("counties"))

            # Validate the configuration data by creating a new AppConfig instance
            try:
                # Preserve base_path if not in incoming data (form doesn't include it)
                if (
                    "monitoring" not in data
                    or "http_server" not in data["monitoring"]
                    or "base_path" not in data["monitoring"]["http_server"]
                ):
                    # Preserve current base_path value
                    if "monitoring" not in data:
                        data["monitoring"] = {}
                    if "http_server" not in data["monitoring"]:
                        data["monitoring"]["http_server"] = {}
                    data["monitoring"]["http_server"]["base_path"] = (
                        self.config.monitoring.http_server.base_path or ""
                    )
                    logger.info(
                        f"Preserving base_path: {data['monitoring']['http_server']['base_path']}"
                    )

                # Handle password updates - if password is empty, keep the current password.
                # Hash any non-empty password before AppConfig sees it (avoids bcrypt 72-byte error).
                try:
                    mon = data.get("monitoring")
                    if isinstance(mon, dict):
                        http = mon.get("http_server")
                        if isinstance(http, dict):
                            auth = http.get("auth")
                            if isinstance(auth, dict) and "password" in auth:
                                new_password = auth["password"]
                                if not new_password or (
                                    isinstance(new_password, str) and new_password.strip() == ""
                                ):
                                    auth["password"] = (
                                        self.config.monitoring.http_server.auth.password
                                    )
                                    logger.info("Keeping current password (new password was empty)")
                                elif self._is_bcrypt_hash(new_password):
                                    # Already hashed by _ensure_auth_password_hashed_in_dict; do not hash again
                                    pass
                                else:
                                    raw = (
                                        new_password.strip()
                                        if isinstance(new_password, str)
                                        else str(new_password)
                                    )
                                    auth["password"] = self._hash_password(raw)
                                    logger.info("Updating password (stored as bcrypt hash)")
                except Exception as e:
                    logger.warning("Could not process password update: %s", e)

                # Handle PushOver credentials - keep current values if empty
                if "pushover" in data:
                    if "api_token" in data["pushover"] and (
                        not data["pushover"]["api_token"]
                        or data["pushover"]["api_token"].strip() == ""
                    ):
                        data["pushover"]["api_token"] = self.config.pushover.api_token
                        logger.info("Keeping current PushOver API token (new token was empty)")
                    if "user_key" in data["pushover"] and (
                        not data["pushover"]["user_key"]
                        or data["pushover"]["user_key"].strip() == ""
                    ):
                        data["pushover"]["user_key"] = self.config.pushover.user_key
                        logger.info("Keeping current PushOver user key (new key was empty)")

                # Handle empty optional Path/string fields - convert empty strings to None
                if "alerts" in data:
                    if "tail_message_path" in data["alerts"]:
                        if (
                            isinstance(data["alerts"]["tail_message_path"], str)
                            and data["alerts"]["tail_message_path"].strip() == ""
                        ):
                            data["alerts"]["tail_message_path"] = None
                    if "tail_message_suffix" in data["alerts"]:
                        if (
                            isinstance(data["alerts"]["tail_message_suffix"], str)
                            and data["alerts"]["tail_message_suffix"].strip() == ""
                        ):
                            data["alerts"]["tail_message_suffix"] = None
                    if "quiet_hours" in data["alerts"] and isinstance(
                        data["alerts"]["quiet_hours"], dict
                    ):
                        tz = data["alerts"]["quiet_hours"].get("timezone")
                        if isinstance(tz, str) and tz.strip() == "":
                            data["alerts"]["quiet_hours"]["timezone"] = None

                if "nhc" in data and isinstance(data["nhc"], dict):
                    for coord in ("static_lat", "static_lon"):
                        if coord in data["nhc"] and isinstance(data["nhc"][coord], str):
                            if data["nhc"][coord].strip() == "":
                                data["nhc"][coord] = None

                if "gpsd" in data and isinstance(data["gpsd"], dict):
                    acc = data["gpsd"].get("min_accuracy_meters")
                    if isinstance(acc, str) and acc.strip() == "":
                        data["gpsd"]["min_accuracy_meters"] = None

                # Normalize empty numeric strings from form (form sends '' for untouched fields)
                _numeric_defaults = {
                    "alerts": {"announcement_hold_minutes": 0},
                    "audio": {"tts": {"speed": 1.0, "sample_rate": 22050, "bit_rate": 128}},
                    "filtering": {"max_alerts": 99},
                    "gpsd": {
                        "port": 2947,
                        "stale_seconds": 900,
                        "hysteresis_polls": 3,
                        "connect_timeout_seconds": 5,
                    },
                    "nhc": {
                        "poll_interval_minutes": 60,
                        "max_distance_miles": 1000,
                        "max_advisory_age_hours": 4,
                    },
                    "scripts": {"default_timeout": 30},
                    "database": {
                        "cleanup_interval_hours": 24,
                        "retention_days": 30,
                        "backup_interval_hours": 24,
                    },
                    "monitoring": {
                        "health_check_interval": 60,
                        "http_server": {"port": 8100, "auth": {"session_timeout_hours": 24}},
                        "metrics": {"retention_days": 7},
                    },
                    "pushover": {"priority": 0, "timeout_seconds": 30},
                }

                def _fix_empty_numerics(d, defs, cfg):
                    if not isinstance(d, dict):
                        return d
                    out = {}
                    for k, v in d.items():
                        subdef = defs.get(k) if isinstance(defs, dict) else None
                        subcfg = getattr(cfg, k, None) if hasattr(cfg, k) else None
                        if isinstance(v, dict):
                            out[k] = _fix_empty_numerics(
                                v, subdef or {}, subcfg or type("_", (), {})()
                            )
                        elif isinstance(v, str) and v.strip() == "":
                            if isinstance(subdef, (int, float)):
                                out[k] = subdef
                            elif subcfg is not None and isinstance(subcfg, (int, float)):
                                out[k] = subcfg
                            elif subcfg is None and k in (
                                "static_lat",
                                "static_lon",
                                "min_accuracy_meters",
                            ):
                                out[k] = None
                            else:
                                out[k] = v
                        else:
                            out[k] = v
                    return out

                data = _fix_empty_numerics(data, _numeric_defaults, self.config)

                from ...core.config import AppConfig

                merged = deep_merge_dict(model_dump_for_merge(self.config), data)
                if "counties" in data:
                    merged["counties"] = data["counties"]

                mon = merged.setdefault("monitoring", {}).setdefault("http_server", {})
                auth = mon.setdefault("auth", {})
                if (
                    not auth.get("secret_key")
                    and self.config.monitoring.http_server.auth.secret_key
                ):
                    auth["secret_key"] = self.config.monitoring.http_server.auth.secret_key

                updated_config = AppConfig(**merged)
                updated_config.dashboard_setup_complete = True

                config_path = resolve_config_path(self.config)
                self._write_config_yaml(updated_config, config_path)

                # Update the application's config reference
                self.config = updated_config
                if self.app:
                    self.app.apply_runtime_config(updated_config)

                logger.info(f"Configuration saved to {config_path}")

                return web.json_response(
                    {
                        "success": True,
                        "message": "Configuration updated and saved successfully",
                        "config_file": str(config_path),
                    }
                )

            except Exception as validation_error:
                logger.error(f"Configuration validation failed: {validation_error}")
                return web.json_response(
                    {"success": False, "error": f"Invalid configuration: {str(validation_error)}"},
                    status=400,
                )

        except Exception as e:
            logger.error(f"Error updating config: {e}", exc_info=True)
            return web.json_response({"error": "Failed to update configuration"}, status=500)

    async def api_config_reset_handler(self, request: Request) -> Response:
        """Handle API config reset endpoint."""
        try:
            from shutil import copy2

            from ...core.config import AppConfig

            config_path = resolve_config_path(self.config)
            example_path = config_path.parent / "config.yaml.example"
            if example_path.is_file():
                copy2(example_path, config_path)
            else:
                repo_default = Path(__file__).resolve().parents[4] / "config" / "default.yaml"
                if repo_default.is_file():
                    copy2(repo_default, config_path)
                else:
                    default_cfg = AppConfig()
                    self._write_config_yaml(default_cfg, config_path)

            self._reload_config_from_disk()
            return web.json_response(
                {
                    "success": True,
                    "message": "Configuration reset from defaults",
                    "config_file": str(config_path),
                }
            )
        except Exception as e:
            logger.error(f"Error resetting config: {e}", exc_info=True)
            return web.json_response({"error": "Failed to reset configuration"}, status=500)

    async def api_config_backup_handler(self, request: Request) -> Response:
        """Handle API config backup endpoint."""
        try:
            from datetime import datetime, timezone
            from shutil import copy2

            config_path = resolve_config_path(self.config)
            if not config_path.is_file():
                return web.json_response({"error": "Config file not found"}, status=404)

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            backup_path = config_path.with_name(f"{config_path.name}.backup.{stamp}")
            copy2(config_path, backup_path)
            return web.json_response(
                {
                    "success": True,
                    "message": "Configuration backed up successfully",
                    "backup_path": str(backup_path),
                }
            )
        except Exception as e:
            logger.error(f"Error backing up config: {e}", exc_info=True)
            return web.json_response({"error": "Failed to back up configuration"}, status=500)

    async def api_county_generate_audio_handler(self, request: Request) -> Response:
        """Handle API county audio generation endpoint."""
        try:
            county_code = request.match_info.get("county_code")
            if not county_code:
                return web.json_response({"error": "county_code is required"}, status=400)

            # Find the county in config
            county = None
            for c in self.config.counties:
                if c.code == county_code:
                    county = c
                    break

            if not county:
                return web.json_response({"error": f"County {county_code} not found"}, status=404)

            if not county.name:
                return web.json_response({"error": "County name is required"}, status=400)

            # Check if audio manager is available
            if not self.app.audio_manager:
                return web.json_response({"error": "Audio manager not available"}, status=503)

            # Generate audio file
            filename = self.app.audio_manager.generate_county_audio(county.name)

            if not filename:
                return web.json_response(
                    {"success": False, "error": "Failed to generate county audio file"}, status=500
                )

            # Update county config with generated filename
            county.audio_file = filename

            # Save config
            try:
                from ruamel.yaml import YAML

                yaml = YAML()
                yaml.preserve_quotes = True
                config_path = resolve_config_path(self.config)

                with open(config_path, "r") as f:
                    config_data = yaml.load(f)

                # Update the county in config
                if "counties" in config_data:
                    for i, c in enumerate(config_data["counties"]):
                        if c.get("code") == county_code:
                            config_data["counties"][i]["audio_file"] = filename
                            break

                # Never write plaintext dashboard auth password to disk
                self._ensure_auth_password_hashed_in_dict(config_data)

                with open(config_path, "w") as f:
                    yaml.dump(config_data, f)

                logger.info(
                    f"Updated config with generated audio file for {county_code}: {filename}"
                )
            except Exception as e:
                logger.warning(f"Failed to update config file: {e}")
                # Continue anyway - the file was generated

            return web.json_response(
                {
                    "success": True,
                    "filename": filename,
                    "message": f"Generated audio file: {filename}",
                }
            )

        except Exception as e:
            logger.error(
                f"Error generating county audio for {request.match_info.get('county_code', 'unknown')}: {e}",
                exc_info=True,
            )
            error_msg = str(e)
            # Provide more helpful error messages
            if "ffmpeg" in error_msg.lower() or "FFmpeg" in error_msg:
                error_msg = "FFmpeg is required for ulaw format conversion. Please install ffmpeg."
            elif "TTS" in error_msg or "synthesize" in error_msg.lower():
                error_msg = "Failed to generate TTS audio. Check TTS configuration."
            return web.json_response({"success": False, "error": error_msg}, status=500)

    async def api_config_restore_handler(self, request: Request) -> Response:
        """Handle API config restore endpoint."""
        try:
            from shutil import copy2

            from ..auth_security import resolve_config_backup_path

            config_path = resolve_config_path(self.config)
            body: dict = {}
            if request.can_read_body and request.content_type == "application/json":
                try:
                    raw = await request.json()
                    if isinstance(raw, dict):
                        body = raw
                except Exception:
                    pass

            backup_arg = body.get("backup_path")
            try:
                src = resolve_config_backup_path(
                    config_path,
                    str(backup_arg) if backup_arg else None,
                )
            except ValueError as e:
                return web.json_response({"error": str(e)}, status=400)

            copy2(src, config_path)
            self._reload_config_from_disk()
            return web.json_response(
                {
                    "success": True,
                    "message": "Configuration restored successfully",
                    "restored_from": str(src),
                    "config_file": str(config_path),
                }
            )
        except Exception as e:
            logger.error(f"Error restoring config: {e}", exc_info=True)
            return web.json_response({"error": "Failed to restore configuration"}, status=500)
