# -*- coding: utf-8 -*-
"""Драйвер двупроходной адаптации томов «Розы Мира».
Usage:  python roza_run.py pass1 01   |   python roza_run.py pass2 01
CLAUDE.md на время проекта переименован (см. add_art_roza.md) — агенты чистые.
"""
import sys, os, re, json, time, subprocess
from pathlib import Path

VOLS = Path(r"C:\Users\admin\roza_mira\text\vols")
OUT  = Path(r"C:\Users\admin\yaniktoim\.batch\roza")
LOGS = OUT / "_logs"
LOGS.mkdir(parents=True, exist_ok=True)

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

def claude_exe():
    base = Path(r"C:\Users\admin\AppData\Local\Packages\Claude_pzs8sxrjxfjjc"
                r"\LocalCache\Roaming\Claude\claude-code")
    if base.is_dir():
        c = sorted((p for p in base.iterdir() if (p/"claude.exe").exists()),
                   key=lambda p: tuple(int(x) if x.isdigit() else -1 for x in p.name.split(".")))
        if c: return str(c[-1]/"claude.exe")
    return "claude"
EXE = claude_exe()

SYS1 = ("You are a meticulous analytical reader of Russian philosophical prose. "
        "You read the full text of one book (volume) of Daniil Andreev's 'Роза Мира' "
        "given in the user message, work through it chapter by chapter, and WRITE "
        "thorough structured notes in Russian to the destination file path given, "
        "using the Write tool (append with Edit if large). Cover every chapter; skip "
        "nothing. Your final reply is ONE short confirmation line — never print the notes.")
SYS2 = ("You are an analytical writer producing a Russian-language digest. From the "
        "chapter notes given, you compose a coherent intermediate summary of one volume "
        "as a strict HTML fragment and WRITE it to the destination file path with the "
        "Write tool. Natural Russian prose, no invented stylization. Final reply: ONE "
        "short confirmation line — never print the fragment.")

