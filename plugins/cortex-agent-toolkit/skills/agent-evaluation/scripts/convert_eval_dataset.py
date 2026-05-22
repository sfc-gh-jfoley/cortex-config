#!/usr/bin/env python3
"""
Convert existing evaluation datasets to the Cortex Agent Evaluations format.

Transforms tables with simple question/expected_answer columns to the required
format with INPUT_QUERY (VARCHAR) and EXPECTED_TOOLS (VARCHAR containing JSON).

Usage:
    python convert_eval_dataset.py \
        --source-table db.schema.existing_eval \
        --target-table db.schema.agent_eval_dataset \
        --question-col question \
        --answer-col expected_answer \
        --connection CONNECTION_NAME

Optional:
    --tool-col COLUMN    Column containing tool name (for tool_selection_accuracy)
    --drop-target        Drop target table if it exists
"""

import argparse
import json
import re
import snowflake.connector
import os

# Strict FQN pattern: DB.SCHEMA.TABLE with alphanumeric + underscore only
_FQN_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*$')
_IDENT_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')

def _validate_fqn(name: str, label: str):
    """Validate that name is a safe 3-part Snowflake identifier."""
    if not _FQN_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label}: '{name}'. "
            f"Must be DB.SCHEMA.TABLE with alphanumeric/underscore characters only."
        )

def _validate_identifier(name: str, label: str):
    """Validate that name is a safe single Snowflake identifier."""
    if not _IDENT_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label}: '{name}'. "
            f"Must contain only alphanumeric/underscore characters."
        )

# Strict FQN pattern: DB.SCHEMA.TABLE with alphanumeric + underscore only
_FQN_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*$')
_IDENT_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')

def _validate_fqn(name: str, label: str):
    """Validate that name is a safe 3-part Snowflake identifier."""
    if not _FQN_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label}: '{name}'. "
            f"Must be DB.SCHEMA.TABLE with alphanumeric/underscore characters only."
        )

def _validate_identifier(name: str, label: str):
    """Validate that name is a safe single Snowflake identifier."""
    if not _IDENT_PATTERN.match(name):
        raise ValueError(
            f"Invalid {label}: '{name}'. "
            f"Must contain only alphanumeric/underscore characters."
        )


def convert_dataset(
    source_table: str,
    target_table: str,
    question_col: str,
    answer_col: str,
    tool_col: str | None,
    connection_name: str,
    drop_target: bool = False
):
    _validate_fqn(source_table, "source-table")
    _validate_fqn(target_table, "target-table")
    _validate_identifier(question_col, "question-col")
    _validate_identifier(answer_col, "answer-col")
    if tool_col:
        _validate_identifier(tool_col, "tool-col")

    conn = snowflake.connector.connect(connection_name=connection_name)
    cursor = conn.cursor()

    try:
        if drop_target:
            print(f"Dropping target table if exists: {target_table}")
            cursor.execute(f"DROP TABLE IF EXISTS {target_table}")

        print(f"Reading from {source_table}...")
        cols = [question_col, answer_col]
        if tool_col:
            cols.append(tool_col)
        cursor.execute(f"SELECT {', '.join(cols)} FROM {source_table}")
        rows = cursor.fetchall()
        print(f"  Found {len(rows)} rows")

        create_sql = f"""
        CREATE OR REPLACE TABLE {target_table} (
            INPUT_QUERY VARCHAR(16777216),
            EXPECTED_TOOLS VARCHAR(16777216)
        )
        """
        cursor.execute(create_sql)

        insert_sql = f"INSERT INTO {target_table} (INPUT_QUERY, EXPECTED_TOOLS) VALUES (%s, %s)"

        converted = []
        for row in rows:
            question = row[0]
            answer = row[1] or ""
            tool_name = row[2] if tool_col and len(row) > 2 else None

            ground_truth = {"ground_truth_output": answer}

            if tool_name and tool_name.strip():
                ground_truth["ground_truth_invocations"] = [
                    {"tool_name": tool_name.strip(), "tool_sequence": 1}
                ]
            else:
                ground_truth["ground_truth_invocations"] = []

            converted.append((question, json.dumps(ground_truth)))

        cursor.executemany(insert_sql, converted)

        cursor.execute(f"SELECT COUNT(*) FROM {target_table}")
        count = cursor.fetchone()[0]
        print(f"\nCreated {target_table} with {count} rows")

        cursor.execute(f"SELECT * FROM {target_table} LIMIT 1")
        sample = cursor.fetchone()
        if sample:
            print(f"\nSample row:")
            q = sample[0]
            print(f"  INPUT_QUERY: {q[:100]}{'...' if len(q) > 100 else ''}")
            print(f"  EXPECTED_TOOLS: {sample[1][:200]}{'...' if len(sample[1]) > 200 else ''}")

        db_schema = '.'.join(target_table.split('.')[:2])
        ds_name = target_table.split('.')[-1] + '_DS'

        print(f"\nNext steps:")
        print(f"  USE DATABASE {target_table.split('.')[0]};")
        print(f"  USE SCHEMA {target_table.split('.')[1]};")
        print(f"  CALL SYSTEM$CREATE_EVALUATION_DATASET(")
        print(f"      'Cortex Agent',")
        print(f"      '{target_table}',")
        print(f"      '{ds_name}',")
        print(f"      OBJECT_CONSTRUCT('query_text', 'INPUT_QUERY', 'expected_tools', 'EXPECTED_TOOLS')")
        print(f"  );")

    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Convert evaluation datasets to Cortex Agent Evaluations format"
    )
    parser.add_argument("--source-table", required=True, help="Source table (db.schema.table)")
    parser.add_argument("--target-table", required=True, help="Target table to create (db.schema.table)")
    parser.add_argument("--question-col", default="question", help="Column with questions (default: question)")
    parser.add_argument("--answer-col", default="expected_answer", help="Column with expected answers (default: expected_answer)")
    parser.add_argument("--tool-col", help="Optional column with tool names for tool_selection_accuracy")
    parser.add_argument("--connection", default=os.getenv("SNOWFLAKE_CONNECTION_NAME", "default"), help="Snowflake connection name")
    parser.add_argument("--drop-target", action="store_true", help="Drop target table if exists")

    args = parser.parse_args()

    convert_dataset(
        source_table=args.source_table,
        target_table=args.target_table,
        question_col=args.question_col,
        answer_col=args.answer_col,
        tool_col=args.tool_col,
        connection_name=args.connection,
        drop_target=args.drop_target
    )


if __name__ == "__main__":
    main()
