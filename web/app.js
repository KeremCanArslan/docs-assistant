(() => {
  "use strict";

  const API = (window.API_BASE || "").replace(/\/$/, "");
  const form = document.getElementById("form");
  const input = document.getElementById("question");
  const submit = document.getElementById("submit");
  const count = document.getElementById("count");
  const statusBox = document.getElementById("status");
  const answerBox = document.getElementById("answer");
  const sourcesBox = document.getElementById("sources");
  const docList = document.getElementById("documents");

  const escapeHtml = (text) =>
    text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function setStatus(text, isError = false) {
    statusBox.textContent = text;
    statusBox.classList.toggle("error", isError);
  }

  // Citation markers such as [2] or [1, 3] become links to the source cards below the answer.
  function renderInline(text) {
    return escapeHtml(text.replace(/\*\*(.+?)\*\*/g, "$1")).replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]/g, (_, group) =>
      group
        .split(",")
        .map((n) => n.trim())
        .map((n) => `<a class="cite" href="#source-${n}" data-source="${n}" aria-label="Source ${n}">${n}</a>`)
        .join("")
    );
  }

  function renderAnswer(text) {
    const html = [];
    let list = [];
    const flush = () => {
      if (list.length) html.push(`<ul>${list.map((item) => `<li>${item}</li>`).join("")}</ul>`);
      list = [];
    };
    for (const raw of text.split("\n")) {
      const line = raw.trim();
      if (!line) { flush(); continue; }
      const bullet = line.match(/^[*\-•]\s+(.*)$/);
      if (bullet) { list.push(renderInline(bullet[1])); continue; }
      flush();
      html.push(`<p>${renderInline(line)}</p>`);
    }
    flush();
    return html.join("");
  }

  function documentUrl(url) {
    return url.startsWith("http") ? url : API + url;
  }

  function showSources(citations) {
    sourcesBox.innerHTML = citations
      .map(
        (c) => `<li class="source" id="source-${c.number}">
          <div class="source-head">
            <div><span class="source-num">${c.number}</span><span class="source-title">${escapeHtml(c.title)}</span></div>
            <a class="source-where" href="${escapeHtml(documentUrl(c.url))}" target="_blank" rel="noopener">${escapeHtml(c.location || c.document)} ↗</a>
          </div>
          <pre>${escapeHtml(c.excerpt)}</pre>
        </li>`
      )
      .join("");
    sourcesBox.hidden = citations.length === 0;
  }

  sourcesBox.parentElement.addEventListener("click", (event) => {
    const link = event.target.closest(".cite");
    if (!link) return;
    event.preventDefault();
    const card = document.getElementById(`source-${link.dataset.source}`);
    if (!card) return;
    sourcesBox.querySelectorAll(".active").forEach((el) => el.classList.remove("active"));
    card.classList.add("active");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  async function ask(question) {
    submit.disabled = true;
    answerBox.hidden = true;
    sourcesBox.hidden = true;
    setStatus("Searching the documents…");
    const slow = setTimeout(
      () => setStatus("Waking up the free server. The first question after a quiet period can take up to a minute…"),
      5000
    );
    try {
      const response = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof body.error === "string" ? body.error : "The question could not be answered.";
        setStatus(detail, true);
        return;
      }
      setStatus("");
      answerBox.className = body.found ? "answer" : "answer not-found";
      const seconds = ((body.retrieval_ms + body.generation_ms) / 1000).toFixed(1);
      const label = body.found ? "" : '<div class="label">Not found in the documents</div>';
      answerBox.innerHTML = `${label}${renderAnswer(body.answer)}<div class="meta">${seconds} s · ${escapeHtml(body.model)}</div>`;
      answerBox.hidden = false;
      showSources(body.found ? body.citations : []);
    } catch (error) {
      setStatus("The server could not be reached. Please try again in a moment.", true);
    } finally {
      clearTimeout(slow);
      submit.disabled = false;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (question) ask(question);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  input.addEventListener("input", () => { count.textContent = `${input.value.length} / 500`; });
  document.querySelectorAll(".example").forEach((button) =>
    button.addEventListener("click", () => {
      input.value = button.textContent;
      count.textContent = `${input.value.length} / 500`;
      form.requestSubmit();
    })
  );

  fetch(`${API}/api/documents`)
    .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
    .then((documents) => {
      docList.innerHTML = documents
        .map((d) => {
          const kind = d.document.split(".").pop();
          const pages = d.pages ? ` · ${d.pages} ${d.pages === 1 ? "page" : "pages"}` : "";
          return `<li><a href="${escapeHtml(documentUrl(d.url))}" target="_blank" rel="noopener">${escapeHtml(d.title)}</a><span class="kind">${escapeHtml(kind)}${pages}</span></li>`;
        })
        .join("");
    })
    .catch(() => {
      docList.innerHTML = '<li class="muted">The list loads when the server is awake.</li>';
    });
})();
