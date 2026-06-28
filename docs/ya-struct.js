/* ya-struct.js — Ф10: управление структурой (admin) на docs/structure.html.
 *
 * Операции: разделы — reorder (↑↓), rename, add, delete(пустой); статьи —
 * reorder в разделе, move в другой раздел, archive/restore (soft-delete,
 * «рукописи не горят»). Источник истины — docs/config/structure.json.
 *
 * Save: ренумерация порядков → регенерация главной + всех активных разделов в
 * браузере (тот же render.js, что и build_index.mjs) → один коммит через Worker
 * /api/commit (admin-only): structure.json + index.html + <slug>/index.html.
 *
 * ПРЕДЕЛ v1 (потом подправим): хлебные крошки внутри САМИХ статей (.view.html /
 * старый .html) при rename/move раздела не обновляются на лету — списки верны
 * сразу, страницы статей подтянут раздел при следующей полной пересборке.
 * Переименование ЗАГОЛОВКА статьи — через ZML-редактор «Править», не здесь.
 */
(function () {
  "use strict";
  var root = document.getElementById("struct-root");
  var sess;
  try { sess = JSON.parse(localStorage.getItem("ya_session") || "null"); } catch (e) {}
  if (!sess || !sess.token || sess.role !== "admin") {
    root.innerHTML = '<p>Управление структурой доступно только администратору.</p>' +
      '<p>Откройте через «Управление» внизу <a href="index.html">главной</a> → «Админка» → «Управление структурой».</p>';
    return;
  }

  var deps = {}, structure = null, byArt = {}, WORKER = "", expanded = {};
  var artDeps = null;

  Promise.all([
    import("./editor/render.js?v=20260628-01"),
    fetch("config/structure.json", { cache: "no-cache" }).then(j),   // свежий после авто-reload (не из кэша)
    fetch("editor/data/manifest.json").then(j),
    fetch("editor/data/template_index.tpl").then(t),
    fetch("editor/data/template_section.tpl").then(t),
    fetch("editor/data/site.json").then(j).catch(function () { return {}; }),
    fetch("config/display.json").then(j).catch(function () { return {}; })
  ]).then(function (a) {
    deps.renderIndexHtml = a[0].renderIndexHtml;
    deps.renderSectionIndexHtml = a[0].renderSectionIndexHtml;
    deps.renderArticle = a[0].renderArticleHtml;
    structure = a[1];
    deps.manifestArr = a[2];
    a[2].forEach(function (r) { byArt[r.art] = r; });
    deps.tplIndex = a[3];
    deps.tplSection = a[4];
    WORKER = ((a[5] && a[5].workerUrl) || "").replace(/\/+$/, "");
    deps.siteConfig = a[5] || {};
    deps.displayConfig = a[6] || {};
    render();
  }).catch(function (e) { root.innerHTML = '<p class="err">Ошибка загрузки: ' + esc(String(e.message || e)) + "</p>"; });

  function j(r) { if (!r.ok) throw new Error(r.url + " " + r.status); return r.json(); }
  function t(r) { if (!r.ok) throw new Error(r.url + " " + r.status); return r.text(); }

  // ── данные ──────────────────────────────────────────────────────────────────
  function activeSecs() {
    return structure.sections.filter(function (s) { return !s.archived; })
      .slice().sort(function (x, y) { return x.order - y.order; });
  }
  function secArticles(slug) {
    return structure.articles
      .filter(function (a) { return a.section === slug && a.status !== "archived"; })
      .sort(function (x, y) { return (x.order - y.order) || (x.art < y.art ? -1 : 1); });
  }
  function archivedArticles() {
    return structure.articles.filter(function (a) { return a.status === "archived"; });
  }
  // Имя в каталоге: запись structure приоритетна (переименование на сайте), иначе
  // manifest, иначе art-id — то же правило, что в render.js::renderSectionIndexHtml.
  function title(art) {
    var a = structure.articles.find(function (x) { return x.art === art; });
    if (a && a.title) return a.title;
    var r = byArt[art];
    return (r && r.title) || art;
  }

  // ── операции ──────────────────────────────────────────────────────────────
  function swapOrder(list, i, jdx) { var t0 = list[i].order; list[i].order = list[jdx].order; list[jdx].order = t0; }

  function moveSection(slug, dir) {
    var secs = activeSecs();
    var i = secs.findIndex(function (s) { return s.slug === slug; });
    var jdx = i + dir;
    if (jdx < 0 || jdx >= secs.length) return;
    swapOrder(secs, i, jdx); render();
  }
  function renameSection(slug) {
    var s = structure.sections.find(function (x) { return x.slug === slug; });
    var nm = prompt("Новое имя раздела (слаг не меняется):", s.name);
    if (nm == null) return;
    nm = nm.trim(); if (nm) { s.name = nm; render(); }
  }
  function addSection() {
    var slug = prompt("Слаг нового раздела (латиница, строчные, напр. essays):", "");
    if (slug == null) return;
    slug = slug.trim().toLowerCase();
    if (!/^[a-z0-9_-]{2,30}$/.test(slug)) { alert("Слаг: 2–30 симв., a-z 0-9 _ -"); return; }
    if (structure.sections.some(function (s) { return s.slug === slug; })) { alert("Такой слаг уже есть"); return; }
    var nm = prompt("Имя раздела:", ""); if (nm == null) return;
    nm = nm.trim(); if (!nm) return;
    var maxO = structure.sections.reduce(function (m, s) { return Math.max(m, s.order); }, -1);
    structure.sections.push({ slug: slug, name: nm, order: maxO + 1, archived: false });
    render();
  }
  function deleteSection(slug) {
    if (secArticles(slug).length) { alert("Раздел не пуст — сначала перенесите/архивируйте статьи."); return; }
    if (!confirmStr("Удалить раздел «" + (structure.sections.find(function (s) { return s.slug === slug; }) || {}).name + "»?")) return;
    structure.sections = structure.sections.filter(function (s) { return s.slug !== slug; });
    render();
  }
  function moveArticle(art, dir) {
    var a = structure.articles.find(function (x) { return x.art === art; });
    var list = secArticles(a.section);
    var i = list.findIndex(function (x) { return x.art === art; });
    var jdx = i + dir;
    if (jdx < 0 || jdx >= list.length) return;
    swapOrder(list, i, jdx); render();
  }
  function moveToSection(art, slug) {
    var a = structure.articles.find(function (x) { return x.art === art; });
    if (a.section === slug) return;
    a.section = slug;
    a.order = secArticles(slug).reduce(function (m, x) { return Math.max(m, x.order); }, -1) + 1;
    render();
  }
  function archiveArticle(art) {
    structure.articles.find(function (x) { return x.art === art; }).status = "archived";
    render();
  }
  // Переименование имени статьи В КАТАЛОГЕ (списки разделов). H1/ZML НЕ трогаем —
  // имя в каталоге намеренно «разнесено» с заголовком страницы. Имя живёт в записи
  // structure.json (a.title) и приоритетно в render; пустой ввод снимает override
  // (возврат к названию из manifest). Применится после «Сохранить».
  function renameArticle(art) {
    var a = structure.articles.find(function (x) { return x.art === art; });
    if (!a) return;
    var cur = a.title || (byArt[art] && byArt[art].title) || "";
    var nm = prompt("Название статьи в каталоге (заголовок H1 на странице не меняется).\n"
      + "Пусто — вернуть имя из корпуса:", cur);
    if (nm == null) return;
    nm = nm.trim();
    if (nm) a.title = nm; else delete a.title;   // пусто → снять переименование
    render();
  }
  function restoreArticle(art) {
    var a = structure.articles.find(function (x) { return x.art === art; });
    a.status = "published";
    a.order = secArticles(a.section).reduce(function (m, x) { return Math.max(m, x.order); }, -1) + 1;
    render();
  }

  // ── ренумерация (стабильные 0..n) перед сохранением ──────────────────────────
  function renumber() {
    activeSecs().forEach(function (s, i) { s.order = i; });
    activeSecs().forEach(function (s) {
      secArticles(s.slug).forEach(function (a, i) { a.order = i; });
    });
  }

  // ── рендер UI ────────────────────────────────────────────────────────────────
  function arrows(kind, id) {
    return '<span class="st-arrows"><button data-act="' + kind + '-up" data-id="' + esc(id) +
      '" title="Выше">↑</button><button data-act="' + kind + '-down" data-id="' + esc(id) + '" title="Ниже">↓</button></span>';
  }
  function render() {
    var secs = activeSecs();
    var secOpts = secs.map(function (s) { return s; });
    var html = '<div class="st-bar">' +
      '<button class="st-btn st-primary" data-act="save">Сохранить</button>' +
      '<button class="st-btn" data-act="reset">Сбросить</button>' +
      '<button class="st-btn" data-act="add-sec">+ Раздел</button>' +
      '<span class="sp"></span><span class="st-status" id="st-status"></span></div>';

    secs.forEach(function (s) {
      var arts = secArticles(s.slug);
      var open = !!expanded[s.slug];
      html += '<div class="st-sec"><div class="st-sec-hd">' +
        '<button class="st-toggle" data-act="sec-toggle" data-id="' + esc(s.slug) + '">' + (open ? "▾" : "▸") + "</button>" +
        arrows("sec", s.slug) +
        '<span class="nm">' + esc(s.name) + '</span>' +
        '<span class="cnt">' + arts.length + '</span>' +
        '<button class="st-mini" data-act="art-add" data-id="' + esc(s.slug) + '">+ статья</button>' +
        '<button class="st-mini" data-act="sec-rename" data-id="' + esc(s.slug) + '">переименовать</button>' +
        '<button class="st-mini" data-act="sec-del" data-id="' + esc(s.slug) + '">удалить</button>' +
        '</div>';
      if (open) {
        html += '<ul class="st-arts">';
        arts.forEach(function (a) {
          var opts = secOpts.filter(function (o) { return o.slug !== s.slug; })
            .map(function (o) { return '<option value="' + esc(o.slug) + '">→ ' + esc(o.name) + "</option>"; }).join("");
          html += '<li class="st-art">' + arrows("art", a.art) +
            '<span class="num">#' + esc(a.num || a.art) + "</span>" +
            '<span class="ttl">' + esc(title(a.art)) + "</span>" +
            (opts ? '<select data-act="art-move" data-id="' + esc(a.art) + '"><option value="">переместить…</option>' + opts + "</select>" : "") +
            '<button class="st-mini" data-act="art-rename" data-id="' + esc(a.art) + '">переименовать</button>' +
            '<button class="st-mini" data-act="art-arch" data-id="' + esc(a.art) + '">в архив</button>' +
            "</li>";
        });
        html += "</ul>";
      }
      html += "</div>";
    });

    var arch = archivedArticles();
    html += '<details class="st-archive"><summary>Архив (' + arch.length + ")</summary><ul class=\"st-arts\">";
    if (!arch.length) html += '<li class="st-art" style="opacity:.6">пусто</li>';
    arch.forEach(function (a) {
      html += '<li class="st-art st-archived"><span class="num">#' + esc(a.num || a.art) + "</span>" +
        '<span class="ttl">' + esc(title(a.art)) + ' <em>(' + esc(a.section) + ")</em></span>" +
        '<button class="st-mini" data-act="art-restore" data-id="' + esc(a.art) + '">восстановить</button></li>';
    });
    html += "</ul></details>";
    root.innerHTML = html;
  }

  // ── события (делегирование) ──────────────────────────────────────────────────
  root.addEventListener("click", function (ev) {
    var el = ev.target.closest("[data-act]"); if (!el) return;
    var act = el.getAttribute("data-act"), id = el.getAttribute("data-id");
    if (el.tagName === "SELECT") return;
    switch (act) {
      case "sec-up": moveSection(id, -1); break;
      case "sec-down": moveSection(id, 1); break;
      case "sec-rename": renameSection(id); break;
      case "sec-del": deleteSection(id); break;
      case "add-sec": addSection(); break;
      case "art-add": createArticle(id); break;
      case "sec-toggle": expanded[id] = !expanded[id]; render(); break;
      case "art-up": moveArticle(id, -1); break;
      case "art-down": moveArticle(id, 1); break;
      case "art-rename": renameArticle(id); break;
      case "art-arch": archiveArticle(id); break;
      case "art-restore": restoreArticle(id); break;
      case "reset": if (confirmStr("Сбросить все несохранённые изменения?")) location.reload(); break;
      case "save": save(); break;
    }
  });
  root.addEventListener("change", function (ev) {
    var el = ev.target.closest('select[data-act="art-move"]'); if (!el) return;
    if (el.value) moveToSection(el.getAttribute("data-id"), el.value);
  });

  // ── сохранение ────────────────────────────────────────────────────────────────
  function save() {
    if (!WORKER) { status("Не задан Worker URL (site.json).", true); return; }
    renumber();
    var buildDate = new Date().toISOString().slice(0, 10);
    var files = [{ path: "docs/config/structure.json", content: JSON.stringify(structure, null, 2) + "\n" }];
    files.push({ path: "docs/index.html", content: deps.renderIndexHtml({ structure: structure, manifestByArt: byArt, template: deps.tplIndex, buildDate: buildDate }) });
    activeSecs().forEach(function (s) {
      files.push({ path: "docs/" + s.slug + "/index.html",
        content: deps.renderSectionIndexHtml({ slug: s.slug, structure: structure, manifestByArt: byArt, template: deps.tplSection, buildDate: buildDate }) });
    });
    var structJson = files[0].content;   // docs/config/structure.json — его и ждём на сайте
    status("Сохранение… (" + files.length + " файлов)");
    setBusy(true);
    fetch(WORKER + "/api/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + sess.token },
      body: JSON.stringify({ files: files, message: "cms: структура — " + sess.nick })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        setBusy(false);
        if (!res.ok || !res.d.ok) throw new Error((res.d && res.d.error) || "HTTP");
        // Сразу выходим из управления на заглавную и ждём обновление ТАМ: что именно
        // ждать (боевой config/structure.json == закоммиченному) кладём в sessionStorage —
        // бутстрап в index.html подхватит это на загрузке и покажет окно ожидания,
        // а по приезду деплоя сам перезагрузит заглавную.
        try {
          sessionStorage.setItem("ya_deploywait", JSON.stringify({
            url: new URL("config/structure.json", document.baseURI).href,
            expect: structJson
          }));
        } catch (e) {}
        location.href = "index.html";
      }).catch(function (e) { setBusy(false); status("Не сохранилось: " + (e.message || e), true); });
  }

  // ── мелочи ────────────────────────────────────────────────────────────────────
  function status(m, err) { var s = document.getElementById("st-status"); if (s) { s.textContent = m || ""; s.classList.toggle("err", !!err); } }
  function setBusy(on) { root.querySelectorAll(".st-btn,.st-mini,.st-arrows button").forEach(function (b) { b.disabled = on; }); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function confirmStr(m) { return window.confirm(m); }

  // ── Ф10E: создание новой статьи ───────────────────────────────────────────────
  // Статья «рождается» в оверлей-редакторе (ze-core) из шаблона; на сайт попадает
  // ТОЛЬКО по «Сохранить» (тогда и становится «не горящей рукописью»). Отмена/
  // закрытие — ничего не коммитит. Новая статья сразу = единый docs/art/NNN.html
  // (ZML-рендер); «old»-варианта нет (нет архива). Заголовок/дата живут в записи
  // structure (manifest её ещё не знает) до следующей полной пересборки.
  var artDepsLoaded = null;
  function loadArtDeps() {
    if (artDepsLoaded) return Promise.resolve(artDepsLoaded);
    return Promise.all([
      fetch("editor/data/zohar_index.json").then(j),
      fetch("editor/data/proper-nouns.txt").then(t),
      // шаблон вью — всегда свежий (нельзя «запечь» устаревший после деплоя).
      fetch("editor/data/template_view.html", { cache: "no-store" }).then(t),
      import("./editor/faw_markup.js")   // авто-разметка [faw] на «Сохранить»
    ]).then(function (a) {
      artDepsLoaded = { zoharIndex: a[0], properNouns: a[1], templateView: a[2], fawMarkup: a[3].autoMarkupFaw };
      return artDepsLoaded;
    });
  }

  function isoToday() {
    var d = new Date(), p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }
  // ── кодек art-id (SPEC §2.3 — побайтно как legacy build_art_ids.py для дат
  // 1994–2029 и суффиксов 1..52). Общий принцип: art-id = дата-префикс +
  // суффикс-разрешитель коллизий, наращиваемый до уникальности. НИЧЕГО не бросаем:
  // год вне диапазона продолжает последовательность, суффикс безграничен.
  function encYear(y) {
    if (y >= 2020 && y <= 2029) return String(y - 2020);                      // '0'..'9'
    if (y >= 1994 && y <= 2019) return String.fromCharCode(90 - (2019 - y));  // 'A'..'Z'
    if (y >= 2030 && y <= 2055) return String.fromCharCode(97 + (y - 2030));  // 'a'..'z' (расширение)
    return "Y" + y;   // запредельный год — лишь бы не бросать; уникальность добьёт суффикс
  }
  function encMonth(m) { return m <= 9 ? String(m) : String.fromCharCode(65 + m - 10); }
  function encDay(d) { return d <= 9 ? String(d) : String.fromCharCode(65 + d - 10); }
  // Суффикс — биективная база-52 (как столбцы Excel): 0→"" · 1..26→A..Z ·
  // 27..52→a..z (байт-в-байт legacy) · 53→AA · 54→AB · … — растёт без предела.
  var SUF52 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
  function encSuffix(n) {
    var s = "";
    while (n > 0) { var r = (n - 1) % 52; s = SUF52.charAt(r) + s; n = Math.floor((n - 1) / 52); }
    return s;
  }
  function mintArtId() {
    var d = new Date();
    var base = encYear(d.getFullYear()) + encMonth(d.getMonth() + 1) + encDay(d.getDate());
    var taken = {};
    structure.articles.forEach(function (a) { taken[a.art] = 1; });
    Object.keys(byArt).forEach(function (k) { taken[k] = 1; });
    for (var p = 0; ; p++) { var id = base + encSuffix(p); if (!taken[id]) return id; }  // суффикс безграничен → id всегда найдётся
  }

  function templateZml(art, today) {
    return [
      "---",
      "title: Новая статья",
      "date: " + today,
      "type: prose",
      "view: zml",
      "---",
      "[epi kind=prose]",
      "Эпиграф или вводная цитата — по желанию. Удалите весь блок, если не нужен.",
      "[/epi]",
      "",
      "[sub]Подзаголовок — необязательный, удалите строку, если не нужен[/sub]",
      "",
      "Это первый абзац новой статьи. Замените текст своим. Слова можно выделить",
      "_курсивом_, поставить [https://example.com|ссылку] или сноску.[^1]",
      "",
      "[poem]",
      "Здесь строка стихотворения,",
      "за ней — вторая,",
      "а пустая строка ниже разделяет строфы.",
      "",
      "Так начинается вторая строфа.",
      "[/poem]",
      "",
      "[^1]: Текст сноски — номера проставляются автоматически.",
      ""
    ].join("\n");
  }

  function parseTitle(zml) {
    var fm = zml.match(/^---([\s\S]*?)---/);
    if (!fm) return "";
    var m = fm[1].match(/^title:[ \t]*(.+?)[ \t]*$/m);
    if (!m) return "";
    return m[1].replace(/^["']|["']$/g, "").trim();
  }

  function secName(slug) {
    var s = structure.sections.find(function (x) { return x.slug === slug; });
    return s ? s.name : slug;
  }

  function renderNewView(zml, art, slug, today) {
    var rec = { art: art, section: slug, title: parseTitle(zml), date_chosen: today, url: "" };
    return deps.renderArticle({
      zml: zml, rec: rec, manifest: deps.manifestArr, manifestByArt: byArt,
      zoharIndex: artDepsLoaded.zoharIndex, template: artDepsLoaded.templateView,
      properNouns: artDepsLoaded.properNouns, displayConfig: deps.displayConfig, siteConfig: deps.siteConfig
    });
  }

  function commitNewArticle(art, slug, zml, html, today, extras) {
    if (!WORKER) return Promise.reject(new Error("не задан Worker URL (site.json)"));
    var title = parseTitle(zml) || "Новая статья";
    // Клон structure; живые не трогаем до успеха коммита (Отмена = ничего).
    var st = JSON.parse(JSON.stringify(structure));
    var ex = st.articles.find(function (a) { return a.art === art; });
    var maxO = st.articles.filter(function (a) { return a.section === slug && a.status !== "archived"; })
      .reduce(function (m, a) { return Math.max(m, a.order); }, -1);
    if (ex) { ex.section = slug; ex.status = "published"; ex.title = title; ex.date = today; }
    else st.articles.push({ art: art, section: slug, order: maxO + 1, status: "published", title: title, date: today });
    var bd = isoToday();
    // url-unification: новая статья сразу = единый docs/art/NNN.html (ZML-рендер).
    // forced_views/default_view упразднены; «old»-варианта у новой статьи нет.
    var files = [
      { path: "docs/config/structure.json", content: JSON.stringify(st, null, 2) + "\n" },
      { path: "docs/art/" + art + ".zml", content: zml },
      { path: "docs/art/" + art + ".html", content: html },
      { path: "docs/index.html",
        content: deps.renderIndexHtml({ structure: st, manifestByArt: byArt, template: deps.tplIndex, buildDate: bd }) },
      { path: "docs/" + slug + "/index.html",
        content: deps.renderSectionIndexHtml({ slug: slug, structure: st, manifestByArt: byArt, template: deps.tplSection, buildDate: bd }) }
    ];
    // Картинки (обложка + [img] в тексте) — бинарными файлами в тот же коммит /api/commit
    // (handleCommit пропускает флаг binary в commitFiles). Имена клиент генерит сам
    // (<art>.<ext> / <art>_N.<ext>) — раскладываем в docs/img/, валидируя имя на всякий.
    var IMG_NAME = /^[A-Za-z0-9_-]{1,64}\.(jpe?g|png|gif|webp)$/i;
    var imgs = [];
    if (extras && extras.image) imgs.push(extras.image);
    if (extras && extras.images) imgs = imgs.concat(extras.images);
    imgs.forEach(function (im) {
      if (im && IMG_NAME.test(im.name || "") && im.content) {
        files.push({ path: "docs/img/" + im.name, content: im.content, binary: true });
      }
    });
    return fetch(WORKER + "/api/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + sess.token },
      body: JSON.stringify({ files: files, message: "cms: новая статья " + art + " (" + slug + ") — " + sess.nick })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok || !res.d.ok) throw new Error((res.d && res.d.error) || "HTTP");
        // успех → отражаем в живой структуре, чтобы дерево показало статью без reload
        structure = st;
        if (!byArt[art]) byArt[art] = { art: art, title: title, section: slug, date_chosen: today };
        expanded[slug] = true;
        render();
      });
  }

  function createArticle(slug) {
    status("Готовлю редактор новой статьи…");
    loadArtDeps().then(function (deps) {
      var today = isoToday(), art;
      try { art = mintArtId(); } catch (e) { status(e.message, true); return; }
      var zml = templateZml(art, today);
      import("./ze-core.js?v=20260628-02").then(function (mod) {
        status("");
        mod.mountZmlEditor({
          label: "Новая статья · #" + art + " → " + secName(slug),
          initialZml: zml,
          renderView: function (z) { return renderNewView(z, art, slug, today); },
          preprocess: deps.fawMarkup,   // [faw] без «|» → разметка по слогам перед сохранением
          // превью из structure.html: база = docs/art/, чтобы ../themes/../img/… вью
          // резолвились (иначе тема/оформление в превью новой статьи не подхватывались)
          previewBase: new URL("art/", document.baseURI).href,
          image: { artId: art },        // панели «Обложка» + «В тексте» ([img]) в новой статье
          save: function (z, html, extras) { return commitNewArticle(art, slug, z, html, today, extras); },
          // после создания ждём появления новой статьи на сайте ПРЯМО В РЕДАКТОРЕ
          // (keepEditorOpen), затем сами переходим на неё — без ручного Ctrl+R.
          deployWait: function (z, html) {
            return {
              keepEditorOpen: true,
              url: new URL("art/" + art + ".html", document.baseURI).href,
              match: function (text) { return text === html; },
              onReady: function () { location.href = "art/" + art + ".html"; }
            };
          }
        });
      }).catch(function (e) { status("ze-core: " + (e.message || e), true); });
    }).catch(function (e) { status("Загрузка движка статьи: " + (e.message || e), true); });
  }
})();
