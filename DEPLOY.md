# Despliegue — Agente RAG

Guía paso a paso para desplegar el sistema en una máquina anfitriona usando
**PM2**. Se levantan dos procesos:

| Proceso          | Puerto | Qué hace                                              |
| ---------------- | -----: | ----------------------------------------------------- |
| `agente-rag-api` | `3090` | API FastAPI (Uvicorn) que habla con Ollama + RAG      |
| `agente-rag-web` | `4000` | Servidor estático de `rag/web/` (interfaz de chat)    |

Ollama corre en **otra máquina** (el servidor con el agente) y la API se
conecta a ella vía red usando su endpoint compatible con OpenAI (`/v1`).

### Resumen de cómo funciona el RAG

- La carpeta `rag/data/` contiene todos los documentos (PDF, DOCX, PPTX, TXT,
  DOC, y en subcarpetas). **Se puede actualizar en caliente**: un watcher
  comprueba cada 30 s (configurable) si cambió algún documento y reindexa en
  segundo plano *sin detener el servicio*. Las consultas siguen respondiendo
  con el índice anterior hasta que el nuevo esté listo.
- Los embeddings usan un **modelo multilingüe** (`paraphrase-multilingual-…`,
  óptimo para documentos en español) y dispositivo **"auto"**: CUDA si hay una
  GPU RTX realmente utilizable, y CPU en caso contrario. No hay que configurar
  nada por servidor. En el primer arranque descarga el modelo (~470 MB).
- Cada respuesta cita sus **fuentes en línea**: un número junto a cada frase
  (estilo DeepSeek). Al pasar el ratón se ve el documento, la página y un
  extracto; al hacer clic se abre el documento (los PDF, en la página exacta)
  a través de `GET /files/<ruta>`, que sirve los archivos de `rag/data/`.
- Bajo cada respuesta hay botones para **copiar** el texto, **exportar a Word**
  (`POST /export/docx`) y ver la lista de fuentes.
- El botón **+** del chat (o arrastrar/pegar) permite adjuntar PDF, Word,
  Excel, PowerPoint, TXT o CSV y preguntar sobre ellos además de la base
  documental. Los adjuntos **no** se guardan en `data/`: viven en memoria
  (4 h por defecto, `UPLOAD_TTL_SECONDS`) y se pierden si se reinicia la API.

---

## 1. Requisitos en la máquina anfitriona

- **Python 3.12** (el `venv` del repo, `rag_env/`, ya está creado).
- **Node.js 18+** y **PM2** instalado de forma global:
  ```bash
  sudo npm install -g pm2
  ```
- Acceso de red **a** la máquina servidor con Ollama (puerto `11434`).
- Puertos `3090` y `4000` libres y abiertos en el firewall local.
- Los embeddings corren en la máquina anfitriona. Con GPU NVIDIA RTX usará
  CUDA automáticamente; sin GPU funcionará en CPU (más lento pero correcto).
  En el primer arranque descarga el modelo de embeddings multilingüe (~470 MB).
  La primera reindexación puede tardar unos minutos; el servicio arranca igual
  y responde `503` ("El índice de documentos se está construyendo") hasta que
  termina.
- **(Opcional)** Para indexar documentos `.doc` antiguos (formato Word legacy)
  instala LibreOffice en la máquina anfitriona:
  ```bash
  sudo apt install -y libreoffice-writer   # Ubuntu/Debian
  ```
  Si no está instalado, los `.doc` se omiten silenciosamente y el resto de
  documentos (PDF, DOCX, PPTX, TXT) funcionan igual.

---

## 2. Clonar y preparar el entorno

```bash
git clone <tu-repo> Tecnomatica
cd Tecnomatica

# Crear venv (solo la primera vez, si no existe)
python3.12 -m venv rag_env
./rag_env/bin/pip install --upgrade pip
./rag_env/bin/pip install -r requirements.txt
```

---

## 3. Configurar la conexión a Ollama y los puertos

Copia la plantilla y edítala (`.env` está en `.gitignore`, no se clona):

```bash
cp rag/.env.example rag/.env
nano rag/.env
```

```ini
# Maquina servidor que aloja Ollama (la PC "agente" de la red)
OLLAMA_HOST=172.18.201.201      # <-- IP REAL del servidor con Ollama
OLLAMA_PORT=11434
OLLAMA_MODEL=qwen3.6:27b
```

> Cuando cambie la IP de Ollama basta con editar `OLLAMA_HOST` y
> reiniciar la API. No hay que tocar código.

### En la máquina servidor que aloja Ollama

1. Ollama debe estar sirviendo en la red (no solo en `127.0.0.1`): arráncalo
   con `OLLAMA_HOST=0.0.0.0 ollama serve` o configura esa variable en su
   servicio systemd.
