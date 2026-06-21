# -*- coding: utf-8 -*-
"""T-B (вопрос 6): roza_mira strong/b → {term|}.
Шаг 1 (collect): собрать distinct strong/b-тексты с контекстом и структурной
ролью. B1 (strong в начале li/p + следом « — ») и B2 (run-in «Подтема.») →
авто-термины (правило, вердикт T-B1/T-B2). Остальное (серая зона T-B3) → на
LLM-классификацию термин/эмфаза (вердикт оператора 13:06: без ручной приёмки).

Usage:
  python extract_roza_terms.py collect   → roza_terms_debug.json (+ grey_prompt.txt)
  python extract_roza_terms.py build      → roza_mira_terms.json (auto ∪ LLM)
LLM-вердикт по серой зоне кладётся в grey_verdict.json (список term-текстов).
"""
import json, os, re, sys, importlib.util
os.chdir(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("conv", "html_to_zml.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)

ART = "roza_mira"
DASH = ("—", "–", "-", "−")


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def leading_strong(parent):
    """Первый значимый ребёнок li/p == strong/b? Вернуть (node, text_after)."""
    seen_text = False
    for ch in parent["kids"]:
        if isinstance(ch, str):
            if ch.strip():
                seen_text = True
            continue
        if ch["tag"] in ("strong", "b") and not seen_text:
            after = []
            hit = False
            for c2 in parent["kids"]:
                if c2 is ch:
                    hit = True
                    continue
                if hit:
                    after.append(conv.raw_text(c2) if isinstance(c2, dict) else c2)
            return ch, norm("".join(after))
        return None, ""
    return None, ""


def collect():
    html = (conv.ART / (ART + ".html")).read_text("utf-8")
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body, flags=re.S)
    t = conv.Tree(); t.feed(body); root = t.root

    auto, grey = {}, {}   # text → role / text → context
    all_strong = conv.find(root, lambda x: x["tag"] in ("strong", "b"))
    classified = set()
    # B1/B2: ведущий strong в li/p
    for parent in conv.find(root, lambda x: x["tag"] in ("li", "p")):
        node, after = leading_strong(parent)
        if node is None:
            continue
        txt = norm(conv.raw_text(node))
        if not txt:
            continue
        if after.startswith(DASH):
            auto[txt] = "b1"
            classified.add(id(node))
        elif txt.endswith(".") and len(txt) <= 60:
            auto[txt] = "b2"
            classified.add(id(node))
    # серая зона: всё остальное
    for node in all_strong:
        if id(node) in classified:
            continue
        txt = norm(conv.raw_text(node))
        if not txt or txt in auto:
            continue
        # контекст: ближайший li/p-предок? упрощённо — текст узла + сам узел
        grey.setdefault(txt, txt)
    # один пример-контекст серой зоны: родительский абзац
    ctx = {}
    for parent in conv.find(root, lambda x: x["tag"] in ("li", "p", "dd")):
        ptxt = norm(conv.raw_text(parent))
        for node in conv.find(parent, lambda x: x["tag"] in ("strong", "b")):
            txt = norm(conv.raw_text(node))
            if txt in grey and txt not in ctx and len(ptxt) > len(txt):
                ctx[txt] = ptxt[:240]
    for txt in grey:
        grey[txt] = ctx.get(txt, txt)

    json.dump({"auto": auto, "grey": grey}, open("roza_terms_debug.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    order = sorted(grey.keys())
    json.dump(order, open("grey_order.json", "w", encoding="utf-8"), ensure_ascii=False)
    print("auto(B1+B2)=%d  grey(LLM)=%d  total_strong=%d" % (len(auto), len(grey), len(all_strong)))
    # промпт для LLM по серой зоне (классификация по НОМЕРАМ — устойчиво к тексту)
    lines = []
    for i, txt in enumerate(order, 1):
        lines.append("%d. «%s»  ⟦%s⟧" % (i, txt, grey[txt]))
    open("grey_prompt.txt", "w", encoding="utf-8").write("\n".join(lines))


def build():
    dbg = json.load(open("roza_terms_debug.json", encoding="utf-8"))
    terms = set(dbg["auto"].keys())
    # вердикт LLM: индексы (1-based) по grey_order.json — предпочтительно
    if os.path.exists("grey_verdict_idx.json") and os.path.exists("grey_order.json"):
        order = json.load(open("grey_order.json", encoding="utf-8"))
        idx = json.load(open("grey_verdict_idx.json", encoding="utf-8"))
        terms |= {order[i - 1] for i in idx if 1 <= i <= len(order)}
    elif os.path.exists("grey_verdict.json"):
        terms |= set(json.load(open("grey_verdict.json", encoding="utf-8")))
    terms = sorted(t for t in terms if t)
    json.dump(terms, open("roza_mira_terms.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    print("roza_mira_terms.json: %d терминов" % len(terms))


if __name__ == "__main__":
    {"collect": collect, "build": build}.get(sys.argv[1] if len(sys.argv) > 1 else "collect", collect)()
