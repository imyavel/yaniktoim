# -*- coding: utf-8 -*-
"""Ф4 viewer — side-by-side: ZML→тема (переключатель 5 тем) vs живой оригинал,
плюс флаги экстрактора. Открыть convert/viewer.html в браузере."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEMES = [("A_editorial", "A · editorial"), ("B_manuscript", "B · manuscript"),
          ("cyberpunk", "cyberpunk"), ("swiss", "swiss"), ("ar_deco", "ar-deco")]
ARTS = [("654", "Подступая к раскрытию Книги Зоар", "A_editorial"),
        ("237", "Дано Творцу… (поэма)", "B_manuscript")]

def opts(default):
    return "".join(f'<option value="{v}"{" selected" if v==default else ""}>{lbl}</option>'
                   for v, lbl in THEMES)

blocks = []
for art, title, default in ARTS:
    flags = (HERE / "out" / f"{art}.flags.txt")
    flags_txt = flags.read_text("utf-8") if flags.exists() else ""
    blocks.append(f"""
<div class="art">
  <div class="bar">
    <h2>{art} — {title}</h2>
    <label>тема ZML:
      <select onchange="document.getElementById('z-{art}').src='../themes/gallery/'+this.value+'__{art}.html'">
        {opts(default)}
      </select>
    </label>
    <a href="../../yaniktoim/docs/art/{art}.html" target="_blank">открыть оригинал ↗</a>
  </div>
  <div class="panes">
    <div class="pane"><h3>ZML → тема (переключай селектором)</h3>
      <iframe id="z-{art}" src="../themes/gallery/{default}__{art}.html"></iframe></div>
    <div class="pane"><h3>Оригинал — живой HTML</h3>
      <iframe src="../../yaniktoim/docs/art/{art}.html"></iframe></div>
  </div>
  <div class="flags"><b>Флаги экстрактора (неуверенный маппинг — кандидаты в «баг/не баг»):</b>
{flags_txt}</div>
</div>""")

html = f"""<!doctype html><meta charset="utf-8">
<title>Ф4 — ZML vs оригинал (тест-выборка)</title>
<style>
  body{{font-family:Arial,system-ui,sans-serif;margin:0;background:#e9e9e9;color:#222}}
  .top{{padding:12px 16px;background:#1c1c1c;color:#eee;font-size:14px}}
  .art{{margin:0 0 26px;background:#fafafa;border-bottom:3px solid #ccc}}
  .bar{{position:sticky;top:0;background:#2a2a2a;color:#fff;padding:10px 16px;
        display:flex;gap:18px;align-items:center;flex-wrap:wrap;z-index:5}}
  .bar h2{{font-size:16px;margin:0}}
  .bar a{{color:#7ec8ff}}
  select{{font-size:14px;padding:3px 6px}}
  .panes{{display:flex;gap:8px;padding:8px}}
  .pane{{flex:1;min-width:0;display:flex;flex-direction:column}}
  .pane h3{{margin:4px 6px;font-size:13px;color:#666}}
  iframe{{width:100%;height:82vh;border:1px solid #999;background:#fff}}
  .flags{{padding:10px 16px;background:#fff;border-left:4px solid #d08400;
          font-size:13px;line-height:1.5;white-space:pre-wrap}}
</style>
<div class="top"><b>Ф4 тест-выборка.</b> Слева — наш ZML, прогнанный через тему
(переключай 5 тем селектором), справа — текущий живой HTML. Сравниваем и решаем
«баг / не баг». Под каждой парой — что экстрактор замапил неуверенно.</div>
{''.join(blocks)}
"""
(HERE / "viewer.html").write_text(html, "utf-8")
print("wrote convert/viewer.html")
