# -*- coding: utf-8 -*-
"""Локальное превью готовых томов (не трогает сайт/manifest).
Пишет .batch/roza/preview.html из имеющихся валидных vol_NN.html."""
import re
from pathlib import Path
import assemble as A

ready = []
for nn in A.NN:
    f = A.ROZA/f"vol_{nn}.html"
    if f.exists():
        h = f.read_text(encoding="utf-8")
        w = len(re.sub(r"<[^>]+>"," ",h).split())
        if w > 800 and f'id="vol-{nn}"' in h:
            ready.append(nn)

def toc(ready):
    lis = [f'<li><a href="#vol-{nn}">Книга {int(nn)}. {A.TITLES[nn]}</a></li>' for nn in ready]
    return ('<details class="toc" open>\n <summary>Содержание (превью: '
            f'{len(ready)} из 12)</summary>\n <ol>\n ' + "\n ".join(lis) + "\n </ol>\n</details>")

def volnav(i, ready):
    parts=['<nav class="volnav">']
    parts.append(f'<a href="#vol-{ready[i-1]}">← Книга {int(ready[i-1])}</a>' if i>0 else '<span></span>')
    parts.append('<a class="top" href="#top">↑ Оглавление</a>')
    parts.append(f'<a href="#vol-{ready[i+1]}">Книга {int(ready[i+1])} →</a>' if i<len(ready)-1 else '<span></span>')
    parts.append('</nav>'); return "".join(parts)

frags=[]
for i,nn in enumerate(ready):
    frags.append((A.ROZA/f"vol_{nn}.html").read_text(encoding="utf-8").strip()+"\n"+volnav(i,ready))

html=f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Роза Мира — основные идеи (ПРЕВЬЮ)</title>
<style>{A.base_css()}{A.EXTRA_CSS}
 .pvw{{background:var(--accent2);color:#fff;text-align:center;padding:8px;font-family:Arial;
  font-size:.85rem;border-radius:4px;margin:14px 0}}</style></head>
<body data-scheme="editorial"><div class="wrap">
<nav class="crumbs" id="top"><a href="#">Главная</a><span class="sep">/</span>Без категории</nav>
<div class="pvw">ЛОКАЛЬНОЕ ПРЕВЬЮ — {len(ready)} из 12 томов готово. На сайт не опубликовано.</div>
<h1>Роза Мира Даниила Андреева — основные идеи</h1>
<p class="tag">#Роза Мира · Д. Андреев</p>
{A.INTRO}
{toc(ready)}
{chr(10).join(frags)}
{A.COLOPHON}
</div></body></html>"""
out = A.ROZA/"preview.html"
out.write_text(html, encoding="utf-8")
print(f"ready={ready}")
print(f"WROTE {out} | {len(html)} bytes")
