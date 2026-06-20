// ════════════════════════════════════════════════════════════════════════════
// verse_split.js — порт verse_tool/verse_split_003.py на JS (для тега [faw]).
//
// Разбивает сплошной текст («стихи в прозе») на стихотворные строки по счёту
// слогов (гласных). Используется движком сайта при «Сохранить» в редакторе: если
// внутри [faw]…[/faw] нет ни одного «|», содержимое размечается этим алгоритмом и
// границы найденных строк проставляются знаком «|».
//
// Параметры алгоритма — те же два файла, что у Python-инструмента
// (Documents/verse_tool/): словарь чтения dict_common.txt и ручные правки
// ovr_common.txt — вшиты ниже константами DICT_COMMON / OVR_COMMON (источник
// истины — те .txt; при правке синхронизировать).
//
// Самотест паритета с Python: `node verse_split.js <input.txt> <out_lines.txt>`
// даёт дамп строк формата dump_lines() — он должен совпасть с --lines-out Python
// на том же входе. См. editor/_faw_test/.
// ════════════════════════════════════════════════════════════════════════════

const VOWELS = new Set("аеёиоуыэюяАЕЁИОУЫЭЮЯ");
const STRIP = '*"().,;:!?-«»+';
const STRIP_SET = new Set(STRIP);
const PUNCT_END = ',.;:!?-")»';
const PUNCT_END_SET = new Set(PUNCT_END);

// Встроенный минимум (как BUILTIN_DICT в Python): частые сокращения с точками.
const BUILTIN_DICT = { "т.п": 2, "т.е": 2, "т.к": 2 };

// ── Вшитые параметры (verbatim из Documents/verse_tool/) ────────────────────
const DICT_COMMON = `# Общий словарь чтения для текстов ЭБМ (61H + 61T): токен <пробел> слогов
# числа и формулы
1 2
8*10^9 8
# латиница и спецсимволы
AI-ЧАТАХ 4
FUTURE 2
Хуz 1
Xyz 1
Xyz-е 2
Xyz-ем 2
Xyz-я 2
Sad 1
but 1
true 1
+ 1
# вставки вне счета
МБ 0
# опечатки (чтение по размеру)
НЕЙРОПРАММОЙ 5
# фонетика автора
ХАББЛ 2
центр 2
цикл 2
вообще 2
`;

const OVR_COMMON = `# Ручные правки 61H: блоки принудительных строк, разделитель -- пустая строка
С ОСТАТКОМ
ОТ ТОГО, ЧТО ОСТАВАЛОСЬ
ОТ ТОГО, ЧТО ПЕРЕД ЭТИМ,
НУ ВЫ ПОНЯЛИ ГДЕ НЯМКА,
ЗА ГОДА МЕЛЕНЬЯ ЧУШИ,
ВСЕ, ОСТАВИВ ГОРШОК С ПЫЛЬЮ,

ТО ЕСТЬ ТАКОЙ ФОРМЫ, ЧАСТЬЮ
ЧЬЕЙ ВСЕГДА БЫВАЮТ ДВОЕ,
А НЕ

ОБ ТО, С ЧЕМ СТАЛ СВЯЗАН С ТЕХ ПОР,
СТАВ ДВОЙНОЙ ЧАСТИЦЕЙ

СВОЕГО ЖЕ ИНТЕЛЛЕКТА
НА ТРОН ДАВШЕГО НАМ РАЗУМ
БОГА
- КВАНТОВЫЙ СУПЕРКОМПЬЮТЕР,

А В ТОЙ ФОРМЕ, У КОТОРОЙ
ЕСТЬ ТО, ВО ЧТО НЕ ПРОНИКАЕТ

ТЕМ, КОГО ОН СДЕЛАЛ НЕ ТЕМ,
КТО С НИМ ВМЕСТЕ ЗНАЕТ,

БЕЗ КОТОРОГО НЕТ СМЫСЛА
НАМ КОНКРЕТНО КИПИШИТЬСЯ
С ЧЕМ ЛИБО ВООБЩЕ ЗДЕСЬ БЫЛО,

ПОТОМУ ЧТО У НИХ НЕТУ
БОГА,

- ЧТО ОБЪЕКТОМ Я САМ И ЯВЛЯЛСЯ
- ТОЛЬКО КОГДА НАПЕЧАТАЛ
"ЗНАТЬ" СТАЛ,
А ДО ТОГО ЧТО УГОДНО,

ЧТО МЫ ТУТ ЛЕТИМ ВСЕМ ФЛОТОМ
НЕ СОВСЕМ КУДА ГЛЯДЕЛИ
ТЕ ГЛАЗА, У ЧЬЕЙ СВОБОДЫ
БЫЛИ РАМКИ МЫСЛЕННОЙ КАРТИНКИ,

# Ручные правки 61T: блоки принудительных строк, разделитель -- пустая строка
и оно, когда посмотрят
на него извне, подобно
Шару, отразит все их внимание
к ним самим не дав обоим
шанса осознать пустотность

и его же ноосфера
плюс частей внешних число
уже за восемь миллиардов,

"ты, что самый умный?",
и так далее по списку,

тети мира взрослых,
дали выбрать за себя им
- всем кому угодно кроме

ВЫСШАЯ - МОЗГ НИЖНИХ),
ИЗ ЧЕГО САМОСОСТАВЛЕН
`;

