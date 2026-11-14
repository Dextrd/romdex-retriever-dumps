"""The dumping tools retriever's HTTP API (Romdex retrieval contract v1.0)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from .contract import CONTRACT_VERSION, FetchRequest, HealthRequest, Jobs, ListRequest, dump, env, error, staging_directory
from .dumps import Dumps

VERSION = "0.1.0"
STAGING = env("STAGING_ROOT", "/staging")
SETTLE_SECONDS = 120

SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "keepOriginals": {
            "type": "boolean", "default": True, "title": "Keep originals",
            "description": "Copy each dump's image and logs, leaving the tool's output as it is. Off, they're moved.",
        },
        "removeLeftovers": {
            "type": "boolean", "default": False, "title": "Remove what a ripper leaves behind",
            "description": "With originals not kept, delete a disc's folder once its image is taken, intermediate files and all.",
        },
        "settleSeconds": {
            "type": "integer", "minimum": 0, "maximum": 86400, "default": SETTLE_SECONDS, "title": "Wait for the tool to finish",
            "description": "Seconds a dump has to be left unchanged before it's taken. Rippers can pause for a while between steps.",
        },
    },
}

MANIFEST: dict[str, Any] = {
    "id": "romdex.retrieval.dumps",
    "name": "Dumping tools",
    "version": VERSION,
    "type": "retrieval",
    "contractVersion": CONTRACT_VERSION,
    "description": "Takes finished dumps from the output folders of disc rippers and cartridge dumpers, with the tools' logs.",
    "homepage": "https://github.com/dextrd/Romdex/tree/main/plugins/retriever-dumps",
    "capabilities": ["list", "cancel"],
    "settingsSchema": SETTINGS_SCHEMA,
    "access": {"network": [], "files": ["dumps (read, and write when moving files out)", "staging (write)"]},
}

app = FastAPI(title="Romdex dumping tools retriever", version=VERSION)
jobs = Jobs(int(env("PARALLEL_FETCHES", "2")))
dumps = Dumps(env("DUMPS_ROOT", "/dumps"))


@app.exception_handler(HTTPException)
async def contract_error(_: Request, e: HTTPException) -> JSONResponse:
    body = e.detail if isinstance(e.detail, dict) else {"error": str(e.detail)}
    return JSONResponse(body, status_code=e.status_code)


def _settle(settings: dict[str, Any]) -> float:
    return float(settings.get("settleSeconds", SETTLE_SECONDS))


@app.get("/v1/manifest")
def manifest() -> dict[str, Any]:
    return MANIFEST


@app.post("/v1/health")
def health(body: HealthRequest) -> dict[str, Any]:
    if not dumps.root.is_dir():
        return {"status": "unhealthy", "message": f"The dumps folder {dumps.root} isn't mounted."}
    count = len(dumps.finished(_settle(body.settings)))
    return {"status": "healthy", "message": f"{count} finished dump{'' if count == 1 else 's'} waiting"}


@app.post("/v1/list")
def list_dumps(body: ListRequest) -> dict[str, Any]:
    if not dumps.root.is_dir():
        raise error(503, f"The dumps folder {dumps.root} isn't mounted.", "source-unavailable")
    return {"candidates": dump([dumps.candidate(d) for d in dumps.finished(_settle(body.settings))])}


@app.post("/v1/fetch", status_code=202)
def fetch(body: FetchRequest) -> dict[str, Any]:
    directory = staging_directory(STAGING, body.staging_directory)
    job = jobs.start(body.job_id, lambda j: dumps.fetch(j, body.candidate.candidate_id, directory, body.settings))
    return job.status()


@app.get("/v1/fetch/{job_id}")
def status(job_id: str) -> dict[str, Any]:
    if (job := jobs.get(job_id)) is None:
        raise error(404, "No such job; the plugin may have restarted.", "unknown-job")
    return job.status()


@app.delete("/v1/fetch/{job_id}", status_code=204)
def cancel(job_id: str) -> None:
    if (job := jobs.get(job_id)) is None:
        raise error(404, "No such job; the plugin may have restarted.", "unknown-job")
    job.cancelled.set()
