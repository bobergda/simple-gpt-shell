import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .common import env_flag

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for Python < 3.11
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "prompt2shell" / "config.toml"
VALID_PROFILES = {"inspect", "safe-edit", "full"}


PROFILE_DEFAULTS = {
    "inspect": {
        "safe_mode": True,
        "safe_mode_strict": True,
        "dry_run": True,
        "explain_only": False,
    },
    "safe-edit": {
        "safe_mode": True,
        "safe_mode_strict": False,
        "dry_run": False,
        "explain_only": False,
    },
    "full": {
        "safe_mode": False,
        "safe_mode_strict": False,
        "dry_run": False,
        "explain_only": False,
    },
}


@dataclass(frozen=True)
class AppConfig:
    profile: str = "safe-edit"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    api_max_retries: int = 2
    api_retry_base_seconds: float = 1.0
    max_output_tokens: int = 1200
    log_enabled: bool = False
    log_file: str | None = None
    safe_mode: bool = True
    safe_mode_strict: bool = False
    show_tokens: bool = True
    command_timeout: int | None = 300
    chat_language: str = "english"
    once_mode: bool = False
    dry_run: bool = False
    explain_only: bool = False
    json_mode: bool = False
    session_report_file: str | None = None
    config_file: str | None = None

    def to_metadata(self):
        return asdict(self)


def _coerce_bool(value, default):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", ""}
    return bool(value)


def _coerce_int(value, default):
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _coerce_positive_int(value, default):
    parsed = _coerce_int(value, default)
    if parsed is None:
        return None
    return parsed if parsed > 0 else default


def _coerce_positive_float(value, default):
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_timeout(value, default):
    if value is None:
        return default
    parsed = _coerce_int(value, default)
    if parsed is None:
        return None
    if parsed <= 0:
        return None
    return parsed


def _normalize_chat_language(value, default="english"):
    normalized = str(value or default).strip().lower()
    if normalized == "polish":
        return "polish"
    return "english"


def _normalize_profile(value, default="safe-edit"):
    normalized = str(value or default).strip().lower()
    if normalized in VALID_PROFILES:
        return normalized
    return default


def _expand_path(value, base_dir=None):
    if value in {None, ""}:
        return None
    expanded = Path(str(value)).expanduser()
    if not expanded.is_absolute() and base_dir is not None:
        expanded = Path(base_dir) / expanded
    return str(expanded.resolve())


def _pick_first(*values):
    for value in values:
        if value not in {None, ""}:
            return value
    return None


def _env_bool(key):
    if key not in os.environ:
        return None
    return env_flag(key, False)


def _read_toml_config(path):
    config_path = Path(path).expanduser()
    if not config_path.exists():
        return {}, str(config_path)

    with config_path.open("rb") as handle:
        parsed = tomllib.load(handle)

    if not isinstance(parsed, dict):
        return {}, str(config_path)

    return parsed, str(config_path.resolve())


