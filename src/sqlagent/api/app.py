import json
import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sqlagent.api.service import AskService
from sqlagent.errors import AbortRun
from sqlagent.index.build import TABLE_MAP
from sqlagent.strategies.selective import build_selective

app = FastAPI(title="Selective-schema text-to-SQL", version="0.1.0")
log = logging.getLogger("sqlagent.api")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    db_id: str = ""


@lru_cache(maxsize=1)
def get_service() -> AskService:
    return AskService(build_selective(validate=True, layout="auto"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/databases")
def databases() -> list[dict]:
    mapping = json.loads(TABLE_MAP.read_text())["databases"]
    return [{"db_id": db_id, "tables": sorted(tables)} for db_id, tables in sorted(mapping.items())]


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    try:
        return get_service().ask(request.question, request.db_id)
    except AbortRun as e:
        log.warning("ask stopped: %s", e)
        raise HTTPException(
            status_code=503, detail="The model is out of quota for now. Try again later."
        ) from e
    except Exception as e:
        log.exception("ask failed")
        raise HTTPException(status_code=502, detail="Something went wrong answering this question.") from e
