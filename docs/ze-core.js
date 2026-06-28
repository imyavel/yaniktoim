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
  // Ф8(b2): картинки В ТЕКСТЕ (тег [img]). Источник истины «какие картинки и где» —
  // сами теги [img src=…] в textarea (их вставляют/удаляют кнопки панели и руки
  // оператора). pendingInline — выбранные, но ещё не сохранённые байты по имени файла
  // {name→{name,mime,b64}}; уходят в save() одним коммитом. Удаление = снять тег из
  // текста (файл в репозитории остаётся — «рукописи не горят»).
  const pendingInline = new Map();

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
  // Открываем В НАЧАЛЕ документа: каретку в 0 и скролл вверх (иначе браузер
  // оставляет textarea прокрученным к концу после установки value).
  try { ta.setSelectionRange(0, 0); } catch (e) {}
  ta.focus();
  ta.scrollTop = 0;
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
    guardThen(doShowPreview);
  }
  function doShowPreview() {
    let html;
    try { html = opts.renderView(ta.value); }
    catch (e) { status("Ошибка рендера: " + (e.message || e), true); return; }
    html = swapPreviewImage(html); // невыложённую картинку показываем как data:-URL
    html = injectPreviewBase(html, opts.previewBase); // см. ниже: база для ../themes/../img/…
    html = injectPreviewNav(html); // якоря #… скроллят ВНУТРИ превью, не уводят на боевой файл
    html = injectPreviewChrome(html); // в превью кнопка «Править» неактивна (мы уже в правке)
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

  // Заморозка индикативных полей (напр. `date` у сохранённой статьи): opts.checkIdentity
  // сверяет текущий ZML с baseline (тем, что на диске). Если поле менять нельзя — вернёт
  // {message, fix}; тогда показываем модалку-предупреждение, а по OK редактор сам
  // возвращает прежнее значение (fix) и действие продолжается. Нет хука / поле не тронуто
  // → сразу proceed. Новые статьи до первого сохранения правят date свободно.
  function guardThen(proceed) {
    if (typeof opts.checkIdentity !== "function") return proceed();
    let res;
    try { res = opts.checkIdentity(ta.value, baselineGet()); }
    catch (e) { return status("Проверка полей не пройдена: " + (e.message || e), true); }
    if (!res) return proceed();
    // Каретку/прокрутку запоминаем ДО переустановки value: ta.value=… сбрасывает курсор
    // в конец. Дата той же длины (ISO 10 симв.) → смещения после неё не плывут, каретка
    // садится на прежнее место.
    const ss = ta.selectionStart, se = ta.selectionEnd, top = ta.scrollTop;
    noticeModal(res.message, function () {
      try {
        const fixed = res.fix && res.fix(ta.value);
        if (typeof fixed === "string") ta.value = fixed;
      } catch (e) { /* fix упал — оставляем как есть */ }
      // По OK НЕ продолжаем действие (не уходим в просмотр/сохранение): вернули прежнее
      // значение и остаёмся на странице правки, с прежней кареткой и прокруткой.
      showEditor();
      const len = ta.value.length;
      try { ta.setSelectionRange(Math.min(ss, len), Math.min(se, len)); } catch (e) {}
      ta.scrollTop = top;
    });
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
    guardThen(doSaveCommit);
  }
  function doSaveCommit() {
    const src = ta.value;   // после возможной авто-починки индикативного поля (date)
    let html;
    try { html = opts.renderView(src); }
    catch (e) { status("Не сохраняю — ошибка рендера: " + (e.message || e), true); return; }
    if (typeof opts.save !== "function") { status("Сохранение не настроено.", true); return; }
    const zml = src;
    status("Сохранение…");
    setBusy(true);
    Promise.resolve()
      .then(function () {
        return opts.save(zml, html, {
          image: pendingImage ? { name: pendingImage.name, content: pendingImage.b64 } : null,
          images: pendingInline.size
            ? Array.from(pendingInline.values()).map(function (p) { return { name: p.name, content: p.b64 }; })
            : null,
        });
      })
      .then(function () {
        setBusy(false);
        baseline = zml;            // сохранено → нет «несохранённых правок»
        pendingImage = null;       // обложка закоммичена
        pendingInline.clear();     // картинки в тексте закоммичены
        // Деплой GitHub Pages идёт 30–90 с после коммита. Если вызывающий описал, что и
        // где проверять (opts.deployWait → {url, match?, onReady?}), показываем модалку-
        // ожидание со счётчиком секунд и кнопкой «ОК»: раз в пару секунд тянем целевой URL
        // и сравниваем с тем, что закоммитили; правка доехала → закрываем редактор и
        // обновляем страницу сами. «ОК» — перестать ждать (правка уже в репо, увидится по Ctrl+R).
        var dw = typeof opts.deployWait === "function" ? opts.deployWait(zml, html) : null;
        if (dw && dw.url) {
          // По умолчанию закрываем редактор и ждём на уже видимой странице (правка
          // СУЩЕСТВУЮЩЕЙ статьи — как сейчас). Если dw.keepEditorOpen (создание НОВОЙ
          // статьи) — окно ожидания висит прямо в редакторе, по готовности уходим на
          // созданную страницу; «Пропустить» тогда закрывает редактор.
          var keep = !!dw.keepEditorOpen;
          if (!keep) close();
          waitForDeploy({
            url: dw.url,
            match: typeof dw.match === "function" ? dw.match : function (text) { return text === html; },
            onReady: function () {
              if (keep) close();
              (typeof dw.onReady === "function" ? dw.onReady : function () { location.reload(); })();
            },
            onDismiss: function () {
              if (keep) close();
              if (typeof dw.onDismiss === "function") dw.onDismiss();
            }
          });
          return;
        }
        // Фолбэк (deployWait не задан): прежнее поведение — коротко подтвердить и закрыть.
        status("Сохранено ✓ — обновление сайта 30–90 с, затем Ctrl+R.");
        if (typeof opts.onSavedPrimary === "function") opts.onSavedPrimary();
        setTimeout(close, 900);
      })
      .catch(function (e) { setBusy(false); status("Сохранение не удалось: " + (e.message || e), true); });
  }

  function isDirty() { return ta.value !== baselineGet() || !!pendingImage || pendingInline.size > 0; }
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

  // Однокнопочная модалка-уведомление (OK). Мягкое предупреждение: показать, дождаться
  // OK, затем продолжить (onOk).
  function noticeModal(msg, onOk) {
    const m = document.createElement("div");
    m.id = "ze-pop";
    m.innerHTML = '<div class="ze-pop-card"><p>' + esc(msg) + '</p>' +
      '<div class="ze-pop-row">' +
        '<button type="button" class="ze-btn ze-primary" data-c="ok">OK</button>' +
      '</div></div>';
    document.body.appendChild(m);
    m.addEventListener("click", function (ev) {
      const b = ev.target.closest("[data-c]"); if (!b) return;
      m.parentNode.removeChild(m);
      if (typeof onOk === "function") onOk();
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

  // ── Ф8(b) панели картинок: «Обложка» (frontmatter image:) + «В тексте» ([img]) ──
  // Монтируются только при opts.image (даёт artId). Обе делят чтение/валидацию файла
  // (readPicked) и подмену в превью (swapPreviewImage).
  function setupImageBar() {
    // (1) Обложка — строка image: во frontmatter (картинка вверху статьи).
    const bar = document.createElement("div");
    bar.className = "ze-imgbar";
    bar.innerHTML =
      '<span class="ze-imglabel">Обложка:</span>' +
      '<span class="ze-imgname"></span>' +
      '<button type="button" class="ze-btn ze-imgpick">Загрузить…</button>' +
      '<button type="button" class="ze-btn ze-imgdel ze-hidden">Удалить</button>' +
      '<input type="file" class="ze-imgfile ze-hidden" accept="image/jpeg,image/png,image/gif,image/webp">' +
      '<span class="ze-imgsep" aria-hidden="true"></span>' +
      '<span class="ze-imglabel">В тексте:</span>' +
      '<span class="ze-inslist"></span>' +
      '<button type="button" class="ze-btn ze-insadd">+ Картинка…</button>' +
      '<input type="file" class="ze-insfile ze-hidden" accept="image/jpeg,image/png,image/gif,image/webp">';
    ui.querySelector(".ze-bar").insertAdjacentElement("afterend", bar);
    const nameEl = bar.querySelector(".ze-imgname");
    const pickBtn = bar.querySelector(".ze-imgpick");
    const delBtn = bar.querySelector(".ze-imgdel");
    const fileInp = bar.querySelector(".ze-imgfile");
    const listEl = bar.querySelector(".ze-inslist");
    const insFile = bar.querySelector(".ze-insfile");
    const addBtn = bar.querySelector(".ze-insadd");

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
      readPicked(f, function (ext, mime, b64) {
        const name = (imgOpt.artId || "image") + "." + ext;
        pendingImage = { name: name, mime: mime, b64: b64 };
        // image: (имя файла, всегда <art>.<ext>) + image_v: (хэш байтов). Имя при замене не
        // меняется → без версии HTML не менялся бы и браузер отдавал бы старый кэш; image_v
        // двигает ?v= у обложки в рендере, так что замена реально видна и детектится деплоем.
        ta.value = setFmImageVer(setFmImage(ta.value, name), hashB64(b64));
        refresh();
        status("Обложка выбрана: " + name + ". «Просмотр» покажет её, «Сохранить» — выложит.");
      });
    });
    delBtn.addEventListener("click", function () {
      ta.value = removeFmImageVer(removeFmImage(ta.value));   // снять и image:, и image_v:
      pendingImage = null;
      refresh();
      status("Обложка отвязана (файл в репозитории остаётся — «рукописи не горят»).");
    });

    // Картинки в тексте — теги [img src=…] (вторая группа той же панели). «+ Картинка…»
    // вставляет тег на месте каретки; у каждой картинки «Заменить…» (новые байты) и
    // «Удалить» (снять тег). Имена файлов — <artId>_N.<ext>, нумеруются автоматически.
    let pickMode = { mode: "add" };   // режим следующего выбора: add | replace(name)

    function refreshInline() {
      const tags = scanImgTags(ta.value);
      if (!tags.length) { listEl.innerHTML = '<span class="ze-insempty">— нет —</span>'; return; }
      listEl.innerHTML = tags.map(function (t) {
        const isNew = pendingInline.has(t.name);
        return '<span class="ze-inschip"><code>' + esc(t.name) + '</code>' +
          (isNew ? '<span class="ze-insnew" title="новая — не сохранена">●</span>' : "") +
          '<button type="button" class="ze-link" data-ins="replace" data-name="' + esc(t.name) + '">Заменить…</button>' +
          '<button type="button" class="ze-link" data-ins="del" data-name="' + esc(t.name) + '">Удалить</button>' +
          '</span>';
      }).join("");
    }
    refreshInline();
    ta.addEventListener("input", refreshInline);  // ручная правка тегов → список освежается

    addBtn.addEventListener("click", function () { pickMode = { mode: "add" }; insFile.click(); });
    bar.addEventListener("click", function (ev) {
      const b = ev.target.closest("[data-ins]"); if (!b) return;
      const name = b.getAttribute("data-name");
      if (b.getAttribute("data-ins") === "del") {
        ta.value = removeImgTag(ta.value, name);
        pendingInline.delete(name);
        refreshInline();
        status("Картинка «" + name + "» снята из текста (файл в репозитории остаётся).");
      } else {
        pickMode = { mode: "replace", name: name }; insFile.click();
      }
    });
    insFile.addEventListener("change", function () {
      const f = insFile.files && insFile.files[0];
      insFile.value = "";
      const mode = pickMode;
      readPicked(f, function (ext, mime, b64) {
        if (mode.mode === "replace") {
          const newName = String(mode.name).replace(/\.[^.]+$/, "") + "." + ext;
          ta.value = setImgSrc(ta.value, mode.name, newName);   // обновить src, если сменилось расширение
          if (newName !== mode.name) pendingInline.delete(mode.name);
          pendingInline.set(newName, { name: newName, mime: mime, b64: b64 });
          refreshInline();
          status("Картинка «" + newName + "» заменена. «Просмотр» покажет её, «Сохранить» — выложит.");
        } else {
          const newName = nextInlineName(ta.value, imgOpt.artId || "img", ext, Array.from(pendingInline.keys()));
          const ins = insertImgTag(ta.value, ta.selectionStart, newName);
          ta.value = ins.text;
          try { ta.setSelectionRange(ins.caret, ins.caret); } catch (e) {}
          pendingInline.set(newName, { name: newName, mime: mime, b64: b64 });
          refreshInline();
          status("Картинка «" + newName + "» вставлена в текст. Допишите alt/подпись (cap=) при желании.");
        }
      });
    });
  }

  // Прочитать выбранный файл-картинку: валидация формата/размера → cb(ext, mime, b64).
  function readPicked(f, cb) {
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
      cb(ext, mimeOf(ext), b64);
    };
    reader.readAsDataURL(f);
  }

  // невыложённые картинки (обложка + [img] в тексте) рендер выдаёт как
  // src="../img/<name>" (файла ещё нет) → в превью подменяем на data:-URL байтов.
  function swapPreviewImage(html) {
    const pend = [];
    if (pendingImage) pend.push(pendingImage);
    pendingInline.forEach(function (p) { pend.push(p); });
    for (const p of pend) {
      // src обложки может нести кэш-версию (?v=…) — матчим её опционально
      const rx = new RegExp('"\\.\\./img/' + p.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + '(?:\\?[^"]*)?"', "g");
      const data = '"data:' + p.mime + ";base64," + p.b64 + '"';
      html = html.replace(rx, function () { return data; });
    }
    return html;
  }

  return { close: close };
}

