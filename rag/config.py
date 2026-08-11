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


def _normalize_lmstudio_url(raw_url, host, port):
    """Devuelve siempre http://host:port/v1 a partir de cualquiera de:

    LMSTUDIO_URL=192.168.1.50
    LMSTUDIO_URL=192.168.1.50:1234
    LMSTUDIO_URL=http://192.168.1.50:1234
    LMSTUDIO_URL=http://192.168.1.50:1234/
    LMSTUDIO_URL=http://192.168.1.50:1234/v1
    LMSTUDIO_HOST=192.168.1.50  (con LMSTUDIO_PORT opcional, default 1234)
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
    port = port or "1234"
    return f"http://{host}:{port}/v1"


# Modelo multilingue para embeddings (funciona bien con documentos en español).
# Si se cambia, el cache se invalida y se reindexa automaticamente.
EMBEDDING_MODEL = _clean(os.getenv("EMBEDDING_MODEL")) or "paraphrase-multilingual-MiniLM-L12-v2"
LMSTUDIO_MODEL = _clean(os.getenv("LMSTUDIO_MODEL")) or "qwen2.5-coder-3b-instruct"

LMSTUDIO_HOST = _clean(os.getenv("LMSTUDIO_HOST"))
LMSTUDIO_PORT = _clean(os.getenv("LMSTUDIO_PORT"))
LMSTUDIO_URL = _normalize_lmstudio_url(
    _clean(os.getenv("LMSTUDIO_URL")),
    LMSTUDIO_HOST,
    LMSTUDIO_PORT,
)
LMSTUDIO_API_KEY = _clean(os.getenv("LMSTUDIO_API_KEY")) or "lm-studio"
LMSTUDIO_TIMEOUT = float(_clean(os.getenv("LMSTUDIO_TIMEOUT")) or "60")

CHUNK_SIZE = int(_clean(os.getenv("CHUNK_SIZE")) or "500")

# Dispositivo para los embeddings: "cpu", "cuda" o "auto" (por defecto).
# En "auto" se usa CUDA si hay una GPU realmente utilizable y se cae a CPU
# en caso contrario. No hay que tocar nada para servidores con RTX.
EMBEDDING_DEVICE = _clean(os.getenv("EMBEDDING_DEVICE")) or "auto"

# Cada cuantos segundos el watcher comprueba si la carpeta data/ cambio
# y, si es asi, reindexa en segundo plano sin detener el servicio.
REINDEX_WATCH_SECONDS = int(_clean(os.getenv("REINDEX_WATCH_SECONDS")) or "30")