2. Verifica que el modelo esté descargado: `ollama list` debe mostrar
   `qwen3.6:27b` (o el modelo configurado en `OLLAMA_MODEL`).
3. Permitir el puerto `11434` en el firewall.

---

## 4. (Opcional) Si la web vive en otra máquina distinta a la API

Por defecto, el frontend asume que la API está en
`http://<mismo-host>:3090`. Si vas a servir la web desde otra máquina,
crea `rag/web/config.js` (o edítalo) y añade:

```js
window.RAG_API_BASE = "http://IP-DE-LA-API:3090";
```

---

## 5. Arranque con PM2

Desde la raíz del repo:

```bash
pm2 start ecosystem.config.cjs
pm2 save                 # persiste la lista actual
pm2 startup              # imprime un comando con sudo: ejecutalo para
                         # que PM2 arranque solo al iniciar el sistema
```

Comprueba el estado:

```bash
pm2 status
pm2 logs agente-rag-api --lines 50
pm2 logs agente-rag-web --lines 20
```

Deberías ver en los logs de la API algo así:

```
[rag] Ollama endpoint: http://172.18.201.201:11434/v1 (modelo=qwen3.6:27b)
Uvicorn running on http://0.0.0.0:3090
```

---

## 6. Verificación

Desde la propia máquina:

```bash
# API responde
curl http://localhost:3090/health
# -> {"status":"ok"}

# La API alcanza Ollama
curl http://localhost:3090/ollama/health
# 200 con lista de modelos  -> conexion OK
# 503 con detalle.error     -> revisa OLLAMA_HOST / firewall / que "ollama serve" escuche en la red

# La web sirve el HTML
curl -I http://localhost:4000/
# -> HTTP/1.0 200 OK
```

Desde otra PC de la red, averigua la IP de la máquina anfitriona:

```bash
hostname -I        # Linux
ipconfig           # Windows
```

Y abre en el navegador:

```
http://<IP-DEL-SERVIDOR>:4000
```

El chat se cargará y, al enviar la primera pregunta, llamará automáticamente
a `http://<IP-DEL-SERVIDOR>:3090/query`.

---

## 7. Firewall (Linux con UFW, ejemplo)

```bash
sudo ufw allow 3090/tcp comment "Agente RAG API"
sudo ufw allow 4000/tcp comment "Agente RAG Web"
sudo ufw reload
```

En Windows: **Firewall de Windows → Reglas de entrada → Nueva regla → Puerto
TCP 3090 y 4000 → Permitir**.

---

## 8. Operaciones comunes

```bash
# Reiniciar tras cambiar .env o codigo
pm2 restart agente-rag-api
pm2 restart agente-rag-web

# Reconstruir el indice FAISS (si añadiste/cambiaste documentos)
curl -X POST http://localhost:3090/reindex

# Estado del indice: nº de documentos, fragmentos y si detecta cambios
curl http://localhost:3090/docs/info
# -> {"documents":12,"chunks":842,"signature":"...","auto_reindex_seconds":30}

# Parar / arrancar todo
pm2 stop all
pm2 start all

# Quitar definitivamente
pm2 delete agente-rag-api agente-rag-web
pm2 save
```

Los logs viven en `logs/`:

```
logs/rag-api-out.log    logs/rag-api-error.log
logs/rag-web-out.log    logs/rag-web-error.log
```

---

## 9. Actualizar a una nueva versión del código

```bash
cd Tecnomatica
git pull
./rag_env/bin/pip install -r requirements.txt   # por si hay nuevas deps
pm2 restart agente-rag-api agente-rag-web
```

> Si la actualización cambia el formato del índice (`CACHE_VERSION` en
> `rag/ollama_chat.py`), la API reindexa sola al arrancar y responde `503`
> hasta que termina.

---

## 10. Resolución de problemas rápida

| Síntoma                                              | Causa probable / acción                                         |
| ---------------------------------------------------- | --------------------------------------------------------------- |
| Indicador del header en rojo: "Ollama inaccesible"    | IP/puerto mal, firewall, o `ollama serve` no escucha en la red  |
| Indicador naranja: "modelo no cargado"                | El nombre de `OLLAMA_MODEL` no coincide con el de `ollama list` |
| Indicador rojo: "API no responde"                     | `pm2 status` → la API está caída o el puerto 3090 cerrado        |
| `pm2 status` muestra `errored`                        | `pm2 logs agente-rag-api --err --lines 100`                      |
| Página web no carga desde otra PC                     | Falta abrir el puerto 4000 en el firewall                         |
| La web carga pero las preguntas dan error de red      | El frontend no encuentra la API en `:3090` → revisa `config.js`  |