// ── Ожидание деплоя GitHub Pages после сохранения ─────────────────────────────
// Коммит уходит мгновенно, но публичный сайт обновляется через 30–90 с (сборка
// Pages). Показываем модалку «Ожидаем обновление сайта…» со счётчиком прошедших
// секунд и кнопкой «ОК», и раз в пару секунд тянем целевой URL (cache-bust + no-store,
// чтобы не словить кэш CDN/браузера) — как только отданный сайтом текст совпал с тем,
// что мы закоммитили, правка доехала: onReady (обычно reload/переход на страницу).
// «ОК» — перестать ждать (onDismiss); правка уже в репо, увидится позже по Ctrl+R.
//   opts: { url, match(text)->bool, onReady(), onDismiss(), intervalMs }
export function waitForDeploy(opts) {
  opts = opts || {};
  injectStyles();
  const url = String(opts.url || "");
  const match = typeof opts.match === "function" ? opts.match : function () { return false; };
  const intervalMs = opts.intervalMs > 0 ? opts.intervalMs : 2000;
  const startedAt = Date.now();
  let finished = false, pollTimer = null, tickTimer = null;

  const m = document.createElement("div");
  m.id = "ze-pop";
  m.innerHTML =
    '<div class="ze-pop-card ze-wait-card">' +
      '<p><b>Ожидаем обновление сайта…</b></p>' +
      '<p class="ze-wait-line">Прошло <span class="ze-wait-sec">0</span>&nbsp;с. ' +
        'Страница обновится сама, как только правка появится на сайте.</p>' +
      '<p class="ze-wait-note ze-hidden">Дольше обычного — можно нажать «Пропустить» и ' +
        'обновить страницу позже вручную (Ctrl+R).</p>' +
      '<div class="ze-pop-row">' +
        '<button type="button" class="ze-btn ze-primary" data-w="ok">Пропустить</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(m);
  const secEl = m.querySelector(".ze-wait-sec");
  const noteEl = m.querySelector(".ze-wait-note");

  function teardown() {
    finished = true;
    if (pollTimer) clearTimeout(pollTimer);
    if (tickTimer) clearInterval(tickTimer);
    if (m.parentNode) m.parentNode.removeChild(m);
  }
  function ready() { if (finished) return; teardown(); if (typeof opts.onReady === "function") opts.onReady(); }
  function dismiss() { if (finished) return; teardown(); if (typeof opts.onDismiss === "function") opts.onDismiss(); }

  tickTimer = setInterval(function () {
    const s = Math.round((Date.now() - startedAt) / 1000);
    if (secEl) secEl.textContent = String(s);
    if (s >= 120 && noteEl) noteEl.classList.remove("ze-hidden");   // дольше обычного — подсказать про ручное обновление
  }, 1000);

  function poll() {
    if (finished) return;
    const bust = url + (url.indexOf("?") < 0 ? "?" : "&") + "_dz=" + Date.now();   // обойти кэш CDN/браузера
    fetch(bust, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (text) {
        if (finished) return;
        if (text != null && match(text)) { ready(); return; }
        pollTimer = setTimeout(poll, intervalMs);
      })
      .catch(function () { if (!finished) pollTimer = setTimeout(poll, intervalMs); });
  }
  pollTimer = setTimeout(poll, 500);   // первый опрос почти сразу (правка без изменений уже «доехала»)

  m.addEventListener("click", function (ev) { if (ev.target.closest('[data-w="ok"]')) dismiss(); });
  return { close: dismiss };
}

