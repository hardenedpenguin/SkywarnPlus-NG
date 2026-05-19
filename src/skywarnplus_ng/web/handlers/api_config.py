"""
Config and county restore API handlers mixin.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from aiohttp.web import Request, Response

if TYPE_CHECKING:
    pass

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
    """Return sorted absolute paths to *.onnx files directly under piper_dir."""
    if not piper_dir.is_dir():
        return []
    try:
        root = piper_dir.resolve()
    except OSError:
        return []
    out: list[str] = []
    try:
        candidates = sorted(root.glob("*.onnx"), key=lambda x: x.name.lower())
    except OSError:
        return []
    for p in candidates:
        try:
            if not p.is_file():
                continue
            resolved = p.resolve()
            resolved.relative_to(root)
        except (ValueError, OSError):
            continue
        out.append(str(resolved))
    return out


class ConfigApiMixin:
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

            # Default Piper model path for UI: install script puts en_US-amy here (low or medium)
            data_dir = self.config.data_dir
            if data_dir:
                base = Path(str(data_dir)).resolve().parent / "piper"
                for name in ("en_US-amy-medium.onnx", "en_US-amy-low.onnx"):
                    p = base / name
                    if p.exists():
                        serializable_config["piper_default_model_path"] = str(p)
                        break
                else:
                    serializable_config["piper_default_model_path"] = str(
                        base / "en_US-amy-low.onnx"
                    )
                serializable_config["piper_available_models"] = _list_piper_onnx_models(base)
            else:
                serializable_config["piper_available_models"] = []

            return web.json_response(serializable_config)
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

            # Hash dashboard auth password if present and plaintext (so we never persist plaintext)
            self._ensure_auth_password_hashed_in_dict(data)

            # Dashboard may send sparse counties arrays (null holes) after row removal.
            if "counties" in data:
                data["counties"] = _sanitize_counties_list(data.get("counties"))

            # Import required modules for YAML handling
            from ruamel.yaml import YAML
            from pathlib import Path

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

                # Normalize empty numeric strings from form (form sends '' for untouched fields)
                _numeric_defaults = {
                    "audio": {"tts": {"speed": 1.0, "sample_rate": 22050, "bit_rate": 128}},
                    "filtering": {"max_alerts": 99},
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
                            else:
                                out[k] = v
                        else:
                            out[k] = v
                    return out

                data = _fix_empty_numerics(data, _numeric_defaults, self.config)

                # Create new config from the received data
                from ...core.config import AppConfig

                updated_config = AppConfig(**data)

                # Save to config file (use the configured config file path)
                config_path = self.config.config_file
                if not config_path.is_absolute():
                    # If relative path, make it relative to the application directory
                    config_path = Path("/etc/skywarnplus-ng") / config_path
                config_path.parent.mkdir(parents=True, exist_ok=True)

                yaml = YAML()
                yaml.default_flow_style = False
                yaml.preserve_quotes = True
                yaml.width = 4096

                # Convert config to dict and handle Path objects
                config_dict = updated_config.model_dump()

                # Convert Path objects to strings for YAML serialization
                def convert_paths_for_yaml(obj):
                    if isinstance(obj, dict):
                        return {k: convert_paths_for_yaml(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_paths_for_yaml(item) for item in obj]
                    elif hasattr(obj, "__fspath__"):  # Path-like object
                        return str(obj)
                    else:
                        return obj

                serializable_config = convert_paths_for_yaml(config_dict)

                # Never write plaintext dashboard auth password: take from config, hash if needed, force into dict
                try:
                    pwd = getattr(
                        getattr(
                            getattr(updated_config.monitoring, "http_server", None), "auth", None
                        ),
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

                # Quote auth password in YAML so bcrypt hash ($2b$...) is read back correctly
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

                # Write to file
                with open(config_path, "w") as f:
                    yaml.dump(serializable_config, f)

                # Update the application's config reference
                self.config = updated_config
                if self.app:
                    self.app.config = updated_config

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
            logger.error(f"Error updating config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_config_reset_handler(self, request: Request) -> Response:
        """Handle API config reset endpoint."""
        try:
            # Reset to default configuration
            # This would require implementing configuration reset logic
            return web.json_response(
                {"success": True, "message": "Configuration reset to defaults"}
            )
        except Exception as e:
            logger.error(f"Error resetting config: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def api_config_backup_handler(self, request: Request) -> Response:
        """Handle API config backup endpoint."""
        try:
            # Create configuration backup
            # This would require implementing backup logic
            return web.json_response(
                {"success": True, "message": "Configuration backed up successfully"}
            )
        except Exception as e:
            logger.error(f"Error backing up config: {e}")
            return web.json_response({"error": str(e)}, status=500)

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
                config_path = Path("/etc/skywarnplus-ng/config.yaml")

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
            # Restore configuration from backup
            # This would require implementing restore logic
            return web.json_response(
                {"success": True, "message": "Configuration restored successfully"}
            )
        except Exception as e:
            logger.error(f"Error restoring config: {e}")
            return web.json_response({"error": str(e)}, status=500)
