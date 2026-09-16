from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sqlagent.api.service import AskService
from sqlagent.strategies.selective import build_selective

app = FastAPI(title="Selective-schema text-to-SQL", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    db_id: str = ""


@lru_cache(maxsize=1)
def get_service() -> AskService:
    return AskService(build_selective(validate=True, layout="pooled"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    try:
        return get_service().ask(request.question, request.db_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}") from e