// ── strip как Python str.strip(chars): срезает с обоих концов символы из набора ─
function pyStrip(s, set) {
  let a = 0, b = s.length;
  while (a < b && set.has(s[a])) a++;
  while (b > a && set.has(s[b - 1])) b--;
  return s.slice(a, b);
}

// ── load_dict ───────────────────────────────────────────────────────────────
function loadDict(text) {
  const dic = Object.assign({}, BUILTIN_DICT);
  if (!text) return dic;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const i = line.lastIndexOf(" ");          // rpartition(' ')
    const tok = i >= 0 ? line.slice(0, i).trim() : "";
    const num = i >= 0 ? line.slice(i + 1) : line;
    if (!tok || !/^-?\d+$/.test(num)) throw new Error("Плохая строка словаря: " + raw);
    dic[tok.toLowerCase()] = parseInt(num, 10);
  }
  return dic;
}

// ── load_overrides: блоки строк, разделитель — пустая строка ──────────────────
function loadOverrides(text) {
  if (!text) return [];
  const blocks = [];
  let cur = [];
  for (const raw of text.split("\n")) {
    const line = raw.replace(/\r$/, "");
    if (line.trim().startsWith("#")) continue;
    if (!line.trim()) { if (cur.length) { blocks.push(cur); cur = []; } continue; }
    cur.push(line.trim());
  }
  if (cur.length) blocks.push(cur);
  return blocks;
}

// ── make_syl ─────────────────────────────────────────────────────────────────
function makeSyl(dic) {
  return function syl(token) {
    const low = token.toLowerCase();
    if (low in dic) return dic[low];
    const base = pyStrip(low, STRIP_SET);
    if (base in dic) return dic[base];
    let n = 0;
    for (const c of token) if (VOWELS.has(c)) n++;
    return n;
  };
}

// ── parse_text: поток токенов [ [слово, метка|null], ... ] ───────────────────
// ¶ — внутренняя метка БЕЗЫМЯННОЙ границы абзаца (пустая строка в [faw]). В отличие от
// именованной «=== label {slug} ===» (нумерованный пункт → бейдж + TOC), безымянная граница
// в выводе даёт «[fp]» без метки: в инертном виде — разрыв абзаца, в стихе — невидима.
const FAW_PARA = String.fromCharCode(0xB6);

