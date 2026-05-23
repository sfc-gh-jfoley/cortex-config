"""AC-to-SQL assertion translation for Tier 4 validation.

Parses acceptance criteria text and translates concrete, verifiable
criteria into executable SQL assertions against a deployed sandbox schema.
"""

import re
from dataclasses import dataclass


@dataclass
class ACAssertion:
    """A single translated acceptance criterion assertion."""

    ac_id: str
    ac_text: str
    assertion_sql: str | None
    translatable: bool
    assertion_type: str  # "column_count", "object_exists", "not_null", "row_count", etc.
    expected_value: str | None = None


# ---------------------------------------------------------------------------
# Pattern matchers: each returns an ACAssertion or None
# ---------------------------------------------------------------------------

_COLUMN_COUNT_PATTERN = re.compile(
    r"(?:table|view)\s+[`\"]?(\w+)[`\"]?\s+(?:has|contains|includes)\s+(\d+)\s+columns?",
    re.IGNORECASE,
)

_OBJECT_EXISTS_PATTERN = re.compile(
    r"(?:creates?|produces?|generates?)\s+(?:a\s+)?(?:table|view|procedure|function|task|stream)"
    r"\s+(?:named?\s+)?[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)

_NOT_NULL_PATTERN = re.compile(
    r"column\s+[`\"]?(\w+)[`\"]?\s+(?:is|must be|should be)\s+NOT\s*NULL",
    re.IGNORECASE,
)

_ROW_COUNT_PATTERN = re.compile(
    r"(?:table|result)\s+[`\"]?(\w+)[`\"]?\s+(?:has|contains|returns)\s+"
    r"(?:at\s+least\s+)?(\d+)\s+rows?",
    re.IGNORECASE,
)

_HAS_COLUMN_PATTERN = re.compile(
    r"(?:table|view)\s+[`\"]?(\w+)[`\"]?\s+(?:has|includes|contains)\s+"
    r"(?:a\s+)?column\s+(?:named?\s+)?[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)

_FOREIGN_KEY_PATTERN = re.compile(
    r"(?:foreign\s+key|references?)\s+(?:from\s+)?[`\"]?(\w+)[`\"]?"
    r"\s+(?:to|references?)\s+[`\"]?(\w+)[`\"]?",
    re.IGNORECASE,
)

_PROCEDURE_EXISTS_PATTERN = re.compile(
    r"(?:procedure|function|sproc)\s+[`\"]?(\w+)[`\"]?\s+(?:exists|is\s+callable|can\s+be\s+called)",
    re.IGNORECASE,
)


def _try_column_count(ac_id: str, text: str, schema: str) -> ACAssertion | None:
    """Match: 'Table X has N columns'."""
    m = _COLUMN_COUNT_PATTERN.search(text)
    if not m:
        return None
    table_name = m.group(1).upper()
    expected = m.group(2)
    sql = (
        f"SELECT COUNT(*) AS col_count FROM {schema}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_SCHEMA = '{schema.split('.')[-1]}' "
        f"AND TABLE_NAME = '{table_name}'"
    )
    return ACAssertion(
        ac_id=ac_id,
        ac_text=text,
        assertion_sql=sql,
        translatable=True,
        assertion_type="column_count",
        expected_value=expected,
    )


def _try_object_exists(ac_id: str, text: str, schema: str) -> ACAssertion | None:
    """Match: 'Creates table/view/procedure X'."""
    m = _OBJECT_EXISTS_PATTERN.search(text)
    if not m:
        return None
    obj_name = m.group(1).upper()
    sql = (
        f"SELECT COUNT(*) AS obj_count FROM {schema}.INFORMATION_SCHEMA.TABLES "
        f"WHERE TABLE_SCHEMA = '{schema.split('.')[-1]}' "
        f"AND TABLE_NAME = '{obj_name}'"
    )
    return ACAssertion(
        ac_id=ac_id,
        ac_text=text,
        assertion_sql=sql,
        translatable=True,
        assertion_type="object_exists",
        expected_value="1",
    )


def _try_not_null(ac_id: str, text: str, schema: str) -> ACAssertion | None:
    """Match: 'Column X is NOT NULL'."""
    m = _NOT_NULL_PATTERN.search(text)
    if not m:
        return None
    col_name = m.group(1).upper()
    # Check via INFORMATION_SCHEMA — IS_NULLABLE = 'NO' means NOT NULL
    sql = (
        f"SELECT IS_NULLABLE FROM {schema}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_SCHEMA = '{schema.split('.')[-1]}' "
        f"AND COLUMN_NAME = '{col_name}' LIMIT 1"
    )
    return ACAssertion(
        ac_id=ac_id,
        ac_text=text,
        assertion_sql=sql,
        translatable=True,
        assertion_type="not_null",
        expected_value="NO",
    )


def _try_row_count(ac_id: str, text: str, schema: str) -> ACAssertion | None:
    """Match: 'Table X has at least N rows'."""
    m = _ROW_COUNT_PATTERN.search(text)
    if not m:
        return None
    table_name = m.group(1).upper()
    expected = m.group(2)
    sql = f"SELECT COUNT(*) AS row_count FROM {schema}.{table_name}"
    return ACAssertion(
        ac_id=ac_id,
        ac_text=text,
        assertion_sql=sql,
        translatable=True,
        assertion_type="row_count",
        expected_value=expected,
    )


def _try_has_column(ac_id: str, text: str, schema: str) -> ACAssertion | None:
    """Match: 'Table X has column named Y'."""
    m = _HAS_COLUMN_PATTERN.search(text)
    if not m:
        return None
    table_name = m.group(1).upper()
    col_name = m.group(2).upper()
    sql = (
        f"SELECT COUNT(*) AS col_exists FROM {schema}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_SCHEMA = '{schema.split('.')[-1]}' "
        f"AND TABLE_NAME = '{table_name}' AND COLUMN_NAME = '{col_name}'"
    )
    return ACAssertion(
        ac_id=ac_id,
        ac_text=text,
        assertion_sql=sql,
        translatable=True,
        assertion_type="has_column",
        expected_value="1",
    )


def _try_procedure_exists(ac_id: str, text: str, schema: str) -> ACAssertion | None:
    """Match: 'Procedure X exists / is callable'."""
    m = _PROCEDURE_EXISTS_PATTERN.search(text)
    if not m:
        return None
    proc_name = m.group(1).upper()
    sql = (
        f"SELECT COUNT(*) AS proc_count FROM {schema}.INFORMATION_SCHEMA.PROCEDURES "
        f"WHERE PROCEDURE_SCHEMA = '{schema.split('.')[-1]}' "
        f"AND PROCEDURE_NAME = '{proc_name}'"
    )
    return ACAssertion(
        ac_id=ac_id,
        ac_text=text,
        assertion_sql=sql,
        translatable=True,
        assertion_type="procedure_exists",
        expected_value="1",
    )


# Ordered list of matchers — first match wins
_MATCHERS = [
    _try_column_count,
    _try_row_count,
    _try_not_null,
    _try_has_column,
    _try_object_exists,
    _try_procedure_exists,
]


def translate_ac_to_assertion(
    ac_id: str, ac_text: str, schema: str
) -> ACAssertion:
    """Translate a single AC text into an executable SQL assertion.

    Parameters
    ----------
    ac_id:
        The acceptance criterion identifier (e.g., "AC-1/bullet-3").
    ac_text:
        The raw text of the acceptance criterion.
    schema:
        Fully qualified sandbox schema (e.g., "DB._SPECBUILDER_SANDBOX_20260521").

    Returns
    -------
    ACAssertion with assertion_sql if translatable, otherwise translatable=False.
    """
    for matcher in _MATCHERS:
        result = matcher(ac_id, ac_text, schema)
        if result is not None:
            return result

    # No pattern matched — mark as manual verification required
    return ACAssertion(
        ac_id=ac_id,
        ac_text=ac_text,
        assertion_sql=None,
        translatable=False,
        assertion_type="manual_verification_required",
    )


def extract_ac_items(content: str) -> list[dict[str, str]]:
    """Extract AC checklist items from spec markdown content.

    Parses lines matching:
        - [ ] Some criterion text
        - [x] Some completed criterion

    Returns list of {id, text, checked} dicts.
    """
    items: list[dict[str, str]] = []
    current_ac_section = ""
    bullet_counter = 0

    for line in content.split("\n"):
        # Track AC section headings
        heading_match = re.match(r"^###\s+(AC-\d+.*)", line)
        if heading_match:
            current_ac_section = heading_match.group(1).split(":")[0].strip()
            bullet_counter = 0
            continue

        # Match checkbox items
        checkbox_match = re.match(r"^\s*-\s+\[([ xX])\]\s+(.+)", line)
        if checkbox_match:
            bullet_counter += 1
            checked = checkbox_match.group(1).lower() == "x"
            text = checkbox_match.group(2).strip()
            ac_id = (
                f"{current_ac_section}/bullet-{bullet_counter}"
                if current_ac_section
                else f"bullet-{bullet_counter}"
            )
            items.append({"id": ac_id, "text": text, "checked": str(checked)})

    return items


def translate_spec_acs(
    spec_content: str, schema: str
) -> list[ACAssertion]:
    """Translate all AC items from a spec into assertions.

    Parameters
    ----------
    spec_content:
        Full markdown content of the spec module.
    schema:
        Fully qualified sandbox schema.

    Returns
    -------
    List of ACAssertion objects (mix of translatable and manual).
    """
    items = extract_ac_items(spec_content)
    assertions: list[ACAssertion] = []

    for item in items:
        assertion = translate_ac_to_assertion(item["id"], item["text"], schema)
        assertions.append(assertion)

    return assertions
