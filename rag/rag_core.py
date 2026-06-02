import os
import pickle
from sentence_transformers import SentenceTransformer
import faiss

from config import EMBEDDING_MODEL, CHUNK_SIZE

CHUNK_OVERLAP = 100
EMBED_BATCH_SIZE = 64

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    if not text:
        return chunks
    step = max(1, size - overlap)
    for i in range(0, len(text), step):
        chunk = text[i:i + size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def build_index(documents):
    all_chunks = []
    for doc in documents:
        all_chunks.extend(chunk_text(doc))

    if not all_chunks:
        raise ValueError("No hay texto para indexar.")

    embedder = get_embedder()
    embeddings = embedder.encode(
        all_chunks,
        batch_size=EMBED_BATCH_SIZE,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    return index, all_chunks


def search(index, chunks, query, k=5):
    embedder = get_embedder()
    q_emb = embedder.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    _, indices = index.search(q_emb, k)
    return [chunks[i] for i in indices[0] if 0 <= i < len(chunks)]


def save_index(index, chunks, index_path, chunks_path):
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, index_path)
    with open(chunks_path, "wb") as f:
        pickle.dump(chunks, f)


def load_index(index_path, chunks_path):
    index = faiss.read_index(index_path)
    with open(chunks_path, "rb") as f:
        chunks = pickle.load(f)
    return index, chunks
