# Local Ollama planning

The default live-planning provider is Ollama running in the Ubuntu WSL
distribution. It requires no hosted API key and sends project content only to the
local Ollama endpoint.

## Selected model

`gemma3:4b` is the default for the reference laptop (RTX 3060 Laptop GPU with
6 GiB VRAM and 8 GiB WSL memory). A deterministic five-stage planning benchmark
used the application's real prompts, Pydantic schemas, reference validation,
scope protection, and task-sizing rules.

| Model | Observed result | Elapsed time | Hardware fit |
|---|---|---:|---|
| `gemma3:4b` | Analysis, modules, milestones, and tasks validated; the dependency stage exposed a self-edge that the production adapter now rejects deterministically | about 60 seconds | Fully GPU-resident at the tested context |
| `llama3.1:8b` | Analysis and modules validated; the first milestone had an invalid zero-hour estimate | about 217 seconds | Partially CPU-offloaded and substantially slower |

These measurements are a hardware-specific comparison, not a universal model
ranking. Re-run the benchmark after changing the GPU, quantization, prompt
catalog, schemas, or context window:

```powershell
Set-Location backend
uv run python -m scripts.benchmark_ollama_models gemma3:4b llama3.1:8b
```

## Runtime settings

- `AI_PROVIDER=ollama`
- `OLLAMA_MODEL=gemma3:4b`
- `OLLAMA_CONTEXT_TOKENS=8192`
- `OLLAMA_MAX_OUTPUT_TOKENS=4096`
- `OLLAMA_TEMPERATURE=0`
- `OLLAMA_SEED=42`
- `OLLAMA_SCHEMA_RETRIES=1`

The worker calls Ollama's native `/api/chat` endpoint with the exact JSON schema
in `format`, streaming disabled, thinking disabled, and a bounded output budget.
Every result is parsed into the requested Pydantic model. One local repair request
is allowed for schema or cross-field failures; application business, permission,
identifier, graph, schedule, health, and approval rules remain deterministic and
outside the model.

The local workflow also compensates for repeatable small-model behavior without
inventing project facts:

- modules are prompted to cover every in-scope requirement;
- milestones, tasks, and acceptance refinement are batched by their stable parent;
- generated milestone/task identifiers and sequences are assigned deterministically;
- acceptance refinement may update only criteria and definition-of-done fields;
- incomplete choice controls become text questions, duplicate analysis previews and
  self-dependencies are discarded, and leaf likely-effort is bounded to 4-24 hours
  while a larger upper estimate remains visible;
- invalid optional clarification, dependency, or risk suggestions are discarded only
  after the single repair attempt; required plan structures still fail closed.

A black-box verification through Nginx, the public REST API, the database-backed
worker, PostgreSQL, and Ollama completed a representative planning run with one
human clarification, six milestones, six tasks, one dependency, a passed quality
gate, and a persisted approval-gated draft. The run used 31,025 local tokens and no
hosted API credentials.

## Start on Windows

From the repository root:

```powershell
& .\infra\release\start-local-ollama.ps1
```

The helper verifies WSL, Ollama, and the model; keeps Ubuntu alive; configures the
ignored demo environment; builds one shared backend image plus the frontend;
starts the stack; and performs a structured probe from the worker container.

If the probe fails, verify these layers in order:

```powershell
wsl -d Ubuntu -- systemctl status ollama
wsl -d Ubuntu -- ollama list
Invoke-RestMethod http://127.0.0.1:11434/api/version
docker run --rm curlimages/curl:8.12.1 http://host.docker.internal:11434/api/version
docker compose --env-file .env.demo -f compose.demo.yaml logs --tail=100 worker
```
