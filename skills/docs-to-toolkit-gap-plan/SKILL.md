---
name: docs-to-toolkit-gap-plan
description: >
  Review a Snowflake docs or blog URL against an existing skill/toolkit, prove each claimed gap with executable tests, then patch only the proven gaps. Use when: review doc for gaps, outline toolkit changes, ground-verify claims, build gap tests, publish patched plugin. Triggers: review this doc any gaps in the toolkit, outline changes to the toolkit, are these grounded double verify, build tests to prove these are real issues, publish the updated plugin over the old version.
version: 1.0.0
---

# Skill: docs-to-toolkit-gap-plan

Take a Snowflake doc or blog URL and an existing toolkit, prove each claimed gap with real tests, then patch only what the tests prove. The discipline this skill enforces is: no claim becomes a patch until a test says it must.

The failure mode this skill exists to prevent: an agent reads a blog, sees three things the toolkit doesn't mention, and patches all three in as guidance. Six months later a user follows that guidance and hits an error the blog never actually described — it was marketing, or a PrPr feature that rolled out differently, or a claim that was true on the blog author's account but not generally. The claim ledger plus the test results are what keep that from happening.

This skill owns three things — doc ingestion, claim extraction, and test-based gap proof. Auditing the existing plugin/skill tree against the checklist is delegated to `~/.snowflake/cortex/vault/skills/plugin-dev/SKILL.md` (audit mode). Publishing the patched result is delegated to the sibling skill `vault-skill-publish`. Do not restate their steps here.

---

## When to Use

- A doc, release notes, or blog post has been dropped on the table and the question is "what should change in the toolkit because of this?"
- A user suspects a toolkit is stale or missing coverage and wants it verified, not assumed.
- Someone wants changes proven before they ship, not patched on plausibility.
- A reviewer asked "are these gaps grounded, double-verify" — the ledger plus test results are the double-verify.

## When NOT to Use

- Pure "what does this doc say" summarization with no toolkit target — just read it.
- Authoring a new skill from scratch (use `plugin-dev` author mode).
- Auditing a plugin tree against the RC checklist without a source doc (use `plugin-dev` audit mode).
- Publishing alone with no new findings to verify (use `vault-skill-publish` directly).
- Performance tuning or cost analysis questions — no toolkit gap to prove.

---

## Prerequisites

- A target URL (docs page, release notes, or engineering blog post).
- The toolkit path being reviewed (skill dir or plugin dir).
- A live Snowflake connection for running tests — tests that cannot run are UNTESTABLE, not PROVEN.
- Enough privilege on the account to run the candidate tests. If a test needs a role you don't have, mark it UNTESTABLE up front rather than guessing at the result.

---

## Claim Ledger

Maintain this ledger from Phase 1 onward. It is the artifact that stops a plausible-sounding gap from being patched into a toolkit as fact without ever being run.

| Claim ID | Claim (verbatim from doc) | Doc status | Toolkit coverage | Test ID | Result | Action |
|---|---|---|---|---|---|---|
| C-01 | "<quoted sentence>" | GA / PrPr / LimitedAccess / blog-only | covered / partial / absent | T-01 | PROVEN / DISPROVEN / UNTESTABLE | patch / discard / monitor |

Status matters because a Private Preview (PrPr) feature behaves differently from GA and may not exist on the target account at all; patching a toolkit as though PrPr were GA produces guidance that fails for most users. Coverage is the toolkit's current state, not its desired state. Result is empty until Phase 4.

Worked row, to make the shape concrete:

| C-02 | "CREATE AGENT requires the SNOWFLAKE.CORTEX_USER database role." | GA | partial (role name wrong in toolkit) | T-02 | PROVEN | patch role reference |

The ledger is the single source of truth across the whole skill. Every later phase reads from it and writes back to it — the test plan is generated from the candidate-gap rows, the run results fill the Result column, and the patch set is derived from the PROVEN rows. If a row is not in the ledger, it does not get patched.

---

## Workflow

### Phase 1 — Extract claims

1. Fetch the doc with `web_fetch` on the supplied URL. For Snowflake-native feature behaviour, also run `cortex search docs "<query>"` to confirm the claim against the canonical docs corpus — the blog and the docs do not always agree, and the docs win.
2. Pull out concrete capability or pitfall claims verbatim. A claim is something testable or falsifiable ("X is unsupported", "Y requires role Z", "Z now defaults to W"). Vague marketing prose is not a claim — drop it.
3. Record release status per claim: GA, PrPr (Private Preview), LimitedAccess, or blog-only. If status is unclear, treat it as blog-only and downgrade your confidence. A blog-only claim about unreleased behaviour is the highest-risk source — it can describe an intent that shipped differently or not at all.
4. Seed the ledger with one row per claim. Coverage and Result stay blank until the phases that fill them.
5. Quote verbatim, not paraphrased. A paraphrase can silently soften a claim ("requires" becomes "prefers") and turn a real gap into a non-gap before any test runs.

### Phase 2 — Map to coverage

