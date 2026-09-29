// [aud] — плеер аудио-плашек статьи (ZML3 §2.8). Разметку даёт render.js::renderAud,
// вид — ya-aud.css. Подключается только статьями с блоком [aud].
//
// Один общий <audio> на страницу: его «разблокирует» первое нажатие читателя, после
// чего смена src и play() из обработчика ended разрешены и на iOS — так запись сама
// переходит к следующей в блоке. Клики — делегированием с document, новые плашки
// (перерисовка в редакторе) подхватывает MutationObserver: привязок к узлам нет.
(function () {
  "use strict";
  if (window.__yaAud) return;
  window.__yaAud = true;

  var BAR = 3, GAP = 2, PEAK_MAX = 31, SEEK_STEP = 5, WARM_BEFORE = 20;
  var A = new Audio();
  A.preload = "auto";
  var cur = null;        // играющая/выбранная плашка (.zaud-item)
  var pendingSeek = null; // позиция, которую надо выставить после loadedmetadata
  var rafId = 0;
  var warm = null;       // подогрев следующей записи (держим ссылку, чтобы не собрал GC)
  var peaksOf = new WeakMap();

  function fmt(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    var h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
    return (h ? h + ":" + (m < 10 ? "0" : "") : "") + m + ":" + (s < 10 ? "0" : "") + s;
  }
  function durOf(it) {
    if (it === cur && isFinite(A.duration) && A.duration > 0) return A.duration;
    return parseFloat(it.getAttribute("data-dur")) || 0;
  }
  function posOf(it) {
    if (it === cur && pendingSeek === null) return A.currentTime || 0;
    if (it === cur) return pendingSeek;
    return parseFloat(it.getAttribute("data-pos")) || 0;
  }
  function siblings(it) {
    var g = it.closest(".zaud");
    return g ? Array.prototype.slice.call(g.querySelectorAll(".zaud-item")) : [it];
  }
  function neighbour(it, step) {
    var list = siblings(it);
    return list[list.indexOf(it) + step] || null;
  }

  // ── вид ────────────────────────────────────────────────────────────────────
  function paint(it) {
    var d = durOf(it), t = Math.min(posOf(it), d || Infinity);
    var wave = it.querySelector(".zaud-wave"), time = it.querySelector(".zaud-time");
    if (wave) {
      wave.style.setProperty("--p", (d ? Math.min(100, t / d * 100) : 0).toFixed(2) + "%");
      wave.setAttribute("aria-valuemax", String(Math.round(d)));
      wave.setAttribute("aria-valuenow", String(Math.round(t)));
      wave.setAttribute("aria-valuetext", fmt(t) + " из " + fmt(d));
    }
    if (time) {
      var txt = (it === cur || t > 0) ? fmt(t) + " / " + fmt(d) : (d ? fmt(d) : "");
      if (time.textContent !== txt) time.textContent = txt;
    }
  }
  function drawWave(it) {
    var wave = it.querySelector(".zaud-wave");
    if (!wave) return;
    var w = Math.floor(wave.clientWidth), h = Math.floor(wave.clientHeight) || 24;
    if (!w) return;
    var peaks = peaksOf.get(it) || null;
    var n = Math.max(1, Math.floor((w + GAP) / (BAR + GAP)));
    var rects = "";
    for (var i = 0; i < n; i++) {
      var v = 0.22; // нет волны (ещё грузится / нет .json) — ровные низкие столбики
      if (peaks && peaks.length) {
        var a = Math.floor(i * peaks.length / n);
        var b = Math.max(a + 1, Math.floor((i + 1) * peaks.length / n));
        v = 0;
        for (var k = a; k < b && k < peaks.length; k++) v = Math.max(v, peaks[k]);
        v = v / PEAK_MAX;
      }
      var bh = Math.max(3, Math.round(v * h));
      rects += '<rect x="' + i * (BAR + GAP) + '" y="' + ((h - bh) / 2) + '" width="' + BAR +
               '" height="' + bh + '" rx="1.5"/>';
    }
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h +
              '" viewBox="0 0 ' + w + " " + h + '">' + rects + "</svg>";
    var url = 'url("data:image/svg+xml,' + encodeURIComponent(svg) + '")';
    wave.style.webkitMaskImage = url;
    wave.style.maskImage = url;
    wave.classList.add("is-ready");
  }
  function loadPeaks(it) {
    var src = it.getAttribute("data-src") || "";
    var json = src.replace(/\.[A-Za-z0-9]+$/, ".json");
    if (!window.fetch || json === src) return;
    fetch(json).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j || !Array.isArray(j.peaks)) return;
      peaksOf.set(it, j.peaks);
      if (!it.getAttribute("data-dur") && j.dur) it.setAttribute("data-dur", String(j.dur));
      drawWave(it);
      paint(it);
    }).catch(function () {});
  }
  var ro = window.ResizeObserver ? new ResizeObserver(function (entries) {
    entries.forEach(function (e) { drawWave(e.target); });
  }) : null;
  function setup(it) {
    if (it.__zaud) return;
    it.__zaud = true;
    drawWave(it);
    paint(it);
    loadPeaks(it);
    if (ro) ro.observe(it);
  }
  function scan() {
    Array.prototype.forEach.call(document.querySelectorAll(".zaud-item"), setup);
    if (cur && !document.documentElement.contains(cur)) { A.pause(); cur = null; }
  }

  // ── воспроизведение ────────────────────────────────────────────────────────
  function tick() {
    if (cur) paint(cur);
    rafId = (cur && !A.paused) ? requestAnimationFrame(tick) : 0;
  }
  function park(it) {           // уходим с плашки: запомнить позицию, снять состояние
    it.setAttribute("data-pos", String(A.ended ? 0 : (A.currentTime || 0)));
    it.classList.remove("is-active", "is-playing", "is-loading");
  }
  function start(it, pos) {
    if (cur && cur !== it) { var old = cur; park(old); cur = null; paint(old); }
    if (cur !== it) {
      cur = it;
      pendingSeek = (pos != null) ? pos : (parseFloat(it.getAttribute("data-pos")) || 0);
      it.classList.remove("is-error");
      it.classList.add("is-active", "is-loading");
      A.src = new URL(it.getAttribute("data-src"), document.baseURI).href;
      announce(it);
    } else if (pos != null) {
      seek(pos);
    }
    var p = A.play();
    if (p && p.catch) p.catch(function () { if (cur === it) it.classList.remove("is-loading"); });
  }
  function seek(t) {
    if (!cur) return;
    var d = durOf(cur);
    t = Math.max(0, d ? Math.min(t, d - 0.05) : t);
    if (A.readyState >= 1) { pendingSeek = null; A.currentTime = t; }
    else pendingSeek = t;
    paint(cur);
  }
  function toggle(it) {
    if (it === cur && !A.paused) A.pause();
    else start(it, null);
  }
  function announce(it) {
    if (!("mediaSession" in navigator) || !window.MediaMetadata) return;
    var cap = it.querySelector(".zaud-cap");
    var h1 = document.getElementById("article-title");
    var list = siblings(it);
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: (cap && cap.textContent.trim()) ||
               ((h1 ? h1.textContent.trim() : document.title) + " — " + (list.indexOf(it) + 1) + "/" + list.length),
        artist: "Путь Восходящей Звезды"
      });
      navigator.mediaSession.setActionHandler("previoustrack", neighbour(it, -1) ? function () { start(neighbour(it, -1), 0); } : null);
      navigator.mediaSession.setActionHandler("nexttrack", neighbour(it, 1) ? function () { start(neighbour(it, 1), 0); } : null);
    } catch (e) {}
  }

  A.addEventListener("loadedmetadata", function () {
    if (!cur) return;
    if (isFinite(A.duration) && A.duration > 0) cur.setAttribute("data-dur", String(A.duration));
    if (pendingSeek !== null) {
      var t = pendingSeek; pendingSeek = null;
      if (t > 0) A.currentTime = Math.min(t, Math.max(0, A.duration - 0.05));
    }
    paint(cur);
  });
  A.addEventListener("playing", function () {
    if (!cur) return;
    cur.classList.remove("is-loading");
    cur.classList.add("is-playing");
    if (!rafId) rafId = requestAnimationFrame(tick);
  });
  A.addEventListener("waiting", function () { if (cur) cur.classList.add("is-loading"); });
  A.addEventListener("pause", function () {
    if (!cur) return;
    cur.classList.remove("is-playing", "is-loading");
    paint(cur);
  });
  A.addEventListener("timeupdate", function () {
    if (!cur) return;
    if (!rafId) paint(cur);
    // подогреть следующую запись незадолго до конца — переход без паузы
    var d = durOf(cur), next = neighbour(cur, 1);
    if (next && d && d - A.currentTime < WARM_BEFORE && !next.__zaudWarm) {
      next.__zaudWarm = true;
      warm = new Audio();
      warm.preload = "auto";
      warm.src = new URL(next.getAttribute("data-src"), document.baseURI).href;
    }
  });
  A.addEventListener("ended", function () {
    if (!cur) return;
    var done = cur, next = neighbour(done, 1);
    done.setAttribute("data-pos", "0");
    if (next) { start(next, 0); return; }
    // конец блока: плашка остаётся выбранной, позиция — в начало
    pendingSeek = 0;
    done.classList.remove("is-playing", "is-loading");
    paint(done);
  });
  A.addEventListener("error", function () {
    if (!cur) return;
    cur.classList.remove("is-playing", "is-loading");
    cur.classList.add("is-error");
    cur.title = "Не удалось загрузить запись";
  });

  // ── управление ─────────────────────────────────────────────────────────────
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".zaud-btn");
    if (!btn) return;
    var it = btn.closest(".zaud-item");
    if (it) { e.preventDefault(); setup(it); toggle(it); }
  });

  var drag = null; // {it, wave}
  function ratio(wave, e) {
    var r = wave.getBoundingClientRect();
    return r.width ? Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) : 0;
  }
  document.addEventListener("pointerdown", function (e) {
    var wave = e.target.closest && e.target.closest(".zaud-wave");
    if (!wave || (e.button != null && e.button !== 0)) return;
    var it = wave.closest(".zaud-item");
    if (!it) return;
    setup(it);
    drag = { it: it, wave: wave };
    try { wave.setPointerCapture(e.pointerId); } catch (err) {}
    var t = ratio(wave, e) * durOf(it);
    if (it === cur) seek(t); else start(it, t);   // нажатие на волну чужой плашки — играть с этого места
  });
  document.addEventListener("pointermove", function (e) {
    if (drag && drag.it === cur) seek(ratio(drag.wave, e) * durOf(cur));
  });
  function drop() { drag = null; }
  document.addEventListener("pointerup", drop);
  document.addEventListener("pointercancel", drop);

  document.addEventListener("keydown", function (e) {
    var wave = e.target.closest && e.target.closest(".zaud-wave");
    if (!wave) return;
    var it = wave.closest(".zaud-item");
    if (!it) return;
    var d = durOf(it), t = posOf(it), to = null;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") to = t + SEEK_STEP;
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") to = t - SEEK_STEP;
    else if (e.key === "Home") to = 0;
    else if (e.key === "End") to = d;
    else if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(it); return; }
    if (to === null) return;
    e.preventDefault();
    to = Math.max(0, d ? Math.min(to, d) : to);
    if (it === cur) seek(to);
    else { it.setAttribute("data-pos", String(to)); paint(it); }
  });

  scan();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", scan);
  if (window.MutationObserver) {
    var t = 0;
    new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var n = muts[i].target;
        if (n.closest && n.closest(".zaud-item")) continue; // своя же перерисовка времени
        clearTimeout(t);
        t = setTimeout(scan, 80);
        return;
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
