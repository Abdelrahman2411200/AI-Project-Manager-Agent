# Phase 12 University Evaluation Baseline

Baseline ID: `university-evaluation-v1`

API: `GET /api/v1/evaluations/latest`

Fixture source: `backend/tests/fixtures/evals/mvp_evaluation.jsonl`

The dashboard baseline is generated from the versioned deterministic fixture
runner and reviewed into
`backend/app/evaluation/baselines/university-v1.json`. The packaged file contains
scores and provenance, not project intake text, credentials, or model output.

Required fixtures:

1. E-commerce website.
2. Football scouting platform.
3. University attendance system.
4. Mobile expense tracker.
5. AI production incident investigator.
6. Small marketing website.
7. Data analytics dashboard.
8. Intentionally impossible deadline.

The release baseline passes only when all eight fixtures pass. The API verifies
the exact fixture set and metric set before returning the document, recalculates
its canonical SHA-256 hash against the accepted reviewed hash, and fails closed
if the packaged file is incomplete or changed.

The Phase 12 dashboard exposes:

- module coverage;
- missing-task rate;
- task-size compliance;
- dependency validity and zero-cycle status;
- hallucination rate;
- deterministic feasible/infeasible schedule match;
- per-fixture pass/fail status;
- thresholds, dataset version, source, and dataset hash.

Provider-backed evaluation remains manual/nightly when credentials and budget
are available. Phase 12 intentionally does not persist evaluation history: the
implementation plan makes that metadata table conditional. A future persisted
runner must retain this response contract and may not replace reviewed baseline
scores silently.
