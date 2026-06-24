"""Агрегатор: enrich_unify/out/*.json (предложения воркеров) → report.md → report.html.
Секции: (1) Унификация «было→стало» с отрендеренным анкором, (2) Снятая атрибуция
(РАШБИ/Бааль Сулам/…), (3) Не определено — на решение оператора. Рендер анкоров —
через render_tags.mjs (resolveInline). Литеральные '|' тегов экранируются для md-таблиц.

  python build_report.py            # собрать report.md + report.html
"""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "out"
TAG = re.compile(r"\{[a-z][a-z0-9-]*\|\d*(?:\|\d*)?\}")
LIVE = "https://imyavel.github.io/yaniktoim/art"

def esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()

CTX = 45  # символов контекста вокруг правки при схлопывании длинной неизменной части

def _elide(s: str, p: int, suf: int) -> str:
    head, mid, tail = s[:p], s[p:len(s) - suf], s[len(s) - suf:]
    def el(t: str) -> str:
        if len(t) <= CTX * 2 + 20:
            return t
        return t[:CTX] + f" …⟨{len(t) - 2 * CTX} симв⟩… " + t[-CTX:]
    return el(head) + mid + el(tail)

def elide_pair(a: str, b: str):
    """Схлопнуть общий префикс/суффикс пары до «…», оставив контекст вокруг отличия."""
    n = min(len(a), len(b))
    p = 0
    while p < n and a[p] == b[p]:
        p += 1
    suf = 0
    while suf < n - p and a[-1 - suf] == b[-1 - suf]:
        suf += 1
    return _elide(a, p, suf), _elide(b, p, suf)

def render_anchors(after_lines: list[str]) -> dict:
    if not after_lines:
        return {}
    p = subprocess.run("node enrich_unify/render_tags.mjs",
                       input=json.dumps(after_lines, ensure_ascii=False),
                       capture_output=True, text=True, encoding="utf-8",
                       shell=True, cwd=str(ROOT))
    try:
        return json.loads(p.stdout)
    except Exception:
        return {}

def load_exclude():
    p = HERE / "exclude.txt"
    if not p.exists():
        return set()
    return {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}

def main():
    exclude = load_exclude()
    files = sorted(OUT.glob("*.json"))
    edits, rashbi, unresolved = [], [], []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        fid = d.get("id", f.stem)
        if fid in exclude:
            continue
        for e in d.get("edits", []):
            e["id"] = fid; edits.append(e)
        for r in d.get("rashbi_removals", []):
            r["id"] = fid; rashbi.append(r)
        for u in d.get("unresolved", []):
            u["id"] = fid; unresolved.append(u)

    # Прозовый класс TEXT (ссылка вплетена в авторский текст) вынесен из авто-батча:
    # откатывается, обрабатывается отдельным аккуратным проходом. В §1/применение не идёт.
    deferred = [e for e in edits if e.get("kind") == "TEXT"]
    edits = [e for e in edits if e.get("kind") != "TEXT"]
    keep = {(e["id"], e.get("line")) for e in edits}
    rashbi = [r for r in rashbi if (r["id"], r.get("line")) in keep]  # снятия только на выживших строках

    # отрендерить анкоры: подаём только теги из каждого "after"
    tag_strings = []
    for e in edits:
        tags = " ".join(TAG.findall(e.get("after", "")))
        e["_tags"] = tags
        if tags: tag_strings.append(tags)
    rendered = render_anchors(sorted(set(tag_strings)))

    L = []
    L.append("# Унификация Зоар-ссылок (Фаза 2) — отчёт на согласование")
    L.append("")
    L.append(f"Структурных правок (сноски/cite/теги): **{len(edits)}** в **{len({e['id'] for e in edits})}** файлах · "
             f"снятий атрибуции: **{len(rashbi)}** · не определено: **{len(unresolved)}** · "
             f"отложено прозовых (TEXT): **{len(deferred)}** (см. §4).")
    L.append("")
    L.append("Правила анкора: «Книга Зоар, ‹глава›, ‹статья›[, § NN]» (akdama → «Предисловие»); § и "
             "`#p`-якорь — только при явном параграфе; `{глава|N}` — без §. Прозовые упоминания (ссылка "
             "вплетена в авторский текст) ВЫНЕСЕНЫ из этого батча — отдельным проходом. Правки в "
             "yaniktoim вношу ТОЛЬКО после твоего «ок».")
    L.append("")

    # 1. Унификация
    L.append("## 1. Унификация — было → стало")
    L.append("")
    by_id = {}
    for e in edits: by_id.setdefault(e["id"], []).append(e)
    for fid in sorted(by_id):
        L.append(f"### [{fid}]({LIVE}/{fid}.html)")
        L.append("")
        L.append("| стр | было | стало | анкор (как увидит читатель) |")
        L.append("|---|---|---|---|")
        for e in by_id[fid]:
            anc = rendered.get(e.get("_tags", ""), {})
            atxt = anc.get("text", "")
            if anc.get("broken"): atxt = "⚠ BROKEN " + e.get("_tags", "")
            bsh, ash = elide_pair(e.get("before", ""), e.get("after", ""))
            L.append(f"| {e.get('line','')} | `{esc(bsh)}` | "
                     f"`{esc(ash)}` | {esc(atxt)} |")
        L.append("")

    # 2. Атрибуция
    L.append("## 2. Снятая атрибуция (РАШБИ / Бааль Сулам / Перуш Сулам / Ашлаг)")
    L.append("")
    if rashbi:
        L.append("| файл | стр | снято | строка после |")
        L.append("|---|---|---|---|")
        for r in rashbi:
            L.append(f"| {r['id']} | {r.get('line','')} | {esc(r.get('removed',''))} | "
                     f"`{esc(r.get('after',''))}` |")
    else:
        L.append("_(нет)_")
    L.append("")

    # 3. Не определено
    L.append("## 3. Не определено — на твоё решение")
    L.append("")
    if unresolved:
        L.append("| файл | стр | текст | почему |")
        L.append("|---|---|---|---|")
        for u in unresolved:
            L.append(f"| {u['id']} | {u.get('line','')} | {esc(u.get('text','')[:160])} | "
                     f"{esc(u.get('why',''))} |")
    else:
        L.append("_(нет)_")
    L.append("")

    # 4. Отложено: прозовые упоминания (TEXT) — отдельным аккуратным проходом
    L.append("## 4. Отложено — прозовые упоминания (TEXT), отдельным проходом")
    L.append("")
    L.append("_Здесь ссылка вплетена в авторский текст; авто-замена рискует снести авторскую прозу "
             "(благословения и т.п.). Эти места НЕ входят в текущий батч — ворклист для отдельного прохода._")
    L.append("")
    if deferred:
        L.append("| файл | стр | предлагавшийся тег | фрагмент (было) |")
        L.append("|---|---|---|---|")
        for e in sorted(deferred, key=lambda x: (x["id"], x.get("line", 0))):
            tg = " ".join(TAG.findall(e.get("after", ""))) or "—"
            L.append(f"| {e['id']} | {e.get('line','')} | `{esc(tg)}` | {esc(e.get('before','')[:200])} |")
    else:
        L.append("_(нет)_")
    L.append("")

    md = "\n".join(L)
    (HERE / "report.md").write_text(md, encoding="utf-8")
    subprocess.run("python cms-revival/editor/md2report.py enrich_unify/report.md",
                  shell=True, cwd=str(ROOT))
    print(f"report.md + report.html: files={len(by_id)} edits={len(edits)} "
          f"rashbi={len(rashbi)} unresolved={len(unresolved)}")

if __name__ == "__main__":
    main()