// ── Свежесть сессии + модальный логин (общий гейт для редакторов) ─────────────
// Перед открытием редактора убеждаемся, что токен не протух: его `exp` (unix-сек)
// зашит в сам токен → читаем локально, без сети. Свежий → resolve(session) сразу.
// Протух/нет токена → показываем модальное окно входа (тот же worker /api/login,
// что и на главной); при успехе обновляем localStorage("ya_session") и резолвим
// свежую сессию. Отмена/Esc → resolve(null): вызывающий редактор НЕ открывает.
// marginSec — запас (деф. 300с): если до истечения меньше, тоже просим перелогин,
// чтобы правка не упёрлась в 401 на «Сохранить».
export function ensureFreshSession(opts) {
  opts = opts || {};
  const worker = String(opts.worker || "").replace(/\/+$/, "");
  const marginSec = opts.marginSec != null ? opts.marginSec : 300;
  const sess = readSession();
  if (sess && sess.token && sessionFresh(sess.token, marginSec)) return Promise.resolve(sess);
  return loginModal({
    worker: worker, prefillNick: sess && sess.nick,
    title: opts.title || "Сессия входа истекла",
    message: opts.message || "Войдите снова, чтобы продолжить правку.",
  });
}

function readSession() {
  try { return JSON.parse(localStorage.getItem("ya_session") || "null"); }
  catch (e) { return null; }
}
// exp зашит в payload токена «<b64url(json)>.<sig>». Берём только число exp — оно
// ASCII, поэтому регэксп по atob-строке надёжен и без utf8-возни вокруг ника.
function tokenExp(token) {
  try {
    let body = String(token).split(".")[0];
    if (!body) return null;
    body = body.replace(/-/g, "+").replace(/_/g, "/");
    while (body.length % 4) body += "=";
    const m = /"exp"\s*:\s*(\d+)/.exec(atob(body));
    return m ? parseInt(m[1], 10) : null;
  } catch (e) { return null; }
}
function sessionFresh(token, marginSec) {
  const exp = tokenExp(token);
  if (exp == null) return false;            // exp не распарсили → считаем несвежим (перелогин безопаснее)
  return exp > (Date.now() / 1000) + marginSec;
}

