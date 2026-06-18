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
        return import("../ze-core.js").then(function (mod) {
          mod.mountZmlEditor({
            label: "Правка ZML · #" + ART,
            initialZml: zml,
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
