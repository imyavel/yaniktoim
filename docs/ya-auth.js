/* Ф8′ — общий клиент авторизации (главная + админка).
 * Логин по нику через Cloudflare Worker; сессия в localStorage("ya_session").
 * Экспорт: window.YaAuth = { WORKER, session, logout, login, renderAuthInto }.
 */
(function (global) {
  "use strict";
  var WORKER = "https://yaniktoim-auth.imyavel.workers.dev";

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

  // Рисует состояние входа в контейнер: «Войти» (раскрывает форму) или ник·Админка·Выйти.
  function renderAuthInto(box) {
    box.innerHTML = "";
    box.setAttribute("style", "display:inline-flex;gap:.9em;align-items:center;font-size:.85rem;");
    var s = session();
    if (s && s.nick) {
      box.appendChild(el("span", { style: "opacity:.75;" }, s.nick + (s.role === "admin" ? " (admin)" : "")));
      box.appendChild(el("a", { href: "admin.html", style: A }, "Админка"));
      var out = el("a", { href: "#", style: A }, "Выйти");
      out.onclick = function (e) { e.preventDefault(); logout(); location.reload(); };
      box.appendChild(out);
      return;
    }
    var open = el("a", { href: "#login", style: A }, "Войти");
    open.onclick = function (e) { e.preventDefault(); showForm(box); };
    box.appendChild(open);
    if (location.hash === "#login") showForm(box);
  }

  function showForm(box) {
    box.innerHTML = "";
    var f = el("form", { style: "display:inline-flex;gap:.5em;align-items:center;flex-wrap:wrap;" });
    var nick = el("input", { type: "text", placeholder: "ник", autocomplete: "username",
      style: "font:inherit;padding:.2em .4em;width:8em;" });
    var pass = el("input", { type: "password", placeholder: "пароль", autocomplete: "current-password",
      style: "font:inherit;padding:.2em .4em;width:8em;" });
    var btn = el("button", { type: "submit", style: "font:inherit;cursor:pointer;padding:.2em .7em;" }, "Войти");
    var msg = el("span", { style: "color:#b00;font-size:.85em;" });
    f.appendChild(nick); f.appendChild(pass); f.appendChild(btn); f.appendChild(msg);
    f.onsubmit = function (e) {
      e.preventDefault(); msg.textContent = ""; btn.disabled = true;
      login(nick.value.trim(), pass.value).then(function () {
        renderAuthInto(box);
      }).catch(function (err) { msg.textContent = err.message || "ошибка"; btn.disabled = false; });
    };
    box.appendChild(f);
    nick.focus();
  }

  global.YaAuth = { WORKER: WORKER, session: session, logout: logout, login: login, renderAuthInto: renderAuthInto };
})(window);