// Модальное окно входа (общее: «Управление» на главной, «Править» на статье,
// перелогин при протухшей сессии). opts.title/opts.message переопределяют текст.
// При успехе пишет ya_session в localStorage и резолвит {token,nick,role};
// Отмена/Esc → resolve(null).
export function loginModal(opts) {
  opts = opts || {};
  injectStyles();                           // #ze-pop стили могут быть ещё не вставлены (редактор не монтировался)
  return new Promise(function (resolve) {
    const worker = String(opts.worker || "").replace(/\/+$/, "");
    const m = document.createElement("div");
    m.id = "ze-pop";
    m.innerHTML =
      '<div class="ze-pop-card">' +
        '<p><b>' + esc(opts.title || "Вход") + '</b></p>' +
        '<p>' + esc(opts.message || "Введите ник и пароль.") + '</p>' +
        '<div class="ze-login-row"><input class="ze-login-nick" type="text" placeholder="ник" autocomplete="username"></div>' +
        '<div class="ze-login-row"><input class="ze-login-pass" type="password" placeholder="пароль" autocomplete="current-password"></div>' +
        '<div class="ze-login-msg" aria-live="polite"></div>' +
        '<div class="ze-pop-row">' +
          '<button type="button" class="ze-btn" data-l="cancel">Отмена</button>' +
          '<button type="button" class="ze-btn ze-primary" data-l="login">Войти</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(m);
    const nick = m.querySelector(".ze-login-nick");
    const pass = m.querySelector(".ze-login-pass");
    const msg = m.querySelector(".ze-login-msg");
    const loginBtn = m.querySelector('[data-l="login"]');
    if (opts.prefillNick) { nick.value = opts.prefillNick; pass.focus(); } else nick.focus();

    function done(result) { if (m.parentNode) m.parentNode.removeChild(m); resolve(result); }
    function setDisabled(on) { loginBtn.disabled = on; nick.disabled = on; pass.disabled = on; }
    function submit() {
      const n = nick.value.trim(), p = pass.value;
      if (!n || !p) { msg.textContent = "Введите ник и пароль."; return; }
      if (!worker) { msg.textContent = "Не задан адрес сервера входа."; return; }
      msg.textContent = ""; setDisabled(true);
      fetch(worker + "/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nick: n, password: p })
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok || !res.d || !res.d.token) throw new Error((res.d && res.d.error) || "ошибка входа");
          const s = { token: res.d.token, nick: res.d.nick, role: res.d.role };
          try { localStorage.setItem("ya_session", JSON.stringify(s)); } catch (e) {}
          done(s);
        })
        .catch(function (e) { setDisabled(false); msg.textContent = (e && e.message) || "ошибка входа"; pass.focus(); pass.select(); });
    }
    m.addEventListener("click", function (ev) {
      const b = ev.target.closest("[data-l]"); if (!b) return;
      if (b.getAttribute("data-l") === "login") submit(); else done(null);
    });
    m.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") { ev.preventDefault(); submit(); }
      else if (ev.key === "Escape") { ev.preventDefault(); done(null); }
    });
  });
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

