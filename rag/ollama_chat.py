import os
import hashlib
import json
import logging
import re
import threading
import time

from openai import OpenAI
from config import (
    EMBEDDING_MODEL,
    LLM_MAX_TOKENS,
    OLLAMA_API_KEY,
    OLLAMA_MODEL,
    OLLAMA_THINK,
    OLLAMA_TIMEOUT,
    OLLAMA_URL,
    REINDEX_WATCH_SECONDS,
)
from loader import SUPPORTED_EXTENSIONS, iter_document_paths, load_all_document
from rag_core import build_index, load_index, save_index, search

client = OpenAI(
    base_url=OLLAMA_URL,
    api_key=OLLAMA_API_KEY,
    timeout=OLLAMA_TIMEOUT,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rag")

print(f"[rag] Ollama endpoint: {OLLAMA_URL} (modelo={OLLAMA_MODEL})")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
INDEX_PATH = os.path.join(CACHE_DIR, "index.faiss")
ITEMS_PATH = os.path.join(CACHE_DIR, "items.pkl")
META_PATH = os.path.join(CACHE_DIR, "meta.json")

CACHE_VERSION = 4

_snapshot = None            # (index, items) listo para consultas
_loaded_signature = None    # firma de los documentos que generaron _snapshot
_ready = False              # True cuando _snapshot puede usarse para consultas
_snapshot_lock = threading.RLock()
_build_lock = threading.Lock()
_rebuild_in_progress = False
_watcher_started = False


def _documents_signature(base_path):
    rows = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if os.path.splitext(file)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            path = os.path.join(root, file)
            try:
                st = os.stat(path)
            except OSError:
                continue
            rel = os.path.relpath(path, base_path)
            rows.append(f"{rel}|{st.st_mtime_ns}|{st.st_size}")
    rows.sort()
    payload = "\n".join(rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_cached_index(signature):
    if not (os.path.exists(INDEX_PATH) and os.path.exists(ITEMS_PATH) and os.path.exists(META_PATH)):
        return None, None

    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if (
            meta.get("signature") != signature
            or meta.get("version") != CACHE_VERSION
            or meta.get("model") != EMBEDDING_MODEL
        ):
            return None, None
        index, items = load_index(INDEX_PATH, ITEMS_PATH)
        return index, items
    except Exception as exc:
        log.warning("Cache de indice no utilizable, se reindexara: %s", exc)
        return None, None


def _save_cached_index(index, items, signature):
    os.makedirs(CACHE_DIR, exist_ok=True)
    save_index(index, items, INDEX_PATH, ITEMS_PATH)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "signature": signature,
                "version": CACHE_VERSION,
                "model": EMBEDDING_MODEL,
                "chunks": len(items),
            },
            f,
        )


def _rebuild(signature):
    """Reconstruye el indice desde cero y lo deja listo para consultas.

    Corre dentro de `_build_lock` para que nunca haya dos reindexaciones a la
    vez. Mientras reindexa, las consultas siguen sirviendose con el indice
    anterior hasta que el nuevo queda listo.
    """
    global _snapshot, _loaded_signature, _ready

    with _snapshot_lock:
        if _snapshot is not None and _loaded_signature == signature:
            _ready = True
            return _snapshot

    print(f"[rag] Cargando documentos desde {DATA_DIR} ...")
    documents = load_all_document(DATA_DIR)
    if not documents:
        raise RuntimeError(
            f"No se encontraron documentos legibles en {DATA_DIR}"
        )
    print(f"[rag] Indexando {len(documents)} documentos...")
    index, items = build_index(documents)
    _save_cached_index(index, items, signature)

    with _snapshot_lock:
        _snapshot = (index, items)
        _loaded_signature = signature
        _ready = True
    print(f"[rag] Indexados {len(items)} fragmentos.")
    return _snapshot


def _ensure_index(force_rebuild=False):
    """Devuelve la snapshot (index, items) actual, cargandola de cache o
    reconstruyendola si la firma de los documentos ha cambiado."""
    global _snapshot, _loaded_signature, _ready

    with _snapshot_lock:
        if _snapshot is not None and not force_rebuild:
            return _snapshot

    signature = _documents_signature(DATA_DIR)

    with _snapshot_lock:
        if (
            _snapshot is not None
            and _loaded_signature == signature
            and not force_rebuild
        ):
            return _snapshot

    if not force_rebuild:
        cached_index, cached_items = _load_cached_index(signature)
        if cached_index is not None:
            with _snapshot_lock:
                _snapshot = (cached_index, cached_items)
                _loaded_signature = signature
                _ready = True
            print(f"[rag] Indice cargado desde cache: {len(cached_items)} fragmentos.")
            return _snapshot

    with _build_lock:
        return _rebuild(signature)


