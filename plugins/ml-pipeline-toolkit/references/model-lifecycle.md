# Model Lifecycle SQL Reference

Alias-based promotion, rollback, cross-environment copy, and version management.

---

## Promotion via Alias (Preferred)

Consumer code should reference an **alias**, never a hardcoded version string. Alias reassignment is atomic and zero-downtime.

```sql
-- Promote v2 to PROD
ALTER MODEL <db>.<schema>.<model_name>
    VERSION '<v2>' SET ALIAS = 'PROD';

-- Rollback to v1 (reassign alias — no consumer code change needed)
ALTER MODEL <db>.<schema>.<model_name>
    VERSION '<v1>' SET ALIAS = 'PROD';
```

```python
# Consumer code pattern:
mv = reg.get_model("<name>").alias("PROD")  # resolves to whatever version PROD points to
scored = mv.run(df, function_name="predict")
```

---

## Default Version

```sql
-- Change which version .default resolves to
ALTER MODEL <db>.<schema>.<model_name>
    SET DEFAULT_VERSION = '<v1>';
```

```python
mv = reg.get_model("<name>").default  # resolves to DEFAULT alias
```

---

## Cross-Environment Copy

> There is **no `COPY MODEL` command**. Use `CREATE MODEL ... FROM MODEL` syntax.

```sql
-- Copy version to new model object in prod database
CREATE MODEL <prod_db>.<schema>.<model_name>
    FROM MODEL <dev_db>.<schema>.<model_name>
    VERSION '<version>';

-- Or add version to existing prod model object
ALTER MODEL <prod_db>.<schema>.<model_name>
    ADD VERSION '<version>'
    FROM MODEL <dev_db>.<schema>.<model_name> VERSION '<version>';
```

---

## Inspect Version History

```sql
-- All versions with aliases, metrics, comments
SHOW VERSIONS IN MODEL <db>.<schema>.<model_name>;

-- Method signatures and full metadata
DESCRIBE MODEL <db>.<schema>.<model_name>;
```

---

## System Aliases

| Alias | Meaning |
|-------|----------|
| `DEFAULT` | Version returned by `.default`; reassignable via `SET DEFAULT_VERSION` |
| `FIRST` | Earliest version by creation time; non-removable |
| `LAST` | Most recent version by creation time; non-removable |

System aliases cannot be deleted or reassigned to point to arbitrary versions.

---

## Version Limits

| Limit | Value |
|-------|-------|
| Versions per model | 1,000 |
| Methods per version | 10 |
| Arguments per method | 500 |
| Metadata size | 100 KB |
| Storage per version (warehouse) | 15 GB |

---

## Immutability Note

Version **implementations** are immutable once logged. Only `comment` and custom **aliases** can be changed after registration. To update model logic: log a new version.
