# Evaluation Completion Contract

Before launching, record the actual run name, agent version/spec identity, dataset snapshot, expected question IDs, and selected metrics. Construct expected question/metric pairs from that snapshot, excluding only deliberately inapplicable metrics recorded before launch.

Poll `EXECUTE_AI_EVALUATION('STATUS', ...)` using the same run name and config path as START. Metric-row counts are progress indicators only, never proof of completion. Stop on FAILED/CANCELLED; bound polling by the run's configured timeout and retain partial results for diagnosis only.

After terminal COMPLETED, normalize results using the actual metric-specific score fields. Tool metrics may require explanation parsing; do not silently turn missing values into zero. Confirm successful scoring from returned status/error evidence, not merely a non-null metric name. Join result identities back to the frozen question IDs; do not substitute row numbers or silently collapse duplicate questions.

Write a local JSON payload for `skills/agent-evaluation/scripts/check_eval_completion.py`:

```json
{
  "status": "COMPLETED",
  "expected": [["q1", "answer_correctness"]],
  "records": [{"question_id": "q1", "metric": "answer_correctness", "score": 0.9, "success": true, "error": null}]
}
```

These are toolkit-normalized fields, not assumed Snowflake output columns. Invoke the script with the payload's absolute path. Only exit code 0 and `ready: true` permit aggregation, tournament selection, or acceptance. Missing, duplicate, unexpected, invalid, or failed results block that handoff. Check every parallel run independently. Do not retry by deleting dataset state while another run may still be using it.
