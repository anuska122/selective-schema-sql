import json
import logging
from functools import lru_cache
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from sqlagent import db
from sqlagent.api.limits import Guard, Rejected
from sqlagent.api.service import AskService
from sqlagent.errors import AbortRun
from sqlagent.index.build import TABLE_MAP
from sqlagent.llm import QuotaExhausted
from sqlagent.strategies.selective import build_selective

app = FastAPI(title="Selective-schema text-to-SQL", version="0.1.0")
log = logging.getLogger("sqlagent.api")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    db_id: str = ""


@lru_cache(maxsize=1)
def get_service() -> AskService:
    db.assert_read_only_role()
    return AskService(build_selective(validate=True, layout="auto"))


@lru_cache(maxsize=1)
def get_guard() -> Guard:
    return Guard.from_env()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    try:
        get_service()
        db.assert_read_only_role()
    except Exception as e:
        log.exception("readiness check failed")
        raise HTTPException(status_code=503, detail="The query service is not ready.") from e
    return {"status": "ready"}


@app.get("/databases")
def databases() -> list[dict]:
    mapping = json.loads(TABLE_MAP.read_text())["databases"]
    return [{"db_id": db_id, "tables": sorted(tables)} for db_id, tables in sorted(mapping.items())]


@app.post("/ask")
def ask(
    request: AskRequest,
    x_api_token: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
) -> dict:
    try:
        get_guard().check(x_api_token, x_client_id)
    except Rejected as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from e
    try:
        request_id = uuid4().hex
        answer = get_service().ask(request.question, request.db_id, request_id=request_id)
        if answer.get("error"):
            log.warning("query failed: %s", answer["error"])
            answer["error"] = "Unable to answer this question. Try rephrasing it."
        details = dict(answer.get("details", {}))
        for key in ("first_error", "repair_error", "final_error"):
            if key in details:
                log.info("query validation %s: %s", key, details.pop(key))
        return {**answer, "details": details}
    except QuotaExhausted as e:
        log.warning("ask stopped: %s", e)
        raise HTTPException(
            status_code=503, detail="The model is out of quota for now. Try again later."
        ) from e
    except AbortRun as e:
        log.warning("ask stopped: %s", e)
        raise HTTPException(status_code=503, detail="The model service is temporarily unavailable.") from e
    except Exception as e:
        log.exception("ask failed")
        raise HTTPException(status_code=502, detail="Something went wrong answering this question.") from e
