/* ya-edit.js — Ф8: правка ZML прямо на сайте.
 *
 * На ZML-виде у залогиненного editor/admin кнопка «✎ Править» открывает общий
 * оверлей-редактор (ze-core.js). Его «Просмотр» рендерит правку тем же
 * render.js, что и build_views.mjs (один код + те же данные из /editor/ →
 * байт-в-байт), «Сохранить» → POST /api/save (Worker коммитит
 * docs/art/<art>.zml + docs/art/<art>.view.html). Аноним/pending кнопку не
 * видят активной. Зависимости рендера тянутся лениво из /editor/.
 */
(function () {
  "use strict";
  // Динамический import() в классическом скрипте резолвится от URL САМОГО скрипта
  // (ya-edit.js лежит в docs/ → на проде это /yaniktoim/ya-edit.js), НЕ от документа.
  // Поэтому модули (editor/render.js, ze-core.js) резолвим абсолютно от src этого
  // скрипта — иначе на под-пути «../» вылетает из /yaniktoim/ в корень (Failed to
  // fetch .../editor/render.js). fetch() ниже остаётся document-relative — он верно
  // резолвится от страницы в docs/art/.
  var SELF = document.currentScript || document.querySelector('script[src*="ya-edit.js"]');
  var SELF_SRC = SELF ? SELF.src : new URL("ya-edit.js", document.baseURI).href;
  var modUrl = function (p) { return new URL(p, SELF_SRC).href; };
  var body = document.body;
  if (!body || !body.classList.contains("article-page")) return;

  var ART = body.getAttribute("data-art") || "";
  var WORKER = (body.getAttribute("data-worker") || "").replace(/\/+$/, "");

  // Ф10: prev/next в подвале ZML-вида пересчитываем из ЖИВОГО structure.json — для
  // ВСЕХ читателей (запускаем до гейта прав). Подвал запекается на сборке из manifest
  // (render.js::siblings), но структуру правят на сайте (вставка/удаление/перемещение/
  // reorder), и manifest при этом не меняется → запечённые ссылки устаревают. Здесь
  // берём раздел+порядок из structure.json (только не-archived), заголовки — из
  // manifest (фолбэк: запись structure / art-id). Касается только .view.html.
  refreshSiblings();

  var btn = document.querySelector(".viewbar .vb-edit");
  if (!btn) return;

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
      import(modUrl("editor/render.js")),
      fetch(base + "data/manifest.json").then(j),
      fetch(base + "data/zohar_index.json").then(j),
      fetch(base + "data/proper-nouns.txt").then(t),
      fetch(base + "data/template_view.html", { cache: "no-store" }).then(t),
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

  // ── открытие: загрузить ZML + зависимости + ze-core, смонтировать редактор ─────
  function openEditor() {
    btn.disabled = true;
    fetch(ART + ".zml", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("ZML " + r.status); return r.text(); })
      .then(function (zml) { return loadDeps().then(function () { return zml; }); })
      .then(function (zml) {
        return import(modUrl("ze-core.js")).then(function (mod) {
          mod.mountZmlEditor({
            label: "Правка ZML · #" + ART,
            initialZml: ensureViewZml(zml),
            renderView: renderView,
            save: saveToWorker,
            image: { artId: ART },     // Ф8(b): блок «Иллюстрация» (image: + бинарь)
            savedPrimaryLabel: "На статью",
            onClosed: function () { btn.disabled = false; }
          });
        });
      })
      .catch(function (e) {
        btn.disabled = false;
        alert("Не удалось открыть редактор: " + (e.message || e));
      });
  }

  // Ф8(d): правка статьи делает её ZML-приоритетной. При ОТКРЫТИИ редактора в
  // frontmatter дописывается `view: zml` (если строки `view:` ещё нет) — она
  // видна в textarea. На сайт это попадает только по «Сохранить»: Worker
  // отразит `view:` в docs/config/forced_views.json тем же коммитом → статья
  // показывается как ZML даже при глобальном default_view=old. Оператор может
  // удалить строку в textarea (статья вернётся к общему умолчанию) или сменить
  // на `view: html` (форсировать старую) — существующий `view:` мы НЕ трогаем.
  // baseline в ze-core берётся из этого же initialZml → открыть+Отмена не считается
  // «грязным» (вставка применяется лишь при реальном Сохранении).
  function ensureViewZml(zml) {
    // Корпус хранится в CRLF — нормализуем в LF (как ze-core делает с baseline:
    // textarea всё равно нормализует, на сохранение уходит LF), иначе `^---\n` не
    // сматчит `---\r\n` и frontmatter задвоится.
    var text = String(zml == null ? "" : zml).replace(/\r\n/g, "\n");
    var m = /^---\n([\s\S]*?)\n---\n?/.exec(text);
    if (!m) return "---\nview: zml\n---\n" + text.replace(/^\n+/, "");
    var inner = m[1];
    if (/^[ \t]*view[ \t]*:/m.test(inner)) return text;   // уже задано — уважаем выбор
    inner = inner.replace(/\s+$/, "") + "\nview: zml";
    return "---\n" + inner + "\n---\n" + text.slice(m[0].length);
  }

  // Пересчёт prev/next из живого structure.json (см. вызов выше). Read-only, без прав.
  function refreshSiblings() {
    var navPrev = document.querySelector(".article-nav .prev");
    var navNext = document.querySelector(".article-nav .next");
    if (!navPrev && !navNext) return;
    if (!ART) return;
    Promise.all([
      fetch("../config/structure.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }),
      fetch("../editor/data/manifest.json").then(function (r) { return r.ok ? r.json() : null; })
    ]).then(function (a) {
      var st = a[0]; if (!st || !Array.isArray(st.articles)) return;
      var titleByArt = {};
      (a[1] || []).forEach(function (r) { titleByArt[r.art] = r.title || ""; });
      var me = st.articles.find(function (x) { return x.art === ART && x.status !== "archived"; });
      if (!me) return;                       // статья архивирована/не в structure — не трогаем запечённое
      var sibs = st.articles
        .filter(function (x) { return x.section === me.section && x.status !== "archived"; })
        .sort(function (x, y) { return (x.order - y.order) || (x.art < y.art ? -1 : 1); });
      var idx = sibs.findIndex(function (x) { return x.art === ART; });
      if (idx < 0) return;
      function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }
      function ttl(rec) { return titleByArt[rec.art] || rec.title || rec.art; }
      function fill(span, rec, dir) {
        if (!span) return;
        if (!rec) { span.innerHTML = ""; return; }
        var t = esc(ttl(rec));
        span.innerHTML = '<a href="' + rec.art + '.view.html">' + (dir < 0 ? "← " + t : t + " →") + "</a>";
      }
      fill(navPrev, idx > 0 ? sibs[idx - 1] : null, -1);
      fill(navNext, idx < sibs.length - 1 ? sibs[idx + 1] : null, 1);
    }).catch(function () { /* офлайн/ошибка → остаётся запечённый prev/next */ });
  }

  function saveToWorker(zml, html, extras) {
    if (!WORKER) return Promise.reject(new Error("не задан адрес Worker (data-worker)"));
    var payload = { art: ART, zml: zml, html: html, branch: "main" };
    // Ф8(b): если выбрана новая/заменённая картинка — кладём её бинарь в тот же коммит.
    if (extras && extras.image) payload.image = { name: extras.image.name, content: extras.image.content };
    return fetch(WORKER + "/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + sess.token },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) { if (!res.ok || !res.d.ok) throw new Error((res.d && res.d.error) || "HTTP-ошибка"); });
  }
})();
