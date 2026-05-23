"""Skill discovery for SpecBuilder (MOD-04).

Introspects the CoCo skill catalog via live CLI introspection and
recommends relevant skills based on intake text.  See spec/modules/04-skill-discovery.md
for the full specification.

Primary path: live CLI discovery → cached to ~/.specbuilder/skill-catalog.json.
domain-hints.json provides keyword→domain mapping for relevance scoring.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    CATALOG_CACHE_DIR,
    CATALOG_CACHE_TTL_DAYS,
    DISCOVERY_MAX_RESULTS,
    DISCOVERY_MIN_RELEVANCE,
    DOMAIN_HINTS_PATH,
)

# ---------------------------------------------------------------------------
# Catalog retrieval
# ---------------------------------------------------------------------------

_CLI_TIMEOUT_SECONDS = 5

# Patterns that suggest Snowflake object references (schema.table, DB.SCHEMA.TABLE)
_SNOWFLAKE_OBJECT_RE = re.compile(r"\b[A-Z_][A-Z0-9_]*\.[A-Z_][A-Z0-9_]*(?:\.[A-Z_][A-Z0-9_]*)?\b")

# Pattern for explicit skill naming: "use <skill>" or "invoke <skill>"
_EXPLICIT_SKILL_RE = re.compile(
    r"\b(?:use|invoke|load|enable|run)\s+([a-z][a-z0-9:_-]+)", re.IGNORECASE
)

# Common synonyms/related-terms mapping for fuzzy domain matching
_SYNONYMS: dict[str, list[str]] = {
    "etl": ["pipeline", "transform", "ingest", "load"],
    "pipeline": ["etl", "workflow", "orchestration", "dag"],
    "dashboard": ["streamlit", "visualization", "app", "UI"],
    "ai": ["ml", "machine learning", "llm", "cortex", "model"],
    "ml": ["ai", "machine learning", "model", "training"],
    "security": ["governance", "access", "permissions", "compliance", "rbac"],
    "migration": ["migrate", "convert", "upgrade", "snowconvert"],
    "api": ["endpoint", "rest", "webhook", "integration"],
    "streaming": ["real-time", "low-latency", "ingestion"],
    "dbt": ["dbt-core", "dbt-fusion", "materialization", "model"],
}


def get_catalog_live() -> list[dict]:
    """Retrieve skill entries from the CoCo CLI.

    Runs ``cortex search docs "cortex code skills"`` and parses the output
    into catalog entries.  Returns an empty list on any failure.
    """
    try:
        result = subprocess.run(
            ["cortex", "search", "docs", "cortex code skills"],
            capture_output=True,
            text=True,
            timeout=_CLI_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return []
        return _parse_cli_output(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def _parse_cli_output(raw: str) -> list[dict]:
    """Best-effort parse of CLI search output into catalog entries.

    The CLI output format is not strictly defined, so we attempt JSON first,
    then fall back to line-based heuristic parsing.
    """
    if not raw.strip():
        return []

    # Attempt 1: output is JSON
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [e for e in data if _is_valid_entry(e)]
        if isinstance(data, dict) and "skills" in data:
            return [e for e in data["skills"] if _is_valid_entry(e)]
    except (json.JSONDecodeError, TypeError):
        pass

    # Attempt 2: line-based heuristic (name — description)
    entries: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Try "name — description" or "name: description"
        for sep in (" — ", " - ", ": "):
            if sep in line:
                name, desc = line.split(sep, 1)
                name = name.strip().lower()
                if name:
                    entries.append(
                        {
                            "name": name,
                            "description": desc.strip(),
                            "domain_tags": [],
                            "keyword_tags": [],
                        }
                    )
                break
    return entries


def _is_valid_entry(entry: dict) -> bool:
    """Check that a catalog entry has the minimum required fields."""
    return isinstance(entry, dict) and isinstance(entry.get("name"), str) and bool(entry["name"])


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

_CACHE_FILE = "skill-catalog.json"


def _get_cache_path() -> Path:
    """Return the path to the cached catalog file."""
    return CATALOG_CACHE_DIR / _CACHE_FILE


def _read_cache() -> dict | None:
    """Read the cached catalog from disk. Returns None if missing/corrupt."""
    cache_path = _get_cache_path()
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "skills" in data:
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return None


def _cache_expired(cache: dict) -> bool:
    """Check if a cache dict has exceeded its TTL."""
    from datetime import datetime, timezone

    cached_at = cache.get("_cached_at", "")
    if not cached_at:
        return True
    try:
        ts = datetime.fromisoformat(cached_at)
        age_days = (datetime.now(timezone.utc) - ts).days
        return age_days >= CATALOG_CACHE_TTL_DAYS
    except (ValueError, TypeError):
        return True


def _write_cache(skills: list[dict]) -> None:
    """Write enriched skills to the cache file."""
    from datetime import datetime, timezone

    cache_path = _get_cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "_cached_at": datetime.now(timezone.utc).isoformat(),
            "_ttl_days": CATALOG_CACHE_TTL_DAYS,
            "_skill_count": len(skills),
            "skills": skills,
        }
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # Cache write failure is non-fatal


def _load_domain_hints() -> dict[str, Any]:
    """Load domain inference rules from domain-hints.json."""
    try:
        data = json.loads(DOMAIN_HINTS_PATH.read_text(encoding="utf-8"))
        result: dict[str, Any] = data.get("domain_rules", {})
        return result
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _infer_domain(entry: dict, domain_rules: dict) -> list[str]:
    """Infer domain_tags for a skill entry based on its name and description."""
    text = f"{entry.get('name', '')} {entry.get('description', '')}".lower()
    domains = []
    for domain, keywords in domain_rules.items():
        if any(kw in text for kw in keywords):
            domains.append(domain)
    return domains if domains else ["meta"]


def _infer_keywords(entry: dict) -> list[str]:
    """Extract keyword_tags from a skill entry's name and description."""
    name = entry.get("name", "")
    desc = entry.get("description", "")
    # Extract meaningful tokens from name (split on : and -)
    name_parts = re.findall(r"[a-z][a-z0-9]+", name.lower())
    # Extract key nouns from description (words > 4 chars, not stop words)
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "will",
        "can",
        "has",
        "have",
        "been",
        "being",
        "use",
        "using",
        "used",
        "over",
        "into",
        "about",
        "their",
        "these",
    }
    desc_words = [
        w for w in re.findall(r"[a-z][a-z0-9]+", desc.lower()) if len(w) > 4 and w not in stop_words
    ]
    return list(dict.fromkeys(name_parts + desc_words[:10]))


