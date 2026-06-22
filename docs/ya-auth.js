/* ya-auth.js — клиент авторизации (главная).
 * Постоянного логина на сайте НЕТ: сессия живёт только внутри потока «Управление»
 * (вход → админка → «Закрыть») или цикла правки статьи; по выходу localStorage
 * чистится. Внизу главной — одна кнопка «Управление»: открывает модальное окно
 * входа (ze-core.loginModal), при успехе ведёт в admin.html.
 * Экспорт: window.YaAuth = { WORKER, session, logout, login, renderManageInto }.
 */
(function (global) {
  "use strict";
  var WORKER = "https://yaniktoim-auth.imyavel.workers.dev";

  // Динамический import() резолвим от URL САМОГО скрипта (на проде /yaniktoim/),
  // а не от документа — иначе ze-core.js не находится (см. ya-edit.js).
  var SELF = document.currentScript || document.querySelector('script[src*="ya-auth.js"]');
  var SELF_SRC = SELF ? SELF.src : new URL("ya-auth.js", document.baseURI).href;
  var ASSET_VER = "20260622-01";   // бастит кэш динамических модулей при правках
  var modUrl = function (p) {
    return new URL(p + (p.indexOf("?") < 0 ? "?v=" + ASSET_VER : ""), SELF_SRC).href;
  };

  function session() {
    try { return JSON.parse(localStorage.getItem("ya_session") || "null"); } catch (e) { return null; }
  }
  function setSession(s) { try { localStorage.setItem("ya_session", JSON.stringify(s)); } catch (e) {} }
  function logout() {
    try { localStorage.removeItem("ya_session"); localStorage.removeItem("ya_default_view"); } catch (e) {}
  }
  function login(nick, pass) {
    return fetch(WORKER + "/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nick: nick, password: pass }),
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok || !d.token) throw new Error(d.error || "ошибка входа");
        setSession({ token: d.token, nick: d.nick, role: d.role });
        return d;
      });
    });
  }

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  var A = "color:inherit;text-decoration:none;border-bottom:1px dotted currentColor;cursor:pointer;white-space:nowrap;";

  // Кнопка «Управление»: модальное окно входа → при успехе в админку.
  function openManage() {
    import(modUrl("ze-core.js"))
      .then(function (mod) {
        return mod.loginModal({
          worker: WORKER, title: "Управление",
          message: "Войдите, чтобы управлять сайтом.",
        });
      })
      .then(function (s) { if (s && s.token) location.href = "admin.html"; })
      .catch(function (e) { alert("Не удалось открыть вход: " + (e && e.message || e)); });
  }

  // Рисует в контейнере одну ссылку «Управление» (заменяет прежний логин-виджет).
  function renderManageInto(box) {
    box.innerHTML = "";
    box.setAttribute("style", "display:inline-flex;gap:.9em;align-items:center;font-size:.85rem;");
    var m = el("a", { href: "#manage", style: A }, "Управление");
    m.onclick = function (e) { e.preventDefault(); openManage(); };
    box.appendChild(m);
    if (location.hash === "#manage") openManage();
  }

  global.YaAuth = {
    WORKER: WORKER, session: session, logout: logout, login: login,
    renderManageInto: renderManageInto,
  };
})(window);
