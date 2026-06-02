import os
from openai import OpenAI
from config import LMSTUDIO_MODEL, LMSTUDIO_URL
from loader import load_all_document
from rag_core import build_index, search

client = OpenAI(base_url=LMSTUDIO_URL, api_key="lm-studio")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_index = None
_chunks = None


def _ensure_index():
    global _index, _chunks
    if _index is None:
        print(f"Cargando documentos desde {DATA_DIR} ...")
        documents = load_all_document(DATA_DIR)
        documents = [d for d in documents if d and d.strip()]
        if not documents:
            raise RuntimeError(
                f"No se encontraron documentos legibles en {DATA_DIR}"
            )
        print(f"Indexando {len(documents)} documentos...")
        _index, _chunks = build_index(documents)
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


def send_to_rag(message, k=5):
    index, chunks = _ensure_index()
    frags = search(index, chunks, message, k=k)
    messages = build_messages(message, frags)

    response = client.chat.completions.create(
        model=LMSTUDIO_MODEL,
        messages=messages,
    )
    return response.choices[0].message.content