// В превью мы УЖЕ внутри редактора → кнопка «✎ Править» (её оживляет ya-edit.js
// внутри iframe) не нужна и не должна быть кликабельной. Прячем её стилем
// (перебивает снятие [hidden] скриптом). Якоря/скролл превью не трогаем.
var PREVIEW_CHROME_STYLE = "<style>.viewbar .vb-edit{display:none!important;}</style>";
function injectPreviewChrome(html) {
  return html.indexOf("</head>") >= 0
    ? html.replace("</head>", PREVIEW_CHROME_STYLE + "</head>")
    : PREVIEW_CHROME_STYLE + html;
}

// srcdoc-превью резолвит относительные пути (../themes/<тема>.css, ../img/…, ../editor/,
// ../config/) от URL РОДИТЕЛЬСКОЙ страницы. У правки статьи родитель = docs/art/NNN.html,
// и пути сходятся сами. У создания статьи родитель = docs/structure.html → ../themes
// уходит в корень репо и оформление темы не подхватывается. opts.previewBase (абсолютный
// URL каталога art/) вставляет <base> ПЕРВЫМ в <head>, чтобы все относительные ссылки вью
// резолвились как из docs/art/. Без previewBase (правка статьи) ничего не вставляем.
function injectPreviewBase(html, base) {
  if (!base) return html;
  var tag = '<base href="' + esc(base) + '">';
  if (html.indexOf("<head>") >= 0) return html.replace("<head>", "<head>" + tag);
  if (html.indexOf("</head>") >= 0) return html.replace("</head>", tag + "</head>");
  return tag + html;
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
// image_v — кэш-версия обложки (хэш байтов): render добавляет её как ?v= к src обложки
// и og:image, чтобы замена картинки С ТЕМ ЖЕ ИМЕНЕМ была видна (не залипала в кэше) и
// меняла HTML (тогда детектор деплоя её ловит). Зеркало set/removeFmImage для ключа image_v.
function setFmImageVer(text, ver) {
  const b = fmBounds(text);
  if (!b) return "---\nimage_v: " + ver + "\n---\n" + text.replace(/^\n+/, "");
  let inner = b.inner;
  if (/^[ \t]*image_v[ \t]*:.*$/m.test(inner)) inner = inner.replace(/^[ \t]*image_v[ \t]*:.*$/m, "image_v: " + ver);
  else inner = inner.replace(/\s+$/, "") + "\nimage_v: " + ver;
  return "---\n" + inner + "\n---\n" + text.slice(b.end);
}
function removeFmImageVer(text) {
  const b = fmBounds(text); if (!b) return text;
  const inner = b.inner.replace(/^[ \t]*image_v[ \t]*:.*\n?/m, "").replace(/\s+$/, "");
  return "---\n" + inner + "\n---\n" + text.slice(b.end);
}
// Короткий детерминированный хэш байтов картинки (FNV-1a 32-бит по base64) → 8 hex.
// Не криптостойкий — нужен лишь как кэш-версия: одинаковые байты → один хэш (идемпотентно),
// разные → разный ?v=. Math.imul даёт точное 32-битное умножение.
function hashB64(s) {
  let h = 0x811c9dc5 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return ("0000000" + h.toString(16)).slice(-8);
}

// ── inline-картинки [img src=…]: чтение/вставка/замена/удаление (чистые функции) ─
// Зеркало IMG_RX рендера: кавыч-сегменты глотаются целиком (`]` внутри cap="…" не рвёт тег).
function imgSrcOfAttrs(s) {
  s = String(s).trim();
  let m = /^=(?:"([^"]*)"|([^\s\]"]+))/.exec(s);              // короткая форма [img="имя"]
  if (m) return (m[1] !== undefined ? m[1] : m[2]).trim();
  m = /(?:^|\s)src=(?:"([^"]*)"|([^\s\]"]+))/.exec(s);        // src=имя (кавыч/голый)
  if (m) return (m[1] !== undefined ? m[1] : m[2]).trim();
  return "";
}
// Все теги [img …] (по одному на строке) → [{name, start, end}] в порядке появления
// (start/end — границы строки тега в text, без завершающего \n).
function scanImgTags(text) {
  const out = [];
  const rx = /^[ \t]*\[img\b((?:"[^"]*"|[^\]"])*)\][ \t]*$/gm;
  let m;
  while ((m = rx.exec(text)) !== null) {
    const name = imgSrcOfAttrs(m[1] || "");
    if (name) out.push({ name: name, start: m.index, end: m.index + m[0].length });
    if (rx.lastIndex === m.index) rx.lastIndex++;              // страховка от пустого матча
  }
  return out;
}
function escapeReLite(s) { return String(s).replace(/[.*+?^${}()|[\]\\-]/g, "\\$&"); }
// Следующее свободное имя <artId>_N.<ext> (N = max существующих +1; учитываются и теги
// в тексте, и уже выбранные, но не сохранённые имена).
function nextInlineName(text, artId, ext, pendingNames) {
  const used = new Set(pendingNames || []);
  scanImgTags(text).forEach(function (t) { used.add(t.name); });
  const rx = new RegExp("^" + escapeReLite(artId) + "_(\\d+)\\.", "i");
  let max = 0;
  used.forEach(function (n) { const mm = rx.exec(n); if (mm) max = Math.max(max, parseInt(mm[1], 10)); });
  return artId + "_" + (max + 1) + "." + ext;
}
// Вставить тег [img src=NAME alt=""] отдельным блоком на месте каретки (пустые строки
// вокруг — правило блока ZML §1). → {text, caret}.
function insertImgTag(text, selStart, name) {
  const pos = typeof selStart === "number" ? selStart : text.length;
  const tag = '[img src=' + name + ' alt=""]';
  const b = text.slice(0, pos).replace(/[ \t]+$/, "");
  const a = text.slice(pos).replace(/^[ \t]+/, "");
  const lead = b === "" ? "" : (b.endsWith("\n\n") ? "" : b.endsWith("\n") ? "\n" : "\n\n");
  const trail = a === "" ? "\n" : (a.startsWith("\n\n") ? "" : a.startsWith("\n") ? "\n" : "\n\n");
  return { text: b + lead + tag + trail + a, caret: (b + lead + tag).length };
}
// Снять тег [img …] с данным именем (вместе со своей строкой); схлопнуть 3+ \n до 2.
function removeImgTag(text, name) {
  const t = scanImgTags(text).find(function (x) { return x.name === name; });
  if (!t) return text;
  const after = (t.end < text.length && text[t.end] === "\n") ? t.end + 1 : t.end;
  return (text.slice(0, t.start) + text.slice(after)).replace(/\n{3,}/g, "\n\n");
}
// Переназначить файл тега [img …] (oldName→newName) — литеральная замена имени ВНУТРИ
// самого тега (имя уникально). Для «Заменить…» при смене расширения.
function setImgSrc(text, oldName, newName) {
  if (oldName === newName) return text;
  const t = scanImgTags(text).find(function (x) { return x.name === oldName; });
  if (!t) return text;
  const seg = text.slice(t.start, t.end).split(oldName).join(newName);
  return text.slice(0, t.start) + seg + text.slice(t.end);
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
    "#ze-root .ze-imgbar{display:flex;flex-wrap:wrap;align-items:center;gap:.5em;padding:.45em .8em;" +
      "background:#242424;border-bottom:1px solid #000;flex:0 0 auto;font-size:.92em;}" +
    "#ze-root .ze-imglabel{color:#9a9a9a;}" +
    "#ze-root .ze-imgname{color:#d8d8a0;font-family:ui-monospace,Consolas,monospace;}" +
    "#ze-root .ze-imgsep{align-self:stretch;width:1px;background:#444;margin:.1em .35em;}" +
    "#ze-root .ze-inslist{display:flex;flex-wrap:wrap;gap:.4em;align-items:center;}" +
    "#ze-root .ze-insempty{color:#777;}" +
    "#ze-root .ze-inschip{display:inline-flex;align-items:center;gap:.4em;background:#2f2f2f;" +
      "border:1px solid #444;border-radius:5px;padding:.12em .55em;}" +
    "#ze-root .ze-inschip code{color:#d8d8a0;font-family:ui-monospace,Consolas,monospace;}" +
    "#ze-root .ze-insnew{color:#9bd39b;font-size:.85em;}" +
    "#ze-root .ze-link{background:none;border:0;color:#7db4ff;cursor:pointer;font:inherit;" +
      "font-size:.9em;padding:0;text-decoration:underline;}" +
    "#ze-root .ze-link:hover{color:#a9ccff;}" +
    "#ze-root .ze-link:disabled{opacity:.5;cursor:default;}" +
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
    "#ze-pop .ze-primary{background:#2d6cdf;border-color:#2d6cdf;color:#fff;}" +
    "#ze-pop .ze-login-row{margin:.5em 0;}" +
    "#ze-pop .ze-login-row input{width:100%;box-sizing:border-box;font:inherit;padding:.45em .6em;" +
      "border:1px solid #bbb;border-radius:6px;background:#fff;color:#222;}" +
    "#ze-pop .ze-login-msg{min-height:1.1em;color:#b00;font-size:.9em;}" +
    "#ze-pop .ze-hidden{display:none!important;}" +
    "#ze-pop .ze-wait-card .ze-wait-sec{font-weight:700;font-variant-numeric:tabular-nums;}" +
    "#ze-pop .ze-wait-card .ze-wait-note{color:#b00;font-size:.9em;}";
  document.head.appendChild(st);
}
