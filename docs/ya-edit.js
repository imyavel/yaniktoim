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
  var ASSET_VER = "20260627-06";   // бастит кэш динамических модулей (ze-core/render) при правках
  var modUrl = function (p) {
    return new URL(p + (p.indexOf("?") < 0 ? "?v=" + ASSET_VER : ""), SELF_SRC).href;
  };
  var body = document.body;
  if (!body || !body.classList.contains("article-page")) return;

  var ART = body.getAttribute("data-art") || "";
  var WORKER = (body.getAttribute("data-worker") || "").replace(/\/+$/, "");

  // «Старый» вид (6-й дизайн) ЗАФИКСИРОВАН и НЕ должен пропадать при правке через
  // сайт. Браузер рендерит без доступа к cms-revival/legacy_html/ (его читает только
  // build_views) → раньше {{LEGACY_BODY}} уходил пустым и опция «оригинал (старый)»
  // отваливалась до следующей полной пересборки (roadmap_url_unification §70). Снимаем
  // уже готовый legacy-оверлей из ТЕКУЩЕЙ страницы (template#legacy-render) ОДИН раз при
  // загрузке и переносим его в каждый ре-рендер (Просмотр/Сохранение) как ctx.legacyBody.
  // Пусто (zml-only статья) → так и остаётся пусто (опция скрыта) — поведение то же.
  // Захват ленивый (в openEditor), чтобы не платить сериализацией .innerHTML на каждой
  // загрузке у читателей; на момент открытия DOM ещё оригинальный (template на месте).
  var LEGACY_BODY = "";

  // Ф10: prev/next в подвале ZML-вида пересчитываем из ЖИВОГО structure.json — для
  // ВСЕХ читателей (запускаем до гейта прав). Подвал запекается на сборке из manifest
  // (render.js::siblings), но структуру правят на сайте (вставка/удаление/перемещение/
  // reorder), и manifest при этом не меняется → запечённые ссылки устаревают. Здесь
  // берём раздел+порядок из structure.json (только не-archived), заголовки — из
  // manifest (фолбэк: запись structure / art-id). Касается только .view.html.
  refreshSiblings();

  var btn = document.querySelector(".viewbar .vb-edit");
  if (!btn) return;

  // Постоянного логина на сайте НЕТ: кнопка «Править» видна ВСЕМ, вход спрашиваем
  // по клику (ze-core.loginModal). Сессия эфемерная — живёт весь цикл правки
  // (правка↔просмотр) и стирается по закрытию редактора (dropSession).
  var sess = null;
  btn.hidden = false;
  btn.disabled = false;
  btn.removeAttribute("aria-disabled");
  btn.title = "Редактировать ZML-источник (нужен вход)";
  btn.addEventListener("click", openEditor);

  function dropSession() {
    sess = null;
    try { localStorage.removeItem("ya_session"); } catch (e) {}
  }

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
      properNouns: deps.properNouns, displayConfig: deps.displayConfig, siteConfig: deps.siteConfig,
      legacyBody: LEGACY_BODY   // переносим зафиксированный «старый» вид (не теряем при правке)
    });
  }

  // Дата индикативна (закодирована в art-id и имени файла) → у сохранённой статьи
  // заморожена: ze-core зовёт checkIdentity на превью И сохранении (см. mount ниже).
  function fmDateField(zml) {
    var m = String(zml || "").match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!m) return null;
    var lines = m[1].split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      if (/^date\s*:/.test(lines[i])) return lines[i].replace(/^date\s*:/, "").trim();
    }
    return "";
  }
  // Авто-починка: вернуть в шапку прежнее значение date. value="" → убрать строку date;
  // иначе заменить значение (или добавить строку, если её не было). Концы строк сохраняем.
  function setFmDateField(zml, value) {
    var s = String(zml);
    var m = s.match(/^(---\r?\n)([\s\S]*?)(\r?\n---)/);
    if (!m) return zml;
    var nl = m[2].indexOf("\r\n") >= 0 ? "\r\n" : "\n";
    var lines = m[2].split(/\r?\n/), hasDate = false;
    for (var i = 0; i < lines.length; i++) {
      if (/^date\s*:/.test(lines[i])) {
        hasDate = true;
        if (value === "") { lines.splice(i, 1); i--; }
        else lines[i] = "date: " + value;
      }
    }
    if (!hasDate && value) lines.push("date: " + value);
    return m[1] + lines.join(nl) + m[3] + s.slice(m[0].length);
  }

  // ── открытие: загрузить ZML + зависимости + ze-core, смонтировать редактор ─────
  function openEditor() {
    btn.disabled = true;
    // снять зафиксированный «старый» вид с текущей (ещё оригинальной) страницы
    var _lt = document.getElementById("legacy-render");
    if (_lt) LEGACY_BODY = _lt.innerHTML;
    import(modUrl("ze-core.js"))
      .then(function (mod) {
        // Вход по клику: модальное окно. Открываем редактор ТОЛЬКО при успешном
        // входе с правом записи. Отмена/Esc → редактор не открываем.
        return mod.loginModal({
          worker: WORKER, title: "Правка статьи",
          message: "Войдите, чтобы редактировать.",
        }).then(function (s) {
          if (!s || !s.token) { btn.disabled = false; return; }
          if (s.role !== "editor" && s.role !== "admin") {
            btn.disabled = false; dropSession();
            alert("У этой учётки нет прав на правку (роль: " + (s.role || "—") + ").");
            return;
          }
          sess = s;   // токен — saveToWorker берёт его в момент сохранения
          return fetch(ART + ".zml", { cache: "no-store" })
            .then(function (r) { if (!r.ok) throw new Error("ZML " + r.status); return r.text(); })
            .then(function (zml) { return loadDeps().then(function () { return zml; }); })
            .then(function (zml) {
              mod.mountZmlEditor({
                label: "Правка ZML · #" + ART,
                initialZml: ensureViewZml(zml),
                renderView: renderView,
                preprocess: function (src) {   // [faw]-разметка + проставить editor:<ник> (контракт «Редакция»)
                  return setFmEditor(deps.fawMarkup(src), sess && sess.nick);
                },
                save: saveToWorker,
                checkIdentity: function (curZml, baseZml) {   // заморозка date у сохранённой статьи
                  var was = fmDateField(baseZml), now = fmDateField(curZml);
                  if (was === now) return null;
                  return {
                    message: "Дату у сохранённой статьи менять нельзя — она индикативна "
                           + "(закодирована в id и имени файла). Возвращаю прежнее значение"
                           + (was ? ": " + was : "") + ".",
                    fix: function (zml) { return setFmDateField(zml, was); }
                  };
                },
                image: { artId: ART },     // Ф8(b): блок «Иллюстрация» (image: + бинарь)
                savedPrimaryLabel: "На статью",
                // после сохранения ждём, пока боевая страница статьи начнёт отдавать СВЕЖИЙ
                // html (тот, что закоммитили), и сами её обновляем — без ручного Ctrl+R.
                deployWait: function (zml, html) {
                  return {
                    url: location.origin + location.pathname,
                    match: function (text) { return text === html; },
                    onReady: function () { location.reload(); }
                  };
                },
                onClosed: function () { btn.disabled = false; dropSession(); }   // логин не сохраняется
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

  // Контракт «Редакция»: дефолт-редактор «Иван Иванович» (= собрано ИИ) меняется на
  // ник вошедшего при реальной правке. Прописываем/обновляем строку `editor:` во
  // frontmatter (render.js берёт fm.editor → подвал «Редакция: <ник>»). Текст в LF
  // (textarea-baseline ze-core), коммит-нормализация дальше по конвейеру.
  function setFmEditor(text, nick) {
    nick = String(nick == null ? "" : nick).trim();
    if (!nick) return text;
    var m = /^---\n([\s\S]*?)\n---\n?/.exec(text);
    if (!m) return "---\neditor: " + nick + "\n---\n" + text.replace(/^\n+/, "");
    var inner = m[1];
    if (/^[ \t]*editor[ \t]*:.*$/m.test(inner)) {
      inner = inner.replace(/^[ \t]*editor[ \t]*:.*$/m, "editor: " + nick);
    } else {
      inner = inner.replace(/\s+$/, "") + "\neditor: " + nick;
    }
    return "---\n" + inner + "\n---\n" + text.slice(m[0].length);
  }

  // Пересчёт prev/next из живого structure.json (см. вызов выше). Read-only, без прав.
  function refreshSiblings() {
    var navPrev = document.querySelector(".article-nav .prev");
    var navNext = document.querySelector(".article-nav .next");
    var topPrev = document.querySelector(".topnav .tn-prev");
    var topNext = document.querySelector(".topnav .tn-next");
    if (!navPrev && !navNext && !topPrev && !topNext) return;
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
      // Крошка раздела из ЖИВОГО structure.json: статью могли перенести в другой раздел
      // (запечённый href/имя ведут на старый до полной пересборки), а SECTION_NAME вообще
      // из хардкода SECTION_HUMAN (для кастомных разделов = слаг). Чиним для всех читателей.
      var secIco = document.querySelector(".topnav .tn-section");
      if (secIco && me.section) {
        var secRec = (st.sections || []).find(function (x) { return x.slug === me.section; });
        var secName = (secRec && secRec.name) || me.section;
        secIco.setAttribute("href", "../" + me.section + "/index.html");
        secIco.setAttribute("title", "Раздел: " + secName);
        secIco.setAttribute("aria-label", "Раздел: " + secName);
      }
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
      // верхняя панель: иконки prev/next (только href; нет соседа → прячем)
      function fillIco(a, rec) {
        if (!a) return;
        if (rec) { a.setAttribute("href", rec.art + ".html"); a.hidden = false; }
        else { a.removeAttribute("href"); a.hidden = true; }
      }
      fillIco(topPrev, idx > 0 ? sibs[idx - 1] : null);
      fillIco(topNext, idx < sibs.length - 1 ? sibs[idx + 1] : null);
    }).catch(function () { /* офлайн/ошибка → остаётся запечённый prev/next */ });
  }

  function saveToWorker(zml, html, extras) {
    if (!WORKER) return Promise.reject(new Error("не задан адрес Worker (data-worker)"));
    var payload = { art: ART, zml: zml, html: html, branch: "main" };
    // Ф8(b): если выбрана новая/заменённая обложка — кладём её бинарь в тот же коммит.
    if (extras && extras.image) payload.image = { name: extras.image.name, content: extras.image.content };
    // Ф8(b2): картинки в тексте ([img]) — массив бинарей в тот же коммит.
    if (extras && extras.images && extras.images.length) {
      payload.images = extras.images.map(function (im) { return { name: im.name, content: im.content }; });
    }
    return fetch(WORKER + "/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + sess.token },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) { if (!res.ok || !res.d.ok) throw new Error((res.d && res.d.error) || "HTTP-ошибка"); });
  }
})();