function parseText(srcText) {
  // re.split(r'^[ \t]*===\s*(.+?)\s*===[ \t]*$', src, flags=re.M)
  const rx = /^[ \t]*===\s*([\s\S]+?)\s*===[ \t]*$/gm;
  const parts = srcText.split(rx);
  const tokens = [];
  let cur = null;
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 1) { cur = parts[i]; continue; }   // имя раздела (=== … ===)
    // НЕ-секционную часть дробим на абзацы по пустым строкам. Первый токен абзаца (кроме
    // самого первого токена потока) несёт безымянную границу FAW_PARA → разрыв абзаца.
    const paras = parts[i].split(/\n[ \t]*\n+/);
    for (let pi = 0; pi < paras.length; pi++) {
      const words = paras[pi].trim().split(/\s+/).filter(Boolean);
      for (let wi = 0; wi < words.length; wi++) {
        let label = null;
        if (wi === 0) {
          if (cur !== null) { label = cur; cur = null; }     // явная === секция
          else if (tokens.length > 0) label = FAW_PARA;      // граница абзаца (пустая строка)
        }
        tokens.push([words[wi], label]);
      }
    }
  }
  return tokens;
}

// ── apply_overrides → {forcedCut:Set, locked:bool[]} ─────────────────────────
function applyOverrides(words, overrides) {
  const n = words.length;
  const forcedCut = new Set();
  const locked = new Array(n + 1).fill(false);

  function findSeq(seq, start) {
    for (let i = start; i <= n - seq.length; i++) {
      let ok = true;
      for (let k = 0; k < seq.length; k++) if (words[i + k] !== seq[k]) { ok = false; break; }
      if (ok) return i;
    }
    return -1;
  }

  let applied = 0, skipped = 0;
  for (const block of overrides) {
    const blk = block.join(" ").split(/\s+/);
    const pos = findSeq(blk, 0);
    if (pos < 0) { skipped++; continue; }            // блок из другого текста — пропуск
    if (findSeq(blk, pos + 1) >= 0) throw new Error("Override-блок встречается не один раз: " + block[0]);
    applied++;
    let i = pos;
    forcedCut.add(i);
    for (const line of block) {
      const ln = line.split(/\s+/).length;
      for (let k = i + 1; k < i + ln; k++) locked[k] = true;
      i += ln;
      forcedCut.add(i);
    }
  }
  return { forcedCut, locked, applied, skipped };
}

// ── build_groups: группа = слово + прилепленные 0-сложные токены ─────────────
function buildGroups(tokens, syl, forcedCut, locked) {
  const n = tokens.length;
  const groups = [];
  let pending = [], pendSec = null, pendStart = null;
  for (let idx = 0; idx < n; idx++) {
    const w = tokens[idx][0], sec = tokens[idx][1];
    const s = syl(w);
    if (sec && pendSec === null) pendSec = sec;
    if (pendStart === null) pendStart = idx;
    if (s === 0) {
      const nxtForced = forcedCut.has(idx + 1) && !locked[idx + 1];
      if (idx + 1 < n && !nxtForced) { pending.push(w); continue; }   // липнет к следующему
      if (groups.length) {
        const g = groups[groups.length - 1];
        g.text += " " + pending.concat([w]).join(" ");
        g.tend = idx + 1;
        pending = []; pendSec = null; pendStart = null;
      } else {
        pending.push(w);
      }
      continue;
    }
    groups.push({ text: pending.concat([w]).join(" "), syl: s, sec: pendSec,
                  tstart: pendStart, tend: idx + 1 });
    pending = []; pendSec = null; pendStart = null;
  }
  if (pending.length && groups.length) {
    const g = groups[groups.length - 1];
    g.text += " " + pending.join(" ");
    g.tend = n;
  }
  return groups;
}

// ── make_pen ─────────────────────────────────────────────────────────────────
function makePen(N) {
  const deficit = [0.0, 1.2, 3.0, 4.5, 5.5, 6.5, 8.0, 10.0];
  return function pen(t) {
    if (t === N) return 0.0;
    if (t < N) { const d = N - t; return d < deficit.length ? deficit[d] : 10.0 + (d - 7); }
    return 2.0 + 2.5 * (t - N - 1);
  };
}