def _get_nested(config_data, *path):
    current = config_data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def load_app_config(cli_overrides=None):
    cli_overrides = dict(cli_overrides or {})

    env_config_path = os.getenv("PROMPT2SHELL_CONFIG_FILE")
    requested_config_path = cli_overrides.get("config_file") or env_config_path or str(DEFAULT_CONFIG_PATH)
    raw_config, resolved_config_path = _read_toml_config(requested_config_path)
    config_base_dir = str(Path(resolved_config_path).expanduser().parent)

    defaults = AppConfig(config_file=resolved_config_path)

    file_values = {
        "profile": _get_nested(raw_config, "app", "profile"),
        "openai_api_key": _get_nested(raw_config, "openai", "api_key"),
        "openai_model": _get_nested(raw_config, "openai", "model"),
        "api_max_retries": _get_nested(raw_config, "openai", "max_retries"),
        "api_retry_base_seconds": _get_nested(raw_config, "openai", "retry_base_seconds"),
        "max_output_tokens": _get_nested(raw_config, "app", "max_output_tokens"),
        "log_enabled": _get_nested(raw_config, "logging", "enabled"),
        "log_file": _expand_path(_get_nested(raw_config, "logging", "file"), base_dir=config_base_dir),
        "safe_mode": _get_nested(raw_config, "app", "safe_mode"),
        "safe_mode_strict": _get_nested(raw_config, "app", "strict_safe_mode"),
        "show_tokens": _get_nested(raw_config, "app", "show_tokens"),
        "command_timeout": _get_nested(raw_config, "app", "command_timeout"),
        "chat_language": _get_nested(raw_config, "openai", "chat_language"),
        "once_mode": _get_nested(raw_config, "app", "once_mode"),
        "dry_run": _get_nested(raw_config, "app", "dry_run"),
        "explain_only": _get_nested(raw_config, "app", "explain_only"),
        "json_mode": _get_nested(raw_config, "app", "json_mode"),
        "session_report_file": _expand_path(_get_nested(raw_config, "report", "file"), base_dir=config_base_dir),
    }

    env_values = {
        "profile": os.getenv("PROMPT2SHELL_PROFILE"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "openai_model": os.getenv("OPENAI_MODEL"),
        "api_max_retries": os.getenv("PROMPT2SHELL_OPENAI_MAX_RETRIES"),
        "api_retry_base_seconds": os.getenv("PROMPT2SHELL_OPENAI_RETRY_BASE_SECONDS"),
        "max_output_tokens": os.getenv("PROMPT2SHELL_MAX_OUTPUT_TOKENS"),
        "log_enabled": _env_bool("PROMPT2SHELL_LOG_ENABLED"),
        "log_file": _expand_path(os.getenv("PROMPT2SHELL_LOG_FILE")),
        "safe_mode": _env_bool("PROMPT2SHELL_SAFE_MODE"),
        "safe_mode_strict": _env_bool("PROMPT2SHELL_SAFE_MODE_STRICT"),
        "show_tokens": _env_bool("PROMPT2SHELL_SHOW_TOKENS"),
        "command_timeout": os.getenv("PROMPT2SHELL_COMMAND_TIMEOUT"),
        "chat_language": os.getenv("PROMPT2SHELL_CHAT_LANGUAGE"),
        "once_mode": _env_bool("PROMPT2SHELL_ONCE"),
        "dry_run": _env_bool("PROMPT2SHELL_DRY_RUN"),
        "explain_only": _env_bool("PROMPT2SHELL_EXPLAIN_ONLY"),
        "json_mode": _env_bool("PROMPT2SHELL_JSON"),
        "session_report_file": _expand_path(os.getenv("PROMPT2SHELL_SESSION_REPORT_FILE")),
    }

    profile = _normalize_profile(
        _pick_first(cli_overrides.get("profile"), env_values["profile"], file_values["profile"], defaults.profile),
        defaults.profile,
    )
    profile_defaults = PROFILE_DEFAULTS[profile]

    merged = replace(
        defaults,
        profile=profile,
        openai_api_key=str(_pick_first(cli_overrides.get("openai_api_key"), env_values["openai_api_key"], file_values["openai_api_key"], defaults.openai_api_key) or ""),
        openai_model=str(_pick_first(cli_overrides.get("openai_model"), env_values["openai_model"], file_values["openai_model"], defaults.openai_model) or defaults.openai_model),
        api_max_retries=_coerce_positive_int(
            _pick_first(cli_overrides.get("api_max_retries"), env_values["api_max_retries"], file_values["api_max_retries"]),
            defaults.api_max_retries,
        ),
        api_retry_base_seconds=_coerce_positive_float(
            _pick_first(cli_overrides.get("api_retry_base_seconds"), env_values["api_retry_base_seconds"], file_values["api_retry_base_seconds"]),
            defaults.api_retry_base_seconds,
        ),
        max_output_tokens=_coerce_positive_int(
            _pick_first(cli_overrides.get("max_output_tokens"), env_values["max_output_tokens"], file_values["max_output_tokens"]),
            defaults.max_output_tokens,
        ),
        log_enabled=_coerce_bool(_pick_first(cli_overrides.get("log_enabled"), env_values["log_enabled"]), _coerce_bool(file_values["log_enabled"], defaults.log_enabled)),
        log_file=_pick_first(cli_overrides.get("log_file"), env_values["log_file"], file_values["log_file"], defaults.log_file),
        safe_mode=_coerce_bool(
            _pick_first(cli_overrides.get("safe_mode"), env_values["safe_mode"], file_values["safe_mode"]),
            profile_defaults["safe_mode"],
        ),
        safe_mode_strict=_coerce_bool(
            _pick_first(cli_overrides.get("safe_mode_strict"), env_values["safe_mode_strict"], file_values["safe_mode_strict"]),
            profile_defaults["safe_mode_strict"],
        ),
        show_tokens=_coerce_bool(
            _pick_first(cli_overrides.get("show_tokens"), env_values["show_tokens"]),
            _coerce_bool(file_values["show_tokens"], defaults.show_tokens),
        ),
        command_timeout=_coerce_timeout(
            _pick_first(cli_overrides.get("command_timeout"), env_values["command_timeout"], file_values["command_timeout"]),
            defaults.command_timeout,
        ),
        chat_language=_normalize_chat_language(
            _pick_first(cli_overrides.get("chat_language"), env_values["chat_language"], file_values["chat_language"], defaults.chat_language)
        ),
        once_mode=_coerce_bool(_pick_first(cli_overrides.get("once_mode"), env_values["once_mode"]), _coerce_bool(file_values["once_mode"], defaults.once_mode)),
        dry_run=_coerce_bool(
            _pick_first(cli_overrides.get("dry_run"), env_values["dry_run"], file_values["dry_run"]),
            profile_defaults["dry_run"],
        ),
        explain_only=_coerce_bool(
            _pick_first(cli_overrides.get("explain_only"), env_values["explain_only"], file_values["explain_only"]),
            profile_defaults["explain_only"],
        ),
        json_mode=_coerce_bool(
            _pick_first(cli_overrides.get("json_mode"), env_values["json_mode"], file_values["json_mode"]),
            defaults.json_mode,
        ),
        session_report_file=_pick_first(
            cli_overrides.get("session_report_file"),
            env_values["session_report_file"],
            file_values["session_report_file"],
            defaults.session_report_file,
        ),
    )

    if merged.explain_only and not merged.dry_run:
        merged = replace(merged, dry_run=True)
    if merged.json_mode:
        merged = replace(merged, once_mode=True, dry_run=True, show_tokens=False)

    return merged
