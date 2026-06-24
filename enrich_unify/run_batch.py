"""Драйвер унификации: на каждый файл из worklist.json спавнит headless `claude -p`
(Opus 4.8, без явного effort), баканный промпт = worker_prompt.txt + нумерованный .zml.
Воркер читает zohar_index.json через Read и возвращает JSON-предложение (НЕ пишет на диск).
Родитель срезает [HH:MM]/огорождения, парсит, кладёт в out/<id>.json. Идемпотентно — уже
готовый out/<id>.json пропускается (если не --force).

  python run_batch.py 09G 06I 11U      # пилот по списку id
  python run_batch.py --all            # весь worklist
  python run_batch.py --all --force    # перегнать всё заново
"""
from __future__ import annotations
import sys, json, re, subprocess, concurrent.futures as cf
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ART = ROOT / "docs" / "art"
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
PROMPT = (HERE / "worker_prompt.txt").read_text(encoding="utf-8")
WORK = json.loads((HERE / "worklist.json").read_text(encoding="utf-8"))
_excl = HERE / "exclude.txt"
EXCLUDE = ({ln.strip() for ln in _excl.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")} if _excl.exists() else set())

MODEL = "claude-opus-4-8"
TIMEOUT = 540
MAXW = 6

def build_prompt(fid: str) -> str:
    zml = (ART / f"{fid}.zml").read_text(encoding="utf-8")
    numbered = "\n".join(f"{i}\t{ln}" for i, ln in enumerate(zml.splitlines(), 1))
    return (PROMPT
            + f"\n\n=== СТАТЬЯ id={fid} : docs/art/{fid}.zml (строки нумерованы 'N<TAB>текст') ===\n"
            + numbered
            + "\n=== КОНЕЦ СТАТЬИ ===\nВерни JSON по схеме. id="+fid)

def _balanced(t: str, i: int):
    depth = 0; instr = False; esc = False
    for j in range(i, len(t)):
        c = t[j]
        if esc: esc = False; continue
        if c == "\\": esc = True; continue
        if c == '"': instr = not instr; continue
        if instr: continue
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return t[i:j+1]
    return None

def extract_json(text: str):
    t = re.sub(r"^\[\d\d:\d\d\]\s*", "", text.strip())   # срезать метку времени
    cands = []
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)   # 1) фенс-блок
    if m: cands.append(m.group(1))
    for i, c in enumerate(t):                                   # 2) каждый сбаланс. объект
        if c == "{":
            b = _balanced(t, i)
            if b: cands.append(b)
    for cand in cands:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict) and ("edits" in obj or "id" in obj):
                return obj
        except Exception:
            continue
    raise ValueError("no valid JSON object with edits/id")

def run_one(fid: str, force: bool):
    outp = OUT / f"{fid}.json"
    if outp.exists() and not force:
        return fid, "skip"
    prompt = build_prompt(fid)
    cmd = ("claude -p --model " + MODEL +
           " --allowedTools Read Grep --output-format json")
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", shell=True, timeout=TIMEOUT, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        (OUT / f"{fid}.err").write_text("TIMEOUT", encoding="utf-8")
        return fid, "timeout"
    raw = proc.stdout
    try:
        env = json.loads(raw)
        if env.get("is_error"):
            (OUT / f"{fid}.err").write_text(raw[:2000], encoding="utf-8")
            return fid, f"api_err:{env.get('api_error_status')}"
        result = env.get("result", "")
    except Exception:
        result = raw
    try:
        obj = extract_json(result)
    except Exception as e:
        (OUT / f"{fid}.err").write_text(f"PARSE {e}\n---\n{result[:3000]}", encoding="utf-8")
        return fid, f"parse_err"
    outp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    ne = len(obj.get("edits", [])); nu = len(obj.get("unresolved", []))
    return fid, f"ok edits={ne} unresolved={nu}"

def main():
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    if "--all" in args:
        ids = list(WORK.keys())
    else:
        ids = args
    ids = [i for i in ids if i not in EXCLUDE]
    if not ids:
        print("usage: run_batch.py <id…> | --all [--force]"); return
    print(f"running {len(ids)} files, {MAXW} concurrent, model={MODEL}")
    done = 0
    with cf.ThreadPoolExecutor(max_workers=MAXW) as ex:
        futs = {ex.submit(run_one, fid, force): fid for fid in ids}
        for fu in cf.as_completed(futs):
            fid, status = fu.result()
            done += 1
            print(f"[{done}/{len(ids)}] {fid}: {status}", flush=True)

if __name__ == "__main__":
    main()
