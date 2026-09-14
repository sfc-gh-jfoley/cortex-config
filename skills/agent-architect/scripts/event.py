"""Render one manifest event with explicit identity; does not write files."""

import argparse
from datetime import datetime, timezone


def render(task, phase, role, run, attempt, dispatch=None, fields=()):
    values = {"run": run, "attempt": str(attempt)}
    if dispatch:
        values["dispatch"] = dispatch
    for field in fields:
        if "=" not in field:
            raise ValueError("fields must be key=value")
        key, value = field.split("=", 1)
        if key in values:
            raise ValueError("duplicate or overridden identity field")
        values[key] = value
    parts = [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), task, phase, role]
    parts.extend(f"{key}={value}" for key, value in values.items())
    if attempt < 1 or any(not part or any(char in part for char in "|\n\r") for part in parts):
        raise ValueError("invalid event delimiter, identity, or attempt")
    return " | ".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["task", "phase", "role", "run"]:
        parser.add_argument(name)
    parser.add_argument("attempt", type=int)
    parser.add_argument("--dispatch")
    parser.add_argument("--field", action="append", default=[])
    args = parser.parse_args()
    try:
        print(render(args.task, args.phase, args.role, args.run, args.attempt, args.dispatch, args.field))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