def run_claude(sys_prompt, user_prompt, tag, max_out="64000", retries=3, timeout=2400):
    cmd = [EXE, "-p", "--model", "claude-opus-4-8", "--effort", "high",
           "--output-format", "json", "--allowedTools", "Read,Write,Edit",
           "--permission-mode", "bypassPermissions", "--add-dir", str(OUT),
           "--max-turns", "40", "--system-prompt", sys_prompt]
    env = dict(os.environ); env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = max_out
    last = ""
    for att in range(1, retries+1):
        try:
            p = subprocess.run(cmd, input=user_prompt.encode("utf-8"),
                               capture_output=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            last = "timeout"; print(f"  [{tag}] timeout att{att}"); continue
        out = p.stdout.decode("utf-8", "replace")
        (LOGS/f"{tag}_att{att}.json").write_text(out, encoding="utf-8")
        try:
            d = json.loads(out); res = d.get("result") or ""
            if not d.get("is_error") and res:
                print(f"  [{tag}] ok att{att}: {res[:80]}"); return True
            last = res or out[:200]
            if re.search(r'429|too many requests|rate', out, re.I):
                print(f"  [{tag}] 429 att{att}, sleep 60"); time.sleep(60); continue
        except Exception as e:
            last = f"parsefail {e}"
        print(f"  [{tag}] fail att{att}: {last[:120]}"); time.sleep(10)
    print(f"  [{tag}] GAVE UP: {last[:200]}"); return False

def pass1(nn):
    title = TITLES[nn]
    voltext = (VOLS/f"vol_{nn}.txt").read_text(encoding="utf-8")
    gloss   = (VOLS/"glossary.txt").read_text(encoding="utf-8")
    notes   = OUT/f"vol_{nn}_notes.md"
    up = (f"Перед тобой ПОЛНЫЙ текст Книги {nn} «{title}» из «Розы Мира» Д. Андреева "
          f"и краткий словарь терминов автора.\n\n"
          f"Задача: пройти текст ПО ГЛАВАМ (главы помечены «ГЛАВА N»). Для КАЖДОЙ главы "
          f"выпиши структурные рабочие заметки на русском:\n"
          f"— главные идеи главы;\n— введённые/использованные модели и концепции (как "
          f"устроено, механизм, связи);\n— ключевые термины (единообразно, как в словаре);\n"
          f"— выводы и смысловые акценты автора, важные образы и примеры.\n"
          f"Будь полным и точным, НИЧЕГО не пропускай — это сырьё для последующей сборки "
          f"выжимки тома. Запиши заметки в файл: {notes} (Markdown, по главам). "
          f"В ответ — только короткое подтверждение.\n\n"
          f"=== СЛОВАРЬ ТЕРМИНОВ ===\n{gloss}\n\n=== ТЕКСТ КНИГИ {nn} ===\n{voltext}")
    ok = run_claude(SYS1, up, f"v{nn}_p1", max_out="64000")
    if ok and notes.exists() and len(notes.read_text(encoding='utf-8')) > 800:
        print(f"PASS1 {nn} OK ({len(notes.read_text(encoding='utf-8'))} chars)"); return True
    print(f"PASS1 {nn} FAILED"); return False

def pass2(nn):
    title = TITLES[nn]
    notes = OUT/f"vol_{nn}_notes.md"
    gloss = (VOLS/"glossary.txt").read_text(encoding="utf-8")
    frag  = OUT/f"vol_{nn}.html"
    nt = notes.read_text(encoding="utf-8")
    up = (f"Перед тобой рабочие заметки по главам Книги {nn} «{title}» из «Розы Мира» "
          f"и словарь терминов. Собери СВЯЗНУЮ промежуточную выжимку этого тома на "
          f"русском, ~1800–2200 слов, строго как HTML-фрагмент по схеме:\n\n"
          f'<section class="vol" id="vol-{nn}">\n  <h2>Книга {nn}. {title}</h2>\n'
          f"  <h3>Главные идеи</h3> ...\n  <h3>Модели и концепции</h3> ...\n"
          f"  <h3>Ключевые термины</h3> ...\n  <h3>Выводы и акценты автора</h3> ...\n</section>\n\n"
          f"Требования: естественная русская проза без выдуманного стиля; внутри только "
          f"<p>, <ul><li>, <strong>; без инлайн-стилей, без <script>, без <html>/<head>/<body>; "
          f"термины — как в словаре. Раздел «Ключевые термины» — компактный <ul> с краткими "
          f"пояснениями специфичных для тома терминов. Запиши фрагмент в файл: {frag}. "
          f"В ответ — только короткое подтверждение.\n\n"
          f"=== СЛОВАРЬ ТЕРМИНОВ ===\n{gloss}\n\n=== ЗАМЕТКИ ПО ГЛАВАМ (Книга {nn}) ===\n{nt}")
    ok = run_claude(SYS2, up, f"v{nn}_p2", max_out="32000")
    if not (ok and frag.exists()):
        print(f"PASS2 {nn} FAILED (no file)"); return False
    h = frag.read_text(encoding="utf-8")
    words = len(re.sub(r"<[^>]+>"," ",h).split())
    need = ["Главные идеи","Модели и концепции","Ключевые термины","Выводы и акценты"]
    miss = [x for x in need if x not in h]
    bad = ("<html" in h.lower()) or ("<script" in h.lower()) or (f'id="vol-{nn}"' not in h)
    print(f"PASS2 {nn}: words={words} miss={miss} bad={bad}")
    if miss or bad or words < 1200 or words > 3200:
        print(f"PASS2 {nn} VALIDATION FAIL"); return False
    print(f"PASS2 {nn} OK"); return True

if __name__ == "__main__":
    mode, nn = sys.argv[1], sys.argv[2]
    ok = pass1(nn) if mode=="pass1" else pass2(nn)
    sys.exit(0 if ok else 1)
