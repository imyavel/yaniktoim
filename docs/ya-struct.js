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
      '<p><a href="index.html">На главную</a> — войдите под учёткой admin.</p>';
    return;
  }

  var deps = {}, structure = null, byArt = {}, WORKER = "", expanded = {};

  Promise.all([
    import("./editor/render.js"),
    fetch("config/structure.json").then(j),
    fetch("editor/data/manifest.json").then(j),
    fetch("editor/data/template_index.tpl").then(t),
    fetch("editor/data/template_section.tpl").then(t),
    fetch("editor/data/site.json").then(j).catch(function () { return {}; })
  ]).then(function (a) {
    deps.renderIndexHtml = a[0].renderIndexHtml;
    deps.renderSectionIndexHtml = a[0].renderSectionIndexHtml;
    structure = a[1];
    a[2].forEach(function (r) { byArt[r.art] = r; });
    deps.tplIndex = a[3];
    deps.tplSection = a[4];
    WORKER = ((a[5] && a[5].workerUrl) || "").replace(/\/+$/, "");
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
  function title(art) { var r = byArt[art]; return (r && r.title) || art; }

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
      case "sec-toggle": expanded[id] = !expanded[id]; render(); break;
      case "art-up": moveArticle(id, -1); break;
      case "art-down": moveArticle(id, 1); break;
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
        savedPopup();
      }).catch(function (e) { setBusy(false); status("Не сохранилось: " + (e.message || e), true); });
  }

  // ── мелочи ────────────────────────────────────────────────────────────────────
  function status(m, err) { var s = document.getElementById("st-status"); if (s) { s.textContent = m || ""; s.classList.toggle("err", !!err); } }
  function setBusy(on) { root.querySelectorAll(".st-btn,.st-mini,.st-arrows button").forEach(function (b) { b.disabled = on; }); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function confirmStr(m) { return window.confirm(m); }
  function savedPopup() {
    var p = document.createElement("div");
    p.style.cssText = "position:fixed;inset:0;z-index:99;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45)";
    p.innerHTML = '<div style="max-width:420px;margin:1em;background:#fff;color:#222;border-radius:10px;padding:1.3em 1.5em;box-shadow:0 12px 40px rgba(0,0,0,.35)">' +
      "<p style=\"margin:0 0 .7em\"><b>Структура сохранена.</b></p>" +
      "<p style=\"margin:0 0 1em\">Сайт обновится через 30–90 сек. Затем обновите страницу (Ctrl+R). Крошки внутри статей подтянут раздел при следующей полной пересборке.</p>" +
      '<div style="text-align:right"><button class="st-btn st-primary" id="st-pop-ok">Ок</button></div></div>';
    document.body.appendChild(p);
    p.querySelector("#st-pop-ok").addEventListener("click", function () { p.remove(); status("Сохранено. Обновите через ~минуту."); });
  }
})();
