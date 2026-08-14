# Setup

Post-install steps for the Semantic View Toolkit. Desktop shows this after install; the SessionStart hook will warn if prerequisites are missing.

## 1. Install prerequisites

```bash
# uv (required for optimization and GEPA scripts)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Ensure `uv` is on your shell PATH. If you use zsh on macOS, add to `~/.zshenv` (not `.zshrc`) so non-interactive shells can find them:

```bash
# ~/.zshenv
export PATH="$HOME/.local/bin:$PATH"
```

## 2. Verify Snowflake grants

Run in Snowsight or via `snow sql`:

```sql
-- Core SV permissions
GRANT CREATE SEMANTIC VIEW ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <your_role>;

-- For evaluations and optimization
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <your_role>;
GRANT CREATE TASK ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT CREATE DATASET ON SCHEMA <database>.<schema> TO ROLE <your_role>;

-- Recommended: access to query history for discovery and VQR generation
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <your_role>;
```

See `PREREQUISITES.md` in this plugin for the full per-skill grant breakdown.

## 3. Confirm

Reload your Cortex Code session. The toolkit banner should appear at session start confirming it's active. If you see a "Setup Incomplete" warning, re-check step 1.
