// Interim ZML-preview access: in a section index, show an "Edit" button next to
// every article that already has a docs/art/<id>.zml (listed in art/zml-index.json).
// The button opens the read-only ZML preview (<id>.view.html, theme/width switcher).
// Grows automatically as more .zml are added; removed once migration completes
// (then the title link itself will point to the new format).
(function () {
  var st = document.createElement("style");
  st.textContent =
    ".edit-btn{display:inline-block;margin:0 10px;padding:1px 13px;border:1px solid #b0683c;" +
    "border-radius:14px;color:#b0683c;font-size:13px;line-height:1.7;text-decoration:none;" +
    "vertical-align:middle;transition:background .15s,color .15s;}" +
    ".edit-btn:hover,.edit-btn:focus{background:#b0683c;color:#fff;}";
  document.head.appendChild(st);

  fetch("../art/zml-index.json", { cache: "no-cache" })
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (list) {
      var have = {};
      (list || []).forEach(function (id) { have[id] = true; });
      document.querySelectorAll("ul.toc > li").forEach(function (li) {
        var link = li.querySelector('a[href*="/art/"]');
        if (!link) return;
        var m = link.getAttribute("href").match(/art\/([^\/]+)\.html(?:[?#].*)?$/);
        if (!m || !have[m[1]]) return;
        var btn = document.createElement("a");
        btn.className = "edit-btn";
        btn.href = "../art/" + m[1] + ".view.html";
        btn.textContent = "Edit";
        btn.title = "ZML-предпросмотр (новый формат)";
        link.insertAdjacentElement("afterend", btn);
      });
    })
    .catch(function () {});
})();
