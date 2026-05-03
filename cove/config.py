import json
import os
import secrets
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cove"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "cove"
CONFIG_FILE = CONFIG_DIR / "settings.json"
DB_FILE = DATA_DIR / "cove.db"
ARIA2_SESSION = DATA_DIR / "aria2.session"
ARIA2_LOG = DATA_DIR / "aria2.log"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads"

# Legacy default. Anything matching this on load is upgraded to a fresh
# random secret so existing installs stop using the predictable token.
_LEGACY_RPC_SECRET = "cove"


@dataclass
class ScheduleWindow:
    enabled: bool = False
    start_hour: int = 2
    start_minute: int = 0
    end_hour: int = 6
    end_minute: int = 0
    days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])


CONNECTION_CHOICES = (1, 2, 4, 8, 16, 24, 32)


def _new_rpc_secret() -> str:
    """Per-install random token. 24 bytes ≈ 32 chars urlsafe-base64."""
    return secrets.token_urlsafe(24)


@dataclass
class Settings:
    download_dir: str = str(DEFAULT_DOWNLOAD_DIR)
    connections_per_server: int = 16
    max_concurrent: int = 1
    overall_speed_limit_kbps: int = 0
    speed_limiter_enabled: bool = False
    time_format_24h: bool = False  # default: 12-hour with AM/PM
    auto_update_check: bool = True
    delete_completed_on_exit: bool = False
    theme: str = "dark"  # "dark" | "light"
    rpc_port: int = 6800
    rpc_secret: str = ""  # populated on first save; never persisted as "cove"
    schedule: ScheduleWindow = field(default_factory=ScheduleWindow)

    @classmethod
    def load(cls) -> "Settings":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_FILE.exists():
            s = cls()
            s.rpc_secret = _new_rpc_secret()
            s.save()
            return s
        try:
            raw = json.loads(CONFIG_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            s = cls()
            s.rpc_secret = _new_rpc_secret()
            s.save()
            return s
        sched = ScheduleWindow(**raw.pop("schedule", {})) if "schedule" in raw else ScheduleWindow()
        s = cls(**{k: v for k, v in raw.items() if k in cls.__annotations__})
        s.schedule = sched
        if s.theme not in ("dark", "light"):
            s.theme = "dark"
        # Migrate legacy / empty / suspiciously-short secrets up to a real one.
        if not s.rpc_secret or s.rpc_secret == _LEGACY_RPC_SECRET or len(s.rpc_secret) < 16:
            s.rpc_secret = _new_rpc_secret()
            s.save()
        return s

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        # Write atomically with restrictive perms so the RPC secret isn't
        # readable by other local users.
        tmp = CONFIG_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, CONFIG_FILE)
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass
