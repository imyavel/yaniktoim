/* ya-edit.js — Ф8: правка ZML прямо на сайте.
 *
 * На ZML-виде у залогиненного editor/admin кнопка «✎ Править» открывает общий
 * оверлей-редактор (ze-core.js). Его «Просмотр» рендерит правку тем же
 * render.js, что и build_views.mjs (один код + те же данные из /editor/ →
 * байт-в-байт), «Сохранить» → POST /api/save (Worker коммитит
 * docs/art/<art>.zml + docs/art/<art>.html — единый адрес). Аноним/pending
 * кнопку не видят активной. Зависимости рендера тянутся лениво из /editor/.
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
  if (!canEdit) return; // кнопка скрыта (hidden в шаблоне) — аноним/не-редактор её не видят

  btn.hidden = false;   // показываем только editor/admin
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
      fetch("../config/display.json").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      import(modUrl("editor/faw_markup.js"))   // авто-разметка [faw] на «Сохранить»
    ]).then(function (a) {
      var manifest = a[1], byArt = {};
      manifest.forEach(function (r) { byArt[r.art] = r; });
      deps = {
        render: a[0].renderArticleHtml, manifest: manifest, byArt: byArt,
        zoharIndex: a[2], properNouns: a[3], template: a[4], siteConfig: a[5], displayConfig: a[6],
        fawMarkup: a[7].autoMarkupFaw
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
    import(modUrl("ze-core.js"))
      .then(function (mod) {
        // Перед правкой проверяем, что логин не протух (TTL сессии 12 ч). Протух/нет —
        // ze-core покажет модальный вход; открываем редактор ТОЛЬКО при успехе, уже
        // свежим токеном. Отмена входа → редактор не открываем.
        return mod.ensureFreshSession({ worker: WORKER }).then(function (fresh) {
          if (!fresh) { btn.disabled = false; return; }
          sess = fresh;   // обновлённый токен — saveToWorker берёт его в момент сохранения
          return fetch(ART + ".zml", { cache: "no-store" })
            .then(function (r) { if (!r.ok) throw new Error("ZML " + r.status); return r.text(); })
            .then(function (zml) { return loadDeps().then(function () { return zml; }); })
            .then(function (zml) {
              mod.mountZmlEditor({
                label: "Правка ZML · #" + ART,
                initialZml: ensureViewZml(zml),
                renderView: renderView,
                preprocess: deps.fawMarkup,   // [faw] без «|» → разметка по слогам перед сохранением
                save: saveToWorker,
                image: { artId: ART },     // Ф8(b): блок «Иллюстрация» (image: + бинарь)
                savedPrimaryLabel: "На статью",
                onClosed: function () { btn.disabled = false; }
              });
            });
        });
      })
      .catch(function (e) {
        btn.disabled = false;
        alert("Не удалось открыть редактор: " + (e.message || e));
      });
  }

  // url-unification: `view:`/forced_views упразднены — у статьи один адрес NNN.html,
  // вид резолвится в рантайме. Редактор больше НЕ дописывает `view:` во фронтматтер.
  // Оставляем лишь нормализацию CRLF→LF (корпус в CRLF; baseline ze-core/textarea —
  // в LF), имя функции и место вызова не трогаем.
  function ensureViewZml(zml) {
    return String(zml == null ? "" : zml).replace(/\r\n/g, "\n");
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
        span.innerHTML = '<a href="' + rec.art + '.html">' + (dir < 0 ? "← " + t : t + " →") + "</a>";
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
