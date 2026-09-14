# Escalation

Primary records ESCALATED using event.py with run, unique id and reason. Record the
blocking task, attempts, findings, unavailable checks and operator options in a
committed report. Active escalations block dispatch and shipping. Do not hide them
in a commit message alone. Three total task attempts is the default budget, not
three retries after an initial attempt. Permission or safety blockers pause sooner.

After an explicit operator decision, Primary records ESCALATION_RESOLVED with the
same id and a pointer to the committed decision. Resume only the approved scope.
Unknown agent liveness requires reconciliation, not speculative duplicate spawning.
