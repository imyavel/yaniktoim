/* ze-core.js — общий полноэкранный оверлей-редактор ZML (ES-модуль).
 *
 * Один движок UI для двух сценариев:
 *   • Ф8  — правка существующей статьи (docs/ya-edit.js).
 *   • Ф10E — создание новой статьи (docs/ya-struct.js).
 *
 * Оверлей владеет ТОЛЬКО интерфейсом/хореографией: textarea ZML · «Просмотр»
 * (рендер в iframe) · «Сохранить» · «Отмена» · popup. Чем рендерить и куда
 * коммитить — знает вызывающий, передавая колбэки:
 *
 *   mountZmlEditor({
 *     label,             // подпись панели, напр. "Правка ZML · #ART"
 *     initialZml,        // стартовый текст textarea
 *     renderView(zml),   // СИНХРОННО → строка HTML (может бросить — покажем ошибку)
 *     save(zml, html),   // → Promise: resolve = успех, reject(Error) = ошибка
 *     savedMessage,      // опц. текст popup после успешного сохранения
 *     savedPrimaryLabel, // опц. подпись главной кнопки popup (деф. «Готово»)
 *     onSavedPrimary(),  // опц. действие главной кнопки popup; затем закрытие
 *     onClosed()         // опц. колбэк после демонтажа оверлея
 *   })  → объект-контроллер { close() } | null (если уже открыт другой редактор).
 */

let MOUNTED = false;

