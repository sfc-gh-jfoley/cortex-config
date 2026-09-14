---
name: sv-agent-findings-handoff
description: "Turn semantic-view and Cortex Agent failure analysis into a grounded, customer-ready remediation document. Use when: findings need packaging, customer handoff, remediation plan. Triggers: does this cover all findings, build a plan the customer can apply, ground these findings in data and docs not guesswork, write out each issue and how to fix it, is this ready to give to the customer"
version: 1.0.0
---

# Skill: sv-agent-findings-handoff

This skill owns one thing: turning analysis findings into a document a customer can act on without you in the room. It does not perform the analysis itself — that lives in the toolkits.

## When to Use

- You have completed (or are mid-way through) a semantic-view or Cortex Agent evaluation and need to package findings for a customer or internal handoff.
- Someone asks whether the findings are "ready to send" or "cover everything."
- You need to separate what *you* can fix from what the *customer* must decide.

## When NOT to Use

- You haven't run an evaluation yet. Load the toolkit first — this skill consumes findings, it doesn't produce them.
- The audience is yourself or another agent. Skip the formality; just fix the issues.
- You need to build or deploy a semantic view or agent. Use the toolkits directly.

## Prerequisites

- **Semantic-view toolkit** — `~/.snowflake/cortex/vault/plugins/semantic-view-toolkit/SKILL.md`
- **Cortex-agent toolkit** — `~/.snowflake/cortex/vault/plugins/cortex-agent-toolkit/SKILL.md`

Load the relevant toolkit before entering this workflow. This skill references findings and evidence the toolkit produces; it never duplicates that analysis logic.

## Workflow

### Phase 1 — Re-analyze from source

Load the relevant toolkit and re-read the actual YAML, DDL, spans, or observability output. Do not rely on a prior summary already in the conversation.

A summary is lossy — it filters and paraphrases, so errors in the first pass get laundered into the deliverable and become impossible to catch later. Go back to the artifact.

### Phase 2 — Classify each issue

Assign every issue to exactly one bucket:

| Bucket | Owner | Examples |
|--------|-------|---------|
| **(a) Semantic-view definition defect** | Builder (you or customer) | Wrong join, missing filter, bad grain, VQR mismatch |
| **(b) Agent instruction / tool gap** | Builder | Missing tool binding, hallucinated column, poor instruction wording |
| **(c) Platform limitation — ENG triage** | Snowflake engineering | Unsupported function, known bug, feature gap |

The bucket is the single most useful thing the document conveys — it tells the reader who can actually fix each issue.

### Phase 3 — Attach evidence

Every issue needs a citation: the VQR that fails, the span showing the wrong SQL, the observability event, or the doc reference. If you cannot find evidence:

> Mark the issue `UNVERIFIED — do not assert to customer` rather than dropping it. The reader can see what still needs proving.

Where verification SQL is needed, run `cortex search docs` first to confirm syntax. Do not invent Snowflake SQL from memory.

### Phase 4 — Surface customer decisions

Some issues cannot be resolved by analysis alone. Separate these out:

- Ambiguous join keys (which FK is canonical?)
- Column semantics (is `revenue` gross or net?)
- Expected grain (one row per order or per line item?)
- Business logic the YAML encodes but nobody confirmed

For each, state the exact question and the minimum information required to unblock. These stall the entire document if not surfaced early.

### Phase 5 — Write issue sections

Use the template below, one section per issue. Keep language concrete — a reader with access to the Snowflake account but zero prior context should be able to execute every fix independently.

### Phase 6 — Self-review pass

Read the full document as someone seeing it cold:

- Every acronym expanded on first use.
- Every fix independently runnable (no "see above" references that break if sections reorder).
- Every unproven claim labelled `UNVERIFIED`.
- No toolkit jargon leaking through (e.g. internal eval-framework terms).

## Issue Section Template

```markdown
### ISS-<NNN>: <short title>

**Severity:** Critical | High | Medium | Low
**Bucket:** (a) SV defect / (b) Agent gap / (c) Platform — ENG triage
**Status:** Fixed | Open | Unverified

**Symptom:** What the user or evaluator observes.

**Root cause:** Why it happens — trace to the specific YAML block, instruction line, or platform behavior.

**Evidence:**
- <VQR name, span ID, observability event, or doc link>

**Customer input required:** <Exact question> / None

**Fix:**
```sql
-- or instruction text; runnable as-is
```

**Verification:**
```sql
-- query that confirms the fix worked
```
```

## Stopping Points

- **After Phase 4:** Present the customer-decision list and wait for answers before proceeding. Writing fixes for ambiguous items produces confident wrong answers — the document's credibility depends on not guessing.
- **Before delivery:** Confirm which `UNVERIFIED` items may be included. The customer may prefer a clean document over a complete one.

## Output

Two artifacts:

1. **Remediation document** — one markdown file with all issue sections, ordered by severity within each bucket.
2. **Cover summary** — a short block at the top:
   - Issue counts by bucket and severity.
   - List of items blocked on customer input.
   - List of `UNVERIFIED` items included (if any).