def _enrich_with_hints(live_skills: list[dict]) -> list[dict]:
    """Apply domain-hints.json to infer tags for live-discovered skills."""
    domain_rules = _load_domain_hints()
    enriched = []
    for skill in live_skills:
        enriched_skill = dict(skill)
        if not enriched_skill.get("domain_tags"):
            enriched_skill["domain_tags"] = _infer_domain(enriched_skill, domain_rules)
        if not enriched_skill.get("keyword_tags"):
            enriched_skill["keyword_tags"] = _infer_keywords(enriched_skill)
        enriched.append(enriched_skill)
    return enriched


def get_catalog() -> list[dict[str, Any]]:
    """Live-populate with cache strategy.

    1. If cache exists and is fresh → return cached skills
    2. If cache expired or missing → try live CLI
    3. If live succeeds → enrich with domain hints, cache, return
    4. If live fails + expired cache exists → return expired cache
    5. If live fails + no cache → try legacy static fallback → return empty
    """
    cache = _read_cache()

    # Fresh cache — use it
    if cache and not _cache_expired(cache):
        skills: list[dict[str, Any]] = cache["skills"]
        return skills

    # Try live refresh
    live = get_catalog_live()
    if live:
        enriched = _enrich_with_hints(live)
        _write_cache(enriched)
        return enriched

    # Live failed — use expired cache if available
    if cache:
        expired_skills: list[dict[str, Any]] = cache["skills"]
        return expired_skills

    # Last resort: no catalog available — return empty
    return []


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Split text into a set of lowercase word tokens."""
    return set(re.findall(r"[a-z][a-z0-9_-]*", text.lower()))


def _expand_synonyms(tokens: set[str]) -> set[str]:
    """Expand a token set with known synonyms for better recall."""
    expanded = set(tokens)
    for token in tokens:
        if token in _SYNONYMS:
            expanded.update(_SYNONYMS[token])
    return expanded


def _compute_relevance(
    skill: dict, intake_tokens: set[str], expanded_tokens: set[str]
) -> tuple[float, list[str]]:
    """Compute a relevance score for a single skill against intake tokens.

    Returns ``(raw_score, matched_keywords)``.
    """
    score = 0.0
    matched: list[str] = []

    # Keyword tag matches (exact token overlap) — 0.3 per match
    for tag in skill.get("keyword_tags", []):
        tag_tokens = _tokenize(tag)
        if tag_tokens & expanded_tokens:
            score += 0.3
            matched.append(tag)

    # Domain tag matches against domain-related words — 0.2 per match
    for dtag in skill.get("domain_tags", []):
        dtag_lower = dtag.lower().replace("-", " ")
        dtag_tokens = set(dtag_lower.split())
        if dtag_tokens & expanded_tokens:
            score += 0.2
            matched.append(dtag)

    # Description word overlap — 0.1 per match, capped at 0.5
    desc_tokens = _tokenize(skill.get("description", ""))
    overlap = desc_tokens & intake_tokens
    desc_score = min(len(overlap) * 0.1, 0.5)
    score += desc_score
    if overlap:
        matched.extend(sorted(overlap))

    return score, matched


def _generate_rationale(skill: dict, matched_keywords: list[str], intake_tokens: set[str]) -> str:
    """Generate a plain-language rationale for why a skill was recommended."""
    name = skill.get("name", "unknown")
    desc = skill.get("description", "")
    kw_str = ", ".join(dict.fromkeys(matched_keywords))  # deduplicated, ordered

    if kw_str:
        return (
            f"The intake mentions {kw_str} — the '{name}' skill "
            f"can help because it {desc[0].lower()}{desc[1:]}"
            if desc
            else f"The intake mentions {kw_str} — '{name}' is relevant."
        )
    return f"'{name}' may be useful: {desc}" if desc else f"'{name}' may be useful."


def _generate_useful_for(skill: dict[str, Any]) -> str:
    """One-line summary of what the skill is useful for."""
    desc: str = skill.get("description", "")
    if desc:
        # Reframe description as a "useful for" phrase
        return desc.rstrip(".")
    return "General assistance"


def match_skills(
    intake_text: str,
    catalog: list[dict] | None = None,
    max_results: int = DISCOVERY_MAX_RESULTS,
    min_relevance: float = DISCOVERY_MIN_RELEVANCE,
) -> dict:
    """Match intake text against the skill catalog and return recommendations.

    Parameters
    ----------
    intake_text:
        Raw text describing the requirement (from intake, spec, or conversation).
    catalog:
        Optional pre-loaded catalog. If ``None``, calls :func:`get_catalog`.
    max_results:
        Maximum number of recommendations.
    min_relevance:
        Minimum normalized score to include a recommendation.

    Returns
    -------
    dict
        ``{"recommendations": [...], "follow_up_questions": [...]}``
    """
    # Edge case: intake too short
    if len(intake_text.split()) < 3:
        return {
            "recommendations": [],
            "follow_up_questions": [
                "Insufficient context for skill recommendations — "
                "try adding more detail to the description."
            ],
        }

    if catalog is None:
        catalog = get_catalog()

    intake_tokens = _tokenize(intake_text)
    expanded_tokens = _expand_synonyms(intake_tokens)

    # Detect explicit skill names in intake
    explicit_names = {m.group(1).lower() for m in _EXPLICIT_SKILL_RE.finditer(intake_text)}

    # Detect Snowflake object references
    has_snowflake_objects = bool(_SNOWFLAKE_OBJECT_RE.search(intake_text))

    # Score each skill
    scored: list[tuple[float, list[str], dict]] = []
    for skill in catalog:
        skill_name = skill.get("name", "").lower()

        # Explicit naming override: score = 1.0
        if skill_name in explicit_names or any(
            alias in explicit_names
            for alias in [skill_name.split(":")[-1], skill_name.replace("-", " ")]
        ):
            scored.append((1.0, [f"explicitly named: '{skill_name}'"], skill))
            continue

        raw_score, matched = _compute_relevance(skill, intake_tokens, expanded_tokens)
        if raw_score > 0:
            scored.append((raw_score, matched, skill))

    # Normalize scores to 0.0–1.0
    if scored:
        max_raw = max(s[0] for s in scored)
        if max_raw > 1.0:
            # Scale all non-explicit entries; explicit (1.0) entries stay at 1.0
            scored = [
                (s[0] / max_raw, s[1], s[2])
                if "explicitly named" not in " ".join(s[1])
                else (1.0, s[1], s[2])
                for s in scored
            ]
        elif 0 < max_raw < 1.0:
            scored = [(s[0] / max_raw, s[1], s[2]) for s in scored]

    # Filter by min_relevance, sort descending
    scored = [s for s in scored if s[0] >= min_relevance]
    scored.sort(key=lambda s: s[0], reverse=True)

    # Meta-skill logic
    meta_skills_to_add: list[tuple[float, list[str], dict, str]] = []

    # If no domain skills matched, add skill-development
    domain_matches = [s for s in scored if "meta" not in (s[2].get("domain_tags") or [])]
    if not domain_matches:
        sd_entry = _find_skill(catalog, "skill-development")
        if sd_entry:
            meta_skills_to_add.append(
                (
                    0.5,
                    ["no domain match"],
                    sd_entry,
                    "No existing skill covers this domain — consider authoring a custom skill.",
                )
            )

    # If intake references Snowflake objects, boost lineage
    if has_snowflake_objects:
        lineage_entry = _find_skill(catalog, "lineage")
        if lineage_entry:
            # Check if lineage is already in results
            existing_lineage = [s for s in scored if s[2].get("name", "").lower() == "lineage"]
            if existing_lineage:
                # Boost its score
                scored = [
                    (min(s[0] + 0.2, 1.0), s[1] + ["snowflake objects referenced"], s[2])
                    if s[2].get("name", "").lower() == "lineage"
                    else s
                    for s in scored
                ]
            else:
                meta_skills_to_add.append(
                    (
                        0.5,
                        ["snowflake objects referenced"],
                        lineage_entry,
                        "The intake references Snowflake objects —"
                        " lineage can help understand data flow context.",
                    )
                )

    # Check if intake asks about CoCo capabilities
    coco_tokens = {"cortex", "coco", "cortex code", "cli", "help", "commands"}
    if intake_tokens & coco_tokens:
        guide_entry = _find_skill(catalog, "cortex-code-guide")
        if guide_entry and not any(
            s[2].get("name", "").lower() == "cortex-code-guide" for s in scored
        ):
            meta_skills_to_add.append(
                (
                    0.4,
                    ["coco capabilities"],
                    guide_entry,
                    "The intake asks about CoCo capabilities —"
                    " this guide explains available features.",
                )
            )

    # Build recommendations
    recommendations: list[dict] = []

    for raw_score, matched, skill in scored[:max_results]:
        is_meta = "meta" in (skill.get("domain_tags") or [])
        recommendations.append(
            {
                "skill_name": skill["name"],
                "relevance_score": round(raw_score, 2),
                "matched_keywords": list(dict.fromkeys(matched)),
                "rationale": _generate_rationale(skill, matched, intake_tokens),
                "useful_for": _generate_useful_for(skill),
                "is_meta": is_meta,
            }
        )

    # Add meta-skills (if not already at max capacity)
    for mscore, mmatched, mskill, mrationale in meta_skills_to_add:
        if len(recommendations) >= max_results:
            break
        # Don't duplicate
        if any(r["skill_name"] == mskill["name"] for r in recommendations):
            continue
        recommendations.append(
            {
                "skill_name": mskill["name"],
                "relevance_score": round(mscore, 2),
                "matched_keywords": mmatched,
                "rationale": mrationale,
                "useful_for": _generate_useful_for(mskill),
                "is_meta": True,
            }
        )

    # Re-sort after meta additions
    recommendations.sort(key=lambda r: r["relevance_score"], reverse=True)

    # Many skills note
    follow_up: list[str] = []
    if len(scored) > max_results:
        follow_up.append(
            "Many skills are relevant — consider breaking the work into "
            "multiple modules for clearer skill alignment."
        )

    follow_up.extend(generate_follow_up_questions(recommendations, intake_text))

    return {
        "recommendations": recommendations,
        "follow_up_questions": follow_up,
    }


def _find_skill(catalog: list[dict], name: str) -> dict | None:
    """Find a skill entry in the catalog by name (case-insensitive)."""
    name_lower = name.lower()
    for skill in catalog:
        if skill.get("name", "").lower() == name_lower:
            return skill
    return None


# ---------------------------------------------------------------------------
# Follow-up question generation
# ---------------------------------------------------------------------------


def generate_follow_up_questions(recommendations: list[dict], intake_text: str) -> list[str]:
    """Generate skill-informed follow-up questions from recommendations.

    Each recommendation yields one question that references both the intake
    content and the skill capability.
    """
    questions: list[str] = []
    seen: set[str] = set()

    intake_lower = intake_text.lower()

    for rec in recommendations:
        skill_name = rec.get("skill_name", "")
        useful_for = rec.get("useful_for", "")
        matched = rec.get("matched_keywords", [])

        question = _question_for_skill(skill_name, useful_for, matched, intake_lower)
        if question and question not in seen:
            seen.add(question)
            questions.append(question)

    return questions


def _question_for_skill(
    skill_name: str,
    useful_for: str,
    matched_keywords: list[str],
    intake_lower: str,
) -> str:
    """Generate a single follow-up question for a skill recommendation."""
    # Use matched keywords to add specificity
    kw_phrase = ""
    real_keywords = [k for k in matched_keywords if not k.startswith("explicitly")]
    if real_keywords:
        kw_phrase = f"You mentioned {', '.join(real_keywords[:3])}"
    else:
        kw_phrase = "Based on your description"

    # Build the question based on the skill's domain
    name_short = skill_name.split(":")[-1] if ":" in skill_name else skill_name
    useful_lower = useful_for.lower() if useful_for else "assist with this"

    return (
        f"{kw_phrase} — would the '{name_short}' skill"
        f" ({useful_lower}) be useful for your implementation?"
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _audit() -> None:
    """Print cache status for diagnostics."""
    from datetime import datetime, timezone

    cache = _read_cache()
    cache_path = _get_cache_path()

    print(f"Cache location: {cache_path}")

    if cache is None:
        print("Cache status: NOT POPULATED")
        print("  No cached catalog found. Run skill discovery to populate.")
        return

    cached_at = cache.get("_cached_at", "unknown")
    skill_count = cache.get("_skill_count", len(cache.get("skills", [])))
    expired = _cache_expired(cache)

    print(f"Cache status: {'EXPIRED' if expired else 'FRESH'}")
    print(f"  Cached at:   {cached_at}")
    print(f"  TTL:         {CATALOG_CACHE_TTL_DAYS} days")
    print(f"  Skills:      {skill_count}")

    if expired:
        try:
            ts = datetime.fromisoformat(cached_at)
            age_days = (datetime.now(timezone.utc) - ts).days
            print(f"  Age:         {age_days} days (expired)")
        except (ValueError, TypeError):
            print("  Age:         unknown (invalid timestamp)")
    else:
        try:
            ts = datetime.fromisoformat(cached_at)
            age_days = (datetime.now(timezone.utc) - ts).days
            print(f"  Age:         {age_days} days")
        except (ValueError, TypeError):
            pass

    # Try live comparison
    print("\nLive CLI check:")
    live = get_catalog_live()
    if live:
        cached_names: set[str] = {s["name"] for s in cache.get("skills", []) if s.get("name")}
        live_names: set[str] = {s["name"] for s in live if s.get("name")}
        new_skills = live_names - cached_names
        removed_skills = cached_names - live_names
        print(f"  Live skills: {len(live)}")
        if new_skills:
            print(f"  New (not in cache): {', '.join(sorted(new_skills))}")
        if removed_skills:
            print(f"  Removed (not live): {', '.join(sorted(removed_skills))}")
        if not new_skills and not removed_skills:
            print("  Cache is up to date with live.")
    else:
        print("  CLI unavailable or returned no results.")


if __name__ == "__main__":
    if "--audit" in sys.argv:
        _audit()
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        if args:
            text = " ".join(args)
        else:
            text = sys.stdin.read()

        result = match_skills(text)
        print(json.dumps(result, indent=2))
