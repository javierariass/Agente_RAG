from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field

try:
    from lmstudio_chat import check_lmstudio, query_rag, warmup_index
except ModuleNotFoundError:
    from rag.lmstudio_chat import check_lmstudio, query_rag, warmup_index


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm up on boot so first user request is fast.
    warmup_index(force_rebuild=False)
    yield


app = FastAPI(title="Agente RAG API", version="1.0.0", lifespan=lifespan)

# CORS abierto: util si abres el frontend desde otro origen o como file://.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3)
    k: int = Field(default=5, ge=1, le=20)
    max_tokens: int = Field(default=512, ge=64, le=4096)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class QueryResponse(BaseModel):
    answer: str
    fragments: list[str]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/lmstudio/health")
def lmstudio_health():
    info = check_lmstudio()
    status_code = 200 if info.get("ok") else 503
    if status_code == 503:
        raise HTTPException(status_code=status_code, detail=info)
    return info


@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest):
    try:
        result = query_rag(
            payload.question,
            k=payload.k,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
        )
        return QueryResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/reindex")
def reindex():
    try:
        warmup_index(force_rebuild=True)
        return {"status": "reindexed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


app.mount("/", StaticFiles(directory="web", html=True), name="web")
