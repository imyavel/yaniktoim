# Build the guide PDF: Chrome (HTML->PDF, keeps clickable in-doc TOC links) +
# pypdf (adds a nested bookmark outline by locating invisible page-sentinels).
import subprocess, sys, re, os
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
HTML_URL = "file:///" + os.path.join(HERE, "guide.html").replace(os.sep, "/")
RAW = HERE + r"\guide_raw.pdf"
OUT = HERE + r"\guide.pdf"

# 1) Chrome render
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                "--print-to-pdf=" + RAW, HTML_URL], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# 2) locate sentinels per page
reader = PdfReader(RAW)
npages = len(reader.pages)
pagetext = []
for p in reader.pages:
    try: pagetext.append(p.extract_text() or "")
    except Exception: pagetext.append("")

def page_of(mark):
    # tolerate spacing the extractor may insert between glyphs
    pat = re.compile(re.escape(mark).replace(r"\~", r"~").replace("", r"\s*").strip() or re.escape(mark))
    # simpler: strip non-alnum and match compact
    target = re.sub(r"[^A-Za-z0-9]", "", mark)
    for i, t in enumerate(pagetext):
        if mark in t:
            return i
        if target and target in re.sub(r"[^A-Za-z0-9]", "", t):
            return i
    return None

# outline structure: (title, mark, [children])
PART1 = [
    ("1. Коротко о том, как устроен сайт", "~MK01~"),
    ("2. Вход и роли", "~MK02~"),
    ("3. Две версии статьи: старая и новая (ZML)", "~MK03~"),
    ("4. Редактирование статьи", "~MK04~"),
    ("5. Иллюстрация статьи", "~MK05~"),
    ("6. Создание новой статьи", "~MK06~"),
    ("7. Управление структурой", "~MK07~"),
    ("8. Архив: «рукописи не горят»", "~MK08~"),
    ("9. «Песнь Ступеней»", "~MK09~"),
    ("10. Админка вида: что видит читатель", "~MK10~"),
    ("11. Поиск по сайту", "~MK11~"),
    ("12. Когда правки видны · частые вопросы", "~MK12~"),
]
PART2 = [
    ("13. Что такое ZML", "~MK13~"),
    ("14. Шапка статьи (frontmatter)", "~MK14~"),
    ("15. Заголовки и разделы", "~MK15~"),
    ("16. Абзацы, курсив, ссылки", "~MK16~"),
    ("17. Сноски", "~MK17~"),
    ("18. Стихи и поэмы", "~MK18~"),
    ("19. Эпиграф, эпилог, посвящение", "~MK19~"),
    ("20. Цитата, подпись, возглас, диалог", "~MK20~"),
    ("21. Перечни и списки", "~MK21~"),
    ("22. Спойлер", "~MK22~"),
    ("23. Термины и лейтмотивы", "~MK23~"),
    ("24. Музыка и аудио", "~MK24~"),
    ("25. «Песнь Ступеней» — блок [shir]", "~MK25~"),
    ("26. Глифы и спецсимволы", "~MK26~"),
    ("27. Темы и ширина", "~MK27~"),
    ("28. Стихи, записанные прозой — [faw]", "~MK28~"),
]

writer = PdfWriter(clone_from=RAW)

missing = []
def add(title, mark, parent=None):
    pg = page_of(mark)
    if pg is None:
        missing.append((title, mark))
        pg = 0
    return writer.add_outline_item(title, pg, parent=parent)

# top: cover/TOC quick jumps
writer.add_outline_item("Обложка и оглавление", 0)
p1 = add("Часть I — Управление сайтом", "~MKP1~")
for title, mark in PART1: add(title, mark, parent=p1)
p2 = add("Часть II — Справочник ZML", "~MKP2~")
for title, mark in PART2: add(title, mark, parent=p2)
add("Приложение — Шпаргалка ZML", "~MKAP~")

with open(OUT, "wb") as f:
    writer.write(f)

print("pages:", npages)
print("missing sentinels:", missing if missing else "none — all located")
# report page map for spot-check
for title, mark in [("PartI","~MKP1~"),("s1","~MK01~"),("PartII","~MKP2~"),("s13","~MK13~"),("App","~MKAP~")]:
    print(f"  {mark} -> page {page_of(mark)}")
print("written:", OUT)
