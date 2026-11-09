"""
On-device model routes: hardware, the catalogue with fit checks, installed
models, pulls, deletes, benchmarks, Hugging Face GGUF lookups, license
acceptance and Auto-Crew.

Pull progress also streams over the WebSocket as pull_progress events.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Path, Query, Response

from juli import config, providers, store
from juli.api.models import (
    HF_REPO_PATTERN,
    OLLAMA_MODEL_PATTERN,
    AutoCrewRequest,
    LicenseAccept,
    ModelName,
)
from juli.local import catalogue, crew, hardware, ollama

router = APIRouter(prefix="/local")

ModelPath = Annotated[str, Path(pattern=OLLAMA_MODEL_PATTERN)]


@contextmanager
def _upstream(endpoints: dict | None = None) -> Iterator[None]:
    """Ollama or Hugging Face failures as HTTP errors."""
    try:
        yield
    except httpx.HTTPError:
        raise HTTPException(503, f"Ollama isn't running at {ollama.base_url(endpoints)}. Start it with `ollama serve`.") from None
    except providers.ProviderError as e:
        raise HTTPException(502, str(e)) from None


@router.get("/hardware")
def get_hardware() -> dict:
    hw = hardware.current()
    gpu_gb, total_gb = hardware.budgets(hw)
    return {**hw, "budgets": {"gpu_gb": round(gpu_gb, 1), "total_gb": round(total_gb, 1)}}


@router.get("/status")
def get_status() -> dict:
    return ollama.status(config.load_settings().get("endpoints"))


@router.get("/models")
def installed_models() -> dict:
    """Installed and loaded models, with this machine's measured speeds."""
    endpoints = config.load_settings().get("endpoints")
    status = ollama.status(endpoints)
    if not status["running"]:
        return {"ollama": status, "installed": [], "loaded": []}
    with _upstream(endpoints):
        tags, loaded = ollama.tags(endpoints), ollama.ps(endpoints)
    speeds = store.get_benchmarks(hardware.current()["fingerprint"])
    for model in tags:
        model["benchmark"] = speeds.get(f"ollama:{model.get('name')}")
    return {"ollama": status, "installed": tags, "loaded": loaded}


@router.get("/catalogue")
def get_catalogue() -> dict:
    settings = config.load_settings()
    endpoints = settings.get("endpoints")
    hw = hardware.current()
    return {
        "hardware": hw,
        "ollama": ollama.status(endpoints),
        "models": catalogue.listing(hw, ollama.installed(endpoints), settings),
    }


@router.get("/hf")
def hugging_face(repo: Annotated[str, Query(pattern=HF_REPO_PATTERN)]) -> dict:
    """The GGUF files in a Hugging Face repo, each with a fit check."""
    settings = config.load_settings()
    endpoints = settings.get("endpoints")
    with _upstream(endpoints):
        return catalogue.hf_models(repo, hardware.current(), ollama.installed(endpoints), settings)


@router.post("/licenses")
def accept_license(body: LicenseAccept) -> dict:
    """Record that the user accepted a model license."""
    try:
        catalogue.accept_license(body.license)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return {"status": "accepted", "license": body.license}


@router.post("/pulls", status_code=202)
def start_pull(body: ModelName) -> dict:
    """Download a model in the background. Its license must be accepted first."""
    settings = config.load_settings()
    endpoints = settings.get("endpoints")
    with _upstream(endpoints):
        lic = catalogue.license_needed(body.model, settings)
    if lic:
        raise HTTPException(409, {"message": f"Accept {lic['name']} before downloading {body.model}", "license": lic})
    job = ollama.PULLS.start(body.model, endpoints)
    if job is None:
        raise HTTPException(409, f"{body.model} is already downloading")
    return job


@router.get("/pulls")
def list_pulls() -> list[dict]:
    return ollama.PULLS.list()


@router.delete("/pulls/{model:path}", status_code=204)
def cancel_pull(model: ModelPath) -> Response:
    """Stop a download. Pulling the model again resumes it."""
    if not ollama.PULLS.cancel(model):
        raise HTTPException(404, f"{model} isn't downloading")
    return Response(status_code=204)


@router.delete("/models/{model:path}", status_code=204)
def delete_model(model: ModelPath) -> Response:
    endpoints = config.load_settings().get("endpoints")
    with _upstream(endpoints):
        if model not in {m.get("name") for m in ollama.tags(endpoints)}:
            raise HTTPException(404, f"{model} isn't installed")
        ollama.delete(model, endpoints)
    return Response(status_code=204)


@router.post("/benchmark")
def benchmark(body: ModelName) -> dict:
    """Measure a model's speed on this machine (generates 128 tokens)."""
    endpoints = config.load_settings().get("endpoints")
    with _upstream(endpoints):
        return ollama.benchmark(body.model, endpoints)


@router.post("/auto-crew")
def auto_crew(body: AutoCrewRequest) -> dict:
    """Pick a model per agent for this machine; with apply, save the picks."""
    try:
        return crew.run_auto_crew(body.agents, apply=body.apply, set_fallback=body.set_fallback)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
