# -*- coding: utf-8 -*-
"""Render docs/art/<id>.view.html with headless Chrome, trim trailing background,
slice into readable vertical JPEG segments (PNG context-loading loses quality →
deliver JPEG; tall full-page images get downscaled → segment by height).
Usage: python viewshots.py <id> [<id> ...] [--theme=NAME] [--width=narrow|wide]
       <id>            → docs/art/<id>.view.html  → _viewshots/<id>_NN.jpg
       <id>.html       → docs/art/<id>.html (оригинал) → _viewshots/<id>.orig_NN.jpg
       --theme=NAME    → force this theme (renders a tmp copy of the .view.html
                         with theme css + data-theme swapped); out → <id>__NAME_NN.jpg
       --width=narrow|wide → force column width (swaps .wrap w-narrow/w-wide)
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
_ROOT = Path(__file__).resolve().parents[2]
ART = _ROOT / "docs" / "art"
SONGS = _ROOT / "docs" / "songs"
OUTDIR = _ROOT.parent / "_viewshots"
OUTDIR.mkdir(exist_ok=True)

W = 1100          # window width (content column centred inside)
W_SONGS = 1400    # спец-страница songs шире (грид плиток до ~1340)
RENDER_H = 26000  # generous; trimmed to real content height
SEG = 800        # сегмент 800px: крупнее контекст-лоадер не ужимает
SCALE = 1


def render(stem, fpath, win=W):
    png = OUTDIR / f"{stem}.full.png"
    udd = tempfile.mkdtemp()
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--no-first-run", "--no-default-browser-check",
         f"--force-device-scale-factor={SCALE}",
         f"--window-size={win},{RENDER_H}", "--virtual-time-budget=3500",
         f"--user-data-dir={udd}", f"--screenshot={png}",
         f"file:///{fpath}"],
        capture_output=True)
    return png


def content_bottom(im):
    """Last row that isn't uniform background (bg = bottom-left corner colour)."""
    px = im.load()
    w, h = im.size
    bg = px[0, h - 1]
    y = h - 1
    while y > 0:
        is_bg = True
        for x in range(0, w, 6):
            if px[x, y] != bg:
                is_bg = False
                break
        if not is_bg:
            break
        y -= 1
    return min(h, y + 10)


def force_theme(basedir, fname, theme, width):
    """Write a tmp copy of basedir/<fname> with theme/width swapped; return its path.
    Theme: rewrite `../themes/<x>.css` href + body data-theme=. Width: toggle the
    .wrap w-narrow/w-wide class. Mirrors the live view's client-side switcher."""
    html = (basedir / fname).read_text(encoding="utf-8")
    if theme:
        html = re.sub(r'(\.\./themes/)[^."?]+(\.css)', rf'\g<1>{theme}\g<2>', html)
        html = re.sub(r'(data-theme=")[^"]*(")', rf'\g<1>{theme}\g<2>', html)
    if width:
        cls = "w-narrow" if width == "narrow" else "w-wide"
        html = re.sub(r'\bw-(?:narrow|wide)\b', cls, html, count=1)
    tmp = basedir / f"{fname}.__shot.html"
    tmp.write_text(html, encoding="utf-8")
    return tmp


def slice_art(arg, theme=None, width=None):
    # спец-страница songs: docs/songs/index.view.html, шире окно (грид плиток).
    # `songs:<name>` → docs/songs/<name>.view.html (для probe-страниц).
    if arg == "songs" or arg.startswith("songs:"):
        nm = "index" if arg == "songs" else arg.split(":", 1)[1]
        basedir, fname, stem, win = SONGS, f"{nm}.view.html", nm, W_SONGS
    elif arg.endswith(".html"):
        basedir, win = ART, W
        fname = arg
        stem = arg[:-5]
        stem = stem + ".orig" if not stem.endswith(".view") else stem[:-5]
    else:
        basedir, win = ART, W
        fname, stem = f"{arg}.view.html", arg
    tmp = None
    if theme or width:
        tmp = force_theme(basedir, fname, theme, width)
        fpath = tmp
        if theme:
            stem = f"{stem}__{theme}"
    else:
        fpath = f"{basedir}/{fname}"
    art = stem
    try:
        png = render(stem, fpath, win)
        im = Image.open(png).convert("RGB")
        cb = content_bottom(im)
        im = im.crop((0, 0, im.size[0], cb))
        segs = []
        y = i = 0
        while y < cb:
            h = min(SEG, cb - y)
            seg = im.crop((0, y, im.size[0], y + h))
            p = OUTDIR / f"{art}_{i:02d}.jpg"
            # >~550 КБ контекст-лоадер ужимает до нечитаемости → держим < 500 КБ
            for q in (88, 70, 58, 45):
                seg.save(p, "JPEG", quality=q)
                if p.stat().st_size < 500_000:
                    break
            segs.append(p.name)
            y += h
            i += 1
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)
    return cb, segs


if __name__ == "__main__":
    theme = width = None
    ids = []
    for a in sys.argv[1:]:
        if a.startswith("--theme="):
            theme = a.split("=", 1)[1]
        elif a.startswith("--width="):
            width = a.split("=", 1)[1]
        else:
            ids.append(a)
    for art in ids:
        cb, segs = slice_art(art, theme=theme, width=width)
        print(f"{art}: content_h={cb} segs={len(segs)} -> {segs}")
