# Security Checklist

Reusable security checklist for code review. Used by the Security Architect role
in agent-architect, but standalone — can be referenced by any skill or review process.

## Universal (All Stacks)

- [ ] **Hardcoded credentials** — passwords, tokens, API keys, account IDs in code?
- [ ] **Secrets in config** — .env / config files committed with real values?
- [ ] **Privilege escalation** — code grants permissions, creates users, or bypasses access controls?
- [ ] **External network calls** — HTTP/socket calls to unapproved external hosts?
- [ ] **Dependency confusion** — imports from unverified packages or unpinned dependencies?
- [ ] **Logging sensitive data** — PII, tokens, or credentials written to logs?
- [ ] **Error message leakage** — stack traces or internal paths exposed to users?

## SQL / Snowflake

- [ ] **SQL injection** — string interpolation or f-strings building SQL without parameterization?
- [ ] **PII exposure** — SELECT returning PII-tagged columns without masking?
- [ ] **DDL without rollback** — CREATE/ALTER/DROP without documented restore path?
- [ ] **Destructive DML** — DELETE/TRUNCATE/MERGE without WHERE or dry-run flag?
- [ ] **Dynamic SQL in procs** — EXECUTE IMMEDIATE with user-controlled input?
- [ ] **Over-broad grants** — GRANT ALL or GRANT OWNERSHIP to PUBLIC or unknown role?
- [ ] **Missing colon prefix** — Variables in stored proc SQL body without `:` prefix?
- [ ] **Unguarded DDL** — CREATE without IF NOT EXISTS in setup scripts?

## Python / Backend

- [ ] **Command injection** — subprocess/os.system with unvalidated input?
- [ ] **Path traversal** — open() / Path() with user-controlled strings?
- [ ] **Pickle / deserialization** — loading untrusted serialized data?
- [ ] **Debug endpoints** — Flask debug=True, print(secret), logging credentials?
- [ ] **Unsafe YAML** — yaml.load() without SafeLoader?
- [ ] **Regex DoS** — unbounded regex on user input (ReDoS)?

## JavaScript / TypeScript / React

- [ ] **XSS** — dangerouslySetInnerHTML, innerHTML, eval() with user input?
- [ ] **Client-side secrets** — API keys, tokens in frontend code or bundled env vars?
- [ ] **CSRF** — state-changing requests without CSRF protection?
- [ ] **Prototype pollution** — Object.assign / deep merge with user-controlled keys?
- [ ] **Open redirects** — window.location set from user-controlled values?

## iOS / Mobile

- [ ] **Keychain vs UserDefaults** — sensitive data stored in UserDefaults instead of Keychain?
- [ ] **ATS exceptions** — NSAllowsArbitraryLoads = true without justification?
- [ ] **Certificate pinning** — network calls without cert pinning for sensitive endpoints?
- [ ] **Logging PII** — print() / NSLog() outputting personal data?
- [ ] **Biometric bypass** — auth fallback that doesn't require re-authentication?

## Snowflake Native App

- [ ] **Over-broad manifest** — requesting more privileges than necessary in manifest.yml?
- [ ] **Consumer data access** — app reading column values (not just metadata)?
- [ ] **Exfiltration risk** — data written outside app container to external stage?
- [ ] **Missing REFERENCE** — setup_script SELECTs consumer tables without REFERENCE in manifest?

## Infrastructure / Deploy

- [ ] **Secrets in CI** — tokens or credentials in pipeline YAML without secret masking?
- [ ] **Overprivileged service accounts** — CI/CD using ACCOUNTADMIN or equivalent?
- [ ] **Missing encryption** — data at rest or in transit without encryption?
- [ ] **No audit trail** — destructive operations without logging who/when/what?

---

## Severity Guide

| Severity | Criteria | Example |
|---|---|---|
| **CRITICAL** | Immediate exploitable vulnerability, data breach risk | SQL injection in user-facing endpoint, hardcoded production credentials |
| **HIGH** | Exploitable with some effort, significant data risk | Path traversal, over-broad grants, missing auth check |
| **MEDIUM** | Requires specific conditions, limited blast radius | Logging PII, missing CSRF on low-impact endpoint |
| **LOW** | Best practice violation, no immediate exploit path | Unpinned dependencies, missing IF NOT EXISTS |

## Usage

SecArch runs every applicable section based on detected stack.
Mark each check: PASS / FAIL / NA.
Any FAIL at CRITICAL or HIGH level → task REJECTED.