// ── dp_segment: разбивка минимального суммарного штрафа (сбой локален) ────────
function dpSegment(groups, N, nTokens, forcedCut, locked) {
  if (!forcedCut) forcedCut = new Set();
  if (!locked) locked = new Array(nTokens + 1).fill(false);
  const G = groups.length;
  const pen = makePen(N);
  const maxlen = N + 6;

  const cuttable = (gi) => { const t = gi < G ? groups[gi].tstart : nTokens; return !locked[t]; };
  const forced = (gi) => { const t = gi < G ? groups[gi].tstart : nTokens; return forcedCut.has(t); };

  const INF = Infinity;
  const best = new Array(G + 1).fill(INF);
  const prev = new Array(G + 1).fill(-1);
  best[0] = 0.0;
  for (let i = 1; i <= G; i++) {
    if (!(i === G || cuttable(i))) continue;
    let t = 0;
    let j = i - 1;
    while (j >= 0) {
      t += groups[j].syl;
      if (t > maxlen) break;
      const startOk = (j === 0) || cuttable(j);
      let crosses = false;
      for (let k = j + 1; k < i; k++) if (forced(k)) { crosses = true; break; }
      if (startOk && !crosses) {
        let cost = pen(t);
        const last = groups[i - 1].text;
        if (last && PUNCT_END_SET.has(last[last.length - 1])) {
          cost -= 0.35;
          if (".!?".includes(last[last.length - 1])) cost -= 0.15;
        }
        if (best[j] + cost < best[i]) { best[i] = best[j] + cost; prev[i] = j; }
      }
      j -= 1;
    }
  }
  if (best[G] === INF) throw new Error("DP не нашёл разбивку (размер " + N + ")");
  const cuts = [];
  let i = G;
  while (i > 0) { cuts.push([prev[i], i]); i = prev[i]; }
  cuts.reverse();
  const lines = [];
  for (const [j, ii] of cuts) {
    const seg = groups.slice(j, ii);
    lines.push({
      parts: seg.map((g) => [g.text, g.sec]),
      syl: seg.reduce((a, g) => a + g.syl, 0),
    });
  }
  return { lines, total: best[G] };
}

// round half-to-even на 3 знака (как Python round(x,3)) — для устойчивого argmax
function round3(x) {
  const scaled = x * 1000;
  const floor = Math.floor(scaled);
  const diff = scaled - floor;
  let r;
  if (diff > 0.5) r = floor + 1;
  else if (diff < 0.5) r = floor;
  else r = (floor % 2 === 0) ? floor : floor + 1;
  return r / 1000;
}

// ── detect_meter: перебор кандидатов размера ─────────────────────────────────
function detectMeter(groups, nTokens, lo, hi) {
  const table = [];
  for (let N = lo; N <= hi; N++) {
    const { lines } = dpSegment(groups, N, nTokens);
    const total = lines.length;
    const clean = lines.filter((ln) => ln.syl === N).length / total;
    const punct = lines.filter((ln) => {
      const lastTxt = ln.parts[ln.parts.length - 1][0];
      return PUNCT_END_SET.has(lastTxt[lastTxt.length - 1]);
    }).length / total;
    table.push([N, clean, punct, total]);
  }
  const bestClean = Math.max(...table.map((r) => r[1]));
  const cands = table.filter((r) => r[1] >= bestClean - 0.03);
  let chosen = cands[0];
  for (const r of cands) {
    const a = [round3(r[2]), r[0]], b = [round3(chosen[2]), chosen[0]];
    if (a[0] > b[0] || (a[0] === b[0] && a[1] > b[1])) chosen = r;
  }
  return { meter: chosen[0], table };
}

// ════════════════════════════════════════════════════════════════════════════
// Публичный API
// ════════════════════════════════════════════════════════════════════════════

