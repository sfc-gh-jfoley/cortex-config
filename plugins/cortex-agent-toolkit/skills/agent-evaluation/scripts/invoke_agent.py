#!/usr/bin/env python3
"""
Invoke a Cortex Agent via REST API and capture response with tool usage details.

Usage:
    Single question:
        python invoke_agent.py <database> <schema> <agent_name> "<question>" <connection>

    Batch mode (from eval table):
        python invoke_agent.py <database> <schema> <agent_name> --batch <eval_table> <connection>

Example:
    python invoke_agent.py MY_DB MY_SCHEMA MY_AGENT "What is the top product?" my_conn
    python invoke_agent.py MY_DB MY_SCHEMA MY_AGENT --batch MY_DB.MY_SCHEMA.EVAL_TABLE my_conn
"""

import os
import json
import re
import sys
import time
import snowflake.connector
import requests

# Strict FQN pattern: DB.SCHEMA.TABLE with alphanumeric + underscore only
_FQN_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*$')


def _validate_fqn(name: str, label: str):
    """Validate that name is a safe 3-part Snowflake identifier."""
    if not _FQN_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label}: '{name}'. "
            f"Must be DB.SCHEMA.TABLE with alphanumeric/underscore characters only."
        )

# Strict FQN pattern: DB.SCHEMA.TABLE with alphanumeric + underscore only
_FQN_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*$')

def _validate_fqn(name: str, label: str):
    """Validate that name is a safe 3-part Snowflake identifier."""
    if not _FQN_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label}: '{name}'. "
            f"Must be DB.SCHEMA.TABLE with alphanumeric/underscore characters only."
        )


def get_snowflake_url_and_token(connection_name: str):
    conn = snowflake.connector.connect(connection_name=connection_name)
    cursor = conn.cursor()
    cursor.execute("SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME()")
    org, account = cursor.fetchone()
    account_fixed = account.replace('_', '-').lower()
    org_fixed = org.lower()
    base_url = f"https://{org_fixed}-{account_fixed}.snowflakecomputing.com"
    token = conn.rest.token
    cursor.close()
    return conn, base_url, token


def invoke_agent(database: str, schema: str, agent_name: str, question: str,
                 base_url: str, token: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f'Snowflake Token="{token}"'
    }

    payload = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": question}]}
        ]
    }

    url = f"{base_url}/api/v2/databases/{database}/schemas/{schema}/agents/{agent_name}:run"

    try:
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
    except requests.exceptions.RequestException as e:
        return {"question": question, "error": str(e)}

    if response.status_code != 200:
        return {"question": question, "error": f"HTTP {response.status_code}: {response.text[:500]}"}

    result = {
        "question": question,
        "answer": "",
        "tool_uses": [],
        "tool_results": []
    }

    current_event = None

    for line in response.iter_lines():
        if not line:
            continue
        line_str = line.decode('utf-8')

        if line_str.startswith('event: '):
            current_event = line_str[7:].strip()
            continue

        if not line_str.startswith('data: '):
            continue

        data = line_str[6:]
        if data.strip() == '[DONE]':
            break

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue

        if current_event == 'response.tool_use' and parsed.get('name'):
            result["tool_uses"].append({
                "name": parsed.get('name'),
                "type": parsed.get('type'),
                "input": parsed.get('input'),
                "tool_use_id": parsed.get('tool_use_id')
            })

        if current_event == 'response.tool_result' and 'content' in parsed:
            for item in parsed['content']:
                if isinstance(item, dict) and 'json' in item:
                    tool_result = item['json']
                    if 'sql' in tool_result:
                        result["tool_results"].append({
                            "type": "analyst",
                            "sql": tool_result['sql'],
                            "result_set": tool_result.get('result_set', {}).get('data', [])[:5]
                        })
                    elif 'search_results' in tool_result:
                        result["tool_results"].append({
                            "type": "search",
                            "search_results": tool_result['search_results'][:5]
                        })
                    else:
                        result["tool_results"].append({"type": "other", "data": tool_result})

        if current_event == 'response.text.delta' and 'text' in parsed:
            result["answer"] += parsed.get('text', '')

        if current_event == 'response.text' and 'text' in parsed:
            if not result["answer"]:
                result["answer"] = parsed.get('text', '')

    return result


