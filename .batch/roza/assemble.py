# -*- coding: utf-8 -*-
"""Сборка финальной страницы docs/art/666A.html из 12 фрагментов + глоссарий.
Стиль (CSS) переиспуется из существующей статьи docs/art/217A.html.
Запускать ПОСЛЕ готовности всех vol_NN.html (и glossary.html — опц.)."""
import re, json
from pathlib import Path

ROOT = Path(r"C:\Users\admin\yaniktoim")
ROZA = ROOT/".batch"/"roza"
ART  = ROOT/"docs"/"art"/"roza_mira.html"
SAMPLE = ROOT/"docs"/"art"/"217A.html"

TITLES = {
 "01":"Роза Мира и её место в истории",
 "02":"О метаисторическом и трансфизическом методах познания",
 "03":"Структура Шаданакара. Миры восходящего ряда",
 "04":"Структура Шаданакара. Инфрафизика",
 "05":"Структура Шаданакара. Стихиали",
 "06":"Высшие миры Шаданакара",
 "07":"К метаистории Древней Руси",
 "08":"К метаистории царства Московского",
 "09":"К метаистории Петербургской империи",
 "10":"К метаистории русской культуры",
 "11":"К метаистории последнего столетия",
 "12":"Возможности",
}
NN = [f"{i:02d}" for i in range(1,13)]

def base_css():
    s = SAMPLE.read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", s, re.S)
    return m.group(1) if m else ""

EXTRA_CSS = """
 /* --- Роза Мира: тома и навигация --- */
 .intro{color:var(--muted);font-size:1rem;margin:0 0 2em;border-left:3px solid var(--rule);padding-left:1.1em}
 .intro p{margin:.5em 0}
 section.vol{margin:0 0 10px;padding:34px 0 8px;border-top:2px solid var(--rule)}
 section.vol h2{font-size:1.7rem;line-height:1.2;margin:.2em 0 .6em;color:var(--accent)}
 section.vol h3{font-family:"Helvetica Neue",Arial,sans-serif;font-size:.95rem;letter-spacing:.04em;
  text-transform:uppercase;color:var(--accent2);margin:1.4em 0 .4em}
 .volnav{display:flex;justify-content:space-between;gap:12px;margin:18px 0 6px;
  font-family:"Helvetica Neue",Arial,sans-serif;font-size:.82rem}
 .volnav a{text-decoration:none;color:var(--accent)} .volnav a:hover{color:var(--accent2)}
 .volnav .top{color:var(--muted)}
 a.totop{color:inherit;text-decoration:none}
 a.totop:hover{color:var(--accent2)}
 a.totop::after{content:" ↑";font-size:.7em;color:var(--muted);opacity:0;transition:opacity .15s}
 h2:hover a.totop::after{opacity:1}
 #glossary{border-top:2px solid var(--rule);padding-top:34px;margin-top:10px}
 #glossary dl{margin:0} #glossary dt{font-weight:700;margin:1em 0 .15em;color:var(--accent)}
 #glossary dd{margin:0 0 .2em 0;color:var(--ink)}
 .colophon{margin-top:40px;padding-top:18px;border-top:1px solid var(--rule);
  color:var(--muted);font-size:.9rem}
 .artnav{display:flex;justify-content:space-between;gap:16px;margin:34px 0 0;
  font-family:"Helvetica Neue",Arial,sans-serif;font-size:.85rem}
 .artnav a{text-decoration:none;color:var(--accent)}
"""

INTRO = """<div class="intro">
<p>Перед вами конспект-изложение «Розы Мира» Даниила Андреева (книга писалась в 1950–1958 годах) — большого религиозно-философского трактата в двенадцати книгах. Полный текст оригинала (в зависимости от издания — порядка 750–900 печатных страниц, около 230 тысяч слов) был обработан языковой моделью <strong>Claude Opus 4.8</strong> (Anthropic): каждая из двенадцати книг прочитана отдельно, по главам, и сведена в сжатое изложение её основных идей. Это не дословный пересказ и не замена оригинала, а путеводитель по ключевым мыслям, моделям и понятиям автора; ссылка на первоисточник — в конце страницы.</p>
<p>Структура страницы повторяет структуру трактата: двенадцать разделов по числу книг, в каждом — «Главные идеи», «Модели и концепции», «Ключевые термины» и «Выводы и акценты автора». В самом конце — общий глоссарий специфических терминов Андреева. Для перемещения пользуйтесь оглавлением и стрелками перехода между книгами.</p>
</div>"""

