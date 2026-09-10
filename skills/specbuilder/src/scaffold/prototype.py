"""Prototype mode management (EXT-004)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DEFAULT_PROTOTYPE_HOURS = 24


def _parse_duration(duration_str: str) -> timedelta:
    """Parse a human-readable duration like '4h', '30m', '2d' into a timedelta."""
    match = re.match(r"^(\d+)\s*([hHmMdD])$", duration_str.strip())
    if not match:
        raise ValueError(
            f"Invalid duration '{duration_str}'."
            " Use format: Nh (hours), Nm (minutes), or Nd (days)."
        )
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "h":
        return timedelta(hours=value)
    elif unit == "m":
        return timedelta(minutes=value)
    elif unit == "d":
        return timedelta(days=value)
    raise ValueError(f"Unknown unit '{unit}'")  # pragma: no cover


def start_prototype(
    project_root: Path,
    spec_dir: str = "spec",
    expires_in: str | None = None,
    reason: str = "",
) -> dict:
    """Create a spec/.prototype sentinel file to suspend change-control.

    Returns a dict with the prototype metadata.
    """
    prototype_path = project_root / spec_dir / ".prototype"

    if expires_in:
        duration = _parse_duration(expires_in)
    else:
        duration = timedelta(hours=_DEFAULT_PROTOTYPE_HOURS)

    now = datetime.now(timezone.utc)
    expires_at = now + duration

    data = {
        "activated": now.isoformat(timespec="seconds"),
        "expires": expires_at.isoformat(timespec="seconds"),
        "reason": reason or "Prototype mode activated",
    }

    prototype_path.parent.mkdir(parents=True, exist_ok=True)
    prototype_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return data


def check_prototype_expiry(
    project_root: Path, spec_dir: str = "spec"
) -> dict:
    """Check whether the prototype sentinel has passed its expiry time.

    If expired, deletes the sentinel and returns::

        {"expired": True, "was_active": True, "expires": <ISO str>}

    If not expired or no sentinel exists, returns::

        {"expired": False, "was_active": <bool>}
    """
    prototype_path = project_root / spec_dir / ".prototype"
    if not prototype_path.exists():
        return {"expired": False, "was_active": False}

    try:
        data = json.loads(prototype_path.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(data["expires"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return {"expired": False, "was_active": True}

    now = datetime.now(timezone.utc)
    if now >= expires:
        try:
            prototype_path.unlink()
        except OSError:
            pass
        return {"expired": True, "was_active": True, "expires": data["expires"]}

    return {"expired": False, "was_active": True}


def end_prototype(project_root: Path, spec_dir: str = "spec") -> dict:
    """End prototype mode and report files modified since activation.

    Returns a dict with audit information.
    """
    prototype_path = project_root / spec_dir / ".prototype"

    if not prototype_path.exists():
        return {"active": False, "message": "Prototype mode is not active."}

    # Check expiry before audit — expired sentinel is treated as already ended (EXT-163)
    expiry = check_prototype_expiry(project_root, spec_dir)
    if expiry.get("expired"):
        return {
            "active": False,
            "message": (
                f"Prototype mode expired at {expiry['expires']} and has been "
                "automatically ended. No manual --end-prototype required."
            ),
        }

    # Read activation time
    try:
        data = json.loads(prototype_path.read_text(encoding="utf-8"))
        activated = datetime.fromisoformat(data["activated"])
    except (json.JSONDecodeError, KeyError):
        activated = None

    # Audit: find files modified since activation (BEFORE deleting sentinel)
    modified_files: list[str] = []
    delete_sentinel = True
    if activated:
        import subprocess

        try:
            # Use git to find files changed since activation
            since_str = activated.strftime("%Y-%m-%d %H:%M:%S")
            log_result = subprocess.run(
                ["git", "log", "--since", since_str, "--name-only", "--pretty=format:"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
            )
            if log_result.returncode == 0:
                modified_files = [f for f in log_result.stdout.strip().split("\n") if f.strip()]

            # Also check uncommitted changes
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
            )
            if status_result.returncode == 0:
                for line in status_result.stdout.strip().split("\n"):
                    if line.strip():
                        # Format: "XY filename" or "XY filename -> newname"
                        filename = line[3:].split(" -> ")[-1]
                        if filename not in modified_files:
                            modified_files.append(filename)
        except FileNotFoundError:
            # git not installed — bail without deleting sentinel
            modified_files = []
            delete_sentinel = False
        except Exception:
            # Other errors (OSError, TimeoutExpired, etc.) — end prototype anyway
            modified_files = []

    # Delete sentinel only after both audits complete (not if git unavailable)
    if delete_sentinel and prototype_path.exists():
        prototype_path.unlink()

    return {
        "active": True,
        "ended": True,
        "files_modified": modified_files,
    }
