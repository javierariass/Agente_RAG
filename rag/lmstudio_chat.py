import os
import hashlib
import json

from openai import OpenAI
from config import (
    LMSTUDIO_API_KEY,
    LMSTUDIO_MODEL,
    LMSTUDIO_TIMEOUT,
    LMSTUDIO_URL,
)
from loader import load_all_document
from rag_core import build_index, load_index, save_index, search

client = OpenAI(
    base_url=LMSTUDIO_URL,
    api_key=LMSTUDIO_API_KEY,
    timeout=LMSTUDIO_TIMEOUT,
)

print(f"[rag] LM Studio endpoint: {LMSTUDIO_URL} (modelo={LMSTUDIO_MODEL})")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
INDEX_PATH = os.path.join(CACHE_DIR, "index.faiss")
CHUNKS_PATH = os.path.join(CACHE_DIR, "chunks.pkl")
META_PATH = os.path.join(CACHE_DIR, "meta.json")

_index = None
_chunks = None


def _documents_signature(base_path):
    rows = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if not file.lower().endswith((".pdf", ".docx", ".pptx", ".txt")):
                continue
            path = os.path.join(root, file)
            st = os.stat(path)
            rel = os.path.relpath(path, base_path)
            rows.append(f"{rel}|{st.st_mtime_ns}|{st.st_size}")
    rows.sort()
    payload = "\n".join(rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_cached_index(signature):
    if not (os.path.exists(INDEX_PATH) and os.path.exists(CHUNKS_PATH) and os.path.exists(META_PATH)):
        return None, None

    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("signature") != signature:
            return None, None
        index, chunks = load_index(INDEX_PATH, CHUNKS_PATH)
        return index, chunks
    except Exception:
        return None, None


def _save_cached_index(index, chunks, signature):
    os.makedirs(CACHE_DIR, exist_ok=True)
    save_index(index, chunks, INDEX_PATH, CHUNKS_PATH)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({"signature": signature, "chunks": len(chunks)}, f)


def _ensure_index(force_rebuild=False):
    global _index, _chunks
    if _index is None:
        signature = _documents_signature(DATA_DIR)

        if not force_rebuild:
            cached_index, cached_chunks = _load_cached_index(signature)
            if cached_index is not None:
                _index, _chunks = cached_index, cached_chunks
                print(f"Indice cargado desde cache: {len(_chunks)} fragmentos.")
                return _index, _chunks

        print(f"Cargando documentos desde {DATA_DIR} ...")
        documents = load_all_document(DATA_DIR)
        if not documents:
            raise RuntimeError(
                f"No se encontraron documentos legibles en {DATA_DIR}"
            )
        print(f"Indexando {len(documents)} documentos...")
        _index, _chunks = build_index(documents)
        _save_cached_index(_index, _chunks, signature)
        print(f"Indexados {len(_chunks)} fragmentos.")
    return _index, _chunks


def build_messages(question, frags):
    context = "\n\n---\n\n".join(frags)
    return [
        {
            "role": "system",
            "content": (
                "Eres un asistente experto en documentos legales y normativos. "
                "Utiliza solamente el contexto proporcionado para responder a la pregunta. "
                "Cita textualmente cuando sea posible. "
                "Si la respuesta no está en el contexto, di que no lo sabes."
            ),
        },
        {
            "role": "user",
            "content": f"Contexto:\n{context}\n\nPregunta: {question}",
        },
    ]


def query_rag(message, k=5, max_tokens=512, temperature=0.1):
    index, chunks = _ensure_index()
    frags = search(index, chunks, message, k=k)
    messages = build_messages(message, frags)

    response = client.chat.completions.create(
        model=LMSTUDIO_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    return {
        "answer": response.choices[0].message.content,
        "fragments": frags,
    }


def send_to_rag(message, k=5):
    return query_rag(message, k=k)["answer"]


def warmup_index(force_rebuild=False):
    _ensure_index(force_rebuild=force_rebuild)


def check_lmstudio():
    """Comprueba que LM Studio responde en LMSTUDIO_URL.

    Devuelve un dict con `ok`, `url`, `model` y, si falla, `error`.
    """
    info = {"url": LMSTUDIO_URL, "model": LMSTUDIO_MODEL}
    try:
        models = client.models.list()
        ids = [m.id for m in getattr(models, "data", [])]
        info["ok"] = True
        info["available_models"] = ids
        info["model_loaded"] = LMSTUDIO_MODEL in ids if ids else None
    except Exception as exc:  # pragma: no cover - depende de red
        info["ok"] = False
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info
