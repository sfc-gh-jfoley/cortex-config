---
name: ml-lifecycle
description: "Manage Snowflake model version lifecycle: promote to production, rollback, copy across environments, deprecate. Use when: promoting a model version from dev to prod, rolling back to a previous version, copying models between databases, deprecating old versions."
---

## ml-lifecycle

Manage model version promotion, rollback, cross-environment copy, and deprecation using Snowflake Model Registry.

---

### Core Concept: Aliases as the Promotion Primitive

Consumer code should **always reference an alias** (e.g., `PROD`) — never a hardcoded version string. Reassigning the alias is a zero-downtime promotion or rollback; no consumer code changes required.

---

### Phase 1: Promote to Production (Alias Reassignment)

```sql
-- Assign PROD alias to new version
ALTER MODEL <database>.<schema>.<model_name>
    VERSION '<v2>' SET ALIAS = 'PROD';

-- Consumer code using .alias("PROD") automatically resolves to v2

-- Rollback: reassign alias to previous version
ALTER MODEL <database>.<schema>.<model_name>
    VERSION '<v1>' SET ALIAS = 'PROD';
-- Zero-downtime; no consumer code change needed
```

```python
# Consumer code pattern (rollback-safe)
mv = reg.get_model("<MODEL_NAME>").alias("PROD")
scored = mv.run(df, function_name="predict")
```

---

### Phase 2: Change Default Version (Alternative Rollback)

```sql
-- Change which version .default resolves to
ALTER MODEL <database>.<schema>.<model_name>
    SET DEFAULT_VERSION = '<v1>';
```

---

### Phase 3: Copy Model to Production Environment

> **NOTE:** There is no `COPY MODEL` command. Use `CREATE MODEL ... FROM MODEL` syntax.

```sql
-- Copy version to new model object in prod database
CREATE MODEL <prod_db>.<schema>.<model_name>
    FROM MODEL <dev_db>.<schema>.<model_name>
    VERSION '<version>';

-- Or add a version to an existing prod model object
ALTER MODEL <prod_db>.<schema>.<model_name>
    ADD VERSION '<version>'
    FROM MODEL <dev_db>.<schema>.<model_name> VERSION '<version>';
```

---

### Phase 4: Inspect Version History

```sql
-- All versions with aliases and metadata
SHOW VERSIONS IN MODEL <database>.<schema>.<model_name>;
-- Columns: name, aliases, comment, created_on, metrics

-- Full signatures and methods
DESCRIBE MODEL <database>.<schema>.<model_name>;
```

---

### Phase 5: Deprecate Old Versions

```python
# Tag as deprecated via comment and alias
old_version = reg.get_model("<name>").version("<old_v>")
old_version.comment = "DEPRECATED: superseded by v3 on 2026-05-27"
old_version.set_alias("DEPRECATED")  # custom alias for tracking
```

```sql
-- Revoke consumer access to old model
REVOKE USAGE ON MODEL <database>.<schema>.<model_name> FROM ROLE <consumer_role>;
```

---

### Phase 6: RBAC Governance

```sql
-- Grant consumer access
GRANT USAGE ON MODEL <db>.<schema>.<model> TO ROLE <consumer_role>;
GRANT READ  ON MODEL <db>.<schema>.<model> TO ROLE <consumer_role>;
-- READ: view metadata + run inference

-- Transfer ownership
GRANT OWNERSHIP ON MODEL <db>.<schema>.<model> TO ROLE <owner_role>;
```

---

### Reference

| Concept | Detail |
|---|---|
| System aliases | `DEFAULT`, `FIRST`, `LAST` — built-in, non-removable |
| Alias target | Points to a version; reassignment is atomic |
| Version limit | 1,000 versions per model |
| Immutability | Version implementations immutable; only `comment` and aliases changeable |
| COPY MODEL | Does not exist; use `CREATE MODEL ... FROM MODEL` |

---

### Success Criteria

- [ ] New version has `PROD` alias assigned
- [ ] Consumer code references alias (not version string)
- [ ] Old version has no active alias (or `DEPRECATED` alias assigned)
- [ ] Cross-environment copy verified with `SHOW VERSIONS IN MODEL`
- [ ] RBAC grants confirmed for consumer roles
