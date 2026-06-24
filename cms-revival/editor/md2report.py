"""Мини-конвертер enrich_zohar_changes.md → .html для удобного просмотра в браузере
(ссылки на preview-серверы открываются в один клик). Узкий, под этот отчёт:
заголовки/списки/таблицы/цитаты/инлайн-код/жирный/ссылки. Экранированные в таблице
`\\|` корректно разэкранируются (markdown-таблицы требуют этого для литерального `|`)."""
from __future__ import annotations
import re
import html
import sys
from pathlib import Path

PIPE = "\\|"          # экранированная вертикальная черта в md-таблице
SENT = chr(0)          # placeholder вместо литерального | при делении ячейки


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
               r'<a href="\2" target="_blank">\1</a>', s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


def cells_of(row: str) -> list[str]:
    row = row.replace(PIPE, SENT)
    parts = row.split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip().replace(SENT, "|") for p in parts]


def convert(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("### "):
            out.append("<h3>" + inline(ln[4:]) + "</h3>")
        elif ln.startswith("## "):
            out.append("<h2>" + inline(ln[3:]) + "</h2>")
        elif ln.startswith("# "):
            out.append("<h1>" + inline(ln[2:]) + "</h1>")
        elif ln.startswith("---"):
            out.append("<hr>")
        elif ln.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + "<br>".join(inline(x) for x in buf if x) + "</blockquote>")
            continue
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            parsed = [cells_of(r) for r in rows]
            body = [c for c in parsed if not set("".join(c)) <= set("-: ")]
            head, data = body[0], body[1:]
            t = "<table><thead><tr>" + "".join("<th>" + inline(c) + "</th>" for c in head) + "</tr></thead><tbody>"
            for r in data:
                t += "<tr>" + "".join("<td>" + inline(c) + "</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table>")
            continue
        elif ln.startswith("- "):
            buf = []
            while i < len(lines) and lines[i].startswith("- "):
                buf.append("<li>" + inline(lines[i][2:]) + "</li>")
                i += 1
            out.append("<ul>" + "".join(buf) + "</ul>")
            continue
        elif ln.strip() == "":
            out.append("")
        else:
            out.append("<p>" + inline(ln) + "</p>")
        i += 1
    return "\n".join(out)


CSS = """body{font:15px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:1280px;margin:2rem auto;padding:0 1.2rem;color:#222}
h1{color:#6b2d5c}h2{color:#6b2d5c;border-bottom:1px solid #eee;padding-bottom:.3rem;margin-top:2rem}h3{color:#7a3a68}
a{color:#3a6ea5}code{background:#f4f0f2;padding:.1em .3em;border-radius:3px;font-size:.9em;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word}
table{border-collapse:collapse;width:100%;margin:1rem 0;table-layout:fixed}th,td{border:1px solid #ddd;padding:.5rem .7rem;text-align:left;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}
th{background:#f7f2f5}td:first-child,th:first-child{white-space:nowrap;width:3.5em}blockquote{background:#f9f6f8;border-left:3px solid #6b2d5c;margin:0;padding:.6rem 1rem;color:#444}
hr{border:none;border-top:1px solid #eee;margin:1.5rem 0}"""


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("enrich_zohar_changes.md")
    dst = src.with_suffix(".html")
    body = convert(src.read_text(encoding="utf-8"))
    dst.write_text(
        "<!doctype html><html lang=ru><meta charset=utf-8><title>"
        + html.escape(src.stem) + "</title><style>" + CSS + "</style>\n" + body,
        encoding="utf-8")
    # самопроверка: все строки таблицы — по 2 колонки
    m = re.search(r"<tbody>(.*?)</tbody>", dst.read_text(encoding="utf-8"), re.S)
    cols = [r.count("<td>") for r in re.findall(r"<tr>.*?</tr>", m.group(1), re.S)] if m else []
    print(f"written {dst} | data rows: {len(cols)} | cols per row: {sorted(set(cols))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
