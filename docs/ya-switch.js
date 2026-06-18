/* Ф8′ — shim старой статьи (docs/art/<art>.html).
 * Конвертер HTML→ZML срезает <script>, поэтому весь UI строится здесь динамически:
 * статика страницы не меняется → конверсия не дрейфует (CHANGED=0).
 *  • ссылка «✦ Новая версия (ZML)» вставляется СПРАВА в строку «хлебных крошек»
 *    (Главная / Раздел) — без отдельного чёрного бара; вход/выход тут НЕ показываем
 *    (логин доступен только на главной).
 *  • авто-редирект на ZML-вью, если эффективный default_view == "new"
 *    (аноним → docs/config/display.json; залогинен → worker /api/settings);
 *    гард ?orig=1 (приход по «Оригинал» из вью) — НЕ редиректить, показать старую.
 */
(function () {
  "use strict";
  var WORKER = "https://yaniktoim-auth.imyavel.workers.dev";

  // <art> из имени файла: .../art/<art>.html
  var m = (location.pathname || "").match(/\/([^\/]+)\.html?$/i);
  var art = m ? m[1] : "";
  if (!art || /\.view$/i.test(art)) return;          // не статья / уже вью
  var viewUrl = art + ".view.html";

  var qs = location.search || "";
  var cameFromView = /[?&]orig=1\b/.test(qs);        // пришли по «Оригинал» — не редиректить

  function session() {
    try { return JSON.parse(localStorage.getItem("ya_session") || "null"); } catch (e) { return null; }
  }

  // эффективный default_view: личный (если залогинен) либо анонимный (display.json).
  function effectiveDefault(cb) {
    var s = session();
    if (s && s.token) {
      fetch(WORKER + "/api/settings", { headers: { Authorization: "Bearer " + s.token } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (cfg) { cb(cfg && cfg.default_view); })
        .catch(function () { cb(null); });
    } else {
      fetch("../config/display.json", { cache: "no-cache" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (cfg) { cb(cfg && cfg.default_view); })
        .catch(function () { cb(null); });
    }
  }

  // ── авто-редирект: forced view: (per-article) > default_view (админ/личный) ──
  // Гард ?orig=1 (приход по «Оригинал») — не редиректить. forced "html" жёстко
  // оставляет старую даже при default_view=new; forced "zml" — всегда на вью.
  function byDefault() { effectiveDefault(function (dv) { if (dv === "new") location.replace(viewUrl); }); }
  if (!cameFromView) {
    fetch("../config/forced_views.json", { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (forced) {
        var f = forced && forced[art];
        if (f === "zml") { location.replace(viewUrl); return; }
        if (f === "html") return;
        byDefault();
      })
      .catch(byDefault);
  }

  // ── ссылка «Новая версия» справа в строке крошек ─────────────────────────
  // Шапка-крошки в корпусе варьируется (nav.crumbs · header.crumbs>nav ·
  // nav.breadcrumbs · div.crumbs), поэтому: берём первый .crumbs/.breadcrumbs,
  // целимся в РОДИТЕЛЯ первой ссылки (это текстовая строка крошек — в т.ч. внутр.
  // <nav> у full-bleed шапок), кладём ссылку последним ребёнком и равняем вправо.
  // Цвет/шрифт/uppercase НЕ задаём — наследуются от .crumbs данной темы (→ однородно).
  function placeSwitchLink() {
    if (document.getElementById("ya-zml-switch")) return;
    var link = document.createElement("a");
    link.id = "ya-zml-switch";
    link.href = viewUrl;
    link.textContent = "✦ Новая версия (ZML)";

    var crumbs = document.querySelector(".crumbs, .breadcrumbs");
    if (crumbs) {
      var firstA = crumbs.querySelector("a");
      var line = firstA ? firstA.parentElement : crumbs;
      var disp = "";
      try { disp = window.getComputedStyle(line).display || ""; } catch (e) {}
      if (/flex/.test(disp)) {
        // в flex-контейнере float игнорируется → авто-маржин уводит вправо
        link.setAttribute("style", "margin-left:auto;white-space:nowrap;");
      } else {
        link.setAttribute("style", "float:right;white-space:nowrap;");
      }
      line.appendChild(link);
      tightenTopGap(crumbs, line);
    } else {
      // подстраховка (крошек нет): тонкая строка сверху, без чёрного бара
      link.setAttribute("style",
        "display:block;text-align:right;padding:.5em .9em;" +
        "font:13px/1.4 system-ui,Segoe UI,Arial,sans-serif;");
      document.body.insertBefore(link, document.body.firstChild);
    }
  }

  // ── срезать вдвое верхний отступ шапки (промежуток до начала крошек) ──────
  // Отступ в корпусе задаётся padding(-top) самих крошек (или внутреннего <nav>
  // у full-bleed шапок), не margin. Режем computed paddingTop/marginTop вдвое на
  // контейнере И линии (дубль исключаем). Idempotent: на свежей загрузке читается
  // CSS-значение (inline не persist), поэтому повторного деления не накапливается.
  function tightenTopGap(container, line) {
    var els = (line && line !== container) ? [container, line] : [container];
    els.forEach(function (el) {
      if (!el) return;
      var cs = window.getComputedStyle(el);
      var pt = parseFloat(cs.paddingTop) || 0;
      if (pt > 0) el.style.paddingTop = (pt / 2) + "px";
      var mt = parseFloat(cs.marginTop) || 0;
      if (mt > 0) el.style.marginTop = (mt / 2) + "px";
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", placeSwitchLink);
  } else {
    placeSwitchLink();
  }
})();
