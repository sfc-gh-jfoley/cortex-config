---
name: telemetry-to-lab-handoff
description: Phase 50. Write the lab-builder intake, run the firewall scan, hand off.
parent_skill: telemetry-to-lab
---

# 50 — Handoff

**Inputs:** `internal/selection.json`, `data_spec.yaml`, `remap.md`. **Output:** `<slug>-lab-intake.md`.

## Steps
1. **Write `<slug>-lab-intake.md`** from `references/intake-template.md`. Every value comes from selection and data_spec.
   Account config fields (account, isolation, DBA contact) stay as `TBD` placeholders. The SE fills those in, not telemetry.
2. **Optional SV spec.** If a selected intent involves semantic views or agents, append an "SV candidates" section using
   archetype names only (tables, grain, joins, candidate metrics), suitable for `sv-ddl` against the lab schema.
3. **Firewall scan** (mandatory):
   ```bash
   python3 ~/.snowflake/cortex/vault/skills/telemetry-to-lab/scripts/firewall_scan.py ~/telemetry-labs/<slug>
   ```
   Exit 0 means clean. On any hit, rewrite the offending text (rename to the archetype or industry term) and re-run.
   Never hand off with hits, and never weaken the deny list to get a pass.
4. **Self-review**: read the intake once as if you were the customer. Anything that sounds like "we noticed" or quotes
   a number that could only come from their telemetry must go. Numbers in the lab are lab-scale synthetic only.
5. **Tell the user:**
   - "Run `lab-builder` with `~/telemetry-labs/<slug>/<slug>-lab-intake.md`. It will take the intake fast path."
   - `data_spec.yaml` drives `hol_setup.sql` generation; `remap.md` goes in the lab's `AGENTS.md` / bonus module.
   - `internal/evidence_map.md` is for the account team only.

## lab-builder compatibility (tested unpatched, 2026-10-28)

The handoff **works without patching lab-builder**, with these caveats. Patch only if a future run hits them.

1. **`data_spec.yaml` is consumed only via the intake's pointer.** lab-builder's fast path documents only
   `*-lab-intake.md`; it has no contract for a sibling `data_spec.yaml` or `remap.md`. The intake must keep the
   explicit lines "See `data_spec.yaml`" and "Include `remap.md`", and name every table, starter and seeded lift.
   *Patch if needed:* in the vault copy of lab-builder's "Intake Document Fast Path", add "If `data_spec.yaml` sits
   next to the intake, generate `hol_setup.sql` archetypes, starters and seeded effects from it."
2. **lab-builder's validate pattern for agents is wrong.** `INFORMATION_SCHEMA.CORTEX_AGENTS` does not exist (verified).
   Use `SHOW AGENTS LIKE '<name>' IN SCHEMA` + `RESULT_SCAN` into a session variable before the UNION ALL. The same
   SHOW pattern was used for semantic views. *Patch:* fix the "Agent exists" check pattern in lab-builder Phase 5.
3. **Open questions are asked up front** (isolation, duration, analyst path). Pre-answer them in the intake when known
   to avoid the extra round.
4. **Seeded effects need sizing.** The first data pass had lift buried in noise (control cells ~100) and a 38-row
   audience. Specify in data_spec: minimum control-cell size (≥300), attribution window, campaign overlap, and the
   expected size of the hero-question audience. Verify by running hol_setup in a scratch account before shipping.
5. **Incremental dynamic tables reject ANY_VALUE.** Put this in data_spec `modules_hint` so the solution and hints
   are right the first time.
