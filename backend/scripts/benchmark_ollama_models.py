"""Compare local Ollama models against the planning workflow's strict contracts."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date
from typing import Any, cast

import httpx
from pydantic import BaseModel

from app.ai.ollama_provider import OllamaStructuredProvider
from app.ai.prompts.registry import get_prompt
from app.ai.provider import StructuredModelRequest
from app.ai.schemas.outputs import (
    DependencySuggestionBatch,
    MilestoneDraftBatch,
    ModuleDraftBatch,
    ProjectAnalysisOutput,
    TaskDraftBatch,
)
from app.ai.validation import ValidationContext, validate_candidate
from app.core.config import Settings

FACTS: dict[str, Any] = {
    "intake": {
        "name": "University Maintenance Request Portal",
        "goal": (
            "Let students report campus maintenance issues and let facilities staff "
            "triage, schedule, and close them."
        ),
        "desired_outcome": (
            "A responsive web application with auditable status history and a usable "
            "pilot by 2026-10-30."
        ),
        "start_date": "2026-08-03",
        "deadline": "2026-10-30",
        "timezone": "Africa/Cairo",
        "capacity_hours_per_week": 80,
        "team_size": 2,
        "notes": "Must run on the university lab network. No external user-data services.",
        "row_version": 1,
    },
    "requirements": [
        {
            "fact_ref": "REQ-001",
            "kind": "required",
            "text": (
                "Students authenticate and submit a request with category, location, "
                "description, and optional photo."
            ),
            "source": "owner",
            "status": "confirmed",
        },
        {
            "fact_ref": "REQ-002",
            "kind": "required",
            "text": "Facilities staff triage requests by urgency and workflow status.",
            "source": "owner",
            "status": "confirmed",
        },
        {
            "fact_ref": "REQ-003",
            "kind": "required",
            "text": "Students track status and see an auditable request timeline.",
            "source": "owner",
            "status": "confirmed",
        },
        {
            "fact_ref": "REQ-004",
            "kind": "required",
            "text": "Administrators see operational counts and overdue requests.",
            "source": "owner",
            "status": "confirmed",
        },
        {
            "fact_ref": "REQ-005",
            "kind": "excluded",
            "text": "Native mobile applications are excluded from the first release.",
            "source": "owner",
            "status": "confirmed",
        },
        {
            "fact_ref": "REQ-006",
            "kind": "excluded",
            "text": "External contractor integrations are excluded.",
            "source": "owner",
            "status": "confirmed",
        },
    ],
    "constraints": [
        {
            "fact_ref": "CONSTRAINT-001",
            "type": "deadline",
            "value": {"date": "2026-10-30"},
            "source": "owner",
            "confirmed": True,
        },
        {
            "fact_ref": "CONSTRAINT-002",
            "type": "deployment",
            "value": {"network": "university_lab"},
            "source": "owner",
            "confirmed": True,
        },
        {
            "fact_ref": "CONSTRAINT-003",
            "type": "capacity",
            "value": {"hours_per_week": 80, "team_size": 2},
            "source": "owner",
            "confirmed": True,
        },
    ],
    "decisions": [
        {
            "fact_ref": "DECISION-001",
            "type": "scope",
            "text": "A responsive web app is sufficient for the pilot.",
            "rationale": "Native mobile is excluded.",
            "source_fact_refs": ["REQ-005"],
        }
    ],
}

ALLOWED_REFS = frozenset(
    item["fact_ref"]
    for group in ("requirements", "constraints", "decisions")
    for item in FACTS[group]
)
EXCLUDED_REFS = frozenset({"REQ-005", "REQ-006"})


async def generate(
    client: httpx.AsyncClient,
    model: str,
    identifier: str,
    context: dict[str, Any],
    validation_context: ValidationContext,
) -> tuple[BaseModel, dict[str, Any]]:
    prompt = get_prompt(identifier)
    instructions, input_text = prompt.render(context)
    settings = Settings(
        ai_provider="ollama",
        ollama_base_url=str(client.base_url),
        ollama_model=model,
        ollama_context_tokens=8_192,
        ollama_max_output_tokens=4_096,
        ollama_schema_retries=1,
        _env_file=None,
    )
    provider = OllamaStructuredProvider(settings, client=client)
    started = time.perf_counter()
    generated = await provider.generate(
        StructuredModelRequest(
            prompt_key=prompt.key,
            prompt_version=prompt.version,
            instructions=instructions,
            input_text=input_text,
            output_type=prompt.output_type,
            token_budget=prompt.output_token_budget,
            safety_identifier="ollama_benchmark",
            reasoning_effort=prompt.reasoning_effort,
            metadata={"purpose": "local_model_benchmark"},
        )
    )
    result = validate_candidate(
        generated.output.model_dump(mode="json"), prompt.output_type, validation_context
    )
    elapsed = time.perf_counter() - started
    return generated.output, {
        "seconds": round(elapsed, 2),
        "input_tokens": generated.usage.input_tokens,
        "output_tokens": generated.usage.output_tokens,
        "tokens_per_second": round(generated.usage.output_tokens / elapsed, 2) if elapsed else 0,
        "valid": result.is_valid,
        "issues": [issue.code for issue in result.issues],
        "model": generated.model,
    }


async def run_pipeline(client: httpx.AsyncClient, model: str) -> dict[str, Any]:
    rows: list[tuple[str, dict[str, Any]]] = []
    analysis, metric = await generate(
        client,
        model,
        "analysis.v3",
        {
            "intake": FACTS["intake"],
            "requirements": FACTS["requirements"],
            "constraints": FACTS["constraints"],
            "decisions": FACTS["decisions"],
        },
        ValidationContext(allowed_refs=ALLOWED_REFS, excluded_refs=EXCLUDED_REFS),
    )
    rows.append(("analysis", metric))
    analysis = cast(ProjectAnalysisOutput, analysis)
    modules, metric = await generate(
        client,
        model,
        "modules.v3",
        {
            "analysis": analysis.model_dump(mode="json"),
            "requirements": FACTS["requirements"],
            "excluded_refs": sorted(EXCLUDED_REFS),
        },
        ValidationContext(
            allowed_refs=ALLOWED_REFS,
            required_refs=frozenset({"REQ-001", "REQ-002", "REQ-003", "REQ-004"}),
            excluded_refs=EXCLUDED_REFS,
        ),
    )
    rows.append(("modules", metric))
    modules = cast(ModuleDraftBatch, modules)
    module_refs = frozenset(item.temp_id for item in modules.items)
    milestones, metric = await generate(
        client,
        model,
        "milestones.v4",
        {
            "modules": modules.model_dump(mode="json"),
            "constraints": FACTS["constraints"],
            "start_date": FACTS["intake"]["start_date"],
            "deadline": FACTS["intake"]["deadline"],
        },
        ValidationContext(
            allowed_refs=ALLOWED_REFS | module_refs,
            excluded_refs=EXCLUDED_REFS,
            project_start=date.fromisoformat(FACTS["intake"]["start_date"]),
        ),
    )
    rows.append(("milestones", metric))
    milestones = cast(MilestoneDraftBatch, milestones)
    milestone_refs = frozenset(item.temp_id for item in milestones.items)
    tasks, metric = await generate(
        client,
        model,
        "tasks.v5",
        {
            "milestones": milestones.model_dump(mode="json"),
            "requirements": FACTS["requirements"],
            "decisions": FACTS["decisions"],
            "workstreams": sorted(
                {workstream for item in milestones.items for workstream in item.module_refs}
            ),
        },
        ValidationContext(allowed_refs=ALLOWED_REFS | milestone_refs, excluded_refs=EXCLUDED_REFS),
    )
    rows.append(("tasks", metric))
    tasks = cast(TaskDraftBatch, tasks)
    task_refs = frozenset(item.temp_id for item in tasks.items)
    dependencies, metric = await generate(
        client,
        model,
        "dependencies.v3",
        {
            "tasks": [
                {
                    "temp_id": item.temp_id,
                    "title": item.title,
                    "deliverable": item.deliverable,
                    "milestone_ref": item.milestone_ref,
                }
                for item in tasks.items
            ]
        },
        ValidationContext(allowed_refs=task_refs),
    )
    rows.append(("dependencies", metric))
    dependencies = cast(DependencySuggestionBatch, dependencies)
    return {
        "steps": dict(rows),
        "counts": {
            "modules": len(modules.items),
            "milestones": len(milestones.items),
            "tasks": len(tasks.items),
            "dependencies": len(dependencies.items),
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("models", nargs="*", default=["llama3.1:8b"])
    args = parser.parse_args()
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(base_url=args.base_url) as client:
        for model in args.models:
            print(f"Benchmarking {model}...", flush=True)
            try:
                results[model] = await run_pipeline(client, model)
            except Exception as error:  # diagnostic CLI reports a model failure and continues
                results[model] = {
                    "error": type(error).__name__,
                    "detail": str(error)[:1_000],
                }
            await client.post("/api/generate", json={"model": model, "keep_alive": 0}, timeout=30)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
