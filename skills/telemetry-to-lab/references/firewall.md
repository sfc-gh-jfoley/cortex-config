# Firewall rules

Customer-facing files: `<slug>-lab-intake.md`, `data_spec.yaml`, `remap.md`, and anything lab-builder generates from them.
Internal files: everything under `internal/`.

## Deny list (built automatically by `scripts/firewall_scan.py` from `internal/`)
- customer name and its tokens (from `internal/account.json.customer`, and any extra names in `internal/deny_extra.txt`)
- account name, alias, id
- every database, schema, table, procedure, warehouse, role and user name found in `internal/findings.json` and
  `internal/evidence_map.md` (any UPPER_SNAKE identifier of 4+ chars, or a dotted FQN, found there)
- email addresses

The scan ignores generic words that also appear in the allow list (`references/allow.txt`, e.g. `CUSTOMER_ID`, `CONTACT_ID`,
`EVENT_DATE`) so ordinary column vocabulary doesn't trip it. If a real column name is also a natural generic
term, add it to allow.txt and note why in the same line.

## Forbidden phrasing (regex, case-insensitive)
`we (saw|noticed|observed|found)`, `your (account|failures|jobs|queries|warehouse)`, `in your environment`, `telemetry`,
`snowhouse`, `based on your usage`.

## Writing guidance
- Describe scenarios as "a <industry> organization" or "teams commonly...".
- Use lab-scale synthetic numbers only. Never reuse counts, percentages or credit figures from findings.
- Failure moments are framed as common pitfalls ("a frequent pattern is...").
