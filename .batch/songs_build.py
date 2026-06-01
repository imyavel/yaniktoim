# -*- coding: utf-8 -*-
import json, os, html
B = r"C:\Users\admin\yaniktoim\.batch"
data = json.load(open(os.path.join(B, "songs_data.json"), encoding="utf-8"))
arts = json.load(open(os.path.join(B, "art_titles.json"), encoding="utf-8"))
FALLBACK = {"KgW0tSoggBk":"Run DMC — It's like that","XS088Opj9o0":"Madonna — Frozen",
            "ORrzn7AhwgA":"БГ — Не было такой и не будет","rJpPqSXw3Tw":"Константин Кинчев — Мама"}
for k, t in FALLBACK.items():
    if k in data and not data[k]["title"]: data[k]["title"] = t

def esc(s): return html.escape(s or "", quote=True)
rows = sorted(data.items(), key=lambda kv: (-len(kv[1]["arts"]), kv[1]["title"].lower()))
def plural(n):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11: return "композиция"
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14: return "композиции"
    return "композиций"
NWORD = "%d %s" % (len(rows), plural(len(rows)))

cards = []
for vid, info in rows:
    title = esc(info["title"] or vid)
    links = []
    for a in info["arts"]:
        nm = arts.get(a, a)
        links.append('<a href="../art/%s.html">%s</a>' % (esc(a), esc(nm)))
    arts_html = ' <span class="sep">♪</span> '.join(links)
    cards.append(
'''    <figure class="song">
      <div class="yt" data-id="{vid}" role="button" tabindex="0" aria-label="Включить: {title}"
           style="background-image:url(https://i.ytimg.com/vi/{vid}/hqdefault.jpg)">
        <span class="play"></span>
      </div>
      <figcaption>
        <p class="t">{title}</p>
        <p class="a">{arts}</p>
      </figcaption>
    </figure>'''.format(vid=esc(vid), title=title, arts=arts_html))

PAGE = '''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Песнь Ступеней — Путь Восходящей Звезды</title>
<meta name="description" content="Песнь Ступеней — вся музыка корпуса «Путь Восходящей Звезды»: {n} композиций со ссылками на статьи.">
<meta property="og:title" content="Песнь Ступеней">
<meta property="og:type" content="website">
<link rel="icon" href="../favicon.ico" sizes="any">
<link rel="icon" type="image/png" href="../img/favicon.png">
<link rel="stylesheet" href="../style.css?v=20260531-02">
<style>
  /* широкоформат для этой страницы */
  .wrap{{max-width:1340px}}
  @media(min-width:1500px){{.wrap{{max-width:1480px}}}}
  .song-intro{{color:var(--muted);margin:.2em 0 1.6em;font-size:1.06rem}}
  .songgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:30px}}
  @media(max-width:1000px){{.songgrid{{grid-template-columns:repeat(2,1fr)}}}}
  @media(max-width:640px){{.songgrid{{grid-template-columns:1fr}}}}
  .song{{margin:0;background:var(--card);border:2px solid var(--border);border-radius:14px;
        overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);display:flex;flex-direction:column;
        transition:box-shadow .15s,border-color .15s}}
  .song:hover{{box-shadow:0 4px 16px rgba(0,0,0,.13);border-color:var(--accent)}}
  .song .yt{{position:relative;aspect-ratio:16/9;background-size:cover;background-position:center;
        cursor:pointer;background-color:#000}}
  .song .yt .play{{position:absolute;inset:0;margin:auto;width:80px;height:56px;
        background:rgba(20,20,20,.78);border-radius:14px;transition:background .15s}}
  .song .yt .play::after{{content:"";position:absolute;top:50%;left:50%;
        transform:translate(-38%,-50%);border-style:solid;border-width:14px 0 14px 23px;
        border-color:transparent transparent transparent #fff}}
  .song .yt:hover .play{{background:#cc0000}}
  .song .yt iframe{{position:absolute;inset:0;width:100%;height:100%;border:0}}
  .wrap h1{{font-size:2.9rem;line-height:1.1;margin:.1em 0 .15em}}
  .song figcaption{{padding:15px 18px 18px}}
  .song .t{{margin:0 0 .5em;font-weight:bold;font-size:1.22rem;line-height:1.25}}
  .song .a{{margin:0;font-size:.92rem;line-height:1.6;color:var(--muted);
        font-family:"Book Antiqua","Palatino Linotype",Palatino,"URW Palladio L",Georgia,serif}}
  .song .a a{{color:#45203c;text-decoration:none;border-bottom:1px solid transparent}}
  .song .a a:hover{{border-bottom-color:#45203c}}
  .song .a .sep{{color:#d98a00;font-size:1.05em;padding:0 .12em;vertical-align:-.04em}}
</style>
</head>
<body>
<div class="wrap">
<header class="breadcrumbs"><a href="../index.html">Главная</a> › Песнь Ступеней</header>
<h1>Песнь Ступеней</h1>
<p class="song-intro">Вся музыка корпуса — {nword}. Под каждой плиткой — статьи, где она звучит.
Нажмите на плитку, чтобы включить.</p>
<div class="songgrid">
{cards}
</div>
<footer class="footer">
<p class="attrib">Адаптировано Claude Opus 4.8 от Anthropic и Элиягу Бар Малей.</p>
<p class="license">Текст доступен на условиях <a href="https://creativecommons.org/licenses/by/4.0/deed.ru" rel="license">Creative Commons Attribution 4.0 (CC BY 4.0)</a>.</p>
</footer>
</div>
<script>
document.querySelectorAll('.yt').forEach(function(el){{
  function go(){{
    var id=el.dataset.id;
    el.innerHTML='<iframe src="https://www.youtube.com/embed/'+id+'?autoplay=1&rel=0" '
      +'title="YouTube" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>';
  }}
  el.addEventListener('click',go);
  el.addEventListener('keydown',function(e){{if(e.key==='Enter'||e.key===' '){{e.preventDefault();go();}}}});
}});
</script>
</body>
</html>
'''.format(n=len(rows), nword=NWORD, cards="\n".join(cards))

os.makedirs(r"C:\Users\admin\yaniktoim\docs\songs", exist_ok=True)
open(r"C:\Users\admin\yaniktoim\docs\songs\index.html", "w", encoding="utf-8").write(PAGE)
print("Generated songs page with %d tracks, %d total article links" %
      (len(rows), sum(len(v["arts"]) for v in data.values())))