COLOPHON = """<div class="colophon">
<p>Источник: Даниил Андреев, «Роза Мира» (1950–1958). Текст оригинала — © наследники Д. Л. Андреева; произведение в РФ охраняется до 2029 года. Настоящее изложение основных идей подготовлено автоматически (Claude Opus 4.8) как производный конспект и не воспроизводит текст оригинала. Полный текст: <a href="https://lib.rmvoz.ru/bigzal/rozamira" target="_blank" rel="noopener noreferrer">Библиотека «Воздушного Замка»</a>.</p>
<p>Текст настоящего изложения — <a href="https://creativecommons.org/licenses/by/4.0/deed.ru" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>.</p>
</div>"""

def toc():
    lis = []
    for nn in NN:
        lis.append(f'<li><a href="#vol-{nn}">Книга {int(nn)}. {TITLES[nn]}</a></li>')
    lis.append('<li><a href="#glossary">Глоссарий терминов</a></li>')
    return ("<details class=\"toc\" open>\n <summary>Содержание</summary>\n <ol>\n "
            + "\n ".join(lis) + "\n </ol>\n</details>")

def volnav(i):
    parts = ['<nav class="volnav">']
    if i > 0:
        p = NN[i-1]; parts.append(f'<a href="#vol-{p}">← Книга {int(p)}</a>')
    else:
        parts.append('<span></span>')
    parts.append('<a class="top" href="#top">↑ Оглавление</a>')
    if i < len(NN)-1:
        n = NN[i+1]; parts.append(f'<a href="#vol-{n}">Книга {int(n)} →</a>')
    else:
        parts.append('<a href="#glossary">Глоссарий →</a>')
    parts.append('</nav>')
    return "".join(parts)

def neighbor_nav():
    m = json.load(open(ROOT/"manifest.json", encoding="utf-8"))
    oth = sorted([r for r in m if r["section"]=="other"], key=lambda r: r.get("section_order",0))
    prev = oth[-1] if oth else None  # последняя существующая статья раздела (станет нашей «предыдущей»)
    # ВАЖНО: файлы статей называются по art (<art>.html), а не по полю html (легаси-стем).
    # Мы становимся замыкающей статьёй корпуса → только «Предыдущая», штатная разметка .pager.
    if not prev:
        return '<nav class="pager"></nav>'
    return (f'<nav class="pager">\n <a class="prev" href="{prev["art"]}.html">\n'
            f'  <span class="lbl">← Предыдущая</span>\n'
            f'  <span class="ttl">{prev["title"]}</span>\n </a>\n</nav>')

def build():
    def link_h2(html):
        # заголовок раздела → ссылка в начало документа (#top)
        return re.sub(r'<h2>(.*?)</h2>',
                      r'<h2><a class="totop" href="#top" title="В начало">\1</a></h2>',
                      html, count=1, flags=re.S)
    frags = []
    for i, nn in enumerate(NN):
        f = ROZA/f"vol_{nn}.html"
        h = link_h2(f.read_text(encoding="utf-8").strip())
        frags.append(h + "\n" + volnav(i))
    gloss_f = ROZA/"glossary.html"
    gloss = link_h2(gloss_f.read_text(encoding="utf-8").strip()) if gloss_f.exists() else \
            '<section id="glossary"><h2>Глоссарий терминов</h2><p>(в подготовке)</p></section>'
    meta = json.dumps({"scheme":"editorial","form":"конспект-изложение (проза)",
        "rationale":"Сборка из 12 авто-конспектов книг «Розы Мира» (Opus 4.8), единый лонгрид с оглавлением и межтомной навигацией.",
        "features":["toc"]}, ensure_ascii=False, indent=1)
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<link rel="icon" href="../favicon.ico" sizes="any">
<link rel="icon" type="image/png" href="../img/favicon.png">
<link rel="apple-touch-icon" href="../img/favicon.png">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Роза Мира Даниила Андреева — основные идеи</title>
<style>{base_css()}{EXTRA_CSS}</style>
</head>
<body data-scheme="editorial">
<div class="wrap">

<nav class="crumbs" id="top">
 <a href="../index.html">Главная</a><span class="sep">/</span><a href="../other/index.html">Без категории</a>
</nav>

<h1>Роза Мира Даниила Андреева — основные идеи</h1>
<p class="tag">#Роза Мира · Д. Андреев</p>

{INTRO}

{toc()}

{chr(10).join(frags)}

{gloss}

{COLOPHON}

</div>
<script type="application/json" id="yanik-meta">
{meta}
</script>
</body>
</html>"""
    ART.write_text(html, encoding="utf-8")
    words = len(re.sub(r"<[^>]+>"," ", html).split())
    print(f"WROTE {ART} | {len(html)} bytes | ~{words} words")

if __name__ == "__main__":
    build()
