# Redespliegue — versión con voz a texto

Pasos para actualizar un servidor que ya tiene el Agente RAG funcionando
(ver [DEPLOY.md](DEPLOY.md) para una instalación desde cero).

**Qué trae esta versión**

- Botón de **micrófono** en el chat: graba hasta 5 minutos y lo convierte a texto.
- Se pueden **subir audios** (mp3, m4a, wav, ogg, opus, webm…) con el botón
  **+** o arrastrándolos, y se transcriben.
- La transcripción se puede **copiar**, **usar como pregunta** o **exportar a Word**.
- Nuevo endpoint `POST /transcribe` en la API (faster-whisper, local).
- Dependencias nuevas: `faster-whisper==1.2.1` y `av==16.1.0`.
- `max_memory_restart` de la API sube de `2G` a `3G`.

---

## 0. Antes de empezar

- Que los cambios estén subidos al repositorio (commit + push desde la PC de
  desarrollo).
- Anotar el commit actual del servidor por si hay que volver atrás:
  ```bash
  cd Tecnomatica
  git rev-parse --short HEAD
  ```
- La primera transcripción necesita **internet** para descargar el modelo de
  voz (~460 MB). Si el servidor no tiene salida, sigue el paso 3b.

---

## 1. Traer el código

```bash
cd Tecnomatica
git pull
```

---

## 2. Instalar las dependencias nuevas

```bash
./rag_env/bin/pip install -r requirements.txt
```

Comprobar que quedó la versión correcta de `av` (la 19 o superior **no**
funciona con faster-whisper 1.2.1):

```bash
./rag_env/bin/pip show av faster-whisper | grep -E "Name|Version"
# Name: av              Version: 16.1.0
# Name: faster-whisper  Version: 1.2.1
```

---

## 3. Descargar el modelo de voz (recomendado)

Así la primera transcripción del usuario no se queda esperando la descarga.

### 3a. Servidor con internet

Ejecutar con el **mismo usuario** que corre PM2 (la caché va a su
`~/.cache/huggingface/`):

```bash
./rag_env/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('OK')"
```

### 3b. Servidor sin internet

En una PC con internet, ejecutar el mismo comando y copiar la carpeta
`~/.cache/huggingface/hub/models--Systran--faster-whisper-small` al mismo
sitio en el servidor (en el home del usuario que corre PM2).

> Si cambias `WHISPER_MODEL` (paso 4), descarga ese modelo en vez de `small`.

---

## 4. (Opcional) Ajustar `.env`

No hace falta tocar nada: los valores por defecto funcionan. Si quieres
cambiarlos, añade en `rag/.env`:

```ini
WHISPER_MODEL=small        # tiny | base | small | medium | large-v3 | turbo
WHISPER_DEVICE=auto        # auto (GPU si sirve, si no CPU) | cpu | cuda
WHISPER_LANGUAGE=es        # "auto" para detectar el idioma
AUDIO_MAX_MB=50
```

En CPU, `small` tarda unos 15–40 s por cada minuto de audio. `medium` o
`turbo` son más precisos pero bastante más lentos sin GPU.

---

## 5. Reiniciar los procesos

Como cambió `ecosystem.config.cjs` (límite de memoria), hay que volver a
crear el proceso de la API para que PM2 lea la configuración nueva.
Un `pm2 restart` normal no la aplica:

```bash
pm2 delete agente-rag-api
pm2 start ecosystem.config.cjs --only agente-rag-api
pm2 restart agente-rag-web
pm2 save
```

Comprobar:

```bash
pm2 status
pm2 logs agente-rag-api --lines 30
```

---

## 6. Verificar

```bash
# La API responde
curl http://localhost:3090/health
# -> {"status":"ok"}

# Transcripción: usar cualquier audio corto (p. ej. una nota de voz del móvil)
curl -X POST http://localhost:3090/transcribe \
  -H "X-Filename: prueba.m4a" \
  --data-binary @prueba.m4a
# -> {"text":"...","language":"es","duration":12.3,"segments":2}
```

En los logs debe aparecer una vez:

```
[rag] Whisper 'small' cargado en cpu (int8)     # o "en cuda (float16)" con GPU
```

Y en el navegador (`http://<IP-DEL-SERVIDOR>:4000`):

1. Recargar con **Ctrl+F5** para que coja el `app.js` nuevo.
2. Subir un audio con **+** → debe aparecer "Transcribiendo…" y luego el texto
   con los botones Copiar / Usar como pregunta / Word.
3. Probar el **micrófono** (ver el paso 7).
4. Hacer una pregunta normal para confirmar que el RAG sigue igual.

---

## 7. Micrófono: requiere HTTPS

El navegador **solo permite usar el micrófono** si la página se abre por
`https://` o desde `http://localhost`. Si se abre por `http://<IP>:4000`,
subir audios funciona, pero el botón del micrófono muestra un aviso.

Opciones:

1. **Recomendado:** poner la web y la API detrás de HTTPS (Caddy o Nginx con
   un certificado interno).
2. **Rápido, PC por PC (Chrome/Edge):** abrir
   `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, añadir
   `http://<IP-DEL-SERVIDOR>:4000`, poner **Enabled** y reiniciar el
   navegador.

---

## 8. Si algo falla

| Síntoma | Qué revisar |
| --- | --- |
| "No se pudo leer el audio: open() got an unexpected keyword argument 'metadata_errors'" | Se instaló `av` 19+. `./rag_env/bin/pip install av==16.1.0` y reiniciar la API |
| "La transcripción no está instalada en el servidor" | No se ejecutó el paso 2 |
| La primera transcripción tarda mucho o da timeout | Está descargando el modelo: hacer el paso 3 |
| "No se pudo cargar el modelo de voz" | Sin internet y sin el modelo en caché (paso 3b) |
| La API se reinicia sola al transcribir | Memoria: comprobar que el paso 5 aplicó `3G` (`pm2 describe agente-rag-api`); con `medium`/`large-v3`, subir más |
| La API se cae al transcribir (`Segmentation fault` en `pm2 logs agente-rag-api --err`) | No probado en 3.12. Guardar el log y probar `WHISPER_DEVICE=cpu`; si sigue, volver atrás (paso 9) |
| El botón de micrófono avisa de https | Normal por `http://IP`: ver el paso 7 |
| La web no muestra el micrófono | Caché del navegador: Ctrl+F5 |

---

## 9. Volver a la versión anterior

```bash
cd Tecnomatica
git checkout <commit-anotado-en-el-paso-0>
pm2 delete agente-rag-api
pm2 start ecosystem.config.cjs --only agente-rag-api
pm2 restart agente-rag-web
pm2 save
```

Las dependencias nuevas pueden quedarse instaladas: la versión anterior no
las usa.
