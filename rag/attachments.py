"""Archivos que el usuario adjunta en el chat.

No se guardan en data/ ni entran en el indice principal: se extrae su texto,
se trocea, se calculan sus embeddings y se quedan en memoria durante un tiempo
limitado (UPLOAD_TTL_SECONDS). Cada consulta puede indicar los ids de los
adjuntos que quiere usar, y sus fragmentos se combinan con los del indice.
"""

import os
import tempfile
import threading
import time
import uuid

import numpy as np

from config import UPLOAD_MAX_FILES, UPLOAD_MAX_MB, UPLOAD_TTL_SECONDS
from loader import UPLOAD_EXTENSIONS, read_document_parts
from rag_core import chunk_text, embed_texts

# Si el adjunto completo cabe en este numero de caracteres se manda entero al
# modelo (preguntas tipo "resume este documento" necesitan verlo todo). Si es
# mas grande, solo se mandan los fragmentos mas parecidos a la pregunta.
FULL_TEXT_CHARS = 6000
TOP_CHUNKS = 5

_uploads = {}
_lock = threading.Lock()


class AttachmentError(ValueError):
    pass


def _purge_expired():
    now = time.time()
    with _lock:
        expired = [
            fid for fid, up in _uploads.items()
            if now - up["created"] > UPLOAD_TTL_SECONDS
        ]
        for fid in expired:
            del _uploads[fid]
        # Si aun hay demasiados, se descartan los mas antiguos.
        overflow = len(_uploads) - UPLOAD_MAX_FILES
        if overflow > 0:
            oldest = sorted(_uploads, key=lambda fid: _uploads[fid]["created"])
            for fid in oldest[:overflow]:
                del _uploads[fid]


def add_attachment(filename, data):
    """Procesa un archivo subido y devuelve sus metadatos publicos."""
    name = os.path.basename(filename or "").strip() or "archivo"
    ext = os.path.splitext(name)[1].lower()
    if ext not in UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(UPLOAD_EXTENSIONS))
        raise AttachmentError(f"Formato no soportado ({ext or 'sin extension'}). Usa: {allowed}")
    if len(data) > UPLOAD_MAX_MB * 1024 * 1024:
        raise AttachmentError(f"El archivo supera el limite de {UPLOAD_MAX_MB} MB")
    if not data:
        raise AttachmentError("El archivo esta vacio")

    # Los lectores trabajan con rutas, asi que se vuelca a un temporal.
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        parts = read_document_parts(tmp_path)
    except AttachmentError:
        raise
    except Exception as exc:
        raise AttachmentError(f"No se pudo leer el archivo: {exc}") from exc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    chunks = []
    total_chars = 0
    for page, text in parts:
        if not text or not text.strip():
            continue
        total_chars += len(text)
        for chunk in chunk_text(text):
            chunks.append((chunk, page))

    if not chunks:
        raise AttachmentError(
            "No se encontro texto en el archivo (si es un PDF escaneado, "
            "necesita OCR antes de subirlo)"
        )

    embeddings = embed_texts([c for c, _ in chunks])
    file_id = uuid.uuid4().hex
    upload = {
        "id": file_id,
        "name": name,
        "chunks": chunks,
        "embeddings": embeddings,
        "chars": total_chars,
        "created": time.time(),
    }

    _purge_expired()
    with _lock:
        _uploads[file_id] = upload

    return {
        "id": file_id,
        "name": name,
        "chunks": len(chunks),
        "chars": total_chars,
        "pages": len({p for _, p in chunks if p is not None}) or None,
    }


def remove_attachment(file_id):
    with _lock:
        return _uploads.pop(file_id, None) is not None


def attachment_hits(file_ids, q_emb):
    """Fragmentos relevantes de los adjuntos indicados.

    Devuelve una lista de tuplas (texto, nombre, pagina). Los ids que ya no
    existen (caducados o del servidor anterior a un reinicio) se ignoran y se
    devuelven aparte para poder avisar al usuario.
    """
    _purge_expired()
    hits = []
    missing = []
    for fid in file_ids or []:
        with _lock:
            upload = _uploads.get(fid)
        if upload is None:
            missing.append(fid)
            continue

        chunks = upload["chunks"]
        if upload["chars"] <= FULL_TEXT_CHARS:
            # Documento corto: se manda entero, agrupado por pagina para que
            # cada cita apunte a una pagina y no a un trozo suelto.
            by_page = {}
            for text, page in chunks:
                by_page.setdefault(page, []).append(text)
            for page, texts in by_page.items():
                hits.append(("\n".join(texts), upload["name"], page))
            continue

        scores = upload["embeddings"] @ q_emb[0]
        top = np.argsort(-scores)[:TOP_CHUNKS]
        # Se mantienen en el orden del documento para que se lean con sentido.
        selected = sorted(int(i) for i in top)

        for i in selected:
            text, page = chunks[i]
            hits.append((text, upload["name"], page))
    return hits, missing
