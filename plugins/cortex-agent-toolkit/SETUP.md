# Setup

Post-install steps for the Cortex Agent Toolkit. Desktop shows this after install; the SessionStart hook will warn if prerequisites are missing.

## 1. Install prerequisites

```bash
# snow CLI (required for agent operations)
# See: https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation
brew install snowflake-cli  # macOS

# uv (required for evaluation and GEPA scripts)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Ensure both are on your shell PATH. If you use zsh on macOS, add to `~/.zshenv` (not `.zshrc`) so non-interactive shells can find them:

```bash
# ~/.zshenv
export PATH="$HOME/.local/bin:$PATH"  # uv
export PATH="$HOME/.snowflake/snow/bin:$PATH"  # snow (if installed via installer)
```

## 2. Configure snow connection

```bash
snow connection add   # interactive setup
snow connection test  # verify it works
```

The connection must point to the same Snowflake account you use in Cortex Code.

## 3. Verify Snowflake grants

Run in Snowsight or via `snow sql`:

```sql
-- Core agent permissions
GRANT CREATE AGENT ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <your_role>;

-- For evaluations
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <your_role>;
GRANT CREATE DATASET ON SCHEMA <database>.<schema> TO ROLE <your_role>;
```

See `PREREQUISITES.md` in this plugin for the full grant list.

## 4. Confirm

Reload your Cortex Code session. The toolkit banner should appear at session start confirming it's active. If you see a "Setup Incomplete" warning, re-check steps 1–2.
