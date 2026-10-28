"""Transcripcion de audio a texto (voz -> texto) con faster-whisper.

Corre en local en la maquina de la API: el audio no sale de la red. Sirve
tanto para archivos subidos (mp3, m4a, wav, ogg...) como para lo grabado con
el microfono del navegador (webm/ogg con opus). La decodificacion la hace
PyAV, que trae su propio ffmpeg, asi que no hay que instalar nada mas.

El modelo se carga la primera vez que se usa (en el primer uso lo descarga,
~460 MB para "small") y se reutiliza. Las transcripciones se hacen de una en
una para no saturar la CPU/GPU.
"""

import os
import tempfile
import threading

from config import WHISPER_DEVICE, WHISPER_LANGUAGE, WHISPER_MODEL

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".oga", ".opus", ".webm",
    ".flac", ".aac", ".wma", ".amr", ".3gp", ".mp4",
}

_model = None
_model_device = None
_load_lock = threading.Lock()
_run_lock = threading.Lock()


class TranscriptionError(ValueError):
    pass


def _load_model():
    """Carga Whisper una sola vez. En "auto" intenta CUDA y, si la GPU no
    sirve (sin CUDA, sin cuDNN o tarjeta antigua), cae a CPU con int8."""
    global _model, _model_device
    if _model is not None:
        return _model
    with _load_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionError(
                "La transcripcion no esta instalada en el servidor "
                "(pip install -r requirements.txt)"
            ) from exc

        requested = WHISPER_DEVICE.lower()
        candidates = {
            "cpu": [("cpu", "int8")],
            "cuda": [("cuda", "float16")],
        }.get(requested, [("cuda", "float16"), ("cpu", "int8")])

        last_exc = None
        for device, compute_type in candidates:
            try:
                model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute_type)
                if device == "cuda":
                    # Los fallos de cuDNN/cuBLAS solo aparecen al ejecutar:
                    # se prueba con medio segundo de silencio.
                    import numpy as np
                    list(model.transcribe(np.zeros(8000, dtype=np.float32), language="es")[0])
                _model, _model_device = model, device
                print(f"[rag] Whisper '{WHISPER_MODEL}' cargado en {device} ({compute_type})")
                return _model
            except Exception as exc:  # se prueba el siguiente dispositivo
                last_exc = exc
        raise TranscriptionError(f"No se pudo cargar el modelo de voz: {last_exc}")


def transcribe_audio(filename, data):
    """Transcribe un audio y devuelve {text, language, duration, segments}."""
    name = os.path.basename(filename or "").strip() or "audio.webm"
    ext = os.path.splitext(name)[1].lower() or ".webm"
    if ext not in AUDIO_EXTENSIONS:
        allowed = ", ".join(sorted(AUDIO_EXTENSIONS))
        raise TranscriptionError(f"Formato de audio no soportado ({ext}). Usa: {allowed}")
    if not data:
        raise TranscriptionError("El audio esta vacio")

    model = _load_model()

    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        with _run_lock:
            try:
                segments, info = model.transcribe(
                    tmp_path,
                    language=WHISPER_LANGUAGE or None,
                    beam_size=5,
                    # Quita silencios largos: mas rapido y evita que Whisper
                    # "invente" frases en los tramos sin voz.
                    vad_filter=True,
                )
                parts = [s.text.strip() for s in segments if s.text.strip()]
            except Exception as exc:
                raise TranscriptionError(f"No se pudo leer el audio: {exc}") from exc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return {
        "text": " ".join(parts).strip(),
        "language": info.language,
        "duration": round(info.duration, 1),
        "segments": len(parts),
    }
