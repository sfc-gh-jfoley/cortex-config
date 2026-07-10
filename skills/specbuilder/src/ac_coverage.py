"""AC Coverage analysis — parse spec ACs, collect test markers, heuristic matching, and reporting.

Provides tools to measure how well acceptance criteria in spec modules are
covered by the test suite, using both explicit @pytest.mark.ac markers and
heuristic keyword matching.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from specbuilder.src.config import MODULE_TEST_MAPPING, get_project_root

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ACItem:
    """A single acceptance criterion parsed from a spec module."""

    id: str  # e.g. "AC-1"
    title: str  # e.g. "Directory Structure"
    bullets: list[str] = field(default_factory=list)


@dataclass
class Match:
    """A heuristic match between an AC and a test function."""

    ac_id: str
    test_name: str
    score: float


# ---------------------------------------------------------------------------
# Stop words for keyword extraction
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "must", "ought", "need",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "up",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how", "all",
    "each", "every", "both", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "as", "until", "while", "if", "or", "and", "but",
    "that", "this", "these", "those", "it", "its", "they", "them", "their",
    "we", "our", "you", "your", "he", "him", "his", "she", "her",
})


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def parse_spec_acs(spec_path: Path) -> list[ACItem]:
    """Parse acceptance criteria from a spec module markdown file.

    Looks for headings matching `### AC-N: Title` and collects subsequent
    bullet lines (starting with `- `) until the next heading or EOF.
    """
    text = spec_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    items: list[ACItem] = []
    current: ACItem | None = None
    ac_heading_re = re.compile(r"^###\s+AC-(\d+):\s*(.+)$")

    for line in lines:
        m = ac_heading_re.match(line)
        if m:
            if current is not None:
                items.append(current)
            ac_num = m.group(1)
            title = m.group(2).strip()
            current = ACItem(id=f"AC-{ac_num}", title=title)
            continue

        if current is not None:
            # Stop on next heading (any level)
            if line.startswith("#") and not line.startswith("###"):
                items.append(current)
                current = None
                continue
            # Also stop on another ### that isn't an AC
            if line.startswith("### ") and not ac_heading_re.match(line):
                items.append(current)
                current = None
                continue

            # Collect bullet lines
            stripped = line.strip()
            if stripped.startswith("- "):
                # Strip checkbox syntax: "- [ ] text" or "- [x] text" → "text"
                bullet_text = re.sub(r"^-\s*\[.\]\s*", "", stripped)
                if not bullet_text:
                    bullet_text = stripped[2:]  # fallback: just strip "- "
                current.bullets.append(bullet_text)

    # Don't forget the last item
    if current is not None:
        items.append(current)

    return items


def collect_ac_markers(tests_dir: Path) -> dict[str, list[str]]:
    """Scan test_*.py files for @pytest.mark.ac("...") decorators.

    Returns a mapping of AC-ID (e.g. "MOD-01/AC-1") to list of test function names.
    """
    mapping: dict[str, list[str]] = {}
    marker_re = re.compile(r'@pytest\.mark\.ac\(["\']([^"\']+)["\']\)')
    func_re = re.compile(r"^\s*def (test_\w+)")

    if not tests_dir.is_dir():
        return mapping

    for test_file in sorted(tests_dir.glob("test_*.py")):
        text = test_file.read_text(encoding="utf-8")
        lines = text.splitlines()

        pending_ac_ids: list[str] = []
        for line in lines:
            marker_match = marker_re.search(line)
            if marker_match:
                pending_ac_ids.append(marker_match.group(1))
                continue

            func_match = func_re.match(line)
            if func_match and pending_ac_ids:
                func_name = func_match.group(1)
                for ac_id in pending_ac_ids:
                    mapping.setdefault(ac_id, []).append(func_name)
                pending_ac_ids = []
            elif func_match:
                pending_ac_ids = []
            # Non-function, non-marker lines: keep accumulating markers
            # (handles blank lines between decorator and def)

    return mapping


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text, stripping stop words."""
    words = re.findall(r"[a-z][a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOP_WORDS and len(w) > 2}


def heuristic_match(ac_items: list[ACItem], test_file: Path) -> list[Match]:
    """Score test functions against ACs using keyword overlap.

    Extracts keywords from AC bullets and compares against test function names
    (split on underscores). Returns matches with score > 0.
    """
    if not test_file.exists():
        return []

    text = test_file.read_text(encoding="utf-8")
    func_re = re.compile(r"^\s*def (test_\w+)", re.MULTILINE)
    test_funcs = func_re.findall(text)

    if not test_funcs:
        return []

    matches: list[Match] = []

    for item in ac_items:
        # Build keyword set from AC title + bullets
        ac_text = item.title + " " + " ".join(item.bullets)
        ac_keywords = _extract_keywords(ac_text)

        if not ac_keywords:
            continue

        for func_name in test_funcs:
            # Extract keywords from function name (split on underscores)
            func_words = set(func_name.replace("test_", "").split("_"))
            func_words = {w for w in func_words if w and len(w) > 2}

            # Score = number of keyword hits
            score = len(ac_keywords & func_words)
            # Require >= 2 keyword hits: a single common token (e.g. "check", "run")
            # is insufficient evidence that a test exercises this specific AC.
            if score >= 2:
                matches.append(Match(ac_id=item.id, test_name=func_name, score=float(score)))

    return matches


def generate_report(module_id: str, *, spec_path: Path, tests_dir: Path) -> str:
    """Generate a markdown coverage report for a module.

    Returns markdown showing each AC with its coverage status.
    """
    items = parse_spec_acs(spec_path)
    markers = collect_ac_markers(tests_dir)

    lines: list[str] = []
    lines.append(f"# AC Coverage Report: {module_id}")
    lines.append("")

    if not items:
        lines.append("No acceptance criteria found in spec.")
        return "\n".join(lines)

    # Collect heuristic matches — prioritize mapped test files for this module
    all_heuristic: dict[str, list[str]] = {}
    if tests_dir.is_dir():
        mapped_filenames = set(MODULE_TEST_MAPPING.get(module_id, []))
        mapped_files: list[Path] = []
        other_files: list[Path] = []

        for tf in sorted(tests_dir.glob("test_*.py")):
            if tf.name in mapped_filenames:
                mapped_files.append(tf)
            else:
                other_files.append(tf)

        # Scan mapped files first (priority ordering; no score weighting)
        for tf in mapped_files:
            hmatches = heuristic_match(items, tf)
            for hm in hmatches:
                all_heuristic.setdefault(hm.ac_id, []).append(hm.test_name)

        # Then scan remaining files at normal priority
        for tf in other_files:
            hmatches = heuristic_match(items, tf)
            for hm in hmatches:
                all_heuristic.setdefault(hm.ac_id, []).append(hm.test_name)

    covered_count = 0
    total_count = len(items)

    for item in items:
        full_ac_id = f"{module_id}/{item.id}"
        marker_tests = markers.get(full_ac_id, [])
        heuristic_tests = all_heuristic.get(item.id, [])

        if marker_tests:
            status = "✓ covered (marker)"
            covered_count += 1
        elif heuristic_tests:
            status = "~ covered (heuristic)"
            covered_count += 1
        else:
            status = "✗ uncovered"

        lines.append(f"## {item.id}: {item.title}")
        lines.append(f"Status: {status}")
        if marker_tests:
            lines.append(f"  Tests: {', '.join(marker_tests)}")
        elif heuristic_tests:
            lines.append(f"  Heuristic matches: {', '.join(heuristic_tests[:3])}")
        lines.append("")

    lines.append("---")
    lines.append(f"Coverage: {covered_count}/{total_count} ACs covered")
    return "\n".join(lines)


def check_strict(baseline_path: Path | None) -> int:
    """Check that all ACs have coverage, respecting baseline exclusions.

    Returns 0 if all uncovered ACs are in the baseline, non-zero otherwise.
    Uses get_project_root() to locate spec/modules/ and tests/.
    """
    root = get_project_root()
    spec_dir = root / "spec" / "modules"
    tests_dir = root / "tests"

    # Load baseline exclusions
    baseline_ids: set[str] = set()
    if baseline_path and baseline_path.exists():
        for line in baseline_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                baseline_ids.add(line)

    # Find all spec modules
    if not spec_dir.is_dir():
        print(f"Error: spec/modules directory not found at {spec_dir}", file=sys.stderr)
        return 2

    markers = collect_ac_markers(tests_dir) if tests_dir.is_dir() else {}
    uncovered_new: list[str] = []

    for spec_file in sorted(spec_dir.glob("*.md")):
        # Extract module ID from filename: 01-slug.md → MOD-01
        match = re.match(r"^(\d{2})-", spec_file.name)
        if not match:
            continue
        mod_num = match.group(1)
        module_id = f"MOD-{mod_num}"

        items = parse_spec_acs(spec_file)

        # Check heuristic coverage from test files
        all_heuristic: dict[str, list[str]] = {}
        if tests_dir.is_dir():
            for tf in sorted(tests_dir.glob("test_*.py")):
                hmatches = heuristic_match(items, tf)
                for hm in hmatches:
                    all_heuristic.setdefault(hm.ac_id, []).append(hm.test_name)

        for item in items:
            full_ac_id = f"{module_id}/{item.id}"
            marker_tests = markers.get(full_ac_id, [])
            heuristic_tests = all_heuristic.get(item.id, [])

            if not marker_tests and not heuristic_tests:
                # Uncovered — check if grandfathered
                if full_ac_id not in baseline_ids:
                    uncovered_new.append(full_ac_id)

    if uncovered_new:
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for ac-coverage command."""
    args = sys.argv[1:]

    # Handle --help
    if "--help" in args or "-h" in args:
        print("Usage: specbuilder ac-coverage [MODULE_NUM] [OPTIONS]")
        print("")
        print("Analyze acceptance criteria test coverage.")
        print("")
        print("Arguments:")
        print("  MODULE_NUM    Module number (e.g., 01) to report on")
        print("")
        print("Options:")
        print("  --strict      Exit non-zero if any ACs lack coverage")
        print("  --new-only    Only check ACs not in .ac-coverage-baseline")
        print("  --format json Output findings as JSON (single-module only)")
        print("  --help, -h    Show this help message")
        sys.exit(0)

    strict = "--strict" in args
    new_only = "--new-only" in args
    json_output = False
    if "--format" in args:
        idx = args.index("--format")
        if idx + 1 < len(args) and args[idx + 1] == "json":
            json_output = True

    if new_only and not strict:
        print("Warning: --new-only has no effect without --strict", file=sys.stderr)

    # Remove flags and their value tokens from args to find positional module_num
    positional = [
        a for i, a in enumerate(args)
        if not a.startswith("--") and (i == 0 or args[i - 1] != "--format")
    ]

    root = get_project_root()
    spec_dir = root / "spec" / "modules"
    tests_dir = root / "tests"

    # Handle --strict mode
    if strict:
        baseline_path: Path | None = None
        if new_only:
            bp = root / ".ac-coverage-baseline"
            if bp.exists():
                baseline_path = bp
        exit_code = check_strict(baseline_path)
        sys.exit(exit_code)

    # Single module report
    if positional:
        mod_num = positional[0].zfill(2)
        module_id = f"MOD-{mod_num}"

        # Find the spec file
        spec_files = list(spec_dir.glob(f"{mod_num}-*.md"))
        if not spec_files:
            print(f"No spec file found for module {mod_num}", file=sys.stderr)
            sys.exit(1)

        if json_output:
            from specbuilder.src.diagnostic_schema import wrap_findings
            items = parse_spec_acs(spec_files[0])
            markers = collect_ac_markers(tests_dir)
            # Build heuristic matches — mirror the text path
            all_heuristic: dict[str, list[str]] = {}
            if tests_dir.is_dir():
                mapped_filenames = set(MODULE_TEST_MAPPING.get(module_id, []))
                mapped_files: list[Path] = []
                other_files: list[Path] = []
                for tf in sorted(tests_dir.glob("test_*.py")):
                    if tf.name in mapped_filenames:
                        mapped_files.append(tf)
                    else:
                        other_files.append(tf)
                for tf in mapped_files + other_files:
                    hmatches = heuristic_match(items, tf)
                    for hm in hmatches:
                        all_heuristic.setdefault(hm.ac_id, []).append(hm.test_name)
            findings = []
            for item in items:
                marker_tests = markers.get(f"{module_id}/{item.id}", [])
                heuristic_tests = all_heuristic.get(item.id, [])
                if marker_tests:
                    status = "covered"
                elif heuristic_tests:
                    status = "heuristic"
                else:
                    status = "uncovered"
                findings.append({"ac_id": item.id, "status": status, "tests": marker_tests})
            print(json.dumps(wrap_findings("ac-coverage", findings, module=module_id), indent=2))
            sys.exit(0)

        report = generate_report(module_id, spec_path=spec_files[0], tests_dir=tests_dir)
        print(report)
        sys.exit(0)

    # No module specified and not strict — show all
    if not spec_dir.is_dir():
        print("No spec/modules directory found", file=sys.stderr)
        sys.exit(1)

    for spec_file in sorted(spec_dir.glob("*.md")):
        match = re.match(r"^(\d{2})-", spec_file.name)
        if not match:
            continue
        mod_num = match.group(1)
        module_id = f"MOD-{mod_num}"
        report = generate_report(module_id, spec_path=spec_file, tests_dir=tests_dir)
        print(report)
        print()

    sys.exit(0)
