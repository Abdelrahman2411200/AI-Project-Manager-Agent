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
- `OLLAMA_TIMEOUT_SECONDS=600`
- `OLLAMA_CONTEXT_TOKENS=8192`
- `OLLAMA_MAX_OUTPUT_TOKENS=4096`
- `PLANNING_RUN_DEFAULT_TOKEN_BUDGET=100000` for the local demo

Task generation groups at most two requirement references per model call, and
acceptance refinement groups at most four tasks per call. These bounds keep each
schema-constrained response below the local 4,096-token output ceiling while the
larger demo run budget covers the additional grounded batches. Hosted environments
retain their separately configured run budget.
- `OLLAMA_TEMPERATURE=0`
- `OLLAMA_SEED=42`
- `OLLAMA_SCHEMA_RETRIES=1`

The 600-second request window accommodates structured generations when the 8B
model is partially CPU-offloaded. Workflow checkpoints, bounded node retry, and
idempotent jobs prevent a transient provider interruption from exposing a partial
plan.

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

Latest black-box verification on 2026-08-01:

- run `d1208595-650c-4202-9bd2-e9a8698951ec` completed in 1,288 seconds;
- all 24 provider calls completed with `llama3.1:8b`, using 46,341 local tokens;
- all 17 workflow checkpoints completed with no failed step and no clarification
  persisted for already-confirmed facts;
- plan `9db7f7d6-ead9-43fc-b701-58308493dd72` contains six stable modules, six
  milestones, and twelve distinct, sized tasks;
- every one of the eight in-scope requirements has a separate grounded task, and
  the production semantic checker found zero mismatched task citations;
- the deterministic quality gate passed with one advisory that the model did not
  identify a grounded risk; no generic risk was invented to hide that result;
- the resulting plan remains an inactive draft with no approval record and no
  active plan version.

Record a new run ID, plan version, token count, entity counts, and timing here
after each model, prompt, or hardware change. Do not reuse historical results as
proof for a new configuration.

## Start on Windows

From the repository root:

```powershell
& .\infra\release\start-local-ollama.ps1
```

The helper verifies WSL, Ollama, and `llama3.1:8b`; keeps Ubuntu alive; writes the
ignored demo environment; builds the backend and frontend; starts the stack; and
performs a structured probe from the worker container.

If the probe fails, verify these layers in order:

```powershell
wsl -d Ubuntu -- systemctl status ollama
wsl -d Ubuntu -- ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
docker run --rm curlimages/curl:8.12.1 http://host.docker.internal:11434/api/version
docker compose --env-file .env.demo -f compose.demo.yaml logs --tail=100 worker
```
