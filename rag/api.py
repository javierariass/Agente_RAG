import os
from datetime import datetime
from urllib.parse import quote, unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
from pydantic import BaseModel, Field

try:
    from config import LLM_MAX_TOKENS, UPLOAD_MAX_MB
    from attachments import AttachmentError, add_attachment, remove_attachment
    from export_docx import build_docx
    from ollama_chat import (
        check_ollama,
        get_index_info,
        query_rag,
        resolve_data_file,
        warmup_index,
    )
except ModuleNotFoundError:
    from rag.config import LLM_MAX_TOKENS, UPLOAD_MAX_MB
    from rag.attachments import AttachmentError, add_attachment, remove_attachment
    from rag.export_docx import build_docx
    from rag.ollama_chat import (
        check_ollama,
        get_index_info,
        query_rag,
        resolve_data_file,
        warmup_index,
    )


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
    max_tokens: int = Field(default=LLM_MAX_TOKENS, ge=64, le=8192)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    # Ids devueltos por POST /upload para preguntar tambien sobre esos archivos.
    attachments: list[str] = Field(default_factory=list, max_length=10)


class Citation(BaseModel):
    id: int
    kind: str  # "doc" (base documental) o "upload" (archivo adjunto)
    source: str
    title: str
    page: int | None = None
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    fragments: list[str]
    sources: list[str]
    citations: list[Citation] = []
    missing_attachments: list[str] = []


class ExportCitation(BaseModel):
    n: int
    title: str = ""
    source: str = ""
    page: int | None = None
    kind: str = "doc"


class ExportRequest(BaseModel):
    question: str = ""
    answer: str = Field(..., min_length=1)
    citations: list[ExportCitation] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ollama/health")
def ollama_health():
    info = check_ollama()
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
            attachments=payload.attachments,
        )
        return QueryResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:
        status_code = 503 if "construyendo" in str(exc) else 500
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/reindex")
def reindex():
    try:
        warmup_index(force_rebuild=True)
        return {"status": "reindexed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/docs/info")
def docs_info():
    try:
        return get_index_info()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/upload")
async def upload(request: Request):
    """Recibe un archivo como cuerpo binario de la peticion (sin multipart) con
    el nombre en la cabecera X-Filename (codificado con encodeURIComponent)."""
    filename = unquote(request.headers.get("x-filename", ""))
    limit = UPLOAD_MAX_MB * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail=f"El archivo supera {UPLOAD_MAX_MB} MB")

    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status_code=413, detail=f"El archivo supera {UPLOAD_MAX_MB} MB")

    try:
        return await run_in_threadpool(add_attachment, filename, bytes(data))
    except AttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/upload/{file_id}")
def delete_upload(file_id: str):
    return {"deleted": remove_attachment(file_id)}


@app.get("/files/{rel_path:path}")
def get_file(rel_path: str):
    """Sirve un documento de data/ para que las citas puedan abrirlo (los PDF
    se abren en el navegador; el #page=N del enlace salta a la pagina)."""
    full = resolve_data_file(rel_path)
    if full is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return FileResponse(
        full,
        filename=os.path.basename(full),
        content_disposition_type="inline",
    )


@app.post("/export/docx")
def export_docx(payload: ExportRequest):
    content = build_docx(
        payload.question,
        payload.answer,
        [c.model_dump() for c in payload.citations],
    )
    filename = datetime.now().strftime("respuesta-%Y%m%d-%H%M.docx")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


_WEB_DIR = Path(__file__).resolve().parent / "web"
app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
