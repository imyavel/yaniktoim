/* ya-songs.js — Ф8(c): правка ZML спец-страницы «Песнь Ступеней» прямо на сайте.
 *
 * На songs/index.view.html у залогиненного editor/admin кнопка «✎ Править»
 * открывает общий оверлей-редактор (ze-core.js). Его «Просмотр» рендерит правку
 * тем же render.js::renderSongsHtml, что и build_songs.mjs (один код + те же
 * данные из /editor/ → байт-в-байт), «Сохранить» → POST /api/save с page:"songs"
 * (Worker коммитит docs/songs/index.zml + docs/songs/index.view.html). Живой
 * docs/songs/index.html НЕ трогается (cutover на Ф9). Аналог ya-edit.js.
 *
 * NB: правка меняет уже собранный index.zml напрямую. Источник генерации
 * (convert/gen_songs_zml.py + songs_overrides.json) при следующем прогоне
 * перезатрёт index.zml — ручные правки делать ПОСЛЕ генерации (или переносить
 * их в overrides). Документировано в roadmap_cms.md (п.3).
 */
(function () {
  "use strict";
  // Динамический import() в классическом скрипте резолвится от URL САМОГО скрипта
  // (ya-songs.js лежит в docs/ → на проде /yaniktoim/ya-songs.js), НЕ от документа.
  // Модули (editor/render.js, ze-core.js) резолвим абсолютно от src этого скрипта —
  // иначе на под-пути «../» из docs/songs/ вылетает из /yaniktoim/ в корень. fetch()
  // ниже остаётся document-relative (верно резолвится от страницы в docs/songs/).
  var SELF = document.currentScript || document.querySelector('script[src*="ya-songs.js"]');
  var SELF_SRC = SELF ? SELF.src : new URL("ya-songs.js", document.baseURI).href;
  var modUrl = function (p) { return new URL(p, SELF_SRC).href; };
  var body = document.body;
  if (!body || !body.classList.contains("songs-page-body")) return;
  var btn = document.querySelector(".viewbar .vb-edit");
  if (!btn) return;

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
  btn.title = "Редактировать ZML-источник «Песни Ступеней»";
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
      fetch(base + "data/template_songs.html", { cache: "no-store" }).then(t),
      fetch(base + "data/site.json").then(j),
      fetch("../config/display.json").then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
    ]).then(function (a) {
      var manifest = a[1], byArt = {};
      manifest.forEach(function (r) { byArt[r.art] = r; });
      deps = {
        renderSongs: a[0].renderSongsHtml, manifest: manifest, byArt: byArt,
        zoharIndex: a[2], properNouns: a[3], template: a[4], siteConfig: a[5], displayConfig: a[6]
      };
      return deps;
    });
    function j(r) { if (!r.ok) throw new Error(r.url + " → " + r.status); return r.json(); }
    function t(r) { if (!r.ok) throw new Error(r.url + " → " + r.status); return r.text(); }
  }

  function renderView(zml) {
    var rec = { art: "songs", section: "", title: "Песнь Ступеней", url: "" };
    return deps.renderSongs({
      zml: zml, rec: rec, manifest: deps.manifest, manifestByArt: deps.byArt,
      zoharIndex: deps.zoharIndex, properNouns: deps.properNouns,
      template: deps.template, artHrefBase: "../art/", siteConfig: deps.siteConfig,
      displayConfig: deps.displayConfig
    });
  }

  // ── открытие: загрузить ZML + зависимости + ze-core, смонтировать редактор ─────
  function openEditor() {
    btn.disabled = true;
    fetch("index.zml", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("ZML " + r.status); return r.text(); })
      .then(function (zml) { return loadDeps().then(function () { return zml; }); })
      .then(function (zml) {
        return import(modUrl("ze-core.js")).then(function (mod) {
          mod.mountZmlEditor({
            label: "Правка ZML · Песнь Ступеней",
            initialZml: zml,
            renderView: renderView,
            save: saveSongs,
            savedPrimaryLabel: "На страницу",
            onClosed: function () { btn.disabled = false; }
          });
        });
      })
      .catch(function (e) {
        btn.disabled = false;
        alert("Не удалось открыть редактор: " + (e.message || e));
      });
  }

  function saveSongs(zml, html) {
    if (!WORKER) return Promise.reject(new Error("не задан адрес Worker (data-worker)"));
    return fetch(WORKER + "/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + sess.token },
      body: JSON.stringify({ page: "songs", zml: zml, html: html, branch: "main" })
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) { if (!res.ok || !res.d.ok) throw new Error((res.d && res.d.error) || "HTTP-ошибка"); });
  }
})();
