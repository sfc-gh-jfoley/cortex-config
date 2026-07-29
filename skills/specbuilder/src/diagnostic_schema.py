"""Shared DiagnosticEnvelope for all specbuilder tool outputs.

Provides a common JSON wrapper so that every tool's ``--format json`` output
carries consistent metadata (tool name, version, timestamp) alongside its
tool-specific findings list.
"""

from __future__ import annotations

import importlib.metadata
from datetime import datetime, timezone
from typing import Any, TypedDict


class DiagnosticEnvelope(TypedDict):
    tool: str
    version: str
    timestamp: str          # ISO-8601 UTC
    module: str | None      # optional: module number/name context
    findings: list[Any]     # inner schema is tool-specific


def wrap_findings(
    tool: str,
    findings: list[Any],
    module: str | None = None,
) -> DiagnosticEnvelope:
    """Wrap tool-specific findings in the shared DiagnosticEnvelope."""
    try:
        version = importlib.metadata.version("specbuilder")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    return DiagnosticEnvelope(
        tool=tool,
        version=version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        module=module,
        findings=findings,
    )
