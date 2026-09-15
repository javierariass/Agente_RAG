import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # fallback si python-dotenv no esta instalado
    def load_dotenv(*_args, **_kwargs):
        return False

# Carga .env desde la carpeta rag/ (junto a este archivo) y desde la raiz del repo.
_HERE = Path(__file__).resolve().parent
for _candidate in (_HERE / ".env", _HERE.parent / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)


def _clean(value):
    if value is None:
        return None
    value = value.strip().strip('"').strip("'")
    return value or None


def _normalize_ollama_url(raw_url, host, port):
    """Devuelve siempre http://host:port/v1 a partir de cualquiera de:

    OLLAMA_URL=172.18.201.201
    OLLAMA_URL=172.18.201.201:11434
    OLLAMA_URL=http://172.18.201.201:11434
    OLLAMA_URL=http://172.18.201.201:11434/
    OLLAMA_URL=http://172.18.201.201:11434/v1
    OLLAMA_HOST=172.18.201.201  (con OLLAMA_PORT opcional, default 11434)
    """
    if raw_url:
        url = raw_url
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        url = url.rstrip("/")
        if not url.endswith("/v1"):
            url = url + "/v1"
        return url

    host = host or "localhost"
    port = port or "11434"
    return f"http://{host}:{port}/v1"


# Modelo multilingue para embeddings (funciona bien con documentos en español).
# Si se cambia, el cache se invalida y se reindexa automaticamente.
EMBEDDING_MODEL = _clean(os.getenv("EMBEDDING_MODEL")) or "paraphrase-multilingual-MiniLM-L12-v2"
OLLAMA_MODEL = _clean(os.getenv("OLLAMA_MODEL")) or "qwen3.6:27b"

OLLAMA_HOST = _clean(os.getenv("OLLAMA_HOST"))
OLLAMA_PORT = _clean(os.getenv("OLLAMA_PORT"))
OLLAMA_URL = _normalize_ollama_url(
    _clean(os.getenv("OLLAMA_URL")),
    OLLAMA_HOST,
    OLLAMA_PORT,
)
OLLAMA_API_KEY = _clean(os.getenv("OLLAMA_API_KEY")) or "ollama"
OLLAMA_TIMEOUT = float(_clean(os.getenv("OLLAMA_TIMEOUT")) or "60")

CHUNK_SIZE = int(_clean(os.getenv("CHUNK_SIZE")) or "500")

# Presupuesto de tokens para la respuesta del LLM. Con modelos de razonamiento
# (qwen3, deepseek-r1, gpt-oss...) el "pensamiento" consume parte del cupo, asi
# que un valor bajo puede agotarlo antes de que el modelo escriba la respuesta
# final y devolver un content vacio.
LLM_MAX_TOKENS = int(_clean(os.getenv("LLM_MAX_TOKENS")) or "1024")

# Si es False (por defecto) se le pide a Ollama que no razone en voz alta, para
# que todo el cupo de tokens se gaste en la respuesta visible. Ponlo a true si
# quieres dejar que el modelo piense antes de responder (sube LLM_MAX_TOKENS).
OLLAMA_THINK = (_clean(os.getenv("OLLAMA_THINK")) or "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Dispositivo para los embeddings: "cpu", "cuda" o "auto" (por defecto).
# En "auto" se usa CUDA si hay una GPU realmente utilizable y se cae a CPU
# en caso contrario. No hay que tocar nada para servidores con RTX.
EMBEDDING_DEVICE = _clean(os.getenv("EMBEDDING_DEVICE")) or "auto"

# Cada cuantos segundos el watcher comprueba si la carpeta data/ cambio
# y, si es asi, reindexa en segundo plano sin detener el servicio.
REINDEX_WATCH_SECONDS = int(_clean(os.getenv("REINDEX_WATCH_SECONDS")) or "30")
