(() => {
  // Por defecto la API corre en el mismo host pero en el puerto 3090.
  // Para forzar otra URL crea rag/web/config.js con:
  //   window.RAG_API_BASE = "http://10.0.0.5:3090";
  const API_BASE = (() => {
    if (typeof window.RAG_API_BASE === "string" && window.RAG_API_BASE) {
      return window.RAG_API_BASE.replace(/\/+$/, "");
    }
    const proto = location.protocol === "https:" ? "https:" : "http:";
    const host = location.hostname || "localhost";
    return `${proto}//${host}:3090`;
  })();

  const chatEl = document.getElementById("chat");
  const formEl = document.getElementById("composer");
  const inputEl = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const welcomeEl = document.getElementById("welcome");
  const themeBtn = document.getElementById("theme-toggle");
  const clearBtn = document.getElementById("clear-btn");
  const statusEl = document.getElementById("status-indicator");
  const statusText = statusEl.querySelector(".status-text");

  // ---------- Tema ----------
  const savedTheme = localStorage.getItem("rag-theme");
  if (savedTheme) document.body.dataset.theme = savedTheme;
  themeBtn.addEventListener("click", () => {
    const next = document.body.dataset.theme === "dark" ? "light" : "dark";
    document.body.dataset.theme = next;
    localStorage.setItem("rag-theme", next);
  });

  // ---------- Limpiar conversacion ----------
  clearBtn.addEventListener("click", () => {
    chatEl.innerHTML = "";
    chatEl.appendChild(welcomeEl);
    inputEl.focus();
  });

  // ---------- Autoexpansion textarea ----------
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + "px";
  });

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      formEl.requestSubmit();
    }
  });

  // ---------- DOM helpers ----------
  function removeWelcome() {
    if (welcomeEl && welcomeEl.parentNode === chatEl) chatEl.removeChild(welcomeEl);
  }

  function appendMessage(role, text) {
    removeWelcome();
    const wrap = document.createElement("div");
    wrap.className = `msg msg--${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;

    wrap.appendChild(bubble);
    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
    return wrap;
  }

  function appendTyping() {
    removeWelcome();
    const wrap = document.createElement("div");
    wrap.className = "msg msg--ai";
    wrap.dataset.typing = "1";
    wrap.innerHTML =
      '<div class="typing" role="status" aria-label="La IA esta escribiendo">' +
      '<span class="dot"></span><span class="dot"></span><span class="dot"></span>' +
      "</div>";
    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
    return wrap;
  }

  function appendSources(sources) {
    const wrap = document.createElement("div");
    wrap.className = "msg msg--ai";
    const bubble = document.createElement("div");
    bubble.className = "bubble bubble--sources";
    bubble.textContent = "Fuentes: " + sources.join("  ·  ");
    wrap.appendChild(bubble);
    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function setStatus(state, text) {
    statusEl.classList.remove("status--ok", "status--bad", "status--warn", "status--unknown");
    statusEl.classList.add(`status--${state}`);
    statusText.textContent = text;
  }

  // ---------- Health check ----------
  async function checkHealth() {
    try {
      const res = await fetch(`${API_BASE}/ollama/health`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = err?.detail?.error || `HTTP ${res.status}`;
        setStatus("bad", "Ollama inaccesible");
        statusEl.title = msg;
        return;
      }
      const data = await res.json();
      if (data.model_loaded === false) {
        setStatus("warn", "modelo no cargado");
        statusEl.title = `Disponibles: ${(data.available_models || []).join(", ") || "(ninguno)"}`;
      } else {
        setStatus("ok", "Ollama conectado");
        statusEl.title = `${data.url} · ${data.model}`;
      }

      fetch(`${API_BASE}/docs/info`)
        .then((r) => (r.ok ? r.json() : null))
        .then((info) => {
          if (info && info.status !== "ready") {
            setStatus("warn", info.status === "building" ? "indexando documentos…" : "índice vacío");
            statusEl.title = `${info.documents} docs · ${info.chunks} fragmentos`;
          }
        })
        .catch(() => {});
    } catch (e) {
      setStatus("bad", "API no responde");
      statusEl.title = String(e);
    }
  }

  checkHealth();
  setInterval(checkHealth, 30000);

  // ---------- Envio ----------
  let pending = false;

  async function sendQuestion(question) {
    if (pending) return;
    pending = true;
    sendBtn.disabled = true;

    appendMessage("user", question);
    const typingNode = appendTyping();

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          k: 5,
          max_tokens: 512,
          temperature: 0.1,
        }),
      });

      typingNode.remove();

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        appendMessage("error", `Error ${res.status}: ${err.detail || res.statusText}`);
        return;
      }

      const data = await res.json();
      appendMessage("ai", data.answer || "(sin respuesta)");
      if (Array.isArray(data.sources) && data.sources.length) {
        appendSources(data.sources);
      }
    } catch (e) {
      typingNode.remove();
      appendMessage("error", `No se pudo contactar con la API: ${e.message || e}`);
    } finally {
      pending = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  formEl.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = inputEl.value.trim();
    if (!q) return;
    inputEl.value = "";
    inputEl.style.height = "auto";
    sendQuestion(q);
  });

  inputEl.focus();
})();
