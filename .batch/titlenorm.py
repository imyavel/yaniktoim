# -*- coding: utf-8 -*-
import json, os, subprocess
B = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(B, "songs_data.json"), encoding="utf-8"))
items = [{"id": k, "t": v["title"]} for k, v in data.items() if v["title"]]
CHUNK = 60
chunks = [items[i:i+CHUNK] for i in range(0, len(items), CHUNK)]

PROMPT = '''Ниже — музыкальные треки: id и текущая подпись (формат вразнобой: где-то «Песня — Исполнитель», где-то «Исполнитель — Песня», где-то с мусором).
Приведи КАЖДУЮ подпись к ЕДИНОМУ формату: «Название песни — Исполнитель» (разделитель — длинное тире « — »).
Правила:
- Переупорядочивай, опираясь на знание музыки (напр. «Elton John — Circle of Life» → «Circle of Life — Elton John»; «Моя Звезда — В. Бутусов» оставить).
- Убери мусор («Самый классный клип!!!», «▶», «Новинка», номера, «(Official Video)», «[HD]», «youtu.be/...», «(Subtitulado...)» и т.п.), оставь чистые Песня и Исполнитель.
- Если исполнитель неизвестен/не указан и ты не уверен — оставь только название песни, без тире.
- НЕ выдумывай сомнительных исполнителей. Сохраняй язык оригинала.
Верни СТРОГО один JSON-объект вида {{"id":"Название песни — Исполнитель", ...}} для ВСЕХ id из ввода, без markdown и пояснений.

ВВОД:
%s
'''

CMD = r'"C:\Users\admin\AppData\Roaming\npm\claude.cmd" -p --model opus --output-format json'
out = {}
for i, ch in enumerate(chunks):
    inp = json.dumps(ch, ensure_ascii=False)
    p = subprocess.run(CMD, input=PROMPT % inp, capture_output=True, text=True,
                       encoding="utf-8", timeout=400, cwd=B, shell=True)
    try:
        res = json.loads(p.stdout).get("result", "")
        s = res.find("{"); e = res.rfind("}")
        m = json.loads(res[s:e+1])
        out.update(m)
        print("chunk %d/%d: got %d" % (i+1, len(chunks), len(m)), flush=True)
    except Exception as ex:
        print("chunk %d FAIL: %s :: %s" % (i+1, ex, p.stdout[:160]), flush=True)
json.dump(out, open(os.path.join(B, "titlenorm.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print("total normalized:", len(out))
