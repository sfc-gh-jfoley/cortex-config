# Scrape Workflow — Fetch & Parse Snowflake Release Notes

## Overview

This reference describes how to fetch Snowflake behavior change documentation and parse it into structured data for impact analysis.

## Data Sources

### Primary: Behavior Change Bundle Pages

Each bundle has a dedicated documentation page:

```
https://docs.snowflake.com/en/release-notes/bcr-bundles/{YYYY_NN}/bcr-bundle-{YYYY_NN}
```

Example for bundle 2026_03:
```
https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_03/bcr-bundle-2026_03
```

### Secondary: Behavior Change Announcements (Index)

The index page lists all bundles with their lifecycle status:
```
https://docs.snowflake.com/en/release-notes/behavior-changes
```

### Tertiary: Unbundled Behavior Changes

Some changes are not in monthly bundles:
```
https://docs.snowflake.com/en/release-notes/bcr-bundles/un-bundled/unbundled-behavior-changes
```

### Optional: Weekly Release Notes

For non-BCR changes (deprecations, new features that replace old patterns):
```
https://docs.snowflake.com/en/release-notes/new-features
```

## Fetch Procedure

### Step 1 — Determine Target Bundle

If user said "latest", fetch the announcements index page first:

```
web_fetch("https://docs.snowflake.com/en/release-notes/behavior-changes")
```

Parse to find the most recent bundle that is either:
- **Disabled by Default** (upcoming, needs proactive assessment)
- **Enabled by Default** (imminent, needs urgent assessment)

### Step 2 — Fetch Bundle Detail Page

```
web_fetch("https://docs.snowflake.com/en/release-notes/bcr-bundles/{YYYY_NN}/bcr-bundle-{YYYY_NN}")
```

If this returns a redirect or 404, try alternate URL patterns:
```
https://docs.snowflake.com/en/release-notes/bcr-bundles/{YYYY_NN}/
```

### Step 3 — Parse Changes

Extract each behavior change entry. Typical structure on bundle pages:

- **Functional area** heading (e.g., "SQL Changes", "Security", "Data Loading")
- **Change title/description**
- **Before behavior** — how it worked previously
- **After behavior** — how it works now
- **Action required** — what customers need to do

Structure each change as:

```
{
  "bundle": "YYYY_NN",
  "category": "<functional area>",
  "title": "<change title>",
  "description": "<full description>",
  "before_behavior": "<old behavior>",
  "after_behavior": "<new behavior>",
  "action_required": "<remediation steps from docs>",
  "affected_features": ["<feature1>", "<feature2>"]
}
```

### Step 4 — Determine Lifecycle Status

From the announcements index page, determine each bundle's current status:

| Status | Meaning | Urgency |
|--------|---------|---------|
| Disabled by Default | Testing period, not yet active | Low — proactive planning |
| Enabled by Default | Active but can opt out | Medium — assess immediately |
| Generally Enabled | Locked, no override | High — must be compliant now |

### Step 5 — Check for Unbundled Changes

Also fetch unbundled behavior changes page and parse any recent entries that may not be in a numbered bundle.

## Output

Produce a structured list of all changes with their metadata. Pass this to Phase 2 (inventory) and Phase 3 (impact analysis).

## Troubleshooting

- **Page structure changed**: If `web_fetch` returns content that doesn't match expected patterns, inform the user and ask them to paste the relevant content or provide an updated URL.
- **Multiple bundles active**: It's common to have 2-3 bundles in different lifecycle stages simultaneously. Process all of them, clearly labeling each change with its bundle ID and status.
- **Rate limiting**: Space `web_fetch` calls with a brief pause if fetching multiple pages. Typically 3-5 pages per scan.