def _launch_rebuild(signature):
    """Lanza un reindexado en segundo plano (no bloquea el hilo que lo llama)."""
    global _rebuild_in_progress

    with _snapshot_lock:
        if _rebuild_in_progress:
            return
        _rebuild_in_progress = True

    print("[rag] Indexando en segundo plano...")
    thread = threading.Thread(
        target=_rebuild_worker, args=(signature,), name="rag-reindex", daemon=True
    )
    thread.start()


def _rebuild_worker(signature):
    global _rebuild_in_progress
    try:
        with _build_lock:
            _rebuild(signature)
    except Exception:
        log.exception("Falló el reindexado automatico; se reintentara.")
    finally:
        with _snapshot_lock:
            _rebuild_in_progress = False


def _maybe_refresh_async():
    """Si los documentos cambiaron en disco, lanza un reindexado en segundo
    plano sin bloquear la consulta actual."""
    with _snapshot_lock:
        if _snapshot is None or _rebuild_in_progress:
            return
        current = _loaded_signature

    signature = _documents_signature(DATA_DIR)
    if signature == current:
        return

    print("[rag] Se detectaron cambios en los documentos. Reindexando en segundo plano...")
    _launch_rebuild(signature)


def _watcher_loop():
    while True:
        time.sleep(REINDEX_WATCH_SECONDS)
        try:
            _maybe_refresh_async()
        except Exception:
            log.exception("Error en el watcher de documentos")


def _start_watcher():
    global _watcher_started
    with _snapshot_lock:
        if _watcher_started:
            return
        _watcher_started = True
    thread = threading.Thread(
        target=_watcher_loop, name="rag-doc-watcher", daemon=True
    )
    thread.start()


def build_messages(question, hits):
    """Construye los mensajes para el LLM.

    `hits` es una lista de tuplas (texto, fuente). Cada fragmento se etiqueta
    con su documento para que la respuesta pueda citar la fuente correcta.
    """
    context_parts = []
    for text, source in hits:
        folder = os.path.dirname(source).replace(os.sep, "/").strip("/")
        name = os.path.splitext(os.path.basename(source))[0]
        label = f"{folder}/{name}" if folder else name
        context_parts.append(f"[{label}]\n{text}")
    context = "\n\n---\n\n".join(context_parts)

    return [
        {
            "role": "system",
            "content": (
                "Eres un asistente experto en documentos legales y normativos. "
                "Responde SIEMPRE en español, nunca en inglés ni en ningún otro idioma, "
                "sin importar en qué idioma parezca estar el razonamiento interno. "
                "Responde con una síntesis clara, útil y natural, no como una lista de fragmentos. "
                "Usa el contexto solo como base de evidencia y redacta la respuesta con tus propias palabras. "
                "No menciones 'fragmentos', 'contexto' ni el mecanismo de recuperación. "
                "No incluyas tu razonamiento, notas internas ni comentarios sobre cómo vas a responder "
                "(nada de frases como 'We need answer in...' o 'User asks...'): entrega solo la respuesta final. "
                "Cita textualmente solo si el usuario lo pide o si una formulación exacta es necesaria. "
                "Cuando la respuesta se apoye en un documento concreto, indica su nombre entre "
                "paréntesis al final, por ejemplo (Decreto 123-2024). "
                "Si la información no está en el contexto, dilo con franqueza y sugiere qué dato faltaría."
            ),
        },
        {
            "role": "user",
            "content": (
                "Instrucciones:\n"
                "- Responde de forma directa y completa.\n"
                "- Integra la evidencia disponible en una sola explicación coherente.\n"
                "- No devuelvas el contexto tal cual ni enumeres trozos de texto.\n\n"
                f"Contexto:\n{context}\n\nPregunta: {question}"
            ),
        },
    ]


_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning_tags(text):
    """Quita bloques <think>...</think> por si el modelo los deja en `content`."""
    return _THINK_TAG_RE.sub("", text).strip()


def _message_text(msg):
    """Texto util de un mensaje del LLM.

    Los modelos de razonamiento (qwen3, deepseek-r1, gpt-oss...) devuelven el
    razonamiento en un campo aparte y dejan `content` vacio si se quedan sin
    tokens antes de escribir la respuesta final. Si eso pasa, al menos
    aprovechamos el razonamiento en lugar de devolver una respuesta vacia.
    """
    content = _strip_reasoning_tags((getattr(msg, "content", None) or "").strip())
    if content:
        return content
    for attr in ("reasoning_content", "reasoning"):
        value = (getattr(msg, attr, None) or "").strip()
        if value:
            return value
    return ""