1. Open the toolkit and map each claim to current coverage: covered, partial, or absent. Read the actual files — don't trust the skill description or a grep hit; the guidance may live in a reference file the description doesn't mention.
2. Every candidate gap starts UNVERIFIED. Nothing is a gap until a test says so — this is the rule that keeps the ledger honest. A doc saying something is missing is a hypothesis, not a finding.
3. "Partial" coverage is the dangerous case: the toolkit mentions the feature but gets a detail wrong (wrong role name, wrong default, wrong minimum). Treat partial the same as absent for testing purposes — the test has to prove the detail, not just the mention.
4. Note where the toolkit already covers a claim well enough that no patch is needed; those rows move straight to Action = discard.

### Phase 3 — Write the test plan (STOP)

1. For each candidate gap, write one runnable test against a real account. Target 5-8 tests total — enough to cover the candidate gaps, few enough to run cheaply.
2. Each test has: a clear setup, an explicit expected result, and a pass/fail condition decided **before** running. Deciding the pass condition after the result is how a null gets reinterpreted as confirmation.
3. Prefer the simplest test that proves the claim: a `SHOW`, a `DESCRIBE`, a one-row DDL-then-check, or a `SELECT ... WHERE <condition the claim predicts>`. Avoid full pipeline builds for what is fundamentally a syntax or behaviour question.
4. State the pass condition in the form: "Test passes (gap PROVEN) if X happens; fails (DISPROVEN) if Y." Writing it as a branch beforehand keeps you honest when the result lands between the two.
5. Tests for PrPr features should first confirm the feature is reachable on the account; if it is not, the result is UNTESTABLE, not DISPROVEN. A feature that is not enabled is not the same as a feature that does not work.
6. Stop here and show the user the test plan plus pass conditions before spending account credits.

### Phase 4 — Run and record (STOP)

1. Run each test against the live account.
2. Record PROVEN (test failed as the gap predicted → the gap is real), DISPROVEN (toolkit already handles it, or the claim was wrong), or UNTESTABLE (feature not reachable, permissions missing, environment won't support it).
3. Discard anything not PROVEN. Say plainly that a discarded claim is **not** evidence of absence — only that it was not demonstrated. Record the distinction in the ledger so a future pass can revisit it.
4. Guard against the recurring error: absence from documentation is not evidence a capability does not exist, particularly for recently announced products. Require a positive citation before recording something as missing. A blog not mentioning a feature does not mean the feature is missing — it means the blog didn't mention it.
5. Stop and confirm with the user which PROVEN gaps to patch before editing the toolkit.

### Phase 5 — Patch proven gaps only

1. Patch only the PROVEN gaps: new audit checks, blocking rules, reference entries, or corrected guidance.
2. While patching, check for bloat — a skill that grows to cover every doc it ever reviewed stops being loadable:
   - Content duplicated from another toolkit → point to the source instead of copy-pasting. A one-line reference beats a thirty-line restatement.
   - Stale artifacts the doc just superseded → remove the old version, don't leave both. Two contradictory guidance blocks is worse than one wrong one.
   - File drifting past the ~500-line conciseness budget → split into a reference file or trim. The SKILL.md is an index and a workflow, not a knowledge base.
   - A patch that only rephrases existing guidance without changing behaviour → drop it. Cosmetic edits inflate the diff and obscure the real fixes.
3. Keep the diff minimal and reviewable. A gap proof that needs three lines of guidance should not produce thirty.
4. For the actual audit of the patched tree against the RC checklist, load `~/.snowflake/cortex/vault/skills/plugin-dev/SKILL.md` in audit mode — do not restate its checklist here.

### Phase 6 — Publish

1. Hand off to the sibling skill `vault-skill-publish` for publish + git backup. This skill does not describe publish steps; `vault-skill-publish` owns them.
2. If `vault-skill-publish` is not installed, stop and tell the user — do not improvise publish steps from memory.

---

## Stopping Points

- **After Phase 3** — review the test plan and pass conditions with the user before spending account credits. Tests with post-hoc pass conditions are worthless.
- **After Phase 4** — confirm which PROVEN gaps to patch. Discarded claims stay in the ledger as UNTESTABLE or DISPROVEN, not silently deleted.
- **Before Phase 6** — the patch diff is committed and reviewed. Do not publish a patch the user has not seen.

---

## Output

1. The completed claim ledger (all columns filled, including Action). This is the primary artifact — it is what a reviewer inspects to see that every patch was earned.
2. The test scripts, saved alongside the toolkit for re-run. Future doc reviews can reuse tests for claims that recur, so the second pass against the same toolkit is cheaper than the first.
3. The toolkit diff — minimal, only PROVEN gaps. A diff touching files the tests never exercised is a signal you patched on plausibility.
4. A one-paragraph summary: what was proven vs what was discarded, and why discarded is not the same as false. UNTESTABLE claims are flagged for a later pass, not silently buried.

The summary is what gets handed to `vault-skill-publish` as the changelog entry. It should name the doc, the count of proven vs discarded claims, and the net change to the toolkit — nothing more.

Do not publish without the ledger. A patch set with no provenance is a liability in a shared vault.
