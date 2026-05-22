---
name: memory-organizer
description: "Organize, consolidate, and maintain the /memories directory. Inspired by Auto Dream — REM sleep for your AI coding agent. Use when: organizing memories, cleaning up memories, running memory audit, consolidating memory files. Triggers: organize memories, clean up memories, memory audit, consolidate memories, dream, auto dream."
---

# Memory Organizer Skill

## Workflow

### Phase 1: Orient
1. `view /memories` directory structure
2. Read `INDEX.md` to understand current index state
3. Read ALL topic files and project files to build a mental map
4. Note file sizes — any file contributing to INDEX.md should be tracked for bloat

### Phase 2: Gather Signal
Look for new information worth persisting. Sources in priority order:

1. **Existing memories that drifted** — facts that contradict what's true now (e.g., references to deleted files, old framework choices, completed projects still marked active)
2. **Temporal decay** — scan ALL files for relative date references ("yesterday", "last week", "recently", "today", "this morning"). These lose meaning as memories age.
3. **Cross-file contradictions** — two files disagreeing about the same fact (e.g., a project listed as active in INDEX.md but marked COMPLETE in its project file)
4. **Duplicate content** — same information captured in multiple files
5. **Orphaned references** — links to files/paths/objects that no longer exist

### Phase 3: Consolidate
For each issue found, fix it at the source. Do NOT just flag issues — resolve them.

**Date normalization (MANDATORY):**
- Convert ALL relative dates to absolute dates: "yesterday" → "2026-03-24", "last week" → "week of 2026-03-16"
- If the original date cannot be determined, use "circa YYYY-MM" based on file context
- Absolute dates remain interpretable no matter when the memory is read

**Contradiction resolution:**
- When two files disagree, determine which is correct (usually the more recent one)
- Fix the wrong entry at the source — do not add a third note explaining the conflict
- If unsure which is correct, ask the user before resolving

**Merge and deduplicate:**
- Merge overlapping entries across files into the authoritative topic file
- If three sessions noted the same build quirk, consolidate into one clean entry
- Prefer existing topic files over creating new ones

**Prune stale content:**
- Remove debugging notes referencing deleted files or resolved issues
- Remove progress logs for completed work (archive the essentials only)
- Remove entries about tools/patterns no longer in use

### Phase 4: Prune and Index
Update `INDEX.md` to stay **under 200 lines**. It is an **index**, not a dump.

1. Remove pointers to memories that are stale, wrong, or superseded
2. Demote verbose entries: keep the gist in the index, move detail into topic files
3. Add pointers to newly important memories
4. Resolve contradictions between index and actual file contents
5. Reorder entries by relevance and recency
6. Files that didn't need changes during consolidation — leave untouched

### Phase 5: Validate
1. View final `/memories` structure
2. Confirm INDEX.md is accurate and under 200 lines
3. Verify no orphaned references remain
4. Confirm no relative dates remain in any file
5. Brief summary of what was consolidated, updated, or pruned. If nothing changed, say so.

## Directory Structure Standard
```
/memories/
├── INDEX.md                    # Master index, UNDER 200 LINES (REQUIRED)
├── SESSION_PROTOCOL.md         # Session start/end checklists
├── <topic>_learnings.md        # Technical reference by topic
├── skills_inventory.md         # Installed skills tracking
├── projects/
│   ├── active/                 # Current work
│   │   └── <project>.md
│   └── archive/                # Completed work (condensed)
│       └── <project>.md
```

## Safety Constraints
- **Read-only to project code.** During memory organization, ONLY write to /memories files. Do not modify source code, configurations, or any project files.
- **One run at a time.** Do not run memory organization concurrently with another consolidation pass.
- **Non-destructive by default.** When unsure whether content is stale, keep it. Better to prune conservatively than lose useful context.

## Anonymization Policy (MANDATORY)
- **INDEX.md and top-level memory files MUST NOT contain customer names, people names, or account-specific identifiers**
- Use generic descriptions (e.g., "Competitive tech stack deck" not "[Customer] tech stack deck")
- Project detail files under `projects/active/` and `projects/archive/` MAY contain customer info
- This applies to: INDEX.md, skills_inventory.md, SESSION_PROTOCOL.md, and any *_learnings.md files

## Archive Guidelines
When archiving completed projects, keep only:
- Project location/identifiers
- Key commands or patterns to reuse
- Final deliverables summary
- Lessons learned (if any)

Remove:
- Step-by-step progress logs
- Debugging notes
- Intermediate findings

## Maintenance Schedule
- Run audit when memories exceed 10 files or feel cluttered
- Archive projects within 1 week of completion
- After major refactors or framework changes, run a consolidation pass immediately
