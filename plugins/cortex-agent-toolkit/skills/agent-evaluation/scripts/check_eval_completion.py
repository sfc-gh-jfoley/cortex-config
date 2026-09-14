"""Validate normalized evaluation coverage, independently of Snowflake transport."""

import argparse
import json
import math
from pathlib import Path


def check_completion(status, expected, records):
    expected_pairs = {tuple(pair) for pair in expected}
    if not expected_pairs or any(len(pair) != 2 for pair in expected_pairs):
        raise ValueError("Expected question/metric pairs must be nonempty")
    seen = set()
    errors = []
    for record in records:
        pair = (record.get("question_id"), record.get("metric"))
        if pair in seen:
            errors.append(f"Duplicate result: {pair}")
        seen.add(pair)
        score = record.get("score")
        if record.get("error") or record.get("success") is not True:
            errors.append(f"Unsuccessful metric: {pair}")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            errors.append(f"Invalid normalized score: {pair}")
    missing = expected_pairs - seen
    unexpected = seen - expected_pairs
    ready = status == "COMPLETED" and not errors and not missing and not unexpected
    return {"ready": ready, "status": status, "missing": sorted(missing),
            "unexpected": sorted(unexpected, key=str), "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Normalized JSON: status, expected pairs, records")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text())
    result = check_completion(payload["status"], payload["expected"], payload["records"])
    print(json.dumps(result))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