// Полный прогон: текст → массив строк (как у Python). Возвращает {lines, meter}.
export function splitVerse(srcText, opts) {
  opts = opts || {};
  const dic = loadDict(opts.dict !== undefined ? opts.dict : DICT_COMMON);
  const overrides = loadOverrides(opts.overrides !== undefined ? opts.overrides : OVR_COMMON);
  const syl = makeSyl(dic);
  const tokens = parseText(srcText);
  const words = tokens.map((t) => t[0]);
  const n = words.length;

  let meter = opts.meter;
  if (meter === undefined || meter === null) {
    const freeGroups = buildGroups(tokens, syl, new Set(), new Array(n + 1).fill(false));
    meter = detectMeter(freeGroups, n, opts.lo || 5, opts.hi || 14).meter;
  }
  const { forcedCut, locked } = applyOverrides(words, overrides);
  const groups = buildGroups(tokens, syl, forcedCut, locked);
  const { lines } = dpSegment(groups, meter, n, forcedCut, locked);
  return { lines, meter };
}

// dump формата dump_lines() Python — для самотеста паритета.
export function dumpLines(lines, meter) {
  const out = [];
  for (let k = 0; k < lines.length; k++) {
    const ln = lines[k];
    const secs = ln.parts.filter((p) => p[1]).map((p) => p[1]);
    const mark = secs.length ? "[" + secs.join(",") + "] " : "";
    const fl = ln.syl !== meter ? "  <<< СБОЙ (" + ln.syl + ")" : "";
    const body = ln.parts.map((p) => p[0]).join(" ");
    out.push(String(k + 1).padStart(4, "0") + " " + mark + body + fl);
  }
  return out.join("\n");
}

// Маркер пункта из имени секции «=== <label> {slug} ===»: → инлайн [fp="label" slug="slug"].
// Пункты НЕ рвут строку (стих течёт через границы) — маркер ставится перед словом, где
// пункт начинается (может оказаться в середине строки). render рисует бейдж + запись в TOC.
function fpMarker(secName) {
  if (secName === FAW_PARA) return "[fp]";   // безымянная граница абзаца → [fp] без метки
  const m = /^([\s\S]*?)\s*\{([^}]+)\}\s*$/.exec(secName);
  const label = (m ? m[1] : secName).trim().replace(/"/g, "");
  const slug = m ? m[2].trim().replace(/[^\w-]/g, "") : "";
  return slug ? `[fp="${label}" slug="${slug}"]` : `[fp="${label}"]`;
}

// ── Главный API для [faw]: расставить «|» по найденным границам строк ─────────
// Берёт «голый» внутренний текст тега (без |), возвращает его же со вставленными «|»
// между строками. Секции «=== <label> {slug} ===» (границы нумерованных пунктов) →
// инлайн-маркеры [fp=…] на позиции начала пункта (строки текут через границы). Авторские
// \n внутри faw — разделители токенов (как пробелы); единственная граница строки — «|».
export function markupFaw(innerText, opts) {
  const src = (innerText || "").replace(/^\n+/, "").replace(/\n+$/, "");
  if (!src.trim()) return innerText;
  const { lines } = splitVerse(src, opts || {});
  return lines.map((ln) =>
    ln.parts.map(([text, sec]) => (sec ? fpMarker(sec) + " " : "") + text).join(" ")
  ).join(" | ");
}

// ── CLI для самотеста под node ───────────────────────────────────────────────
// node verse_split.js <input.txt> <out_lines.txt>
if (typeof process !== "undefined" && process.argv && process.argv[1] &&
    /verse_split\.js$/.test(process.argv[1].replace(/\\/g, "/")) && process.argv[2]) {
  const fs = await import("node:fs");
  const inp = fs.readFileSync(process.argv[2], "utf-8");
  const { lines, meter } = splitVerse(inp, {});
  const dump = dumpLines(lines, meter);
  if (process.argv[3]) fs.writeFileSync(process.argv[3], dump, "utf-8");
  console.log("meter=" + meter + " lines=" + lines.length +
    " breaks=" + lines.filter((l) => l.syl !== meter).length);
}
