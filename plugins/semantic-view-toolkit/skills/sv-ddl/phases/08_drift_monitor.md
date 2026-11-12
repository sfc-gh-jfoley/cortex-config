---
name: sv-ddl-phase8-drift-monitor
description: Pointer only. Drift monitoring for deployed semantic views is owned by sv-watch.
---

# Phase 8: Drift Monitor (moved)

sv-ddl ends at Phase 7. Drift monitoring, health checks and scheduled runs for a deployed
semantic view are owned by the **sv-watch** skill
([../../sv-watch/SKILL.md](../../sv-watch/SKILL.md)).

Any fix that sv-watch finds is made on a `cand` candidate copy and reaches production only
through gate `SV-PROMOTE` ([../../../references/candidate-promotion.md](../../../references/candidate-promotion.md)).
