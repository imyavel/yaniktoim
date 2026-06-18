/* ya-edit.js — Ф8: правка ZML прямо на сайте.
 *
 * Модель (оператор 2026-06-18): на ZML-виде у залогиненного editor/admin кнопка
 * «✎ Править» ЗАМЕНЯЕТ просмотр статьи простым текстовым редактором ZML. Кнопки:
 *   • Просмотр  — рендер правки в браузере тем же render.js, что и build_views.mjs
 *                 (один код + те же данные из /editor/ → байт-в-байт совпадает),
 *                 показ в iframe.
 *   • Сохранить — рендер → POST /api/save: Worker коммитит docs/art/<art>.zml +
 *                 docs/art/<art>.view.html. Затем popup «обновится через ~N сек».
 *   • Отмена    — выход без сохранения (с подтверждением при несохранённых правках).
 *
 * Аноним/pending кнопку не видит активной (остаётся disabled). Зависимости рендера
 * (render.js + manifest/zohar/proper-nouns/шаблон/site) тянутся лениво из /editor/.
 */
(function () {
  "use strict";
  var body = document.body;
  if (!body || !body.classList.contains("article-page")) return;
  var btn = document.querySelector(".viewbar .vb-edit");
  if (!btn) return;

  var ART = body.getAttribute("data-art") || "";
  var WORKER = (body.getAttribute("data-worker") || "").replace(/\/+$/, "");

  function getSession() {
    try { return JSON.parse(localStorage.getItem("ya_session") || "null"); }
    catch (e) { return null; }
  }
  var sess = getSession();
  var canEdit = !!(sess && sess.token && (sess.role === "editor" || sess.role === "admin"));
  if (!canEdit) return; // кнопка остаётся disabled (только просмотр)

  btn.disabled = false;
  btn.removeAttribute("aria-disabled");
  btn.title = "Редактировать ZML-источник";
  btn.addEventListener("click", openEditor);

  // ── ленивые зависимости рендера (грузятся 1 раз при первом открытии) ──────────
  var deps = null;
  function loadDeps() {
    if (deps) return Promise.resolve(deps);
    var base = "../editor/";
    return Promise.all([
      import(base + "render.js"),
      fetch(base + "data/manifest.json").then(j),
      fetch(base + "data/zohar_index.json").then(j),
      fetch(base + "data/proper-nouns.txt").then(t),
      fetch(base + "data/template_view.html").then(t),
      fetch(base + "data/site.json").then(j),
      fetch("../config/display.json").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
    ]).then(function (a) {
      var manifest = a[1], byArt = {};
      manifest.forEach(function (r) { byArt[r.art] = r; });
      deps = {
        render: a[0].renderArticleHtml, manifest: manifest, byArt: byArt,
        zoharIndex: a[2], properNouns: a[3], template: a[4], siteConfig: a[5], displayConfig: a[6]
      };
      return deps;
    });
    function j(r) { if (!r.ok) throw new Error(r.url + " → " + r.status); return r.json(); }
    function t(r) { if (!r.ok) throw new Error(r.url + " → " + r.status); return r.text(); }
  }

  function renderView(zml) {
    var rec = deps.byArt[ART] ||
      { art: ART, section: body.getAttribute("data-art-section") || "other", title: "", url: "" };
    return deps.render({
      zml: zml, rec: rec, manifest: deps.manifest, manifestByArt: deps.byArt,
      zoharIndex: deps.zoharIndex, template: deps.template,
      properNouns: deps.properNouns, displayConfig: deps.displayConfig, siteConfig: deps.siteConfig
    });
  }

  // ── UI ────────────────────────────────────────────────────────────────────────
  var ui = null, original = "";

  function openEditor() {
    btn.disabled = true;
    fetch(ART + ".zml", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("ZML " + r.status); return r.text(); })
      .then(function (zml) { return loadDeps().then(function () { return zml; }); })
      .then(buildUI)
      .catch(function (e) { toast("Не удалось открыть редактор: " + e.message, true); btn.disabled = false; });
  }

  function buildUI(zml) {
    injectStyles();
    original = zml;
    ui = document.createElement("div");
    ui.id = "ze-root";
    ui.innerHTML =
      '<div class="ze-bar">' +
        '<span class="ze-title">Правка ZML · #' + esc(ART) + '</span>' +
        '<span class="ze-spacer"></span>' +
        '<button type="button" class="ze-btn" data-act="preview">Просмотр</button>' +
        '<button type="button" class="ze-btn ze-hidden" data-act="back">← Редактировать</button>' +
        '<button type="button" class="ze-btn ze-primary" data-act="save">Сохранить</button>' +
        '<button type="button" class="ze-btn" data-act="cancel">Отмена</button>' +
      '</div>' +
      '<div class="ze-body">' +
        '<textarea class="ze-text" spellcheck="false" wrap="soft"></textarea>' +
        '<iframe class="ze-prev ze-hidden" title="Просмотр"></iframe>' +
      '</div>' +
      '<div class="ze-status" aria-live="polite"></div>';
    document.body.appendChild(ui);
    document.documentElement.classList.add("ze-lock");

    var ta = ui.querySelector(".ze-text");
    var iframe = ui.querySelector(".ze-prev");
    ta.value = zml;
    ta.focus();

    ui.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-act]"); if (!b) return;
      var act = b.getAttribute("data-act");
      if (act === "preview") showPreview(ta, iframe);
      else if (act === "back") showEditor(ta, iframe);
      else if (act === "save") doSave(ta);
      else if (act === "cancel") doCancel(ta);
    });
    document.addEventListener("keydown", escClose);
  }

  function showPreview(ta, iframe) {
    var html;
    try { html = renderView(ta.value); }
    catch (e) { status("Ошибка рендера: " + e.message, true); return; }
    iframe.srcdoc = html;             // srcdoc → относительные ../themes,../img резолвятся от родителя
    iframe.classList.remove("ze-hidden");
    ta.classList.add("ze-hidden");
    toggle("preview", false); toggle("back", true);
    status("");
  }
  function showEditor(ta, iframe) {
    iframe.classList.add("ze-hidden"); ta.classList.remove("ze-hidden");
    toggle("preview", true); toggle("back", false);
    ta.focus();
  }

  function doSave(ta) {
    if (!WORKER) { status("Не задан адрес Worker (data-worker) — сохранение недоступно.", true); return; }
    var zml = ta.value, html;
    try { html = renderView(zml); }
    catch (e) { status("Не сохраняю — ошибка рендера: " + e.message, true); return; }
    status("Сохранение…");
    setBusy(true);
    fetch(WORKER + "/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + sess.token },
      body: JSON.stringify({ art: ART, zml: zml, html: html, branch: "main" })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        setBusy(false);
        if (!res.ok || !res.d.ok) throw new Error((res.d && res.d.error) || "HTTP-ошибка");
        original = zml;            // сохранено → нет «несохранённых правок»
        savedPopup();
      })
      .catch(function (e) { setBusy(false); status("Сохранение не удалось: " + e.message, true); });
  }

  function doCancel(ta) {
    if (ta.value !== original) { confirmModal("Отменить несохранённые изменения?", closeEditor); return; }
    closeEditor();
  }
  function escClose(ev) {
    if (ev.key === "Escape" && ui) { var ta = ui.querySelector(".ze-text"); if (ta && ta.value !== original) return; closeEditor(); }
  }

  function closeEditor() {
    document.removeEventListener("keydown", escClose);
    document.documentElement.classList.remove("ze-lock");
    if (ui && ui.parentNode) ui.parentNode.removeChild(ui);
    ui = null;
    btn.disabled = false;
  }

  // popup после успешного сохранения: возврат на статью + инструкция обновить
  function savedPopup() {
    var pop = document.createElement("div");
    pop.id = "ze-pop";
    pop.innerHTML =
      '<div class="ze-pop-card">' +
        '<p><b>Изменения сохранены.</b></p>' +
        '<p>Обновление сайта обычно занимает <b>30–90 секунд</b>. После этого нажмите ' +
        '<kbd>Ctrl</kbd>+<kbd>R</kbd> (или <kbd>F5</kbd>), чтобы увидеть результат.</p>' +
        '<div class="ze-pop-row">' +
          '<button type="button" class="ze-btn" data-pop="stay">Остаться в правке</button>' +
          '<button type="button" class="ze-btn ze-primary" data-pop="ok">На статью</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(pop);
    pop.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-pop]"); if (!b) return;
      pop.parentNode.removeChild(pop);
      if (b.getAttribute("data-pop") === "ok") closeEditor();
    });
  }

  // DOM-модалка подтверждения (вместо нативного confirm — он блокирует рендерер).
  function confirmModal(msg, onYes) {
    injectStyles();
    var m = document.createElement("div");
    m.id = "ze-pop";
    m.innerHTML = '<div class="ze-pop-card"><p>' + esc(msg) + '</p>' +
      '<div class="ze-pop-row">' +
        '<button type="button" class="ze-btn" data-c="no">Нет</button>' +
        '<button type="button" class="ze-btn ze-primary" data-c="yes">Да</button>' +
      '</div></div>';
    document.body.appendChild(m);
    m.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-c]"); if (!b) return;
      var yes = b.getAttribute("data-c") === "yes";
      m.parentNode.removeChild(m);
      if (yes) onYes();
    });
  }

  // не-блокирующий тост (для ошибок до открытия редактора)
  function toast(msg, err) {
    injectStyles();
    var el = document.createElement("div");
    el.className = "ze-toast" + (err ? " ze-err" : "");
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () { el.classList.add("ze-show"); }, 10);
    setTimeout(function () {
      el.classList.remove("ze-show");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }, 4000);
  }

  // ── helpers ─────────────────────────────────────────────────────────────────
  function toggle(act, show) {
    var b = ui.querySelector('[data-act="' + act + '"]');
    if (b) b.classList.toggle("ze-hidden", !show);
  }
  function setBusy(on) {
    ui.querySelectorAll(".ze-btn").forEach(function (b) { b.disabled = on; });
  }
  function status(msg, err) {
    var s = ui.querySelector(".ze-status");
    s.textContent = msg || "";
    s.classList.toggle("ze-err", !!err);
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function injectStyles() {
    if (document.getElementById("ze-style")) return;
    var st = document.createElement("style");
    st.id = "ze-style";
    st.textContent =
      "html.ze-lock,html.ze-lock body{overflow:hidden!important;}" +
      "#ze-root{position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;" +
        "background:#1e1e1e;color:#e6e6e6;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;}" +
      "#ze-root .ze-bar{display:flex;align-items:center;gap:.5em;padding:.55em .8em;" +
        "background:#2a2a2a;border-bottom:1px solid #000;flex:0 0 auto;}" +
      "#ze-root .ze-title{font-weight:600;letter-spacing:.02em;}" +
      "#ze-root .ze-spacer{flex:1 1 auto;}" +
      "#ze-root .ze-btn{font:inherit;color:#e6e6e6;background:#3a3a3a;border:1px solid #555;" +
        "border-radius:5px;padding:.35em .9em;cursor:pointer;}" +
      "#ze-root .ze-btn:hover{background:#454545;}" +
      "#ze-root .ze-btn:disabled{opacity:.5;cursor:default;}" +
      "#ze-root .ze-primary{background:#2d6cdf;border-color:#2d6cdf;color:#fff;}" +
      "#ze-root .ze-primary:hover{background:#3a78ea;}" +
      "#ze-root .ze-body{flex:1 1 auto;min-height:0;display:flex;}" +
      "#ze-root .ze-text{flex:1 1 auto;width:100%;border:0;resize:none;outline:none;" +
        "background:#1e1e1e;color:#e6e6e6;padding:1em 1.1em;" +
        "font:14px/1.6 ui-monospace,SFMono-Regular,Consolas,'Liberation Mono',monospace;" +
        "tab-size:2;white-space:pre-wrap;}" +
      "#ze-root .ze-prev{flex:1 1 auto;width:100%;border:0;background:#fff;}" +
      "#ze-root .ze-status{flex:0 0 auto;min-height:1.2em;padding:.3em .9em;background:#2a2a2a;" +
        "border-top:1px solid #000;font-size:.86em;color:#9bd39b;}" +
      "#ze-root .ze-status.ze-err{color:#ff8a8a;}" +
      "#ze-root .ze-hidden{display:none!important;}" +
      "#ze-pop{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;" +
        "justify-content:center;background:rgba(0,0,0,.5);}" +
      "#ze-pop .ze-pop-card{max-width:420px;margin:1em;background:#fff;color:#222;border-radius:10px;" +
        "padding:1.3em 1.5em;box-shadow:0 12px 40px rgba(0,0,0,.35);" +
        "font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;}" +
      "#ze-pop p{margin:0 0 .7em;}" +
      "#ze-pop kbd{background:#eee;border:1px solid #ccc;border-radius:4px;padding:0 .35em;font-size:.9em;}" +
      "#ze-pop .ze-pop-row{display:flex;gap:.6em;justify-content:flex-end;margin-top:1em;}" +
      "#ze-pop .ze-btn{font:inherit;border-radius:6px;padding:.4em 1em;cursor:pointer;border:1px solid #bbb;background:#f3f3f3;color:#222;}" +
      "#ze-pop .ze-primary{background:#2d6cdf;border-color:#2d6cdf;color:#fff;}" +
      ".ze-toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,16px);z-index:10001;" +
        "max-width:80vw;background:#2a2a2a;color:#e6e6e6;border:1px solid #555;border-radius:8px;" +
        "padding:.7em 1.1em;box-shadow:0 8px 30px rgba(0,0,0,.4);opacity:0;transition:opacity .25s,transform .25s;" +
        "font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;}" +
      ".ze-toast.ze-show{opacity:1;transform:translate(-50%,0);}" +
      ".ze-toast.ze-err{border-color:#a33;color:#ffb3b3;}";
    document.head.appendChild(st);
  }
})();
