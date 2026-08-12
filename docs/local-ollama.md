# Local Ollama planning with Llama 3.1

The default live-planning provider is Ollama running in the Ubuntu WSL
distribution. It requires no hosted API key and sends project content only to the
configured local Ollama endpoint.

## Selected model

The project standard is `llama3.1:8b`. Ollama publishes this model as a 4.9 GB
text model with a 128K model context window. The reference laptop deliberately
uses an 8,192-token application context so the model can run with its 6 GiB GPU
and 8 GiB WSL allocation; Ollama reports a partial CPU/GPU split on that machine.
Model capability and the application's hardware-conscious runtime limit are
therefore different values.

- Model reference: <https://ollama.com/library/llama3.1>
- Ollama structured outputs: <https://docs.ollama.com/capabilities/structured-outputs>

`llama3.1:8b` is the default in Pydantic settings, all committed environment
examples, Docker Compose profiles, the Windows startup helper, tests, demo
fixtures, and operator documentation. A configurable model field remains so an
operator can deliberately test another local model without changing code.

Run the application-path benchmark after changing hardware, quantization,
prompts, schemas, or context size:

```powershell
Set-Location backend
uv run python -m scripts.benchmark_ollama_models
```

The benchmark uses the production Ollama adapter rather than a separate raw API
client.

## Runtime settings

- `AI_PROVIDER=ollama`
- `OLLAMA_MODEL=llama3.1:8b`
- `OLLAMA_TIMEOUT_SECONDS=1800`
- `OLLAMA_CONTEXT_TOKENS=8192`
- `OLLAMA_MAX_OUTPUT_TOKENS=4096`
- `OLLAMA_FAST_PLANNING=true`
- `PLANNING_RUN_DEFAULT_TOKEN_BUDGET=100000` for the local demo
- `DEMO_WORKER_REPLICAS=4` for four concurrently claimed workflows

Fast local planning uses the model for project analysis and module shaping. It uses a
clarification model call only when the structured intake is missing delivery essentials.
It consolidates excessive module fan-out near four modules without dropping requirement
references, then deterministically creates the milestones, requirement-level tasks,
acceptance evidence, and validation inputs. This keeps a complete uninterrupted local
run to two model calls and removes the redundant full-task acceptance rewrite
that could exhaust the output or run-token limit. Set `OLLAMA_FAST_PLANNING=false` only
when deliberately evaluating the slower model-authored downstream stages. Hosted OpenAI
planning retains its separately configured multi-call workflow and run budget.
- `OLLAMA_TEMPERATURE=0`
- `OLLAMA_SEED=42`
- `OLLAMA_SCHEMA_RETRIES=1`

The 1,800-second request window accommodates an unusually slow structured generation
and provider-side waiting when several workers share one local Ollama instance. Ollama
can still serialize model requests when GPU memory is limited; extra workers remove the
application queue, not the physical compute limit. Workflow checkpoints, bounded node
retry, and idempotent jobs prevent a transient provider interruption from exposing a
partial plan.

## Structured-output boundary

The worker calls Ollama's native `/api/chat` endpoint with streaming and thinking
disabled. It supplies the exact minified Pydantic JSON Schema in both the API
`format` field and the local system message, following Ollama's structured-output
guidance. Each response is parsed into the requested Pydantic model before the
workflow can use it.

One provider-level retry handles malformed schema output, and one workflow repair
request handles identifier or business-rule failures. The application then
validates schema, identifiers, confirmed scope, permissions, task sizing,
dependencies, scheduling, quality, and approval rules. Model output cannot
activate or mutate an approved plan.

The Llama-specific hardening remains grounded in supplied project facts:

- questions already answered by structured intake or confirmed facts are removed;
- invented analysis citations are mapped to the closest confirmed fact reference;
- module, milestone, and task identifiers are assigned stable sequential values;
- every in-scope requirement must appear in a module and in actionable task work;
- an under-decomposed milestone receives a deterministic, traceable task for each
  omitted requirement only after the bounded model repair fails;
- duplicate task titles from separate model batches are disambiguated before the
  deterministic quality gate;
- zero or oversized leaf estimates, incomplete controls, self-dependencies, and
  invalid optional suggestions are normalized or rejected under explicit rules;
- reports and recommendations may cite only persisted evidence.

These controls make the workflow dependable; they do not treat any generative
model as infallible. Invalid required structures fail closed and do not produce a
reviewable draft.

## Verified workflow

The release verification runs a real project through Nginx, the versioned REST
API, secure owner session, database-backed worker, PostgreSQL checkpoints, and
the local `llama3.1:8b` API. The completed run must show:

- no clarification for facts already present in intake;
- successful schema and deterministic validation for all 17 planning nodes;
- stable modules and milestones;
- requirement-linked, sized, distinct tasks;
- a passed quality gate;
- one persisted draft that remains approval-gated and inactive.

Latest black-box verification on 2026-08-10:

- run `fdd51b57-049d-4ce5-a2dd-a67dcf3b69fc` completed in 50.31 seconds;
- both provider calls completed with `llama3.1:8b`, using 3,520 local tokens;
- all 17 workflow checkpoints completed on their first attempt with no failed or
  truncated step;
- plan `a91df850-2b3f-40f1-9dd3-f3f1da14026a` contains two stable modules, two
  milestones, and four distinct tasks for four confirmed requirements;
- the deterministic graph, schedule, priority, and quality gates passed;
- the resulting plan remains an inactive draft with no approval record and no
  active plan version.

Record a new run ID, plan version, token count, entity counts, and timing here
after each model, prompt, or hardware change. Do not reuse historical results as
proof for a new configuration.

## Start on Windows

For normal use, double-click `AI Project Manager.exe` in the repository root.
It reuses cached images when available, waits for the public application readiness
endpoint, and opens the browser. Use **Stop project** in the launcher to stop the
services while preserving PostgreSQL data.

For terminal-driven startup, run from the repository root:

```powershell
& .\infra\release\start-local-ollama.ps1 -WorkerReplicas 4
```

The helper verifies WSL, Ollama, and `llama3.1:8b`; keeps Ubuntu alive; writes the
ignored demo environment; builds the backend and frontend; starts the stack with
the requested number of durable workers; and
performs a structured probe from the worker container.

If the probe fails, verify these layers in order:

```powershell
wsl -d Ubuntu -- systemctl status ollama
wsl -d Ubuntu -- ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
docker run --rm curlimages/curl:8.12.1 http://host.docker.internal:11434/api/version
docker compose --env-file .env.demo -f compose.demo.yaml logs --tail=100 worker
```
