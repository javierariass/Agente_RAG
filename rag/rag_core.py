import os
import pickle
import re

from config import CHUNK_SIZE, EMBEDDING_DEVICE, EMBEDDING_MODEL

if EMBEDDING_DEVICE.lower() in ("cpu", ""):
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from sentence_transformers import SentenceTransformer
import faiss
import torch

EMBED_BATCH_SIZE = 64

_embedder = None
_embedder_device = None


def _pick_device():
    """Devuelve el dispositivo para los embeddings.

    Prioridad:
      1. EMBEDDING_DEVICE explicito en el .env (cpu / cuda).
      2. 'auto' (o vacio): usa CUDA solo si hay una GPU realmente utilizable
         (se comprueba con una operacion minima que falla de forma capturable
         si la GPU no sirve, p.ej. una tarjeta antigua con un build de PyTorch
         incompatible). En caso contrario usa CPU.
    """
    requested = EMBEDDING_DEVICE.lower()
    if requested in ("cpu", ""):
        return "cpu"
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "EMBEDDING_DEVICE=cuda pero no se encontro GPU CUDA utilizable"
            )
        return "cuda"
    if torch.cuda.is_available():
        try:
            probe = torch.zeros(8, 8, device="cuda")
            (probe + 1).cpu()
            del probe
            torch.cuda.empty_cache()
            return "cuda"
        except Exception:
            pass
    return "cpu"


def get_embedder():
    global _embedder, _embedder_device
    device = _pick_device()
    if _embedder is None or _embedder_device != device:
        _embedder = SentenceTransformer(EMBEDDING_MODEL, device=device)
        _embedder_device = device
    return _embedder


def _split_long(paragraph, size):
    """Divide un parrafo que excede `size` en fragmentos que respetan oraciones."""
    sentences = re.split(r"(?<=[.;:!?\u00bf\u00a1])\s+", paragraph)
    chunks = []
    buf = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        while len(s) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(s[:size].strip())
            s = s[size:]
        if not s:
            continue
        if buf and len(buf) + 1 + len(s) > size:
            chunks.append(buf)
            buf = s
        else:
            buf = (f"{buf} {s}" if buf else s).strip()
    if buf:
        chunks.append(buf)
    return chunks


def chunk_text(text, size=CHUNK_SIZE, overlap=100):
    """Divide un documento en fragmentos coherentes.

    Une parrafos completos hasta llegar a `size` y, si un parrafo es muy largo,
    lo corta respetando los limites de oracion. Esto mejora notablemente la
    calidad de la recuperacion frente al corte ciego por caracteres.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks = []
    buf = ""
    for para in paragraphs:
        if len(para) <= size:
            if buf and len(buf) + 1 + len(para) > size:
                chunks.append(buf)
                buf = ""
            buf = (f"{buf} {para}" if buf else para).strip()
        else:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_split_long(para, size))
    if buf:
        chunks.append(buf)
    return chunks


def build_index(documents):
    """Construye el indice FAISS.

    `documents` es una lista de tuplas (texto, fuente). Cada fragmento generado
    conserva su fuente para poder citarla en la respuesta.
    """
    items = []
    for text, source in documents:
        for chunk in chunk_text(text):
            items.append((chunk, source))

    if not items:
        raise ValueError("No hay texto para indexar.")

    embedder = get_embedder()
    texts = [t for t, _ in items]
    embeddings = embedder.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    return index, items


def search(index, items, query, k=5):
    """Devuelve hasta `k` tuplas (texto, fuente) mas relevantes."""
    embedder = get_embedder()
    q_emb = embedder.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    _, indices = index.search(q_emb, k)
    return [items[i] for i in indices[0] if 0 <= i < len(items)]


def save_index(index, items, index_path, items_path):
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, index_path)
    with open(items_path, "wb") as f:
        pickle.dump(items, f)


def load_index(index_path, items_path):
    index = faiss.read_index(index_path)
    with open(items_path, "rb") as f:
        items = pickle.load(f)
    return index, items