export function mountZmlEditor(opts) {
  if (MOUNTED || document.getElementById("ze-root")) return null;  // один за раз — существующий оверлей НЕ трогаем (в нём м.б. несохранённое)
  opts = opts || {};
  MOUNTED = true;
  injectStyles();

  // textarea нормализует CRLF→LF при установке value → baseline тоже к LF,
  // иначе CRLF-исходник всегда «грязный» (ложное «несохранённые изменения»).
  const baselineGet = () => baseline;
  let baseline = (opts.initialZml || "").replace(/\r\n/g, "\n");
  // Ф8(b): иллюстрация. imgOpt={artId} включает блок «Иллюстрация»; pendingImage —
  // выбранный, но ещё не сохранённый файл {name, mime, b64}. Источник истины «какая
  // картинка» — строка `image:` во frontmatter textarea (её и правят кнопки блока);
  // байты уходят в save() только при загрузке/замене (удаление = отвязка строки).
  const imgOpt = opts.image && typeof opts.image === "object" ? opts.image : null;
  let pendingImage = null;

  const ui = document.createElement("div");
  ui.id = "ze-root";
  ui.innerHTML =
    '<div class="ze-bar">' +
      '<span class="ze-title">' + esc(opts.label || "Редактор ZML") + '</span>' +
      '<span class="ze-spacer"></span>' +
      '<button type="button" class="ze-btn" data-act="preview">Просмотр</button>' +
      '<button type="button" class="ze-btn ze-hidden" data-act="back">← Редактировать</button>' +
      '<button type="button" class="ze-btn ze-primary" data-act="save">Сохранить</button>' +
      '<button type="button" class="ze-btn" data-act="cancel">Отмена</button>' +
    '</div>' +
    '<div class="ze-body">' +
      '<textarea class="ze-text" spellcheck="false" wrap="soft"></textarea>' +
      '<iframe class="ze-prev ze-hidden" title="Просмотр"></iframe>' +
    '</div>' +
    '<div class="ze-status" aria-live="polite"></div>';
  document.body.appendChild(ui);
  document.documentElement.classList.add("ze-lock");

  const ta = ui.querySelector(".ze-text");
  const iframe = ui.querySelector(".ze-prev");
  ta.value = baseline;
  ta.focus();
  if (imgOpt) setupImageBar();

  ui.addEventListener("click", function (ev) {
    const b = ev.target.closest("[data-act]"); if (!b) return;
    const act = b.getAttribute("data-act");
    if (act === "preview") showPreview();
    else if (act === "back") showEditor();
    else if (act === "save") doSave();
    else if (act === "cancel") doCancel();
  });
  document.addEventListener("keydown", escClose);

  function showPreview() {
    let html;
    try { html = opts.renderView(ta.value); }
    catch (e) { status("Ошибка рендера: " + (e.message || e), true); return; }
    html = swapPreviewImage(html); // невыложённую картинку показываем как data:-URL
    html = injectPreviewNav(html); // якоря #… скроллят ВНУТРИ превью, не уводят на боевой файл
    iframe.srcdoc = html;          // srcdoc → относительные ../themes, ../img от родителя
    iframe.classList.remove("ze-hidden");
    ta.classList.add("ze-hidden");
    toggle("preview", false); toggle("back", true);
    status("");
  }
  function showEditor() {
    iframe.classList.add("ze-hidden"); ta.classList.remove("ze-hidden");
    toggle("preview", true); toggle("back", false);
    ta.focus();
  }

  function doSave() {
    // Предобработка перед сохранением (opts.preprocess): например, авто-разметка
    // [faw] по слогам (вставка «|»). Результат показываем в textarea — оператор
    // видит, что именно сохраняется, и может поправить/пересохранить.
    let src = ta.value;
    if (typeof opts.preprocess === "function") {
      try { src = opts.preprocess(src); }
      catch (e) { status("Не сохраняю — ошибка предобработки: " + (e.message || e), true); return; }
      if (typeof src !== "string") src = ta.value;
      if (src !== ta.value) ta.value = src;
    }
    let html;
    try { html = opts.renderView(src); }
    catch (e) { status("Не сохраняю — ошибка рендера: " + (e.message || e), true); return; }
    if (typeof opts.save !== "function") { status("Сохранение не настроено.", true); return; }
    const zml = src;
    status("Сохранение…");
    setBusy(true);
    Promise.resolve()
      .then(function () {
        return opts.save(zml, html,
          { image: pendingImage ? { name: pendingImage.name, content: pendingImage.b64 } : null });
      })
      .then(function () {
        setBusy(false);
        baseline = zml;            // сохранено → нет «несохранённых правок»
        pendingImage = null;       // картинка закоммичена
        savedPopup();
      })
      .catch(function (e) { setBusy(false); status("Сохранение не удалось: " + (e.message || e), true); });
  }

  function isDirty() { return ta.value !== baselineGet() || !!pendingImage; }
  function doCancel() {
    if (isDirty()) { confirmModal("Отменить несохранённые изменения?", close); return; }
    close();
  }
  function escClose(ev) {
    if (ev.key === "Escape" && ui.parentNode && !isDirty()) close();
  }

  function close() {
    document.removeEventListener("keydown", escClose);
    document.documentElement.classList.remove("ze-lock");
    if (ui.parentNode) ui.parentNode.removeChild(ui);
    MOUNTED = false;
    if (typeof opts.onClosed === "function") opts.onClosed();
  }

  // popup после успешного сохранения: «Остаться» (продолжить правку) | главная кнопка
  function savedPopup() {
    const pop = document.createElement("div");
    pop.id = "ze-pop";
    pop.innerHTML =
      '<div class="ze-pop-card">' +
        '<p><b>Изменения сохранены.</b></p>' +
        '<p>' + esc(opts.savedMessage ||
          "Обновление сайта обычно занимает 30–90 секунд. Затем нажмите Ctrl+R (или F5).") + '</p>' +
        '<div class="ze-pop-row">' +
          '<button type="button" class="ze-btn" data-pop="stay">Остаться в правке</button>' +
          '<button type="button" class="ze-btn ze-primary" data-pop="ok">' +
            esc(opts.savedPrimaryLabel || "Готово") + '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(pop);
    pop.addEventListener("click", function (ev) {
      const b = ev.target.closest("[data-pop]"); if (!b) return;
      const primary = b.getAttribute("data-pop") === "ok";
      pop.parentNode.removeChild(pop);
      if (primary) {
        if (typeof opts.onSavedPrimary === "function") opts.onSavedPrimary();
        close();
      } else {
        status("Сохранено. Можно продолжать правку.");
      }
    });
  }

  // DOM-модалка подтверждения (нативный confirm блокирует рендерер iframe).
  function confirmModal(msg, onYes) {
    const m = document.createElement("div");
    m.id = "ze-pop";
    m.innerHTML = '<div class="ze-pop-card"><p>' + esc(msg) + '</p>' +
      '<div class="ze-pop-row">' +
        '<button type="button" class="ze-btn" data-c="no">Нет</button>' +
        '<button type="button" class="ze-btn ze-primary" data-c="yes">Да</button>' +
      '</div></div>';
    document.body.appendChild(m);
    m.addEventListener("click", function (ev) {
      const b = ev.target.closest("[data-c]"); if (!b) return;
      const yes = b.getAttribute("data-c") === "yes";
      m.parentNode.removeChild(m);
      if (yes) onYes();
    });
  }

  function toggle(act, show) {
    const b = ui.querySelector('[data-act="' + act + '"]');
    if (b) b.classList.toggle("ze-hidden", !show);
  }
  function setBusy(on) { ui.querySelectorAll(".ze-btn").forEach(function (b) { b.disabled = on; }); }
  function status(msg, err) {
    const s = ui.querySelector(".ze-status");
    s.textContent = msg || "";
    s.classList.toggle("ze-err", !!err);
  }

  // ── Ф8(b) блок «Иллюстрация» (монтируется только при opts.image) ─────────────
  function setupImageBar() {
    const bar = document.createElement("div");
    bar.className = "ze-imgbar";
    bar.innerHTML =
      '<span class="ze-imglabel">Иллюстрация:</span>' +
      '<span class="ze-imgname"></span>' +
      '<span class="ze-spacer"></span>' +
      '<button type="button" class="ze-btn ze-imgpick">Загрузить…</button>' +
      '<button type="button" class="ze-btn ze-imgdel ze-hidden">Удалить</button>' +
      '<input type="file" class="ze-imgfile ze-hidden" accept="image/jpeg,image/png,image/gif,image/webp">';
    ui.querySelector(".ze-bar").insertAdjacentElement("afterend", bar);
    const nameEl = bar.querySelector(".ze-imgname");
    const pickBtn = bar.querySelector(".ze-imgpick");
    const delBtn = bar.querySelector(".ze-imgdel");
    const fileInp = bar.querySelector(".ze-imgfile");

    function refresh() {
      const cur = getFmImage(ta.value);
      nameEl.textContent = cur ? (cur + (pendingImage ? "  (новая — не сохранена)" : "")) : "— нет —";
      delBtn.classList.toggle("ze-hidden", !cur);
      pickBtn.textContent = cur ? "Заменить…" : "Загрузить…";
    }
    refresh();

    pickBtn.addEventListener("click", function () { fileInp.click(); });
    fileInp.addEventListener("change", function () {
      const f = fileInp.files && fileInp.files[0];
      fileInp.value = "";                 // позволить повторно выбрать тот же файл
      if (!f) return;
      const ext = pickExt(f);
      if (!ext) { status("Формат не поддержан (нужно jpg/png/gif/webp).", true); return; }
      if (f.size > 8 * 1024 * 1024) { status("Файл больше 8 МБ — слишком крупно для коммита.", true); return; }
      const reader = new FileReader();
      reader.onerror = function () { status("Не удалось прочитать файл.", true); };
      reader.onload = function () {
        const res = String(reader.result || "");
        const b64 = res.slice(res.indexOf(",") + 1);
        if (!b64) { status("Пустой файл.", true); return; }
        const name = (imgOpt.artId || "image") + "." + ext;
        pendingImage = { name: name, mime: mimeOf(ext), b64: b64 };
        ta.value = setFmImage(ta.value, name);   // прописать строку image: во frontmatter
        refresh();
        status("Картинка выбрана: " + name + ". «Просмотр» покажет её, «Сохранить» — выложит.");
      };
      reader.readAsDataURL(f);
    });
    delBtn.addEventListener("click", function () {
      ta.value = removeFmImage(ta.value);
      pendingImage = null;
      refresh();
      status("Иллюстрация отвязана (файл в репозитории остаётся — «рукописи не горят»).");
    });
  }

  // невыложённую картинку рендер выдаёт как src="../img/<name>" (файла ещё нет) →
  // в превью подменяем на data:-URL выбранных байтов.
  function swapPreviewImage(html) {
    if (!pendingImage) return html;
    const dataUrl = "data:" + pendingImage.mime + ";base64," + pendingImage.b64;
    return html.split('"../img/' + pendingImage.name + '"').join('"' + dataUrl + '"');
  }

  return { close: close };
}