def run_batch(database: str, schema: str, agent_name: str,
              eval_table: str, connection_name: str):
    _validate_fqn(eval_table, "eval-table")
    conn, base_url, token = get_snowflake_url_and_token(connection_name)
    cursor = conn.cursor()

    cursor.execute(f"SELECT INPUT_QUERY FROM {eval_table}")
    questions = [row[0] for row in cursor.fetchall()]
    cursor.close()

    print(f"Running {len(questions)} questions against {database}.{schema}.{agent_name}\n")

    results = []
    for i, question in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {question[:80]}...")
        start = time.time()
        result = invoke_agent(database, schema, agent_name, question, base_url, token)
        elapsed = time.time() - start
        result["duration_sec"] = round(elapsed, 1)

        tools_used = [t["name"] for t in result.get("tool_uses", [])]
        has_error = "error" in result

        status = "ERROR" if has_error else ("NO TOOLS" if not tools_used else "OK")
        print(f"  → {status} | Tools: {tools_used} | {elapsed:.1f}s")

        results.append(result)

    conn.close()

    print(f"\n{'='*60}")
    print(f"BATCH SUMMARY")
    print(f"{'='*60}")
    ok = sum(1 for r in results if r.get("tool_uses") and "error" not in r)
    no_tools = sum(1 for r in results if not r.get("tool_uses") and "error" not in r)
    errors = sum(1 for r in results if "error" in r)
    print(f"  OK (tools used): {ok}/{len(results)}")
    print(f"  No tools used:   {no_tools}/{len(results)}")
    print(f"  Errors:          {errors}/{len(results)}")

    tool_counts = {}
    for r in results:
        for t in r.get("tool_uses", []):
            name = t["name"]
            tool_counts[name] = tool_counts.get(name, 0) + 1

    if tool_counts:
        print(f"\n  Tool usage distribution:")
        for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            print(f"    {name}: {count}")

    return results


def run_single(database: str, schema: str, agent_name: str,
               question: str, connection_name: str):
    conn, base_url, token = get_snowflake_url_and_token(connection_name)
    conn.close()

    print(f"Invoking {database}.{schema}.{agent_name}...")
    print(f"Question: {question}\n")

    result = invoke_agent(database, schema, agent_name, question, base_url, token)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        return result

    print(f"{'='*60}")
    print("TOOL USES:")
    print(f"{'='*60}")
    for tu in result["tool_uses"]:
        print(f"  Tool: {tu['name']} ({tu['type']})")
        if tu['input']:
            print(f"  Input: {json.dumps(tu['input'], indent=4)}")
        print()

    print(f"{'='*60}")
    print("TOOL RESULTS:")
    print(f"{'='*60}")
    for tr in result["tool_results"]:
        if tr.get("type") == "analyst":
            print(f"SQL:\n{tr['sql'][:500]}")
            if tr.get("result_set"):
                print(f"Results (first 5): {tr['result_set']}")
        elif tr.get("type") == "search":
            print(f"Search results: {json.dumps(tr['search_results'], indent=2)[:500]}")
        else:
            print(json.dumps(tr.get("data", tr), indent=2)[:500])
        print()

    print(f"{'='*60}")
    print("FINAL ANSWER:")
    print(f"{'='*60}")
    print(result["answer"].strip())

    return result


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)

    database = sys.argv[1]
    schema = sys.argv[2]
    agent_name = sys.argv[3]

    if sys.argv[4] == "--batch":
        if len(sys.argv) < 7:
            print("Batch usage: invoke_agent.py <db> <schema> <agent> --batch <eval_table> <connection>")
            sys.exit(1)
        eval_table = sys.argv[5]
        connection = sys.argv[6]
        results = run_batch(database, schema, agent_name, eval_table, connection)
        output_file = f"/tmp/{agent_name}_batch_results.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nFull results saved to: {output_file}")
    else:
        question = sys.argv[4]
        connection = sys.argv[5] if len(sys.argv) > 5 else os.getenv("SNOWFLAKE_CONNECTION_NAME", "default")
        run_single(database, schema, agent_name, question, connection)


if __name__ == "__main__":
    main()
