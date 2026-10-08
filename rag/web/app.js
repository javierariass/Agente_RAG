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

  const UPLOAD_EXTENSIONS = [".pdf", ".doc", ".docx", ".pptx", ".txt", ".xlsx", ".xlsm", ".csv"];

  const chatEl = document.getElementById("chat");
  const formEl = document.getElementById("composer");
  const inputEl = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const welcomeEl = document.getElementById("welcome");
  const themeBtn = document.getElementById("theme-toggle");
  const clearBtn = document.getElementById("clear-btn");
  const statusEl = document.getElementById("status-indicator");
  const statusText = statusEl.querySelector(".status-text");
  const attachBtn = document.getElementById("attach-btn");
  const fileInput = document.getElementById("file-input");
  const attachmentsEl = document.getElementById("attachments");

  const ICONS = {
    copy: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M8 3h11a2 2 0 0 1 2 2v11h-2V5H8V3Zm-3 4h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Zm0 2v10h10V9H5Z"/></svg>',
    check: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="m9.5 16.2-4.2-4.2-1.4 1.4 5.6 5.6L21 7.4 19.6 6 9.5 16.2Z"/></svg>',
    word: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm7 1.5V9h5.5L13 3.5ZM7.2 12l1.3 6h1.6l1-4 1 4h1.6l1.3-6h-1.5l-.7 3.8-1-3.8h-1.4l-1 3.8-.7-3.8H7.2Z"/></svg>',
    sources: '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M4 5h16v2H4V5Zm0 6h16v2H4v-2Zm0 6h10v2H4v-2Z"/></svg>',
    file: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm7 1.5V9h5.5L13 3.5Z"/></svg>',
    close: '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="m6.4 5 5.6 5.6L17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6l5.6-5.6L5 6.4 6.4 5Z"/></svg>',
  };

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
    hideTip();
    clearAttachments();
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

  function scrollToBottom() {
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function el(tag, className, html) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (html != null) node.innerHTML = html;
    return node;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function appendMessage(role, text, files) {
    removeWelcome();
    const wrap = el("div", `msg msg--${role}`);
    const bubble = el("div", "bubble");
    bubble.textContent = text;
    if (files && files.length) {
      const list = el("div", "bubble-files");
      for (const f of files) {
        const chip = el("span", "file-chip file-chip--static", ICONS.file);
        chip.appendChild(document.createTextNode(f.name));
        list.appendChild(chip);
      }
      bubble.prepend(list);
    }
    wrap.appendChild(bubble);
    chatEl.appendChild(wrap);
    scrollToBottom();
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
    scrollToBottom();
    return wrap;
  }

  // ---------- Citas ----------
  // El modelo cita con los numeros de los fragmentos que recibio ([3], [1][5],
  // [2, 4]...). Se renumeran por orden de aparicion (1, 2, 3...) y se
  // descartan los numeros que no correspondan a ninguna fuente real.
  const CITE_RE = /\[(\d+(?:\s*[,;]\s*\d+)*)\]/g;

  function processCitations(answer, citations) {
    const byId = new Map((citations || []).map((c) => [c.id, c]));
    const order = new Map(); // id original -> numero mostrado
    const used = [];

    const marked = answer
      .replace(CITE_RE, (_m, group) => {
        const nums = [];
        for (const part of group.split(/[,;]/)) {
          const id = parseInt(part.trim(), 10);
          if (!byId.has(id)) continue;
          if (!order.has(id)) {
            order.set(id, order.size + 1);
            used.push({ ...byId.get(id), n: order.size });
          }
          const n = order.get(id);
          if (!nums.includes(n)) nums.push(n);
        }
        return nums.map((n) => `[${n}]`).join("");
      })
      // Grupos seguidos ([2][1][1]) -> numeros unicos y ordenados ([1][2]).
      .replace(/(?:\[\d+\])+/g, (run) => {
        const nums = [...new Set(run.match(/\d+/g).map(Number))].sort((a, b) => a - b);
        return nums.map((n) => `[${n}]`).join("");
      });

    // Texto limpio (para copiar): sin marcas y sin el espacio que las precedia.
    const plain = marked
      .replace(/\s*(\[\d+\])+/g, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/^\s*#{1,4}\s+/gm, "");

    return { marked, plain, used };
  }

  function fileUrl(cit) {
    if (cit.kind !== "doc") return null;
    const path = cit.source.split(/[\\/]/).map(encodeURIComponent).join("/");
    const isPdf = /\.pdf$/i.test(cit.source);
    return `${API_BASE}/files/${path}${isPdf && cit.page ? `#page=${cit.page}` : ""}`;
  }

  function citeLabel(cit) {
    const parts = [];
    if (cit.page) parts.push(`pág. ${cit.page}`);
    if (cit.kind === "upload") parts.push("archivo adjunto");
    return parts.join(" · ");
  }

  function renderInline(text, citeMap) {
    let html = escapeHtml(text);
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\[(\d+)\]/g, (m, num) => {
      const cit = citeMap.get(parseInt(num, 10));
      if (!cit) return m;
      const url = fileUrl(cit);
      const attrs = `class="cite" data-n="${cit.n}"`;
      return url
        ? `<a ${attrs} href="${escapeHtml(url)}" target="_blank" rel="noopener">${cit.n}</a>`
        : `<button ${attrs} type="button">${cit.n}</button>`;
    });
    // Cada grupo de citas se pega a la palabra anterior para que un numero
    // nunca quede solo al principio de una linea.
    html = html.replace(/([^\s<>]*)\s*((?:<(?:a|button) class="cite"[^>]*>\d+<\/(?:a|button)>)+)/g,
      '<span class="cite-group">$1$2</span>');
    return html;
  }

  // Markdown minimo: parrafos, titulos, listas y negritas.
  function renderAnswer(marked, used) {
    const citeMap = new Map(used.map((c) => [c.n, c]));
    const out = [];
    let list = null;
    const closeList = () => {
      if (list) {
        out.push(`</${list}>`);
        list = null;
      }
    };
    for (const raw of marked.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) {
        closeList();
        continue;
      }
      let m;
      if ((m = line.match(/^(#{1,4})\s+(.*)$/))) {
        closeList();
        out.push(`<h4>${renderInline(m[2], citeMap)}</h4>`);
      } else if ((m = line.match(/^[-*•]\s+(.*)$/))) {
        if (list !== "ul") {
          closeList();
          out.push("<ul>");
          list = "ul";
        }
        out.push(`<li>${renderInline(m[1], citeMap)}</li>`);
      } else if ((m = line.match(/^\d+[.)]\s+(.*)$/))) {
        if (list !== "ol") {
          closeList();
          out.push("<ol>");
          list = "ol";
        }
        out.push(`<li>${renderInline(m[1], citeMap)}</li>`);
      } else {
        closeList();
        out.push(`<p>${renderInline(line, citeMap)}</p>`);
      }
    }
    closeList();
    return out.join("");
  }

  // Tooltip flotante con el detalle de cada cita (titulo, pagina y extracto).
  const tipEl = el("div", "cite-tip");
  tipEl.setAttribute("role", "tooltip");
  tipEl.hidden = true;
  document.body.appendChild(tipEl);
  let tipAnchor = null;
  let tipHideTimer = null;

  function showTip(anchor) {
    const cit = anchor._cit;
    if (!cit) return;
    clearTimeout(tipHideTimer);
    tipAnchor = anchor;
    const meta = citeLabel(cit);
    const url = fileUrl(cit);
    tipEl.innerHTML =
      `<div class="cite-tip-head"><span class="cite-tip-n">${cit.n}</span>` +
      `<span class="cite-tip-title">${escapeHtml(cit.title)}</span></div>` +
      (meta ? `<div class="cite-tip-meta">${escapeHtml(meta)}</div>` : "") +
      `<div class="cite-tip-snippet">${escapeHtml(cit.snippet.trim())}${cit.snippet.length >= 400 ? "…" : ""}</div>` +
      (url ? `<a class="cite-tip-open" href="${escapeHtml(url)}" target="_blank" rel="noopener">Abrir documento ↗</a>` : "");
    tipEl.hidden = false;

    const r = anchor.getBoundingClientRect();
    const tw = tipEl.offsetWidth;
    const th = tipEl.offsetHeight;
    let left = r.left + r.width / 2 - tw / 2;
    left = Math.max(12, Math.min(left, window.innerWidth - tw - 12));
    let top = r.top - th - 8;
    if (top < 8) top = r.bottom + 8;
    tipEl.style.left = `${left}px`;
    tipEl.style.top = `${top}px`;
  }

  function hideTip() {
    tipEl.hidden = true;
    tipAnchor = null;
  }

  function scheduleHideTip() {
    clearTimeout(tipHideTimer);
    tipHideTimer = setTimeout(hideTip, 180);
  }

  tipEl.addEventListener("mouseenter", () => clearTimeout(tipHideTimer));
  tipEl.addEventListener("mouseleave", scheduleHideTip);
  chatEl.addEventListener("scroll", hideTip, { passive: true });
  document.addEventListener("click", (e) => {
    if (tipAnchor && !tipEl.contains(e.target) && !e.target.closest(".cite")) hideTip();
  });

  function bindCitations(container, used) {
    const byN = new Map(used.map((c) => [c.n, c]));
    container.querySelectorAll(".cite").forEach((node) => {
      node._cit = byN.get(parseInt(node.dataset.n, 10));
      node.addEventListener("mouseenter", () => showTip(node));
      node.addEventListener("mouseleave", scheduleHideTip);
      node.addEventListener("focus", () => showTip(node));
      node.addEventListener("blur", scheduleHideTip);
      if (node.tagName === "BUTTON") {
        node.addEventListener("click", () => (tipAnchor === node ? hideTip() : showTip(node)));
      }
    });
  }

  // ---------- Acciones (copiar / Word / fuentes) ----------
  async function copyText(text) {
    // navigator.clipboard solo existe en contextos seguros (https o
    // localhost); si la web se abre por IP en la LAN se usa el metodo clasico.
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    if (!ok) throw new Error("copy failed");
  }

  function flash(btn, html, label, ms = 1600) {
    const prev = btn.innerHTML;
    btn.innerHTML = html + `<span>${label}</span>`;
    btn.classList.add("is-done");
    setTimeout(() => {
      btn.innerHTML = prev;
      btn.classList.remove("is-done");
    }, ms);
  }

  async function exportWord(question, marked, used, btn) {
    btn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/export/docx`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          answer: marked,
          citations: used.map((c) => ({
            n: c.n,
            title: c.title,
            source: c.source,
            page: c.page,
            kind: c.kind,
          })),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const a = document.createElement("a");
      const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
      a.href = URL.createObjectURL(blob);
      a.download = `respuesta-${stamp}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      flash(btn, ICONS.check, "Descargado");
    } catch (e) {
      flash(btn, ICONS.close, "Error al exportar");
    } finally {
      btn.disabled = false;
    }
  }

  function renderSourcesList(used) {
    const list = el("ol", "sources-list");
    for (const cit of used) {
      const li = el("li");
      const url = fileUrl(cit);
      const meta = citeLabel(cit);
      const title = `<span class="src-n">${cit.n}</span><span class="src-title">${escapeHtml(cit.title)}</span>` +
        (meta ? `<span class="src-meta">${escapeHtml(meta)}</span>` : "");
      li.innerHTML = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${title}</a>`
        : `<span class="src-static">${title}</span>`;
      list.appendChild(li);
    }
    return list;
  }

  function appendAnswer(question, data) {
    removeWelcome();
    const citations = Array.isArray(data.citations) ? data.citations : [];
    let { marked, plain, used } = processCitations(data.answer.trim(), citations);

    // Si el modelo no cito nada, se muestran igualmente los documentos
    // consultados (uno por documento) para no perder la trazabilidad.
    let uncited = false;
    if (!used.length && citations.length) {
      uncited = true;
      const seen = new Set();
      for (const c of citations) {
        const key = `${c.kind}|${c.source}`;
        if (seen.has(key)) continue;
        seen.add(key);
        used.push({ ...c, n: used.length + 1 });
      }
    }

    const wrap = el("div", "msg msg--ai");
    const col = el("div", "ai-col");
    const bubble = el("div", "bubble bubble--rich", renderAnswer(marked, used));
    bindCitations(bubble, used);
    col.appendChild(bubble);

    const actions = el("div", "msg-actions");
    const copyBtn = el("button", "act-btn", `${ICONS.copy}<span>Copiar</span>`);
    copyBtn.type = "button";
    copyBtn.title = "Copiar respuesta";
    copyBtn.addEventListener("click", async () => {
      try {
        await copyText(plain.trim());
        flash(copyBtn, ICONS.check, "Copiado");
      } catch {
        flash(copyBtn, ICONS.close, "No se pudo copiar");
      }
    });

    const wordBtn = el("button", "act-btn", `${ICONS.word}<span>Word</span>`);
    wordBtn.type = "button";
    wordBtn.title = "Exportar a Word (.docx)";
    wordBtn.addEventListener("click", () => exportWord(question, marked, used, wordBtn));

    actions.append(copyBtn, wordBtn);

    let sourcesPanel = null;
    if (used.length) {
      const label = uncited
        ? `${used.length} ${used.length === 1 ? "documento consultado" : "documentos consultados"}`
        : `${used.length} ${used.length === 1 ? "fuente" : "fuentes"}`;
      const srcBtn = el("button", "act-btn act-btn--sources", `${ICONS.sources}<span>${label}</span>`);
      srcBtn.type = "button";
      srcBtn.setAttribute("aria-expanded", "false");
      sourcesPanel = renderSourcesList(used);
      sourcesPanel.hidden = true;
      srcBtn.addEventListener("click", () => {
        sourcesPanel.hidden = !sourcesPanel.hidden;
        srcBtn.setAttribute("aria-expanded", String(!sourcesPanel.hidden));
        if (!sourcesPanel.hidden) sourcesPanel.scrollIntoView({ block: "nearest", behavior: "smooth" });
      });
      actions.appendChild(srcBtn);
    }

    col.appendChild(actions);
    if (sourcesPanel) col.appendChild(sourcesPanel);
    wrap.appendChild(col);
    chatEl.appendChild(wrap);
    scrollToBottom();
  }

  // ---------- Adjuntos ----------
  // Cada adjunto: { localId, name, status: "uploading"|"ready"|"error", id, error, promise }
  let attachments = [];
  let localSeq = 0;

  function renderAttachments() {
    attachmentsEl.innerHTML = "";
    attachmentsEl.hidden = attachments.length === 0;
    for (const att of attachments) {
      const chip = el("div", `file-chip file-chip--${att.status}`);
      chip.title = att.status === "error" ? att.error : att.name;
      const icon = att.status === "uploading" ? '<span class="spinner" aria-hidden="true"></span>' : ICONS.file;
      chip.innerHTML =
        `${icon}<span class="file-chip-name">${escapeHtml(att.name)}</span>` +
        (att.status === "error" ? `<span class="file-chip-err">${escapeHtml(att.error)}</span>` : "");
      const rm = el("button", "file-chip-rm", ICONS.close);
      rm.type = "button";
      rm.setAttribute("aria-label", `Quitar ${att.name}`);
      rm.addEventListener("click", () => removeAttachment(att.localId));
      chip.appendChild(rm);
      attachmentsEl.appendChild(chip);
    }
  }

  function removeAttachment(localId) {
    const att = attachments.find((a) => a.localId === localId);
    attachments = attachments.filter((a) => a.localId !== localId);
    if (att && att.id) {
      fetch(`${API_BASE}/upload/${att.id}`, { method: "DELETE" }).catch(() => {});
    }
    renderAttachments();
  }

  function clearAttachments() {
    for (const att of attachments) {
      if (att.id) fetch(`${API_BASE}/upload/${att.id}`, { method: "DELETE" }).catch(() => {});
    }
    attachments = [];
    renderAttachments();
  }

  function addFiles(fileList) {
    for (const file of fileList) {
      const ext = (file.name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
      const att = { localId: ++localSeq, name: file.name, status: "uploading" };
      attachments.push(att);
      if (!UPLOAD_EXTENSIONS.includes(ext)) {
        att.status = "error";
        att.error = "formato no soportado";
        continue;
      }
      att.promise = fetch(`${API_BASE}/upload`, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
        },
        body: file,
      })
        .then(async (res) => {
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
          att.id = data.id;
          att.status = "ready";
        })
        .catch((e) => {
          att.status = "error";
          att.error = e.message || String(e);
        })
        .finally(renderAttachments);
    }
    renderAttachments();
    inputEl.focus();
  }

  attachBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) addFiles(fileInput.files);
    fileInput.value = "";
  });

  // Arrastrar y soltar archivos sobre la pagina.
  let dragDepth = 0;
  document.addEventListener("dragenter", (e) => {
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes("Files")) return;
    dragDepth++;
    formEl.classList.add("is-dragging");
  });
  document.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) formEl.classList.remove("is-dragging");
  });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    formEl.classList.remove("is-dragging");
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });

  // Pegar archivos con Ctrl+V en el cuadro de texto.
  inputEl.addEventListener("paste", (e) => {
    const files = e.clipboardData && e.clipboardData.files;
    if (files && files.length) {
      e.preventDefault();
      addFiles(files);
    }
  });

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

    // Si algun archivo aun se esta subiendo, se espera a que termine.
    const uploading = attachments.filter((a) => a.status === "uploading" && a.promise);
    const ready = () => attachments.filter((a) => a.status === "ready");
    appendMessage("user", question, attachments.filter((a) => a.status !== "error"));
    const typingNode = appendTyping();
    if (uploading.length) await Promise.all(uploading.map((a) => a.promise));

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // max_tokens lo decide la API (LLM_MAX_TOKENS en el .env): con modelos
        // de razonamiento un cupo corto se agota pensando y la respuesta llega
        // vacia.
        body: JSON.stringify({
          question,
          k: 5,
          temperature: 0.1,
          attachments: ready().map((a) => a.id),
        }),
      });

      typingNode.remove();

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail || res.statusText);
        appendMessage("error", `Error ${res.status}: ${detail}`);
        return;
      }

      const data = await res.json();
      const answer = (data.answer || "").trim();
      if (!answer) {
        // No deberia ocurrir (la API ya reintenta y falla con detalle), pero si
        // pasa es un fallo del modelo, no una respuesta valida.
        appendMessage("error", "El modelo no devolvió ninguna respuesta. Revisa los logs de la API.");
        return;
      }
      appendAnswer(question, data);

      // Adjuntos que el servidor ya no tiene (caducados o reinicio de la API).
      const missing = new Set(data.missing_attachments || []);
      if (missing.size) {
        for (const att of attachments) {
          if (missing.has(att.id)) {
            att.status = "error";
            att.error = "caducó, vuelve a subirlo";
            att.id = null;
          }
        }
        renderAttachments();
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