// В srcdoc-превью базовый URL = URL родительской (боевой) страницы, поэтому ссылка
// «#foo» резолвится в «<реальный .view.html>#foo» и КЛИК уводит iframe на боевой
// (старый) файл — оглавление/сноски/«↑ наверх» показывали бы СТАРУЮ версию вместо
// правки. Вшиваем в превью перехватчик: клик по a[href^="#"] → скролл ВНУТРИ превью.
var PREVIEW_NAV_SCRIPT =
  '<script>(function(){document.addEventListener("click",function(e){' +
  'var a=e.target.closest?e.target.closest(\'a[href^="#"]\'):null;if(!a)return;' +
  'e.preventDefault();var id=decodeURIComponent((a.getAttribute("href")||"").slice(1));' +
  'var t=id?document.getElementById(id):null;' +
  'if(t)t.scrollIntoView();else window.scrollTo(0,0);},true);})();<\/script>';
function injectPreviewNav(html) {
  return html.indexOf("</body>") >= 0
    ? html.replace("</body>", PREVIEW_NAV_SCRIPT + "</body>")
    : html + PREVIEW_NAV_SCRIPT;
}

// ── frontmatter image: чтение/установка/удаление строки (чистые функции) ───────
function fmBounds(text) {
  const m = /^---\n([\s\S]*?)\n---\n?/.exec(text);
  return m ? { inner: m[1], end: m[0].length } : null;
}
function getFmImage(text) {
  const b = fmBounds(text); if (!b) return "";
  const lm = /^[ \t]*image[ \t]*:[ \t]*(.*?)[ \t]*$/m.exec(b.inner);
  if (!lm) return "";
  let v = lm[1].trim();
  if ((v[0] === '"' && v.slice(-1) === '"') || (v[0] === "'" && v.slice(-1) === "'")) v = v.slice(1, -1);
  return v;
}
function setFmImage(text, name) {
  const b = fmBounds(text);
  if (!b) return "---\nimage: " + name + "\n---\n" + text.replace(/^\n+/, "");
  let inner = b.inner;
  if (/^[ \t]*image[ \t]*:.*$/m.test(inner)) inner = inner.replace(/^[ \t]*image[ \t]*:.*$/m, "image: " + name);
  else inner = inner.replace(/\s+$/, "") + "\nimage: " + name;
  return "---\n" + inner + "\n---\n" + text.slice(b.end);
}
function removeFmImage(text) {
  const b = fmBounds(text); if (!b) return text;
  const inner = b.inner.replace(/^[ \t]*image[ \t]*:.*\n?/m, "").replace(/\s+$/, "");
  return "---\n" + inner + "\n---\n" + text.slice(b.end);
}
function pickExt(file) {
  const t = (file.type || "").toLowerCase();
  if (t === "image/jpeg") return "jpg";
  if (t === "image/png") return "png";
  if (t === "image/gif") return "gif";
  if (t === "image/webp") return "webp";
  const m = /\.(jpe?g|png|gif|webp)$/i.exec(file.name || "");
  return m ? m[1].toLowerCase().replace("jpeg", "jpg") : "";
}
function mimeOf(ext) {
  return ext === "jpg" ? "image/jpeg" : ext === "png" ? "image/png"
    : ext === "gif" ? "image/gif" : ext === "webp" ? "image/webp" : "application/octet-stream";
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
  });
}