def _complete(messages, max_tokens, temperature, think):
    """Una llamada al LLM. Devuelve (texto, finish_reason).

    Ollama solo respeta el flag nativo `think` en su endpoint /api/chat; en el
    endpoint compatible con OpenAI (el que usamos aqui) el razonamiento se
    activa solo para modelos que lo soportan, y se controla con
    `reasoning_effort` ("none" para desactivarlo).
    """
    extra_body = {"reasoning_effort": "medium" if think else "none"}
    response = client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=extra_body,
    )
    choice = response.choices[0]
    finish_reason = getattr(choice, "finish_reason", None)
    return _message_text(choice.message), finish_reason


def query_rag(message, k=5, max_tokens=LLM_MAX_TOKENS, temperature=0.1):
    with _snapshot_lock:
        ready = _ready
    if not ready:
        raise RuntimeError(
            "El índice de documentos se está construyendo. "
            "Reintenta en unos segundos."
        )

    _maybe_refresh_async()
    index, items = _ensure_index()
    hits = search(index, items, message, k=k)
    messages = build_messages(message, hits)

    answer, finish_reason = _complete(messages, max_tokens, temperature, OLLAMA_THINK)

    if not answer:
        # Suele ocurrir cuando el modelo agota el cupo razonando (finish_reason
        # "length"). Reintentamos una vez sin razonamiento y con mas margen.
        log.warning(
            "El modelo devolvio una respuesta vacia (finish_reason=%s). "
            "Reintentando sin razonamiento y con mas tokens.",
            finish_reason,
        )
        answer, finish_reason = _complete(
            messages, max(max_tokens * 2, 1024), temperature, False
        )

    if not answer:
        raise RuntimeError(
            "El modelo devolvió una respuesta vacía "
            f"(finish_reason={finish_reason}, modelo={OLLAMA_MODEL}). "
            "Sube LLM_MAX_TOKENS o revisa que el modelo configurado sea el que "
            "sirve Ollama."
        )

    texts = [t for t, _ in hits]
    sources = []
    for _, source in hits:
        if source not in sources:
            sources.append(source)

    return {
        "answer": answer,
        "fragments": texts,
        "sources": sources,
    }


def send_to_rag(message, k=5):
    return query_rag(message, k=k)["answer"]


def warmup_index(force_rebuild=False):
    """Carga el indice de cache si existe (rapido) o lanza el primer indexado
    en segundo plano. Nunca bloquea el arranque del servicio."""
    global _snapshot, _loaded_signature, _ready

    signature = _documents_signature(DATA_DIR)

    if force_rebuild:
        _launch_rebuild(signature)
        _start_watcher()
        return

    with _snapshot_lock:
        snapshot = _snapshot
    if snapshot is None:
        cached_index, cached_items = _load_cached_index(signature)
        if cached_index is not None:
            with _snapshot_lock:
                _snapshot = (cached_index, cached_items)
                _loaded_signature = signature
                _ready = True
            print(f"[rag] Indice cargado desde cache: {len(cached_items)} fragmentos.")
        else:
            _launch_rebuild(signature)

    _start_watcher()


def get_index_info():
    """Metadatos utiles para monitorear el indice (ver /docs/info)."""
    with _snapshot_lock:
        snapshot = _snapshot
        signature = _loaded_signature
        ready = _ready
        building = _rebuild_in_progress
    n_chunks = len(snapshot[1]) if snapshot else 0
    n_docs = len(list(iter_document_paths(DATA_DIR)))
    return {
        "status": "ready" if ready else ("building" if building else "empty"),
        "documents": n_docs,
        "chunks": n_chunks,
        "signature": signature,
        "data_dir": DATA_DIR,
        "auto_reindex_seconds": REINDEX_WATCH_SECONDS,
    }


def check_ollama():
    """Comprueba que Ollama responde en OLLAMA_URL.

    Devuelve un dict con `ok`, `url`, `model` y, si falla, `error`.
    """
    info = {"url": OLLAMA_URL, "model": OLLAMA_MODEL}
    try:
        models = client.models.list()
        ids = [m.id for m in getattr(models, "data", [])]
        info["ok"] = True
        info["available_models"] = ids
        info["model_loaded"] = OLLAMA_MODEL in ids if ids else None
    except Exception as exc:  # pragma: no cover - depende de red
        info["ok"] = False
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info
