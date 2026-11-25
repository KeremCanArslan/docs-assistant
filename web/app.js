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
  const resultBox = document.getElementById("result");
  const docList = document.getElementById("documents");

  // Page texts. The answers themselves follow the language of the question, not this setting.
  const STRINGS = {
    en: {
      title: "Document assistant demo · Hollvik (fictional)",
      tag: "Document assistant demo",
      heading: "Ask the service documents",
      intro:
        "A demo of an assistant that answers questions from a company's own documents, such as manuals, price lists and internal guidelines, and links every answer to the page it came from.",
      lead:
        "Here it reads six documents of a fictional heat pump maker: datasheet, installation manual, warranty terms, service price list, customer FAQ and an internal service guideline. Answers come only from these documents. Ask in English, German or Turkish.",
      questionLabel: "Your question",
      placeholder: "e.g. How loud is the LW 12 at night?",
      ask: "Ask",
      examples: "Try an example",
      documents: "Documents",
      loading: "Loading the list…",
      listAsleep: "The list loads when the server is awake.",
      howTitle: "How it works",
      how1: "The documents are split into passages and indexed once.",
      how2: "For each question the closest passages are found by meaning, so an English question also finds a German page. Error codes are matched exactly.",
      how3: "The language model answers only from those passages and cites the source after each fact. If the documents do not contain the answer, it says so.",
      github: "Source code, tests and evaluation on GitHub",
      footer:
        "Hollvik Wärmetechnik GmbH and all documents are fictional, created for this demo. Questions are sent to the language model providers (Groq, Google) to produce the answer and are not stored by this demo; please do not enter personal data. Free hosting: the first question after a quiet period can take up to a minute.",
      searching: "Searching the documents…",
      waking: "Waking up the free server. The first question after a quiet period can take up to a minute…",
      unreachable: "The server could not be reached. Please try again in a moment.",
      failed: "The question could not be answered.",
      notFound: "Not found in the documents",
      hint: "Ask about warranty, prices, error codes, installation or maintenance, or click one of the example questions above.",
      page: "page",
      pages: "pages",
      pageShort: "p.",
      source: "Source",
      openPage: "Open page",
      openDoc: "Open document",
      errEmpty: "The question is empty.",
      errTooLarge: "The request is too large.",
      errMinute: "Too many questions in a minute. Please wait a moment.",
      errClientDay: "You have reached your daily question limit for this demo. Please try again tomorrow.",
      errDay: "The daily question limit of this demo is reached. Please try again tomorrow.",
      errModel: "The language model is not available right now. Please try again.",
    },
    de: {
      title: "Demo Dokumentenassistent · Hollvik (fiktiv)",
      tag: "Dokumentenassistent (Demo)",
      heading: "Fragen Sie die Servicedokumente",
      intro:
        "Die Demo eines Assistenten, der Fragen aus den eigenen Dokumenten eines Unternehmens beantwortet, etwa aus Handbüchern, Preislisten und internen Richtlinien, und jede Antwort mit der Seite verknüpft, aus der sie stammt.",
      lead:
        "Hier liest er sechs Dokumente eines fiktiven Wärmepumpenherstellers: Datenblatt, Installationsanleitung, Garantiebedingungen, Servicepreisliste, Kunden-FAQ und eine interne Serviceanweisung. Die Antworten stammen nur aus diesen Dokumenten. Fragen Sie auf Deutsch, Englisch oder Türkisch.",
      questionLabel: "Ihre Frage",
      placeholder: "z. B. Wie laut ist die LW 12 nachts?",
      ask: "Fragen",
      examples: "Beispiel ausprobieren",
      documents: "Dokumente",
      loading: "Liste wird geladen…",
      listAsleep: "Die Liste erscheint, sobald der Server wach ist.",
      howTitle: "So funktioniert es",
      how1: "Die Dokumente werden einmal in Abschnitte zerlegt und indexiert.",
      how2: "Zu jeder Frage werden die inhaltlich ähnlichsten Abschnitte gesucht, eine englische Frage findet also auch eine deutsche Seite. Fehlercodes werden exakt abgeglichen.",
      how3: "Das Sprachmodell antwortet nur aus diesen Abschnitten und nennt nach jeder Aussage die Quelle. Steht die Antwort nicht in den Dokumenten, sagt es das.",
      github: "Quellcode, Tests und Auswertung auf GitHub",
      footer:
        "Die Hollvik Wärmetechnik GmbH und alle Dokumente sind fiktiv und nur für diese Demo erstellt. Fragen werden zur Beantwortung an die Sprachmodell-Anbieter (Groq, Google) gesendet und von dieser Demo nicht gespeichert; bitte geben Sie keine personenbezogenen Daten ein. Kostenloses Hosting: Die erste Frage nach einer Pause kann bis zu einer Minute dauern.",
      searching: "Die Dokumente werden durchsucht…",
      waking: "Der kostenlose Server wird geweckt. Die erste Frage nach einer Pause kann bis zu einer Minute dauern…",
      unreachable: "Der Server ist nicht erreichbar. Bitte versuchen Sie es gleich noch einmal.",
      failed: "Die Frage konnte nicht beantwortet werden.",
      notFound: "Nicht in den Dokumenten gefunden",
      hint: "Fragen Sie nach Garantie, Preisen, Fehlercodes, Installation oder Wartung, oder klicken Sie oben auf eine Beispielfrage.",
      page: "Seite",
      pages: "Seiten",
      pageShort: "S.",
      source: "Quelle",
      openPage: "Seite öffnen",
      openDoc: "Dokument öffnen",
      errEmpty: "Die Frage ist leer.",
      errTooLarge: "Die Anfrage ist zu groß.",
      errMinute: "Zu viele Fragen in einer Minute. Bitte warten Sie einen Moment.",
      errClientDay: "Sie haben Ihr tägliches Fragenlimit für diese Demo erreicht. Bitte versuchen Sie es morgen wieder.",
      errDay: "Das tägliche Fragenlimit dieser Demo ist erreicht. Bitte versuchen Sie es morgen wieder.",
      errModel: "Das Sprachmodell ist gerade nicht verfügbar. Bitte versuchen Sie es erneut.",
    },
    tr: {
      title: "Belge asistanı demosu · Hollvik (uydurma)",
      tag: "Belge asistanı demosu",
      heading: "Servis belgelerine sorun",
      intro:
        "Bir firmanın kendi belgelerinden (kılavuzlar, fiyat listeleri, iç yönergeler) soruları cevaplayan ve her cevabı alındığı sayfaya bağlayan bir asistanın demosu.",
      lead:
        "Burada uydurma bir ısı pompası üreticisinin altı belgesini okuyor: teknik veri sayfası, kurulum kılavuzu, garanti şartları, servis fiyat listesi, müşteri soruları ve bir iç servis yönergesi. Cevaplar yalnız bu belgelerden gelir. Türkçe, İngilizce ya da Almanca sorabilirsiniz.",
      questionLabel: "Sorunuz",
      placeholder: "ör. LW 12 gece ne kadar ses çıkarıyor?",
      ask: "Sor",
      examples: "Örnek deneyin",
      documents: "Belgeler",
      loading: "Liste yükleniyor…",
      listAsleep: "Liste, sunucu uyanınca yüklenir.",
      howTitle: "Nasıl çalışır",
      how1: "Belgeler bir kez parçalara bölünüp dizinlenir.",
      how2: "Her soru için anlamca en yakın parçalar bulunur; İngilizce bir soru Almanca bir sayfayı da bulur. Hata kodları birebir eşleştirilir.",
      how3: "Dil modeli yalnız bu parçalardan cevap verir ve her bilginin arkasına kaynağını yazar. Cevap belgelerde yoksa bunu söyler.",
      github: "Kaynak kod, testler ve ölçüm sonuçları GitHub'da",
      footer:
        "Hollvik Wärmetechnik GmbH ve bütün belgeler uydurmadır, bu demo için hazırlandı. Sorular cevap üretmek için dil modeli sağlayıcılarına (Groq, Google) gönderilir ve bu demo tarafından saklanmaz; lütfen kişisel bilgi girmeyin. Ücretsiz sunucu: bir süre soru gelmezse ilk soru bir dakikaya kadar sürebilir.",
      searching: "Belgelerde aranıyor…",
      waking: "Ücretsiz sunucu uyandırılıyor. Bir süre soru gelmediyse ilk soru bir dakikaya kadar sürebilir…",
      unreachable: "Sunucuya ulaşılamadı. Lütfen biraz sonra yeniden deneyin.",
      failed: "Soru cevaplanamadı.",
      notFound: "Belgelerde bulunamadı",
      hint: "Garanti, fiyat, hata kodu, kurulum ya da bakım hakkında sorun veya yukarıdaki örnek sorulardan birine tıklayın.",
      page: "sayfa",
      pages: "sayfa",
      pageShort: "s.",
      source: "Kaynak",
      openPage: "Sayfayı aç",
      openDoc: "Belgeyi aç",
      errEmpty: "Soru boş.",
      errTooLarge: "İstek çok büyük.",
      errMinute: "Bir dakikada çok fazla soru soruldu. Lütfen biraz bekleyin.",
      errClientDay: "Bu demo için günlük soru hakkınız doldu. Lütfen yarın yeniden deneyin.",
      errDay: "Bu demonun günlük soru sınırı doldu. Lütfen yarın yeniden deneyin.",
      errModel: "Dil modeli şu an kullanılamıyor. Lütfen yeniden deneyin.",
    },
  };
  const LANGUAGES = Object.keys(STRINGS);
  // The API answers errors in English; known messages are shown in the page language.
  const ERROR_KEYS = Object.fromEntries(
    ["errEmpty", "errTooLarge", "errMinute", "errClientDay", "errDay", "errModel"].map((key) => [STRINGS.en[key], key])
  );

  function storedLanguage() {
    try {
      return localStorage.getItem("lang");
    } catch {
      return null;
    }
  }

  function pickLanguage() {
    const fromUrl = new URLSearchParams(location.search).get("lang");
    const browser = (navigator.languages || [navigator.language || ""]).map((l) => l.slice(0, 2).toLowerCase());
    return [fromUrl, storedLanguage(), ...browser].find((l) => LANGUAGES.includes(l)) || "en";
  }

  let lang = pickLanguage();
  let status = null; // { key } or { text }, plus isError
  let lastAnswer = null;
  let documents = null;

  const t = (key) => STRINGS[lang][key] ?? STRINGS.en[key];

  const escapeHtml = (text) =>
    text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function setStatus(next) {
    status = next;
    renderStatus();
  }

  function renderStatus() {
    statusBox.textContent = status ? (status.key ? t(status.key) : status.text) : "";
    statusBox.classList.toggle("error", Boolean(status && status.isError));
    statusBox.classList.toggle("busy", Boolean(status && status.busy));
  }

  // Citation markers such as [2], [1, 3] or [1][3] become tabs that point to the source pages next to the answer.
  const CITATION_RUN = /\[\d{1,2}(?:\s*,\s*\d{1,2})*\](?:\s*\[\d{1,2}(?:\s*,\s*\d{1,2})*\])*/g;
  function renderInline(text) {
    return escapeHtml(text.replace(/\*\*(.+?)\*\*/g, "$1")).replace(CITATION_RUN, (run) =>
      [...new Set(run.match(/\d{1,2}/g))]
        .map((n) => `<a class="cite" href="#source-${n}" data-source="${n}" aria-label="${t("source")} ${n}">${n}</a>`)
        .join("")
    );
  }

  // PDF text keeps the line breaks of the printed page; a line that continues a sentence is joined to the one before.
  const reflow = (text) => text.replace(/,\n/g, ", ").replace(/([^\n])\n(?=[a-zäöüßçğış])/g, "$1 ");

  const EXTERNAL_ICON =
    '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M5 2.5H2.5v7h7V7M7 2.5h2.5V5M9.5 2.5 5.5 6.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';

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

  const fileKind = (name) => name.split(".").pop().toUpperCase();

  // animate is false when the same answer is only redrawn in another page language.
  function showAnswer(body, animate = true) {
    answerBox.className = body.found ? "answer" : "answer not-found";
    const seconds = ((body.retrieval_ms + body.generation_ms) / 1000).toFixed(1);
    const label = body.found ? "" : `<div class="label">${escapeHtml(t("notFound"))}</div>`;
    const hint = body.found ? "" : `<p class="hint">${escapeHtml(t("hint"))}</p>`;
    answerBox.innerHTML = `${label}${renderAnswer(body.answer)}${hint}<div class="meta"><span>${seconds} s</span><span>${escapeHtml(body.model)}</span></div>`;
    answerBox.hidden = false;
    showSources(body.found ? body.citations : [], animate);
  }

  function showSources(citations, animate) {
    const active = sourcesBox.querySelector(".active")?.id;
    sourcesBox.innerHTML = citations
      .map((c, i) => {
        const where = c.page ? `${t("pageShort")} ${c.page}` : c.location;
        return `<li class="source" id="source-${c.number}" style="--i: ${i}">
          <span class="source-tab" aria-hidden="true">${c.number}</span>
          <div class="source-head">
            <span class="source-title"><span class="visually-hidden">${escapeHtml(t("source"))} ${c.number}: </span>${escapeHtml(c.title)}</span>
            <span class="source-kind">${escapeHtml(fileKind(c.document))}</span>
          </div>
          <p class="excerpt"><span>${escapeHtml(reflow(c.excerpt))}</span></p>
          <div class="source-foot">
            <span>${escapeHtml(where || "")}</span>
            <a href="${escapeHtml(documentUrl(c.url))}" target="_blank" rel="noopener">${escapeHtml(t(c.page ? "openPage" : "openDoc"))}${EXTERNAL_ICON}</a>
          </div>
        </li>`;
      })
      .join("");
    if (active) document.getElementById(active)?.classList.add("active");
    sourcesBox.classList.toggle("dealt", animate);
    sourcesBox.hidden = citations.length === 0;
    resultBox.classList.toggle("has-sources", citations.length > 0);
  }

  function showDocuments() {
    if (!documents) {
      docList.innerHTML = `<li class="muted">${escapeHtml(t(documents === null ? "loading" : "listAsleep"))}</li>`;
      return;
    }
    docList.innerHTML = documents
      .map((d) => {
        const pages = d.pages ? `<span class="doc-meta">${d.pages} ${escapeHtml(t(d.pages === 1 ? "page" : "pages"))}</span>` : "";
        return `<li><span class="file" aria-hidden="true">${escapeHtml(fileKind(d.document))}</span><div><a class="doc-title" href="${escapeHtml(documentUrl(d.url))}" target="_blank" rel="noopener">${escapeHtml(d.title)}</a>${pages}</div></li>`;
      })
      .join("");
  }

  function applyLanguage(next) {
    lang = next;
    document.documentElement.lang = lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    document.querySelectorAll(".lang").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.lang === lang)));
    renderStatus();
    showDocuments();
    if (lastAnswer) showAnswer(lastAnswer, false);
  }

  document.querySelectorAll(".lang").forEach((button) =>
    button.addEventListener("click", () => {
      try {
        localStorage.setItem("lang", button.dataset.lang);
      } catch {
        // Without storage the choice simply lasts until the page is closed.
      }
      applyLanguage(button.dataset.lang);
    })
  );

  resultBox.addEventListener("click", (event) => {
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
    sourcesBox.innerHTML = "";
    resultBox.classList.remove("has-sources");
    lastAnswer = null;
    setStatus({ key: "searching", busy: true });
    const slow = setTimeout(() => setStatus({ key: "waking", busy: true }), 5000);
    try {
      const response = await fetch(`${API}/api/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = typeof body.error === "string" ? body.error : "";
        if (ERROR_KEYS[message]) setStatus({ key: ERROR_KEYS[message], isError: true });
        else if (message) setStatus({ text: message, isError: true });
        else setStatus({ key: "failed", isError: true });
        return;
      }
      setStatus(null);
      lastAnswer = body;
      showAnswer(body);
    } catch (error) {
      setStatus({ key: "unreachable", isError: true });
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

  applyLanguage(lang);

  fetch(`${API}/api/documents`)
    .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
    .then((list) => {
      documents = list;
      showDocuments();
    })
    .catch(() => {
      documents = false;
      showDocuments();
    });
})();
