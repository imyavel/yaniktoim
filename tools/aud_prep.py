#!/usr/bin/env python3
"""Подготовка аудио для блока [aud] (ZML3 §2.8).

Из исходных записей (ogg/opus голосовые Telegram, wav, m4a, mp3 …) делает то, что
читает плеер статьи:
  docs/audio/<art>_<N>.mp3   — моно MP3 (играет во всех браузерах, включая старый Safari,
                               который Ogg/Opus не умеет);
  docs/audio/<art>_<N>.json  — «волна» плашки: {"v":1,"dur":сек,"peaks":[0..31 × 128]}.

и печатает готовые строки для тела блока [aud] (файл | м:сс).

  python tools/aud_prep.py 69T a.ogg b.ogg c.ogg
  python tools/aud_prep.py 69T new.ogg --start 6        # дописать 6-ю запись
  python tools/aud_prep.py 69T --peaks-only             # пересчитать волну готовых mp3

Нужен ffmpeg/ffprobe в PATH. Порядок файлов в аргументах = порядок плашек.
"""
import argparse
import array
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "docs" / "audio"
PEAKS_N = 128          # число столбиков волны (плеер сам ужимает под ширину плашки)
PEAK_MAX = 31          # 5 бит на столбик, как waveform голосовых в Telegram
PCM_RATE = 8000        # для огибающей хватает с запасом


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)]).stdout
    return float(out.decode().strip())


def encode_mp3(src: Path, dst: Path, quality: int) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
         "-c:a", "libmp3lame", "-q:a", str(quality),
         "-map_metadata", "-1", "-write_xing", "1", str(dst)])


def peaks(path: Path, n: int = PEAKS_N) -> list:
    raw = run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
               "-ar", str(PCM_RATE), "-f", "s16le", "-"]).stdout
    pcm = array.array("h")
    pcm.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder == "big":
        pcm.byteswap()
    total = len(pcm)
    if not total:
        return [0] * n
    # огибающая: RMS по корзине (ровнее пика, тишина остаётся тишиной)
    env = []
    for i in range(n):
        a, b = i * total // n, max((i + 1) * total // n, i * total // n + 1)
        chunk = pcm[a:b]
        env.append(math.sqrt(sum(s * s for s in chunk) / len(chunk)))
    # нормировка по 95-му перцентилю: одиночный всплеск не прижимает всю волну к нулю
    ref = sorted(env)[min(n - 1, int(n * 0.95))] or max(env) or 1.0
    return [min(PEAK_MAX, int(round(v / ref * PEAK_MAX))) for v in env]


def mmss(sec: float) -> str:
    s = int(round(sec))
    return f"{s // 60}:{s % 60:02d}" if s < 3600 else f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Аудио для блока [aud]: mp3 + волна")
    ap.add_argument("art", help="id статьи (префикс имён файлов)")
    ap.add_argument("files", nargs="*", help="исходные записи по порядку плашек")
    ap.add_argument("--start", type=int, default=1, help="номер первой записи (деф. 1)")
    ap.add_argument("--q", type=int, default=2, help="качество LAME VBR 0..9 (деф. 2)")
    ap.add_argument("--peaks-only", action="store_true",
                    help="не кодировать: пересчитать .json для готовых docs/audio/<art>_*.mp3")
    args = ap.parse_args()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    if args.peaks_only:
        targets = sorted(AUDIO_DIR.glob(f"{args.art}_*.mp3"),
                         key=lambda p: int(p.stem.rsplit("_", 1)[1]))
        if not targets:
            print(f"нет готовых файлов docs/audio/{args.art}_*.mp3", file=sys.stderr)
            return 2
    else:
        if not args.files:
            ap.error("нужны исходные файлы (или --peaks-only)")
        targets = []
        for i, f in enumerate(args.files):
            src = Path(f)
            if not src.is_file():
                print(f"нет файла: {src}", file=sys.stderr)
                return 2
            dst = AUDIO_DIR / f"{args.art}_{args.start + i}.mp3"
            encode_mp3(src, dst, args.q)
            targets.append(dst)

    lines = []
    for dst in targets:
        dur = duration(dst)
        write_json(dst.with_suffix(".json"),
                   {"v": 1, "dur": round(dur, 2), "peaks": peaks(dst)})
        lines.append(f"{dst.name} | {mmss(dur)}")
        print(f"{dst.name}  {mmss(dur)}  {dst.stat().st_size / 1e6:.2f} МБ", file=sys.stderr)

    print("[aud]")
    print("\n".join(lines))
    print("[/aud]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