function injectStyles() {
  if (document.getElementById("ze-style")) return;
  const st = document.createElement("style");
  st.id = "ze-style";
  st.textContent =
    "html.ze-lock,html.ze-lock body{overflow:hidden!important;}" +
    "#ze-root{position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;" +
      "background:#1e1e1e;color:#e6e6e6;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;}" +
    "#ze-root .ze-bar{display:flex;align-items:center;gap:.5em;padding:.55em .8em;" +
      "background:#2a2a2a;border-bottom:1px solid #000;flex:0 0 auto;}" +
    "#ze-root .ze-title{font-weight:600;letter-spacing:.02em;}" +
    "#ze-root .ze-spacer{flex:1 1 auto;}" +
    "#ze-root .ze-imgbar{display:flex;align-items:center;gap:.5em;padding:.45em .8em;" +
      "background:#242424;border-bottom:1px solid #000;flex:0 0 auto;font-size:.92em;}" +
    "#ze-root .ze-imglabel{color:#9a9a9a;}" +
    "#ze-root .ze-imgname{color:#d8d8a0;font-family:ui-monospace,Consolas,monospace;}" +
    "#ze-root .ze-btn{font:inherit;color:#e6e6e6;background:#3a3a3a;border:1px solid #555;" +
      "border-radius:5px;padding:.35em .9em;cursor:pointer;}" +
    "#ze-root .ze-btn:hover{background:#454545;}" +
    "#ze-root .ze-btn:disabled{opacity:.5;cursor:default;}" +
    "#ze-root .ze-primary{background:#2d6cdf;border-color:#2d6cdf;color:#fff;}" +
    "#ze-root .ze-primary:hover{background:#3a78ea;}" +
    "#ze-root .ze-body{flex:1 1 auto;min-height:0;display:flex;}" +
    "#ze-root .ze-text{flex:1 1 auto;width:100%;border:0;resize:none;outline:none;" +
      "background:#1e1e1e;color:#e6e6e6;padding:1em 1.1em;" +
      "font:14px/1.6 ui-monospace,SFMono-Regular,Consolas,'Liberation Mono',monospace;" +
      "tab-size:2;white-space:pre-wrap;}" +
    "#ze-root .ze-prev{flex:1 1 auto;width:100%;border:0;background:#fff;}" +
    "#ze-root .ze-status{flex:0 0 auto;min-height:1.2em;padding:.3em .9em;background:#2a2a2a;" +
      "border-top:1px solid #000;font-size:.86em;color:#9bd39b;}" +
    "#ze-root .ze-status.ze-err{color:#ff8a8a;}" +
    "#ze-root .ze-hidden{display:none!important;}" +
    "#ze-pop{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;" +
      "justify-content:center;background:rgba(0,0,0,.5);}" +
    "#ze-pop .ze-pop-card{max-width:420px;margin:1em;background:#fff;color:#222;border-radius:10px;" +
      "padding:1.3em 1.5em;box-shadow:0 12px 40px rgba(0,0,0,.35);" +
      "font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;}" +
    "#ze-pop p{margin:0 0 .7em;}" +
    "#ze-pop .ze-pop-row{display:flex;gap:.6em;justify-content:flex-end;margin-top:1em;}" +
    "#ze-pop .ze-btn{font:inherit;border-radius:6px;padding:.4em 1em;cursor:pointer;border:1px solid #bbb;background:#f3f3f3;color:#222;}" +
    "#ze-pop .ze-primary{background:#2d6cdf;border-color:#2d6cdf;color:#fff;}";
  document.head.appendChild(st);
}
