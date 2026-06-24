// ZML → HTML renderer (spec v0.1). SINGLE SOURCE OF TRUTH for rendering.
// Runs unchanged in Node (build: tools/build.mjs) and in the browser
// (live preview + save inside the gh-pages editor) → same code, no drift.
// Ported from the now-retired Python src/4_render.py (archived in _backups/).

// ════════════════════════════════════════════════════════════════════════════
// CONSTANTS  (keep in sync with 4_render.py)
// ════════════════════════════════════════════════════════════════════════════

export const CSS_VERSION = "20260620-01";

// АВТОРСКИЕ названия разделов (сборники proza.ru). НЕ переименовывать/не
// «адаптировать» — переносятся как есть. Канон сверен с первым деплоем; должно
// совпадать с SECTION_NAMES в src/5_index.py.
export const SECTION_HUMAN = {
  best: "Избранное",
  dreamon: "Мечтай!!",
  cyberson: "Киберсон",
  dabudet: "Да будет Свет!",
  confront: "Конфронтология Духа",
  shoshana: "Роза Среди Шипов",
  other: "Без категории",
};

// ── PROPER NOUNS (kept capitalised inside small-caps) ───────────────────────
// The word list lives in an editable file (config/proper-nouns.txt), passed in
// via ctx.properNouns. Only BASE (nominative) forms; Russian case endings are
// matched by regex. A leading "!" marks an exact-only word (no declensions).

const CASE_ENDINGS = new Set([
  "", "А", "Я", "У", "Ю", "Е", "Ы", "И", "О", "ОМ", "ЕМ", "ЁМ",
  "ОВ", "ЕВ", "АМ", "ЯМ", "АМИ", "ЯМИ", "АХ", "ЯХ",
  "ОЙ", "ЕЙ", "ОЮ", "ЕЮ", "Ь", "Й",
]); // "О" — средний род (Кольцо/Царство/Древо)

// ё/е-insensitive uppercase normaliser.
const pnNorm = (s) => s.toUpperCase().replace(/Ё/g, "Е");

// Oblique stem for a base (ё-normalised, uppercase) nominative form.
function pnStem(base) {
  if (base === "ТВОРЕЦ") return "ТВОРЦ"; // fleeting vowel
  if (base === "ОРЕЛ") return "ОРЛ";     // fleeting vowel (ОРЁЛ→ОРЕЛ)
  const last = base[base.length - 1];
  if (last === "Ь" || last === "Й" || last === "А" || last === "Я") return base.slice(0, -1);
  return base; // consonant / vowel stem
}

// Parse the editable list → matcher (bareUpper) → boolean.
function compileProperNouns(txt) {
  const exact = new Set();
  const lemmas = [];
  for (let line of (txt || "").split("\n")) {
    line = line.trim();
    if (!line || line.startsWith("#")) continue;
    let exactOnly = false;
    if (line.startsWith("!")) { exactOnly = true; line = line.slice(1).trim(); }
    const base = pnNorm(line);
    if (!base) continue;
    if (exactOnly) exact.add(base);
    else lemmas.push({ base, stem: pnStem(base) });
  }
  return (bareUpper) => {
    const b = pnNorm(bareUpper);
    if (!b) return false;
    if (exact.has(b)) return true;
    for (const { base, stem } of lemmas) {
      if (b === base) return true;
      if (b.startsWith(stem) && CASE_ENDINGS.has(b.slice(stem.length))) return true;
    }
    return false;
  };
}

// Honorific phrase — capitalised only as a unit inside CAPS lines. Longer form
// first so "Свят Благословен Он" wins over the bare "Благословен Он".
const RX_SVYAT_BLAG = /(?<![А-Яа-яЁёA-Za-z])СВЯТ\s+БЛАГОСЛОВЕН\s+ОН(?![А-Яа-яЁёA-Za-z])/g;
const RX_BLAG_ON = /(?<![А-Яа-яЁёA-Za-z])БЛАГОСЛОВЕН\s+ОН(?![А-Яа-яЁёA-Za-z])/g;
function applyHonorific(s) {
  return s.replace(RX_SVYAT_BLAG, "Свят Благословен Он").replace(RX_BLAG_ON, "Благословен Он");
}

// Epilogue is NOT a separate tag (ZML3 A4): an epilogue is an [epi] block in
// TAIL position, labelled «Эпилог» by the renderer via block index. So only
// [epi] is parsed here — [epil] was retired with the Ф3 shadowing quirk.
const PAIRED = ["poem", "epi", "quote", "num", "mus", "shir", "subsec", "sub", "meta", "sig", "cry", "line", "ul", "dlg", "faw"];
const PAIRED_ALT = PAIRED.join("|");

// Footnote GROUPS (fn-ревью, вердикты 1+3): marker [^имя.N], definition
// [^имя.N]:, output block [refs=имя] at the authorial position, optional
// series glyph [refs=имя glyph=¤] → markers render as «¤1, ¤2…».
const FN_GROUP_NAME = "[A-Za-z\\u0400-\\u04FF0-9_-]+";

// ════════════════════════════════════════════════════════════════════════════
// SMALL HELPERS
// ════════════════════════════════════════════════════════════════════════════

function htmlEscape(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Python str.capitalize(): first char upper, the rest lower.
function capitalizeWord(w) {
  if (!w) return w;
  return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
}

const WORD_CHAR_RX = /[0-9_]|\p{L}/u; // ≈ Python \w (unicode): letters + digits + _
function isWordChar(c) {
  return c !== "" && c !== undefined && WORD_CHAR_RX.test(c);
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Literal (non-regex) replace-all — mirrors Python str.replace.
function replaceAllLiteral(str, find, val) {
  return str.split(find).join(val);
}

// Split on a 1-char separator NOT preceded by a backslash; the escaped «\sep»
// collapses to a literal sep in the field. Used by [shir] (§6.2: rare `|`/`,`
// inside a field is escaped `\|` / `\,`).
function splitEscaped(s, sep) {
  const parts = [];
  let buf = "";
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "\\" && s[i + 1] === sep) { buf += sep; i++; continue; }
    if (s[i] === sep) { parts.push(buf); buf = ""; continue; }
    buf += s[i];
  }
  parts.push(buf);
  return parts;
}

// ════════════════════════════════════════════════════════════════════════════
// FRONTMATTER + BODY SPLIT
// ════════════════════════════════════════════════════════════════════════════

export function parseFrontmatter(zml) {
  const fm = {};
  let body = zml;
  const m = /^---\n([\s\S]*?)\n---\n?/.exec(zml);
  if (m) {
    for (let line of m[1].split("\n")) {
      line = line.replace(/\s+$/, ""); // rstrip
      if (!line || !line.includes(":")) continue;
      const idx = line.indexOf(":");
      const k = line.slice(0, idx);
      let v = line.slice(idx + 1).trim();
      if ((v.startsWith('"') && v.endsWith('"')) ||
          (v.startsWith("'") && v.endsWith("'"))) {
        v = v.slice(1, -1);
      }
      fm[k.trim()] = v;
    }
    body = zml.slice(m[0].length);
  }
  return [fm, body.replace(/^\n+/, "")]; // body.lstrip("\n")
}

// ════════════════════════════════════════════════════════════════════════════
// BLOCK PARSER
// ════════════════════════════════════════════════════════════════════════════

// ## section heading + ### nested sub-heading (fn-ревью, вердикт 4: h3 И h4
// оригиналов → один уровень ###; TOC рисует ### вложенным вторым уровнем).
// slug NEVER contains «|» → exclude it so a trailing inline {term|X}/{leit|X} in
// the heading text (17BA: «## 2 {term|Хохма}») isn't swallowed as the slug.
const SECTION_RX = /^(#{2,3})\s+(.*?)(?:\s+\{([^}|]+)\})?\s*$/;
const FN_BODY_RX = new RegExp(
  "^\\[\\^(" + FN_GROUP_NAME + "\\.\\d+|\\d+|\\*+|\\|[^\\]]*)?\\]:\\s?(.*)$",
);
// standalone markers (no closing tag): [toc] / [toc collapsed] (вердикт 11) and
// [refs] / [refs=имя] / [refs=имя glyph=¤] (вердикт 1).
// [toc] / [toc collapsed] (вердикт 11) / [toc nonum] — nonum гасит авто-числа
// <ol> (когда сами заголовки нумерованы «1 / 1.1 / 1.1.1» — иначе двойная нумерация).
const TOC_RX = /^\[toc\b([^\]]*)\]\s*$/;
const REFS_RX = /^\[refs(?:=(?:"([^"\]]+)"|([^\s\]"]+)))?((?:\s+[^\]]*)?)\]\s*$/;

export function parseBody(body) {
  const lines = body.split("\n");
  let fnStart = null;
  for (let i = 0; i < lines.length; i++) {
    if (FN_BODY_RX.test(lines[i])) { fnStart = i; break; }
  }
  if (fnStart !== null) {
    const bodyMain = lines.slice(0, fnStart).join("\n").replace(/\n+$/, "");
    const footnotes = parseFootnotes(lines.slice(fnStart).join("\n"));
    return [parseMain(bodyMain), footnotes];
  }
  return [parseMain(body), []];
}

function parseFootnotes(text) {
  const out = [];
  let cur = null;
  let curLines = [];

  function flush() {
    if (cur === null) return;
    cur.body = curLines.join("\n").replace(/\s+$/, ""); // rstrip
    out.push(cur);
    cur = null;
    curLines = [];
  }

  for (const raw of text.split("\n")) {
    if (raw.trim() === "") {
      if (cur !== null) curLines.push("");
      continue;
    }
    const m = FN_BODY_RX.exec(raw);
    if (m && !raw.startsWith(" ")) {
      flush();
      const fid = m[1]; // undefined if absent
      let kind = "numbered";
      let idInt = null;
      let prefix = null;
      let star = null;
      let group = null;
      if (fid === undefined) {
        kind = "anon";
      } else if (fid.startsWith("|")) {
        kind = "anon";
        // «» (из [^|]:) = голый анон без ярлыка (ZML3 А1); непустой = свой ярлык.
        // НЕ сворачиваем "" в null — это отличает [^|]: от [^]: (дефолт «См. также»).
        prefix = fid.slice(1).trim();
        if (prefix && /^\*+$/.test(prefix)) { kind = "starred"; star = prefix; }
      } else if (/^\*+$/.test(fid)) {
        kind = "starred";
        star = fid;
      } else if (fid.includes(".")) {
        // named group definition [^имя.N]: (fn-ревью, вердикт 1)
        const di = fid.lastIndexOf(".");
        group = fid.slice(0, di);
        idInt = parseInt(fid.slice(di + 1), 10);
      } else {
        idInt = parseInt(fid, 10);
      }
      cur = { kind, id: idInt, prefix, star, group };
      curLines = [m[2]];
    } else {
      if (raw.startsWith("    ")) curLines.push(raw.slice(4));
      else curLines.push(raw);
    }
  }
  flush();
  for (const fn of out) fn.body = fn.body.replace(/\n+$/, "");
  return out;
}

function parseMain(body) {
  const blocks = [];
  let pos = 0;
  const n = body.length;

  const blankRx = /\n+/y;
  // Inner uses `.` (no newline) to mirror Python's `.*?` (no re.DOTALL): a
  // single-line block must have open tag, body and close tag on one physical
  // line. Multi-line blocks fall through to openRx below — including Python's
  // epi-before-epil shadowing quirk, which we reproduce for exact parity.
  // attr-кусок: кавычки могут нести `]` внутри ([mus="Песнь Ступеней[^10]"],
  // 2C3/12F…) — двойно-квотированные строки глотаются целиком (фикс 20:33).
  // Альтернативы НЕ пересекаются ([^\]"] без кавычки) — иначе катастрофический
  // бэктрекинг на длинных строках с `[` без закрытия (повисание 20:39)
  const ATTR_PART = '(=?(?:"[^"]*"|[^\\]"])*)?';
  const singleRx = new RegExp(
    "\\[(" + PAIRED_ALT + ")" + ATTR_PART + "\\](.*?)\\[\\/\\1\\]\\s*(?=\\n|$)",
    "y",
  );
  const openRx = new RegExp(
    "\\[(" + PAIRED_ALT + ")" + ATTR_PART + "\\]\\s*\\n",
    "y",
  );

  while (pos < n) {
    blankRx.lastIndex = pos;
    const mb = blankRx.exec(body);
    if (mb && mb.index === pos) { pos += mb[0].length; continue; }
    if (pos >= n) break;

    let lineEnd = body.indexOf("\n", pos);
    if (lineEnd === -1) lineEnd = n;
    const line = body.slice(pos, lineEnd);

    const mh = SECTION_RX.exec(line);
    if (mh) {
      blocks.push({
        type: "heading",
        level: mh[1].length, // 2 = ##, 3 = ###
        text: mh[2].trim(),
        slug: (mh[3] || "").trim() || null,
      });
      pos = lineEnd + 1;
      continue;
    }

    const mt = TOC_RX.exec(line);
    if (mt) {
      const a = mt[1] || "";
      blocks.push({
        type: "toc",
        collapsed: /\bcollapsed\b/.test(a),
        nonum: /\bnonum\b/.test(a),
      });
      pos = lineEnd + 1;
      continue;
    }

    const mr = REFS_RX.exec(line);
    if (mr) {
      blocks.push({
        type: "refs",
        group: (mr[1] || mr[2] || "").trim(),
        attrs: parseAttrs(mr[3] || ""),
      });
      pos = lineEnd + 1;
      continue;
    }

    singleRx.lastIndex = pos;
    const ms = singleRx.exec(body);
    if (ms && ms.index === pos) {
      blocks.push({ type: ms[1], attrs: parseAttrs(ms[2] || ""), inner: ms[3] });
      pos += ms[0].length;
      continue;
    }

    openRx.lastIndex = pos;
    const mo = openRx.exec(body);
    if (mo && mo.index === pos) {
      const tag = mo[1];
      const attrs = parseAttrs(mo[2] || "");
      const innerStart = pos + mo[0].length;
      const closeRx = new RegExp("\\n\\[\\/" + escapeRe(tag) + "\\]\\s*(\\n|$)", "g");
      closeRx.lastIndex = innerStart;
      const mc = closeRx.exec(body);
      if (mc) {
        const inner = body.slice(innerStart, mc.index);
        pos = mc.index + mc[0].length;
        blocks.push({ type: tag, attrs, inner });
        continue;
      }
    }

    const ppEnd = body.indexOf("\n\n", pos);
    let para;
    if (ppEnd !== -1) { para = body.slice(pos, ppEnd); pos = ppEnd + 2; }
    else { para = body.slice(pos); pos = n; }
    para = para.replace(/\s+$/, ""); // rstrip
    if (para) blocks.push({ type: "paragraph", text: para });
  }
  return blocks;
}

function parseAttrs(s) {
  const out = {};
  s = s.trim();
  if (s.startsWith("=")) {
    // quoted ="…" or bare =value (bare: up to whitespace — fn-ревью syntax)
    const m = /^=(?:"([^"]*)"|([^\s\]"]+))/.exec(s);
    if (m) { out.label = m[1] !== undefined ? m[1] : m[2]; s = s.slice(m[0].length); }
  }
  // key=value пары → out, вырезаем (заменяем пробелом)
  s = s.replace(/(\w+)=(?:"([^"]*)"|([^\s\]"]+))/g,
    (mm, k, q, v) => { out[k] = q !== undefined ? q : v; return " "; });
  // голые булевы флаги ([mus num], [mus="…" num])
  for (const tok of s.split(/\s+/)) if (/^\w+$/.test(tok)) out[tok] = true;
  return out;
}

// ════════════════════════════════════════════════════════════════════════════
// INLINE CASCADE
// ════════════════════════════════════════════════════════════════════════════

export function resolveInline(text, inline) {
  const capsPass = inline.capsPass !== false;
  let s = htmlEscape(text);
  s = resolveFootnotes(s, inline);
  s = resolveInternals(s, inline.manifestByArt);
  s = resolveZohar(s, inline.zoharIndex);
  s = resolveTermLeit(s);
  s = resolveExternal(s);
  s = resolveItalic(s);
  s = resolveGlyphs(s);
  if (capsPass && inline.capsEnabled) s = resolveCaps(s, inline.matchProperNoun);
  s = resolveSpoiler(s);
  return s;
}

// Inline footnote markers. Three shapes (fn-ревью, вердикты 1+3):
//   [^N]      numeric, default group        → label [N]
//   [^*]/[^**] authorial starred (182)      → label = the bare asterisk run
//   [^имя.N]  named group                   → id cite_note-имя-N; label = [N],
//             or «¤N» when the group's [refs=имя glyph=¤] declares a series glyph.
// seenRefs lives on the inline ctx (shared across ALL resolveInline calls of one
// article) so repeated markers get -extraK suffixes document-wide, not per-block.
const FN_MARKER_RX = new RegExp(
  "\\[\\^(?:(" + FN_GROUP_NAME + ")\\.)?(\\d+|\\*+)\\]", "g",
);
function fnMarkerKey(group, d) {
  if (!group && d[0] === "*") return `star${d.length}`;
  return group ? `${group}-${parseInt(d, 10)}` : String(parseInt(d, 10));
}
function resolveFootnotes(s, inline) {
  const seen = (inline && inline.seenRefs) || {};
  const glyphs = (inline && inline.groupGlyphs) || {};
  return s.replace(FN_MARKER_RX, (_, g, d) => {
    const star = !g && d[0] === "*";
    const nid = fnMarkerKey(g, d);
    if (inline && inline.refNotes) inline.refNotes.add(nid);
    seen[nid] = (seen[nid] || 0) + 1;
    const suffix = seen[nid] === 1 ? "" : `-extra${seen[nid] - 1}`;
    const label = star ? d
      : (g && glyphs[g] ? `${htmlEscape(glyphs[g])}${parseInt(d, 10)}` : `[${parseInt(d, 10)}]`);
    return `<sup id="cite_ref-${nid}${suffix}"><a href="#cite_note-${nid}">${label}</a></sup>`;
  });
}

function resolveInternals(s, manifestByArt) {
  return s.replace(/\[\[([A-Za-z0-9]+)\]\]/g, (_, art) => {
    const rec = manifestByArt[art];
    if (!rec) return `<a class="broken" href="#">[[${art}]]</a>`;
    const title = rec.title || art;
    // url-unification: единственный публичный адрес статьи — NNN.html (тот же dir).
    const href = `${art}.html`;
    return `<a class="internal" href="${href}">${htmlEscape(title)}</a>`;
  });
}

// {ch|N} — конкретная статья главы; {ch|} — ВСЯ глава (её index-страница);
// {|} — ВЕСЬ Зоар (корневой index = полное оглавление). Глава и номер в регэкспе
// необязательны (пустые). Следующий пасс {term|…}/{leit|…} ловит только нецифровое
// содержимое, поэтому {term|текст} сюда НЕ попадает (цифр после | нет).
function resolveZohar(s, zoharIndex) {
  const chapters = zoharIndex.chapters || {};
  const articles = zoharIndex.articles || {};
  const base = zoharIndex._url_base || "https://imyavel.github.io/zohar-sulam";
  return s.replace(/\{([a-z][a-z-]*)?\|(\d*)\}/g, (_, ch, num) => {
    // {|} → весь Зоар: корневой index (полное оглавление)
    if (!ch) return `<a class="zohar" href="${base}/">Книга Зоар</a>`;
    const chInfo = chapters[ch];
    if (!chInfo) return `<a class="broken" href="#">{${ch}|${num}}</a>`;
    const knigaHuman = chInfo.kniga_human || "";
    // {ch|} → вся глава: её собственная index-страница
    if (!num) {
      const chHuman = chInfo.human || ch;
      const anchor = knigaHuman ? `Книга Зоар. ${knigaHuman}. ${chHuman}` : `Книга Зоар. ${chHuman}`;
      return `<a class="zohar" href="${base}/${ch}/">${htmlEscape(anchor)}</a>`;
    }
    // {ch|N} → конкретная статья
    const artTitle = (articles[ch] || {})[num];
    if (!artTitle) return `<a class="broken" href="#">{${ch}|${num}}</a>`;
    const href = `${base}/${ch}/${String(parseInt(num, 10)).padStart(3, "0")}.html`;
    const anchor = `Книга Зоар. ${knigaHuman}. ${artTitle}`;
    return `<a class="zohar" href="${href}">${htmlEscape(anchor)}</a>`;
  });
}

function resolveExternal(s) {
  s = s.replace(
    /\[(https?:\/\/[^\s\|\]]+)\|([^\]]+)\]/g,
    (_, url, anchor) => `<a href="${url}" target="_blank" rel="noopener">${anchor}</a>`,
  );
  s = s.replace(
    /\[(https?:\/\/[^\s\]]+)\]/g,
    (_, url) => `<a href="${url}" target="_blank" rel="noopener">${url}</a>`,
  );
  return s;
}

// {term|текст} / {leit|текст} — optional inline hook for a term / leitmotif
// (ZML3 C10 = ZML2 Q13). The theme colours it or ignores it. Runs after the
// zohar pass ({chapter|N} takes digits only, so no clash) and before links.
function resolveTermLeit(s) {
  return s.replace(
    /\{(term|leit)\|([^}\n]+)\}/g,
    (_, kind, inner) => `<span class="${kind}">${inner}</span>`,
  );
}

// C13 (ZML3 §3/§5): authorial glyphs — whitelist (extend as the corpus reveals
// more), wrapped AFTER htmlEscape so patterns match the escaped text. The
// parser never interprets them. NOT to be confused with proza.ru `;;;;` junk —
// that is cleaned converter-side, never wrapped.
const GLYPH_PATTERNS = [
  /&lt;\\\^\/&gt;/g, // <\^/> — руки вверх
  /&lt;\/v\\&gt;/g,  // </v\> — руки вниз
  /;::\)+/g,         // ;::))) — авторский эмотикон
];
function resolveGlyphs(s) {
  for (const re of GLYPH_PATTERNS) {
    s = s.replace(re, (m) => `<span class="glyph">${m}</span>`);
  }
  return s;
}

function resolveItalic(s) {
  return s.replace(
    /(?<![A-Za-zА-Яа-яёЁ0-9_])_([^_\n]{1,60}?)_(?![A-Za-zА-Яа-яёЁ0-9_])/g,
    "<em>$1</em>",
  );
}

// [spl]…[/spl] — inline spoiler (Telegram-style): content hidden under a cover
// (CSS ::before; default animated shimmer, or a gif via [spl="cover.gif"]…),
// revealed on click (JS in the page template). Resolved LAST so the inner text
// already went through every inline pass (footnotes/links/italic/caps); works
// inside [sub] headings and any block since it's a plain inline span.
function resolveSpoiler(s) {
  return s.replace(
    /\[spl(?:="([^"]*)")?\]([\s\S]*?)\[\/spl\]/g,
    (_, cover, inner) => {
      const style = cover ? ` style="--spl-cover:url('${cover}')"` : "";
      return (
        `<span class="spoiler" tabindex="0" role="button" ` +
        `aria-label="Спойлер — нажмите, чтобы открыть"${style}>` +
        `<span class="spoiler-content">${inner}</span></span>`
      );
    },
  );
}

const CYRILLIC_LETTER = /[А-Яа-яёЁ]/;
const CYRILLIC_UPPER = /[А-ЯЁ]/;

function isCapsLine(line) {
  const text = line.replace(/<[^>]+>/g, "");
  const letters = text.match(/[А-Яа-яёЁ]/g) || [];
  if (letters.length < 3) return false;
  let uppers = 0;
  for (const c of letters) if (CYRILLIC_UPPER.test(c)) uppers++;
  return uppers / Math.max(1, letters.length) >= 0.70;
}

function resolveCaps(s, matchProperNoun) {
  const out = [];
  for (const line of s.split("\n")) {
    if (isCapsLine(line)) {
      out.push(capsToSmallcaps(line, matchProperNoun));
    } else {
      out.push(line.replace(/\^([A-ZА-ЯЁ][A-ZА-ЯЁ-]*)/g, (_, w) => capitalizeWord(w)));
    }
  }
  return out.join("\n");
}

function capsToSmallcaps(line, matchProperNoun) {
  const match = matchProperNoun || (() => false);
  const foldWord = (w) => {
    if (!w) return w;
    const bare = w.toUpperCase().replace(/[^А-ЯЁA-Z]/g, "");
    if (match(bare)) return capitalizeWord(w);
    return w.toLowerCase();
  };

  // ^WORD — forced capital, drop the caret.
  line = line.replace(/\^([A-ZА-ЯЁ][A-ZА-ЯЁ-]*)/g, (_, w) => capitalizeWord(w));
  // Honorific phrase as a unit, before per-word folding lowercases it.
  line = applyHonorific(line);

  // Fold free-text runs, leave HTML tags verbatim.
  const parts = [];
  let last = 0;
  const tagRe = /<[^>]+>/g;
  let m;
  while ((m = tagRe.exec(line)) !== null) {
    parts.push(foldTextCaps(line.slice(last, m.index), foldWord));
    parts.push(m[0]);
    last = m.index + m[0].length;
  }
  parts.push(foldTextCaps(line.slice(last), foldWord));
  let folded = parts.join("");
  folded = capitaliseSentences(folded);
  return '<span class="sb">' + folded + "</span>";
}

// Emulates Python  re.sub(r'\b[А-ЯЁA-Z][А-ЯЁA-Z-]*\b', foldWord, text)
// — JS \b is ASCII-only, so word boundaries are checked manually against a
// Unicode word-char class.
function foldTextCaps(text, foldWord) {
  function boundaryAt(p) {
    const a = p > 0 ? isWordChar(text[p - 1]) : false;
    const b = p < text.length ? isWordChar(text[p]) : false;
    return a !== b;
  }
  const re = /[А-ЯЁA-Z][А-ЯЁA-Z-]*/g;
  let out = "";
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    const start = m.index;
    const greedyEnd = start + m[0].length;
    // Leading \b: char before the run must be a non-word char (or start).
    if (start > 0 && isWordChar(text[start - 1])) {
      re.lastIndex = greedyEnd;
      continue;
    }
    // Trailing \b: backtrack the run end until it sits on a word boundary.
    let end = greedyEnd;
    while (end > start && !boundaryAt(end)) end--;
    if (end <= start) { re.lastIndex = greedyEnd; continue; }
    const token = text.slice(start, end);
    out += text.slice(last, start) + foldWord(token);
    last = end;
    re.lastIndex = end;
  }
  out += text.slice(last);
  return out;
}

function capitaliseSentences(s) {
  const out = [];
  let capNext = true;
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "<") {
      const end = s.indexOf(">", i);
      if (end === -1) { out.push(s.slice(i)); break; }
      out.push(s.slice(i, end + 1));
      i = end + 1;
      continue;
    }
    if (capNext && /\p{L}/u.test(c)) {
      out.push(c.toUpperCase());
      capNext = false;
    } else {
      out.push(c);
      if (c === "." || c === "!" || c === "?") {
        const j = i + 1;
        if (j >= s.length || s[j] === " " || s[j] === "\t" || s[j] === "\n") {
          capNext = true;
        }
      }
    }
    i++;
  }
  return out.join("");
}

// ════════════════════════════════════════════════════════════════════════════
// BLOCK RENDERERS
// ════════════════════════════════════════════════════════════════════════════

function renderBlocks(blocks, ctx) {
  const out = [];
  const lastIdx = blocks.length - 1;
  for (let bi = 0; bi < blocks.length; bi++) {
    const b = blocks[bi];
    switch (b.type) {
      case "heading":   out.push(renderHeading(b, ctx)); break;
      case "paragraph": out.push(renderParagraph(b, ctx)); break;
      case "poem":      out.push(renderPoem(b, ctx)); break;
      case "faw":       out.push(renderFaw(b, ctx)); break;
      case "epi": {
        // Epilogue = [epi] in TAIL position (last body block, and not the only
        // one — ZML3 A4). Render decides the label by position; no [epil] tag.
        const isEpilogue = bi === lastIdx && bi > 0;
        out.push(renderEpigraph(b, ctx,
          isEpilogue ? "Эпилог" : "Эпиграф",
          isEpilogue ? "epilogue" : "epigraph"));
        break;
      }
      case "quote":     out.push(renderQuote(b, ctx)); break;
      case "num":       out.push(renderNum(b, ctx)); break;
      case "mus": {
        // [mus] сразу после ## — этикетку карточки прячет тема (.has-heading):
        // заголовок секции уже называет блок (158/28MA, «идём за оригиналом»)
        const prev = blocks[bi - 1];
        out.push(renderMusic(b, ctx, Boolean(prev && prev.type === "heading")));
        break;
      }
      case "shir":      out.push(renderShir(b, ctx)); break;
      case "subsec":    out.push(renderSubsec(b, ctx)); break;
      case "sub":       out.push(renderSub(b, ctx)); break;
      case "meta":      out.push(renderMeta(b, ctx)); break;
      case "sig":       out.push(renderSigCry(b, ctx, "sig")); break;
      case "cry":       out.push(renderSigCry(b, ctx, "cry")); break;
      case "line":      out.push(renderLine(b, ctx)); break;
      case "ul":        out.push(renderUl(b, ctx)); break;
      case "dlg":       out.push(renderDialog(b, ctx)); break;
      case "toc": {
        // [toc] marker (вердикт 11): TOC is drawn ONLY here, at the authorial
        // position. Entries aren't complete yet → leave a placeholder, the
        // assembled TOC replaces it after body+notes are rendered.
        ctx.tocMarker = { collapsed: Boolean(b.collapsed), nonum: Boolean(b.nonum) };
        out.push(TOC_PLACEHOLDER);
        break;
      }
      case "refs":      out.push(renderRefsBlock(b, ctx)); break;
    }
  }
  return out.filter((p) => p).join("\n\n");
}

const TOC_PLACEHOLDER = "<!--ZML:TOC-->";

// [refs] / [refs=имя] (вердикт 1): emit the group's footnote list at the
// authorial position; the heading above it is a plain ##/### in the document.
// A [refs] whose group has no definitions (or was already emitted) is a FLAG:
// nothing is drawn, an HTML comment + console.warn mark the spot.
function renderRefsBlock(b, ctx) {
  const key = b.group || "";
  const fns = (ctx.fnGroups && ctx.fnGroups.get(key)) || [];
  if (!fns.length || ctx.renderedGroups.has(key)) {
    if (typeof console !== "undefined" && console.warn) {
      console.warn(`ZML: сиротский [refs${key ? "=" + key : ""}] — нет определений группы (или группа уже выведена)`);
    }
    return `<!-- ZML:flag orphan-refs group="${key}" -->`;
  }
  ctx.renderedGroups.add(key);
  return renderNotesList(fns, ctx);
}

function renderHeading(b, ctx) {
  const level = b.level === 3 ? 3 : 2;
  const tag = `h${level}`;
  const text = resolveInline(b.text, ctx.inline);
  const slug = b.slug || makeSlug(b.text);
  const tocLabel = tocInline(b.text, ctx);
  ctx.toc.push({ slug, label: tocLabel, level });
  return (
    `<${tag} id="${slug}">${text} ` +
    `<a class="back-to-toc" href="#article-title" title="К началу статьи">↑</a></${tag}>`
  );
}

function tocInline(text, ctx) {
  text = text.replace(/\[\^[^\]\s]+\]/g, "").replace(/\s{2,}/g, " ").trim();
  return resolveInline(text, ctx.inline);
}

// §9: \n значим ВЕЗДЕ — каждый перенос в .zml авторский, render рисует <br>
// (глобальный инвариант «ничего не плющится», решение 2026-06-12 14:25).
function linesToHtml(text, inline) {
  return text.split("\n")
    .map((ln) => resolveInline(ln.trim(), inline))
    .filter((x) => x)
    .join("<br>\n");
}

function renderParagraph(b, ctx) {
  return `<p>${linesToHtml(b.text, ctx.inline)}</p>`;
}

function renderSub(b, ctx) {
  // §9: и в подзаголовке переносы авторские → <br>
  return `<h2 class="subtitle">${linesToHtml(b.inner, ctx.inline)}</h2>`;
}

function renderSubsec(b, ctx) {
  // section subtitle (explanatory line under a ## heading): keep authorial line
  // breaks (each \n → <br>); muted italic style lives in theme/template CSS.
  const lines = b.inner.replace(/^\n+/, "").replace(/\n+$/, "").split(/\n/)
    .map((ln) => resolveInline(ln.trim(), ctx.inline)).filter((x) => x);
  return `<p class="sec-sub">${lines.join("<br>\n")}</p>`;
}

// [meta] — metadata «card» (proza-шапка: Серия/Рассказ/Написано/Формат…). Каждая
// строка «Ярлык: значение» → жирный ярлык до первого «:» + значение, строки через
// <br> в панели с левым акцентным кантом (CSS .meta в шаблоне/темах — мирит 5 тем
// через --accent/--ink/--muted/--rule). Хвостовой блок, отделённый пустой строкой,
// рендерится как .epi-дек (курсив под пунктиром) — как <span class="epi"> в ориг.
// (1C1). Регистр литеральный (capsPass:false), сноски/ссылки в значениях работают.
function renderMeta(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const inlineCtx = Object.assign({}, ctx.inline, { capsPass: false });
  const chunks = inner.split(/\n\s*\n/);
  const deck = chunks.slice(1).join("\n").trim();
  const rows = (chunks[0] || "").split("\n")
    .map((ln) => ln.trim())
    .filter((x) => x)
    .map((line) => {
      const m = line.match(/^([^:\n]{1,40}:)\s*(.*)$/);
      return m
        ? `<b>${resolveInline(m[1], inlineCtx)}</b> ${resolveInline(m[2], inlineCtx)}`
        : resolveInline(line, inlineCtx);
    });
  const deckHtml = deck
    ? `\n<span class="epi">${deck.split("\n").map((ln) => resolveInline(ln.trim(), inlineCtx)).filter((x) => x).join("<br>\n")}</span>`
    : "";
  return `<div class="meta">\n${rows.join("<br>\n")}${deckHtml}\n</div>`;
}

// [sig] — author's signature (right-aligned italic) · [cry] — emphatic refrain/
// invocation (centered). ZML3 C11 = ZML2 §2.4. Authorial line breaks survive.
function renderSigCry(b, ctx, cls) {
  const lines = b.inner.replace(/^\n+/, "").replace(/\n+$/, "").split(/\n/)
    .map((ln) => resolveInline(ln.trim(), ctx.inline)).filter((x) => x);
  return `<div class="${cls}">${lines.join("<br>\n")}</div>`;
}

function renderPoem(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const inlineCtx = Object.assign({}, ctx.inline, { capsPass: false });
  const lines = inner.split("\n").map((ln) => resolveInline(ln, inlineCtx));

  let body;
  if (ctx.inline.capsEnabled) {
    const outLines = [];
    let i = 0;
    while (i < lines.length) {
      const ln = lines[i];
      if (isCapsLine(ln)) {
        const run = [ln];
        let j = i + 1;
        while (j < lines.length && isCapsLine(lines[j])) { run.push(lines[j]); j++; }
        const folded = run.map((r) => capsToSmallcaps(r, ctx.inline.matchProperNoun));
        const merged = folded
          .map((x) => x.replace(/^<span class="sb">(.*)<\/span>$/, "$1"))
          .join("\n");
        outLines.push(`<span class="sb">${merged}</span>`);
        i = j;
      } else {
        outLines.push(ln.replace(/\^([A-ZА-ЯЁ][A-ZА-ЯЁ-]*)/g, (_, w) => capitalizeWord(w)));
        i += 1;
      }
    }
    body = outLines.join("\n");
  } else {
    // caps OFF (ZML3 default, A1): verse stays literal — no small-caps folding.
    body = lines.join("\n");
  }
  const title = b.attrs.title || "";
  const titleHtml = title ? `<div class="poem-title">${htmlEscape(title)}</div>` : "";
  return `<div class="poem">${titleHtml}${body}</div>`;
}

// [faw] — free-associative writing (стихи, записанные прозой). Разметка строк — знаком
// «|» (ставит движок при «Сохранить», verse_split.js по счёту слогов). Render не считает
// слоги: делит inner по верхнеуровневым «|» на строки-сегменты, чередует .faw-l.a/.b
// (границы видны). Темы решают режим: монолит (display:inline — swiss/editorial/cyberpunk)
// или построчно (display:block — manuscript/ar_deco). Внутри сегмента: маркеры пунктов
// [fp=…] (бейдж + TOC, §2.5) и капитализация первой буквы. «|» внутри [url|анкор] и пр.
// скобок НЕ разделитель (splitTopLevelPipes).
// Сентинелы капитализации — control-символы через fromCharCode (не пишем сырыми в исходник).
const FAW_SENT0 = String.fromCharCode(0), FAW_SENT1 = String.fromCharCode(1);
const FAW_CAP_RX = /\u0000([\s\S])\u0001/u;
const FAW_PT_RX = /\[fp\b((?:"[^"]*"|[^\]"])*)\]/g;

function renderFaw(b, ctx) {
  // allow_faw OFF (деф.): разметка [faw] инертна — рисуем прозой (renderFawInert).
  if (!ctx.fawEnabled) return renderFawInert(b, ctx);
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const segs = splitTopLevelPipes(inner)
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter((s) => s);
  if (!segs.length) return "";
  // [faw sta=N]: строфы по N строк — после каждой N-й строки зазор (класс .faw-se).
  // Действует лишь в построчном (block) режиме; в монолите верт. margin к inline не
  // применяется → параметр сам собой не виден (как и капитализация .faw-cap).
  const sta = parseInt(b.attrs.sta, 10);
  const hasSta = Number.isFinite(sta) && sta > 0;
  // Безымянный [fp] в начале строки (граница абзаца, §2.5) → новый АБЗАЦ-блок .faw-p:
  // между абзацами есть отступ (виден и в монолите, и построчно), а ВНУТРИ абзаца стих
  // течёт/ломается по теме. Нумерованные [fp="N"] абзац НЕ начинают (текут как раньше,
  // бейдж в строке — их рисует renderFawSegment).
  const paras = [[]];
  for (let s of segs) {
    const mp = /^\[fp\]\s*/.exec(s);
    if (mp) {
      s = s.slice(mp[0].length).trim();
      if (paras[paras.length - 1].length) paras.push([]);
    }
    if (s) paras[paras.length - 1].push(s);
  }
  let lineN = 0;
  const total = segs.length;
  const blocks = paras.filter((p) => p.length).map((para) => {
    const rows = para.map((s) => {
      let cls = "faw-l " + (lineN % 2 === 0 ? "a" : "b");
      if (hasSta && (lineN + 1) % sta === 0 && lineN < total - 1) cls += " faw-se";
      lineN++;
      return `<span class="${cls}">${renderFawSegment(s, ctx)}</span>`;
    });
    return `<div class="faw-p">\n${rows.join("\n")}\n</div>`;
  });
  return `<div class="faw">\n${blocks.join("\n")}\n</div>`;
}

// Один сегмент-строка: чередуем текстовые куски и маркеры пунктов [fp=…]. Маркер → инлайн-
// бейдж .faw-pt (id-якорь) + запись в TOC (уровень 2, как ## которые он заменяет); строку
// НЕ рвёт, может стоять в середине. Первую БУКВУ строки оборачиваем в .faw-cap (построчные
// темы поднимают в верхний регистр — заглавная, как в стихах; монолит не трогает). Сентинелы
// ставим на СЫРОЙ текст ДО inline-резолва: пропускаем ведущую пунктуацию/тире/markup, не
// цепляем html-сущности.
function renderFawSegment(s, ctx) {
  const out = [];
  let lastIdx = 0, m, capDone = false;
  const pushText = (txt) => {
    if (!txt) return;
    if (!capDone && /\p{L}/u.test(txt)) {
      capDone = true;
      txt = txt.replace(/^([^\p{L}]*)(\p{L})/u, (mm, pre, ch) => pre + FAW_SENT0 + ch + FAW_SENT1);
    }
    out.push(resolveInline(txt, ctx.inline).replace(FAW_CAP_RX, '<span class="faw-cap">$1</span>'));
  };
  FAW_PT_RX.lastIndex = 0;
  while ((m = FAW_PT_RX.exec(s)) !== null) {
    pushText(s.slice(lastIdx, m.index));
    const a = parseAttrs(m[1] || "");
    const label = (a.label != null ? String(a.label) : "").trim();
    if (label) {
      // нумерованный пункт → бейдж + TOC
      const slug = (a.slug || makeSlug(label) || ("fp-" + (ctx.toc.length + 1))).trim();
      ctx.toc.push({ slug, label: htmlEscape(label), level: 2 });
      out.push(`<span class="faw-pt" id="${slug}">${htmlEscape(label)}</span>`);
    }
    // безымянная граница абзаца (label="") в стихе НЕВИДИМА — строки уже разбиты по «|»
    lastIdx = m.index + m[0].length;
  }
  pushText(s.slice(lastIdx));
  return out.join("");
}

// allow_faw OFF (деф.): [faw] рисуется ОБЫЧНОЙ ПРОЗОЙ — |-строки склеиваются через пробел
// (границы стиха инертны), пункты [fp] остаются разрывом абзаца + бейдж .faw-pt (id-якорь) +
// запись в TOC, чтобы нумерация/оглавление статьи сохранились до включения allow_faw. Сама
// разметка | при этом ОСТАЁТСЯ в .zml — оператор включает вид флагом allow_faw: true + Сохранить.
function renderFawInert(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const flat = splitTopLevelPipes(inner)
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter((s) => s).join(" ");
  if (!flat) return "";
  const out = [];
  let idx = 0, m, pendingBadge = "";
  const emit = (badge, txt) => {
    txt = txt.replace(/\s+/g, " ").trim();
    if (!badge && !txt) return;
    out.push(`<p>${badge}${badge && txt ? " " : ""}${resolveInline(txt, ctx.inline)}</p>`);
  };
  FAW_PT_RX.lastIndex = 0;
  while ((m = FAW_PT_RX.exec(flat)) !== null) {
    emit(pendingBadge, flat.slice(idx, m.index));
    const a = parseAttrs(m[1] || "");
    const label = (a.label != null ? String(a.label) : "").trim();
    if (label) {
      // нумерованный пункт → разрыв абзаца + бейдж + TOC
      const slug = (a.slug || makeSlug(label) || ("fp-" + (ctx.toc.length + 1))).trim();
      ctx.toc.push({ slug, label: htmlEscape(label), level: 2 });
      pendingBadge = `<span class="faw-pt" id="${slug}">${htmlEscape(label)}</span>`;
    } else {
      pendingBadge = "";   // безымянная граница абзаца — просто новый <p> без бейджа/TOC
    }
    idx = m.index + m[0].length;
  }
  emit(pendingBadge, flat.slice(idx));
  return out.join("\n");
}

// Делит строку по «|» только на верхнем уровне (вне «[…]»): «|» внутри [url|анкор]/
// [mus]-полей не считается границей строки. Этой же логикой движок решает, размечен
// ли уже [faw] (есть хоть один верхнеуровневый «|»).
function splitTopLevelPipes(s) {
  const out = [];
  let depth = 0, cur = "";
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "[") depth++;
    else if (c === "]") { if (depth > 0) depth--; }
    if (c === "|" && depth === 0) { out.push(cur); cur = ""; continue; }
    cur += c;
  }
  out.push(cur);
  return out;
}

function renderEpigraph(b, ctx, label, cls) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const cite = b.attrs.cite || "";
  const kind = b.attrs.kind || "";
  const verse = kind === "verse";
  // kind axis (ZML3 §2.1): verse | prose | aphorism | dedi (посвящение, fn-ревью).
  if (kind === "aphorism") cls += " aphorism";
  if (kind === "dedi") { cls += " dedication"; label = "Посвящение"; }
  const paras = inner.split(/\n\s*\n/).filter((p) => p.trim());
  // §9: каждый \n авторский → <br> в ЛЮБОМ kind (verse — лишь стилевой класс)
  const paraHtml = paras
    .map((p) => `<p>${linesToHtml(p, ctx.inline)}</p>`)
    .join("\n");
  const citeHtml = cite ? `\n<span class="cite">— ${resolveInline(cite, ctx.inline)}</span>` : "";
  return `<div class="${cls}${verse ? " verse" : ""}" data-label="${label}">\n${paraHtml}${citeHtml}\n</div>`;
}

// [line kind=tags|dateline] (fn-ревью, вердикт 8) — one-line service roles:
// p.line.line-<kind>; themes style, dropcap chains must skip p.line.
function renderLine(b, ctx) {
  const kind = (b.attrs.kind || "").toLowerCase().replace(/[^a-z-]/g, "");
  const text = b.inner.replace(/\n+/g, " ").trim();
  const cls = "line" + (kind ? ` line-${kind}` : "");
  return `<p class="${cls}">${resolveInline(text, ctx.inline)}</p>`;
}

// [ul] / [ul marker=◆] (fn-ревью, вердикт 12): items are «- » lines; the
// optional marker swaps ONLY the bullet via --marker → li::marker (CSS in the
// template; each theme sets its own default --marker).
function renderUl(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const items = [];
  for (const raw of inner.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("- ")) items.push(line.slice(2).trim());
    else if (items.length) items[items.length - 1] += "\n" + line; // §9: перенос авторский
    else items.push(line);
  }
  const marker = (b.attrs.marker || "").replace(/['"\\]/g, "");
  const style = marker ? ` style="--marker:'${htmlEscape(marker)} '"` : "";
  const itemsHtml = items
    .map((t) => `<li>${linesToHtml(t, ctx.inline)}</li>`)
    .join("\n");
  return `<ul class="ul"${style}>\n${itemsHtml}\n</ul>`;
}

function renderQuote(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const cite = b.attrs.cite || "";
  const paras = inner.split(/\n\s*\n/).filter((p) => p.trim());
  // §9: переносы внутри цитаты авторские → <br> (инвариант «не плющить»)
  const paraHtml = paras
    .map((p) => `<p>${linesToHtml(p, ctx.inline)}</p>`)
    .join("\n");
  const citeHtml = cite ? `\n<span class="cite">— ${resolveInline(cite, ctx.inline)}</span>` : "";
  // В1 (вердикт оператора 13:06): ярлык «ЦИТАТА» убран — в оригинале его нет (2BS).
  // data-label не выводим → тематический ::before (content:attr(data-label)) пуст.
  // Эпиграф/эпилог свои ярлыки сохраняют (renderEpigraph data-label остаётся).
  return `<blockquote class="q">\n${paraHtml}${citeHtml}\n</blockquote>`;
}

// [dlg] форум-стиль (№2, эталон ccastaneda.ru): ведущая спикер-метка реплики →
// пост-в-рамке с меткой small-caps. Метка живёт текст-префиксом (конвертер не плющит
// её начисто). Паттерны: «Ник написал(а):» (форум-тред) · «Вопрос/Ответ:» (Q&A) ·
// «Имя:» (короткое имя). Нет метки (скрипт-тире, intro-caption) → обычная строка.
function splitSpeaker(text) {
  const t = text.replace(/^\s+/, "");
  let m = /^(.{1,40}?)\s+написал\(а\)\s*:?\s*/.exec(t);          // форум-тред
  if (m) return { label: m[1].trim(), body: t.slice(m[0].length) };
  m = /^(Вопрос|Ответ)\s*[:.]\s*/.exec(t);                       // Q&A
  if (m) return { label: m[1], body: t.slice(m[0].length) };
  m = /^([A-ZА-ЯЁ][^\s:]{0,23}):\s+(?=\S)/.exec(t);              // «Имя:» (один токен)
  if (m) return { label: m[1], body: t.slice(m[0].length) };
  return null;
}

// Метка поста определяется двумя путями (взаимоисключающими в пределах блока):
//  · ЯВНЫЙ маркер «>> Метка» — конвертер ставит для standalone-header форум-тредов
//    (10 статей, №2): он знает класс .speaker → render не угадывает по двоеточию;
//  · ЭВРИСТИКА splitSpeaker — для inline-меток (19 статей: «Ник: реплика» одним
//    узлом). Если в блоке есть хоть один «>> » — весь блок идёт явным путём.
// Пост = метка + её тело; следующие НЕразмеченные абзацы впитываются в тот же пост
// отдельными <p> (форум-реплика многоабзацна). Абзац без метки и без открытого
// поста (лид-капшен, «Диалог на форуме…» до первого спикера) → обычная строка.
function renderDialog(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const paras = inner.split(/\n\s*\n/).filter((p) => p.trim());
  const explicit = paras.some((p) => /^>>\s/.test(p));
  const items = [];
  let cur = null;
  for (const p of paras) {
    let label = null, firstBody = "";
    if (explicit) {
      if (/^>>\s/.test(p)) {
        const nl = p.indexOf("\n");
        label = (nl === -1 ? p.slice(2) : p.slice(2, nl)).trim();
        firstBody = nl === -1 ? "" : p.slice(nl + 1).trim();
      }
    } else {
      const sp = splitSpeaker(p);
      if (sp) { label = sp.label; firstBody = sp.body.trim(); }
    }
    if (label !== null) {
      cur = { label, bodies: firstBody ? [firstBody] : [] };
      items.push(cur);
    } else if (cur) {
      cur.bodies.push(p);
    } else {
      items.push({ line: p });
    }
  }
  const html = items.map((it) => {
    if (it.line !== undefined) {
      return `<p class="dlg-line">${linesToHtml(it.line, ctx.inline)}</p>`;
    }
    const body = it.bodies.map((bd) =>
      `<span class="post-text">${linesToHtml(bd, ctx.inline)}</span>`).join("");
    return `<div class="post"><span class="post-by">` +
      `${linesToHtml(it.label, ctx.inline)}</span>${body}</div>`;
  }).join("\n");
  return `<div class="dialog">\n${html}\n</div>`;
}

// Rich [num] (вердикт оператора 2026-06-13): пункт может НЕСТИ вложенный блок
// ([epi]/[quote]/[mus]…) под своим номером — 35Q «Коллекция Целемов» 1–10, где
// пп. 1,2 = эпиграф/цитата, 4,5 = плееры. Маркер вложенности в inner [num].
const NUM_NESTED_RX = /\[(?:poem|epi|quote|num|mus|subsec|sub|sig|cry|shir|ul|line|dlg)\b/;

function renderNum(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  let items;
  if (NUM_NESTED_RX.test(inner)) {
    // Богатый [num]: внутренние пустые строки принадлежат вложенным блокам
    // (строфы эпиграфа и т.п.) → бьём НЕ по пустым строкам, а по «N. »/«N) »
    // маркеру в начале строки. Обычный [num] идёт прежним путём (zero-regress).
    const NUMRX = /^\d+[.)]\s/;
    items = [];
    let cur = null;
    for (const ln of inner.split("\n")) {
      if (NUMRX.test(ln)) { cur = [ln]; items.push(cur); }
      else if (cur) cur.push(ln);
      else { cur = [ln]; items.push(cur); }
    }
    items = items.map((a) => a.join("\n").replace(/\s+$/, "")).filter((p) => p.trim());
  } else {
    items = inner.split(/\n\s*\n/).filter((p) => p.trim());
  }
  // Authorial numbers + bracket style (fn-ревью, вердикт 7): an item starting
  // «N. » or «N) » keeps ITS number (li value=N — gaps/repeats stay authorial);
  // «N)» switches the list to paren markers (ol.num.num-paren via li::marker).
  // kind=toc (15:00): items get anchors and enter the TOC by their numbers.
  // kind=toc|Пункт (15:04): optional label prefix → «Пункт 1.», «Пункт 2.»…
  const kindParts = (b.attrs.kind || "").split("|");
  const isToc = kindParts[0] === "toc";
  const tocPrefix = isToc && kindParts.length > 1 ? kindParts.slice(1).join("|").trim() : "";
  let paren = false;
  let seq = 0;
  const itemsHtml = items
    .map((p) => {
      const text = p.trim();
      const m = /^(\d+)([.)])\s+/.exec(text);
      const val = m ? parseInt(m[1], 10) : seq + 1;
      seq = val;
      const bracket = m ? m[2] : ".";
      if (m && m[2] === ")") paren = true;
      const bodyRaw = m ? text.slice(m[0].length) : text;
      let body, rich = false;
      if (NUM_NESTED_RX.test(bodyRaw)) {
        // вложенный блок телом пункта; у [mus] номер служит этикеткой → плашку
        // «Музыка под настроение» гасим (hasHeading=true)
        rich = true;
        body = parseMain(bodyRaw.replace(/^\s+/, ""))
          .map((blk) => (blk.type === "mus"
            ? renderMusic(blk, ctx, true)
            : renderBlocks([blk], ctx)))
          .filter(Boolean)
          .join("\n");
      } else {
        // Многоабзацный пункт без вложенного блока (напр. 06I п.2 — два абзаца
        // прозы под одним номером): рендерим через parseMain, чтобы пустая строка
        // стала границей <p>, а не схлопнулась в один <br> (linesToHtml выкидывает
        // пустые строки). Одноабзацные пункты идут прежним путём — zero-regress
        // для 22R/23TA/35Q/1CB/1CM.
        const plainBlocks = parseMain(bodyRaw.replace(/^\s+/, ""));
        body = plainBlocks.length > 1
          ? plainBlocks.map((blk) => renderBlocks([blk], ctx)).filter(Boolean).join("\n")
          : linesToHtml(bodyRaw, ctx.inline);
      }
      let idAttr = "";
      if (isToc) {
        const slug = `num-${val}`;
        // с префиксом — БЕЗ точки/скобки на конце («Пункт 1»), голые — «1.»
        const lbl = tocPrefix
          ? `${htmlEscape(tocPrefix)} ${val}`
          : `${val}${bracket}`;
        ctx.toc.push({ slug, label: lbl, level: 2 });
        idAttr = ` id="${slug}"`;
      }
      const richCls = rich ? ' class="num-rich"' : "";
      return m
        ? `<li${idAttr}${richCls} value="${val}">${body}</li>`
        : `<li${idAttr}${richCls}>${body}</li>`;
    })
    .join("\n");
  return `<ol class="num${paren ? " num-paren" : ""}">\n${itemsHtml}\n</ol>`;
}

function extractYoutubeId(url) {
  const m = /(?:v=|youtu\.be\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/.exec(url);
  return m ? m[1] : null;
}

// Кнопка-динамик для трек-строки [mus] (2026-06-18): YouTube в рекламе убрал
// кнопку «без звука» — даём свою. Управляет встроенным плеером через IFrame API
// (postMessage mute/unMute; embed несёт ?enablejsapi=1). Глиф — монохромный SVG
// (currentColor, в палитру темы), слэш-перечёркивание показывается в mute-состоянии.
const SPK_SVG =
  '<svg viewBox="0 0 24 24" aria-hidden="true">' +
  '<path class="spk-cone" fill="currentColor" d="M4 9v6h4l5 4V5L8 9H4z"/>' +
  '<g class="spk-wave" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">' +
  '<path d="M16.4 8.6a5 5 0 0 1 0 6.8"/><path d="M18.8 6.2a8.5 8.5 0 0 1 0 11.6"/></g>' +
  '<line class="spk-slash" x1="3.4" y1="3.4" x2="20.6" y2="20.6" ' +
  'stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>' +
  '</svg>';
const MUTE_BTN =
  '<span class="trk-mute" role="button" tabindex="0" aria-pressed="false"' +
  ' aria-label="Заглушить звук" title="Заглушить звук (реклама YouTube)">' +
  SPK_SVG + '</span>';

function renderMusic(b, ctx, hasHeading) {
  // refs-группа: треки этого [mus] — ЦЕЛИ сносок (1CM ¶, 12F). Маркер [^refs.N]
  // в тексте ссылается на трек-плеер; трек получает cite_note-id + обратную стрелку.
  const refsGroup = b.attrs.refs || "";
  const label = b.attrs.label || "Музыка под настроение";
  // data-label (::before темы) — плоский текст, маркеры туда не рисуются;
  // в видимых полях [^N] резолвится рабочей сноской (кейс Gregorian[12], 15:14)
  const labelPlain = label.replace(/\[\^[^\]]+\]/g, "").trim();
  const fld = (s) => resolveGlyphs(resolveFootnotes(htmlEscape(s), ctx.inline));
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const tracks = [];
  for (const rawLine of inner.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    if (line.startsWith(">")) {                         // Б2: inter-track заметка
      tracks.push(`<p class="music-note">${fld(line.replace(/^>\s?/, ""))}</p>`);
      continue;
    }
    // строка трека: [url|title|author] — поля могут нести [^N], поэтому не
    // regex по скобкам, а срез внешних [ ] + split по | (маркеры | не содержат)
    let parts = null;
    if (line.startsWith("[") && line.endsWith("]") && line.includes("|")) {
      parts = line.slice(1, -1).split("|");
    }
    if (!parts || parts.length < 2) {
      tracks.push(
        `<div class="music-noplayer"><div class="summary">` +
        `<span class="label">${htmlEscape(labelPlain)}:</span>` +
        `<span class="title">${fld(line)}</span>` +
        `</div></div>`,
      );
      continue;
    }
    const url = parts[0], title = parts[1] || "";
    let author, fnum = null;
    if (refsGroup && parts.length >= 4) {
      fnum = parts[parts.length - 1];        // 4-е поле = номер сноски-цели
      author = parts.slice(2, -1).join("|");
    } else {
      author = parts.slice(2).join("|");
    }
    const ytId = extractYoutubeId(url);
    // канон-плашка (как в оригинальном HTML): ▶ N) **Название** — *Автор*
    // (название жирным, автор обычным-курсивом, ► играбел-индикатор); слоты канонизированы
    // конвертером (music_canon.py) — title=поле2 всегда название, «N)» = номер (Б1, не жирним)
    let titleInner;
    if (author && title) {
      const nm = /^(\d+\))\s*/.exec(title);
      const numHtml = nm ? `<span class="trk-num">${nm[1]}</span> ` : "";
      const ttl = nm ? title.slice(nm[0].length) : title;
      titleInner = `${numHtml}<span class="trk-ttl">${fld(ttl)}</span>` +
        ` <span class="trk-sep">—</span> <span class="trk-art">${fld(author)}</span>`;
    } else {
      const only = title || author || url;
      const nm = /^(\d+\))\s*/.exec(only);
      const numHtml = nm ? `<span class="trk-num">${nm[1]}</span> ` : "";
      titleInner = `${numHtml}<span class="trk-ttl">${fld(nm ? only.slice(nm[0].length) : only)}</span>`;
    }
    // трек = цель сноски: cite_note-id (маркер целит сюда) + обратная стрелка к маркеру
    let idAttr = "", backref = "";
    if (refsGroup && fnum) {
      const key = `${refsGroup}-${fnum}`;
      idAttr = ` id="cite_note-${key}"`;
      const refs = (ctx.inline && ctx.inline.refNotes) || new Set();
      if (refs.has(key)) {
        backref = `<a class="backref" href="#cite_ref-${key}" title="Вернуться к месту в тексте">↑</a>`;
      }
    }
    if (ytId) {
      tracks.push(
        `<details class="music"${idAttr}><summary>` +
        `<span class="label">${htmlEscape(labelPlain)}:</span>` +
        `<span class="trk-play">▶</span> <span class="title">${titleInner}</span>` +
        `<a class="ext" href="${url}" target="_blank" rel="noopener" ` +
        `title="Открыть на YouTube">↗</a>${backref}` +
        MUTE_BTN + `</summary>` +
        `<div class="player">` +
        `<iframe data-src="https://www.youtube.com/embed/${ytId}?enablejsapi=1" ` +
        `title="YouTube video player" ` +
        `allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" ` +
        `referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>` +
        `</div></details>`,
      );
    } else if (url) {
      tracks.push(
        `<div class="music-noplayer"${idAttr}><div class="summary">` +
        `<span class="label">${htmlEscape(labelPlain)}:</span>` +
        `<span class="title">${titleInner}</span>` +
        `<a class="ext" href="${url}" target="_blank" rel="noopener">↗</a>${backref}` +
        `</div></div>`,
      );
    } else {
      tracks.push(
        `<div class="music-noplayer"${idAttr}><div class="summary">` +
        `<span class="label">${htmlEscape(labelPlain)}:</span>` +
        `<span class="title">${fld(trackLabel)}</span>${backref}` +
        `</div></div>`,
      );
    }
  }
  // маркер сноски на самой этикетке («Песнь Ступеней[^7]» — 12F/2C3…): ::before
  // из data-label кликабельным быть не может → реальная строка .music-label
  // с резолвом сноски; тема прячет ::before по .has-label-row (вердикт 20:27)
  const labelRow = /\[\^[^\]]+\]/.test(label) && !hasHeading
    ? `<div class="music-label">${fld(label)}</div>\n`
    : "";
  return (
    `<div class="music-group${hasHeading ? " has-heading" : ""}${labelRow ? " has-label-row" : ""}" data-label="${htmlEscape(labelPlain)}">\n` +
    labelRow + tracks.join("\n") +
    `\n</div>`
  );
}

const YTID_RX = /^[A-Za-z0-9_-]{11}$/;

// [shir cols=N min=M] — грид музыкальных плиток (ZML3 §6). Песня = ОДНА СТРОКА:
//   <ytID> | <Композиция> | <Автор> | <id, id:Подпись, …>
// 3 обязательных поля (ytID + Композиция + Автор); 4-я колонка (список статей,
// per-id override-подпись `id:Текст`) — необязательна. `|`/`,` внутри поля → `\|`/`\,`.
// Битая строка (нет любого из трёх) роняет ТОЛЬКО свою плитку и рисует видимый
// маркер-диагноз (важно в ~220-строчном блоке, §6.3) + console.warn + HTML-флаг.
// Плеер lazy-YouTube 1:1 (§6.5): превью hqdefault.jpg → клик впрыскивает iframe
// (механика в шаблоне/скрипте); вид плитки — тема (§6.7). art-href с базой
// ctx.artHrefBase ("" внутри статьи, "../art/" на спец-странице songs).
function renderShir(b, ctx) {
  const cols = Math.max(1, parseInt(b.attrs.cols, 10) || 3);
  const min = Math.max(1, parseInt(b.attrs.min, 10) || 300);
  const base = ctx.artHrefBase || "";
  const manifestByArt = (ctx.inline && ctx.inline.manifestByArt) || {};
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const tiles = [];
  let lineNo = 0;
  for (const raw of inner.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    lineNo += 1;
    const f = splitEscaped(line, "|").map((x) => x.trim());
    const ytID = f[0] || "", comp = f[1] || "", author = f[2] || "", artlist = f[3] || "";
    // Валидно при ytID + Композиции. Автор НЕОБЯЗАТЕЛЕН (консистентно с [mus]: ~17
    // карточек одобренной songs — саундтреки/детские — без автора; comp-only, не
    // регресс). Спека §6.3 называла автора обязательным — смягчение на ратификации.
    const missing = [];
    if (!YTID_RX.test(ytID)) missing.push("ytID");
    if (!comp) missing.push("название");
    if (missing.length) {
      if (typeof console !== "undefined" && console.warn) {
        console.warn(`ZML [shir]: строка ${lineNo} — нет: ${missing.join(", ")} — «${line}»`);
      }
      tiles.push(
        `<figure class="song song-broken" role="alert">` +
        `<div class="shir-broken">⚠ строка ${lineNo}: нет ${htmlEscape(missing.join(", "))}` +
        `<br><code>${htmlEscape(line)}</code></div></figure>` +
        `<!-- ZML:flag shir-broken line=${lineNo} -->`,
      );
      continue;
    }
    // 4-я колонка: список статей (бар-id или id:Подпись), резолв title из manifest.
    const links = [];
    if (artlist) {
      for (const item of splitEscaped(artlist, ",").map((x) => x.trim()).filter(Boolean)) {
        const ci = item.indexOf(":");
        const id = (ci === -1 ? item : item.slice(0, ci)).trim();
        const override = ci === -1 ? "" : item.slice(ci + 1).trim();
        const rec = manifestByArt[id];
        const label = override || (rec && rec.title) || id;
        const cls = rec ? "internal" : "broken";
        links.push(`<a class="${cls}" href="${base}${id}.html">${htmlEscape(label)}</a>`);
      }
    }
    const linksHtml = links.join(' <span class="sep">♪</span> ');
    const aria = htmlEscape(`Включить: ${author ? `${comp} — ${author}` : comp}`);
    const titleHtml = author
      ? `<span class="trk-ttl">${htmlEscape(comp)}</span> ` +
        `<span class="trk-sep">—</span> <span class="trk-art">${htmlEscape(author)}</span>`
      : `<span class="trk-ttl">${htmlEscape(comp)}</span>`;
    tiles.push(
      `<figure class="song">\n` +
      `<div class="yt" data-id="${htmlEscape(ytID)}" role="button" tabindex="0" aria-label="${aria}" ` +
      `style="background-image:url(https://i.ytimg.com/vi/${htmlEscape(ytID)}/hqdefault.jpg)">` +
      `<span class="play"></span></div>\n` +
      // динамик-mute — в правом-нижнем углу ПОДПИСИ (под ссылками): на картинке клипа
      // его часто не видно, в подписи (светлый фон) виден всегда (position:absolute,
      // место зарезервировано padding-bottom → ссылки не наезжают)
      `<figcaption><p class="t">${titleHtml}</p>` +
      (linksHtml ? `<p class="a">${linksHtml}</p>` : "") +
      `<button class="song-mute" type="button" aria-pressed="false" ` +
      `aria-label="Заглушить звук" title="Заглушить звук (реклама)">${SPK_SVG}</button>` +
      `</figcaption></figure>`,
    );
  }
  // Адаптив без медиазапросов (§6.4): auto-fill + minmax(max(min, доля-cols), 1fr) —
  // широко → ровно cols колонок, узко → сам отдаёт колонки до min.
  const style = `--shir-cols:${cols};--shir-min:${min}px`;
  return `<div class="songgrid" style="${style}">\n${tiles.join("\n")}\n</div>`;
}

// ════════════════════════════════════════════════════════════════════════════
// FOOTNOTES + TOC
// ════════════════════════════════════════════════════════════════════════════

// One <ol class="notes"> for a list of footnote definitions (a [refs] group or
// the tail fallback). Group-aware ids: default → cite_note-N, named group →
// cite_note-имя-N; a glyph series prints «¤N» instead of the list number.
function renderNotesList(footnotes, ctx) {
  // Resolve all bodies first: registers any [^N] INSIDE footnote bodies into
  // refNotes, so a note cross-referenced only from another note isn't seen as orphan.
  // 📏: continuation-строки тела сноски — авторские (стих-в-сноске, 182) → <br>
  const resolved = footnotes.map((fn) => [
    fn,
    fn.body.split("\n").map((ln) => resolveInline(ln.trim(), ctx.inline))
      .filter((x) => x).join("<br>\n"),
  ]);
  const refs = (ctx.inline && ctx.inline.refNotes) || new Set();
  const glyphs = (ctx.inline && ctx.inline.groupGlyphs) || {};
  const items = [];
  for (const [fn, bodyHtml] of resolved) {
    if (fn.kind === "numbered") {
      const key = fn.group ? `${fn.group}-${fn.id}` : String(fn.id);
      // Orphan (no inbound marker anywhere): keep the number but DROP the back-
      // arrow — nothing to return to, the ↑ would dangle. ZML3 A3 (2026-06-10).
      const back = refs.has(key)
        ? `<a class="backref" href="#cite_ref-${key}" title="Вернуться к месту в тексте">↑</a> `
        : "";
      const glyph = fn.group ? glyphs[fn.group] : null;
      if (glyph) {
        // glyph series: suppress the ol number, print «¤N» as the label
        items.push(`<li class="anon" id="cite_note-${key}">${back}${htmlEscape(glyph)}${fn.id} ${bodyHtml}</li>`);
      } else {
        items.push(`<li id="cite_note-${key}" value="${fn.id}">${back}${bodyHtml}</li>`);
      }
    } else if (fn.kind === "starred") {
      // authorial asterisk note `[^*]:` — clickable both ways like a numbered one
      const key = `star${fn.star.length}`;
      const back = refs.has(key)
        ? `<a class="backref" href="#cite_ref-${key}" title="Вернуться к месту в тексте">↑</a> `
        : "";
      items.push(`<li class="anon" id="cite_note-${key}">${back}${fn.star} ${bodyHtml}</li>`);
    } else if (fn.prefix === "") {
      // ZML3 А1: голый анон без ярлыка (note-anon 0BH/184 — wiki-ссылка/строка
      // без номера и без «См. также»). prefix "" приходит из [^|]:.
      items.push(`<li class="anon anon-bare">${bodyHtml}</li>`);
    } else {
      const prefix = fn.prefix || "См. также";
      items.push(`<li class="anon">${htmlEscape(prefix)}: ${bodyHtml}</li>`);
    }
  }
  return `<ol class="notes">\n` + items.join("\n") + `\n</ol>`;
}

// Tail fallback (ZML3 §4.1): groups (incl. the default one) WITHOUT their own
// [refs] block are emitted at the end of the document under notes_title.
function renderFootnotes(footnotes, ctx) {
  const remaining = footnotes.filter((fn) => !ctx.renderedGroups.has(fn.group || ""));
  if (!remaining.length) return "";
  // notes_title may carry inline markers («Ор Пашут[^3]:») — resolve, not escape.
  const titleHtml = ctx.notesTitleHtml || htmlEscape((ctx && ctx.notesTitle) || "Примечания");
  return (
    `<h2 id="notes">${titleHtml} ` +
    `<a class="back-to-toc" href="#article-title" title="К началу статьи">↑</a></h2>\n` +
    renderNotesList(remaining, ctx)
  );
}

// TOC (вердикт 11: only at the [toc] marker; default OPEN, [toc collapsed] for
// the single folded article). ### entries nest as a second level (вердикт 4).
function renderToc(toc, hasNotes, notesTitleToc, tocOpts) {
  if (!toc.length && !hasNotes) return "";
  const entries = toc.slice();
  if (hasNotes) entries.push({ slug: "notes", label: notesTitleToc || "Примечания", level: 2 });
  const parts = [];
  let liOpen = false;
  let subOpen = false;
  for (const e of entries) {
    if (e.level >= 3) {
      if (!subOpen) { parts.push("<ol>"); subOpen = true; }
      parts.push(`<li><a href="#${e.slug}">${e.label}</a></li>`);
    } else {
      if (subOpen) { parts.push("</ol>"); subOpen = false; }
      if (liOpen) parts.push("</li>");
      parts.push(`<li><a href="#${e.slug}">${e.label}</a>`);
      liOpen = true;
    }
  }
  if (subOpen) parts.push("</ol>");
  if (liOpen) parts.push("</li>");
  const open = tocOpts && tocOpts.collapsed ? "" : " open";
  const nonum = tocOpts && tocOpts.nonum ? " nonum" : "";
  return (
    `<details class="article-toc${nonum}"${open}>\n<summary>Содержание</summary>\n` +
    `<ol>\n` + parts.join("\n") + `\n</ol>\n</details>`
  );
}

function makeSlug(text) {
  text = text.replace(/[^А-Яа-яA-Za-z0-9 -]/g, "");
  const words = text.split(/\s+/).filter(Boolean).slice(0, 3);
  const slug = words.map((w) => w.toLowerCase()).join("-");
  return slug || "section";
}

// ════════════════════════════════════════════════════════════════════════════
// SIBLINGS (prev/next)
// ════════════════════════════════════════════════════════════════════════════

function siblings(rec, manifest) {
  const section = rec.section;
  const order = rec.section_order;
  if (!section || order === undefined || order === null) return ["", ""];
  const sibs = manifest
    .filter((r) => r.section === section && Number.isInteger(r.section_order))
    .sort((a, b) => a.section_order - b.section_order);
  const idx = sibs.findIndex((r) => r.art === rec.art);
  if (idx === -1) return ["", ""];
  let prevHtml = "";
  let nextHtml = "";
  if (idx > 0) {
    const p = sibs[idx - 1];
    prevHtml = `<a href="${p.art}.html">← ${htmlEscape(p.title || p.art)}</a>`;
  }
  if (idx < sibs.length - 1) {
    const nx = sibs[idx + 1];
    nextHtml = `<a href="${nx.art}.html">${htmlEscape(nx.title || nx.art)} →</a>`;
  }
  return [prevHtml, nextHtml];
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE ASSEMBLY
// ════════════════════════════════════════════════════════════════════════════

// Render everything EXCEPT the page template — the parsed frontmatter plus the
// HTML that goes inside <article> (TOC + body + notes) and the byline/nav bits.
// Used by the in-page inline editor to refresh only <article> live, and by
// renderArticleHtml() below to fill the full-page template.
// ctx: { zml, rec, manifest, manifestByArt, zoharIndex }
export function renderArticleParts(ctx) {
  const { rec, manifest, manifestByArt, zoharIndex } = ctx;
  // Match Python's universal-newline read: CRLF / lone CR → LF.
  const nl = (s) => s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const zml = nl(ctx.zml);
  const section = rec.section || "";
  const sectionHuman = SECTION_HUMAN[section] || section;

  const [fm, body] = parseFrontmatter(zml);
  const [blocks, footnotes] = parseBody(body);

  const fnIdMap = {};
  for (const fn of footnotes) if (fn.kind === "numbered") fnIdMap[fn.id] = fn;

  // CAPS folding (small-caps + proper-nouns + ^marker) is OFF by default in ZML3
  // (A1): text renders literally unless frontmatter `caps:` opts in.
  const capsEnabled = /^(on|true|1|yes|да)$/i.test((fm.caps || "").trim());
  // [faw] активна ТОЛЬКО при frontmatter `allow_faw: true` (деф. OFF — «везде false»).
  // Иначе разметка [faw] инертна: |-строки и [fp]-пункты рисуются обычной прозой (но
  // сама разметка остаётся в .zml — оператор включает вид флагом allow_faw + Сохранить).
  const fawEnabled = /^(on|true|1|yes|да)$/i.test((fm.allow_faw || "").trim());
  // Authorial notes-section heading (ZML3 A2): «Примечания» / «Полезные ссылки» /
  // «Пост скриптум» … — render draws fm.notes_title instead of a hardcoded label.
  const notesTitle = (fm.notes_title || "").trim() || "Примечания";
  const titleRaw = fm.title || "";

  // Footnote groups (§4.1): definitions grouped by name ("" = default group);
  // series glyphs declared on [refs=имя glyph=¤] blocks feed marker rendering.
  const fnGroups = new Map();
  for (const fn of footnotes) {
    const key = fn.group || "";
    if (!fnGroups.has(key)) fnGroups.set(key, []);
    fnGroups.get(key).push(fn);
  }
  const groupGlyphs = {};
  for (const b of blocks) {
    if (b.type === "refs" && b.attrs && b.attrs.glyph) groupGlyphs[b.group || ""] = b.attrs.glyph;
    // [mus refs=group glyph=¶]: трек-как-цель-сноски — глиф маркера берётся отсюда
    if (b.type === "mus" && b.attrs && b.attrs.refs && b.attrs.glyph) groupGlyphs[b.attrs.refs] = b.attrs.glyph;
  }

  // Pre-scan ALL marker references (body incl. footnote bodies + title +
  // notes_title) BEFORE rendering: orphan detection must not depend on the
  // render order of [refs] blocks vs later body text.
  const refNotes = new Set();
  const scanRefs = (txt, isBody) => {
    if (!txt) return;
    let m;
    const rx = new RegExp(FN_MARKER_RX.source, "g");
    while ((m = rx.exec(txt)) !== null) {
      if (isBody) {
        // skip definition lines `[^…]:` at line start — they are not references
        const atLineStart = m.index === 0 || txt[m.index - 1] === "\n";
        if (atLineStart && txt[m.index + m[0].length] === ":") continue;
      }
      refNotes.add(fnMarkerKey(m[1], m[2]));
    }
  };
  scanRefs(body, true);
  scanRefs(titleRaw, false);
  scanRefs(notesTitle, false);

  const inline = {
    manifestByArt, zoharIndex, fnIdMap,
    matchProperNoun: compileProperNouns(ctx.properNouns),
    refNotes,           // note keys referenced by markers; orphan = absent
    seenRefs: {},       // document-wide duplicate-marker counter (-extraK ids)
    groupGlyphs,
    capsEnabled,
  };
  const renderCtx = {
    inline, toc: [], notesTitle, notesTitleHtml: "", fawEnabled,
    fnGroups, renderedGroups: new Set(), tocMarker: null,
    // [shir] art-link href base: "" inside an article (flat docs/art/), "../art/"
    // on the songs special page (docs/songs/ → docs/art/).
    artHrefBase: ctx.artHrefBase || "",
  };

  // H1 sup markers (вердикт 2): title keeps its [^N] — resolved FIRST so the
  // H1 marker claims the base cite_ref id (document order: H1 precedes body).
  const titleH1 = resolveGlyphs(resolveFootnotes(htmlEscape(titleRaw), inline));
  // <title>/breadcrumbs/alt get the marker-free text.
  const title = titleRaw.replace(/\s*\[\^[^\]\s]+\]/g, "").replace(/\s{2,}/g, " ").trim();

  const bodyHtml = renderBlocks(blocks, renderCtx);
  renderCtx.notesTitleHtml = resolveInline(notesTitle, inline);
  const notesHtml = renderFootnotes(footnotes, renderCtx); // tail fallback only
  const notesTitleToc = tocInline(notesTitle, renderCtx);

  let articleInner = bodyHtml;
  if (notesHtml) articleInner += "\n\n" + notesHtml;

  // TOC only at the [toc] marker (вердикт 11); without a marker — no TOC at all.
  let tocHtml = "";
  if (renderCtx.tocMarker) {
    const built = renderToc(renderCtx.toc, Boolean(notesHtml), notesTitleToc, renderCtx.tocMarker);
    articleInner = replaceAllLiteral(articleInner, TOC_PLACEHOLDER, built);
  }

  const description = fm.summary || "";
  // byline date is ALWAYS the manifest/FM date; authorial date strings live in
  // the body as [line kind=dateline] (вердикт-6 dates: отменён 2026-06-12).
  const dateDisplay = fm.date || rec.date_chosen || "";
  // Attribution (§0.6): who last touched the article and when. Default editor
  // is "Иван Иванович" (= ИИ: built by AI, never hand-edited — намеренная метка,
  // НЕ заглушка); the pipeline / editor overwrite fm.editor/fm.edited on real edits.
  const editor = fm.editor || "Иван Иванович";
  const edited = fm.edited || "";
  const originUrl = rec.url || "";
  const originLabel = originUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  const [prevLink, nextLink] = siblings(rec, manifest);
  let illustration = "";
  if (fm.image) {
    illustration =
      `<img class="cover" src="../img/${fm.image}" alt="${htmlEscape(title)}">\n`;
  }

  // audio narration 🎧 (ZML3): frontmatter audio:[{url,label}] → 🎧 link(s) by H1.
  let audioHtml = "";
  try {
    const audio = JSON.parse(fm.audio || "[]");
    if (Array.isArray(audio)) {
      const links = audio
        .filter((a) => a && a.url)
        .map((a) => {
          const lbl = htmlEscape(a.label || "Аудио-озвучка");
          return `<a class="audio-link" href="${htmlEscape(a.url)}" target="_blank" ` +
                 `rel="noopener" title="${lbl}" aria-label="${lbl}">🎧</a>`;
        });
      // U+2060 WORD JOINER glues 🎧 to the H1's last word (and icons to each
      // other): emoji are a line-break opportunity, so without it the icons
      // wrap onto their own orphan line at narrow widths.
      audioHtml = links.length ? "⁠" + links.join("⁠") : "";
    }
  } catch (e) { audioHtml = ""; }

  return {
    fm, title, titleH1, description, dateDisplay, editor, edited, originUrl, originLabel,
    sectionHuman, illustration, audioHtml, tocHtml, articleInner, prevLink, nextLink,
  };
}

// Ф8′ резолвер вида: (раздел/тип) → {design,width}. Приоритет: per-field
// frontmatter-override → первое совпавшее правило (по разделу ИЛИ типу, сверху
// вниз) → global. Зеркалится в template_view.html (клиент) и в admin.html.
export function resolveDisplay(cfg, section, type, fmTheme, fmWidth) {
  const g = (cfg && cfg.global) || {};
  const rules = cfg && Array.isArray(cfg.rules) ? cfg.rules : [];
  let ruleDesign = "", ruleWidth = "";
  for (const r of rules) {
    const m = r && r.match;
    if (!m) continue;
    if ((m.kind === "section" && m.value === section) ||
        (m.kind === "type" && m.value === type)) {
      ruleDesign = r.design || ""; ruleWidth = r.width || ""; break;
    }
  }
  const design = (fmTheme && fmTheme.trim()) || ruleDesign || g.design || "A_editorial";
  const width  = (fmWidth && fmWidth.trim())  || ruleWidth  || g.width  || "wide";
  return { design, width };
}

// ctx: { zml, rec, manifest, manifestByArt, zoharIndex, template, displayConfig, siteConfig }
export function renderArticleHtml(ctx) {
  const p = renderArticleParts(ctx);
  const nl = (s) => s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const template = nl(ctx.template);
  const {
    title, description, sectionHuman, illustration, dateDisplay, editor, edited,
    originUrl, originLabel, tocHtml, articleInner, prevLink, nextLink,
  } = p;
  const lastEdit = edited
    ? `${htmlEscape(edited)} · ${htmlEscape(editor)}`
    : htmlEscape(editor);

  // theme/width (Ф8′): per-article frontmatter обнулён — эффективный вид резолвится
  // из displayConfig (раздел/тип → дизайн+ширина); fm.theme/fm.width, если заданы
  // вручную, перебивают пер-полем. ctx.displayConfig отсутствует → дефолты A/wide
  // (совместимость с in-page редактором). Width ОРТОГОНАЛЬНА теме (класс колонки).
  const fmTheme = (p.fm.theme || "").trim();
  const fmWidth = (p.fm.width || "").trim();
  const artType = (p.fm.type || "prose").trim();
  const artSection = ctx.rec.section || "other";
  const resolved = resolveDisplay(ctx.displayConfig || null, artSection, artType, fmTheme, fmWidth);
  // «old» НИКОГДА не печём статикой (url-unification §8.3): no-JS/краулер всегда видят
  // индексируемый ZML-рендер с OG. design==="old" применяет boot оверлеем в рантайме
  // (из data-fm-theme/display.json), а запечённая тема — ZML-дефолт A_editorial.
  const theme = resolved.design === "old" ? "A_editorial" : resolved.design;
  const widthRaw = resolved.width.toLowerCase();
  // dropcap: буквицы per-article. Default ON (no frontmatter mention needed);
  // `dropcap: off` opts out → .no-dropcap on .wrap, theme CSS gates on it.
  const dropcapOff = /^(off|false|0|no|нет)$/i.test((p.fm.dropcap || "").trim());
  const wrapClass = (/narrow|820/.test(widthRaw) ? "w-narrow" : "w-wide") +
    (dropcapOff ? " no-dropcap" : "");

  let html = template;
  html = replaceAllLiteral(html, "{{THEME}}", theme);
  html = replaceAllLiteral(html, "{{WRAP_CLASS}}", wrapClass);
  // Ф8′: раздел/тип/fm-override/worker — для клиентского ре-резолвинга у залогиненных.
  html = replaceAllLiteral(html, "{{ART_SECTION}}", htmlEscape(artSection));
  html = replaceAllLiteral(html, "{{ART_TYPE}}", htmlEscape(artType));
  html = replaceAllLiteral(html, "{{FM_THEME}}", htmlEscape(fmTheme));
  html = replaceAllLiteral(html, "{{FM_WIDTH}}", htmlEscape(fmWidth));
  html = replaceAllLiteral(html, "{{WORKER_URL}}",
    htmlEscape((ctx.siteConfig && ctx.siteConfig.workerUrl) || ""));
  // H1 gets glyphs (<\^/> → span.glyph) AND working [^N] sup markers (вердикт 2);
  // <title>/breadcrumbs/prev-next keep the marker-free literal text.
  html = replaceAllLiteral(html, "{{TITLE_H1}}", p.titleH1);
  html = replaceAllLiteral(html, "{{TITLE}}", htmlEscape(title));
  html = replaceAllLiteral(html, "{{AUDIO}}", p.audioHtml || "");
  html = replaceAllLiteral(html, "{{DESCRIPTION}}", htmlEscape(description));
  html = replaceAllLiteral(html, "{{CSS_VERSION}}", CSS_VERSION);
  html = replaceAllLiteral(html, "{{SECTION_NAME}}", htmlEscape(sectionHuman));
  // Flat layout: article at docs/art/<art>.html → section index is one level up.
  html = replaceAllLiteral(html, "{{SECTION_HREF}}", `../${ctx.rec.section || "other"}/index.html`);
  html = replaceAllLiteral(html, "{{ILLUSTRATION}}", illustration);
  // OG/twitter image (P3): абсолютный URL той же иллюстрации (fm.image) — ради
  // богатого раскрытия в Telegram. Нет картинки → плейсхолдер пуст (OG падёт на title).
  const ogImage = p.fm.image
    ? `<meta property="og:image" content="https://imyavel.github.io/yaniktoim/img/${p.fm.image}">\n` +
      `<meta name="twitter:image" content="https://imyavel.github.io/yaniktoim/img/${p.fm.image}">`
    : "";
  html = replaceAllLiteral(html, "{{OG_IMAGE}}", ogImage);
  html = replaceAllLiteral(html, "{{NUMBER}}", ctx.rec.art);
  html = replaceAllLiteral(html, "{{DATE_DISPLAY}}", htmlEscape(dateDisplay));
  html = replaceAllLiteral(html, "{{ORIGIN_URL}}", originUrl);
  html = replaceAllLiteral(html, "{{ORIGIN_LABEL}}", htmlEscape(originLabel));
  // Источник-фрагмент byline целиком — пусто, если url нет (новые оригинальные
  // статьи без proza.ru). У 352 корпусных url есть → фрагмент байт-в-байт прежний.
  const originByline = originUrl
    ? ` · Источник: <a href="${htmlEscape(originUrl)}" target="_blank" rel="noopener">${htmlEscape(originLabel)}</a>`
    : "";
  html = replaceAllLiteral(html, "{{ORIGIN_BYLINE}}", originByline);
  html = replaceAllLiteral(html, "{{ARTICLE_TOC}}", tocHtml);
  html = replaceAllLiteral(html, "{{ARTICLE_BODY}}", articleInner);
  html = replaceAllLiteral(html, "{{PREV_LINK}}", prevLink);
  html = replaceAllLiteral(html, "{{NEXT_LINK}}", nextLink);
  // Иконки prev/next в закреплённой верхней панели: только href (текст — у иконки).
  // Берём адрес из готовых prevLink/nextLink; нет соседа → пустой href + hidden
  // (no-JS не кликнет в никуда; ya-edit.js::refreshSiblings уточнит по живой структуре).
  const navPrevHref = (prevLink.match(/href="([^"]+)"/) || ["", ""])[1];
  const navNextHref = (nextLink.match(/href="([^"]+)"/) || ["", ""])[1];
  html = replaceAllLiteral(html, "{{NAV_PREV_HREF}}", navPrevHref);
  html = replaceAllLiteral(html, "{{NAV_NEXT_HREF}}", navNextHref);
  html = replaceAllLiteral(html, "{{NAV_PREV_HIDDEN}}", navPrevHref ? "" : "hidden");
  html = replaceAllLiteral(html, "{{NAV_NEXT_HIDDEN}}", navNextHref ? "" : "hidden");
  html = replaceAllLiteral(html, "{{LAST_EDIT}}", lastEdit);
  // Индексируемость (P3/url-unification): сам отрендеренный NNN.html — теперь
  // ЕДИНСТВЕННЫЙ публичный адрес и должен попадать в Pagefind (раньше искался
  // старый html). Атрибут оставлен в шаблоне ради синка docs/editor/data/
  // (служебную копию шаблона Pagefind индексировать не должен), а из вывода убираем.
  html = replaceAllLiteral(html, ' data-pagefind-ignore="all"', '');
  // «old»-носитель: тело архивного старого html. build_views.mjs наполняет
  // ctx.legacyBody (вынимает из cms-revival/legacy_html/); в браузерном редакторе
  // его нет → пусто, и boot прячет опцию «оригинал». Подставляем ПОСЛЕДНИМ —
  // содержимое архива не должно перехватываться другими плейсхолдерами.
  html = replaceAllLiteral(html, "{{LEGACY_BODY}}", ctx.legacyBody || "");
  return html;
}

// ════════════════════════════════════════════════════════════════════════════
// Спец-страница «Песнь Ступеней» (ZML3 §6.8): renderArticleParts + СВОЙ шаблон
// template_songs.html (без byline/TOC/prev-next; грид [shir], lazy-YouTube).
// ОБЩИЙ код для build_songs.mjs (Node) и docs/ya-songs.js (браузер) → паритет
// байт-в-байт (как renderArticleHtml ↔ ya-edit). ctx: { zml, rec, manifest,
//   manifestByArt, zoharIndex, properNouns, template, artHrefBase, siteConfig }.
export function renderSongsHtml(ctx) {
  const p = renderArticleParts(ctx); // ctx.artHrefBase="../art/" → art-ссылки [shir]
  // Ф8′: «Песнь Ступеней» — раздел "songs" в правилах admin (дизайн/ширина). fm.theme/
  // fm.width (если заданы вручную) перебивают пер-полем; иначе правило раздела/global.
  const fmTheme = (p.fm.theme || "").trim();
  const fmWidth = (p.fm.width || "").trim();
  const resolved = resolveDisplay(ctx.displayConfig || null, "songs", "", fmTheme, fmWidth);
  // у songs «old»-варианта нет (P6.3): если правило/глобаль дали "old" — печём ZML-дефолт.
  const theme = resolved.design === "old" ? "A_editorial" : resolved.design;
  const widthRaw = resolved.width.toLowerCase();
  const wrapClass = /narrow|820/.test(widthRaw) ? "w-narrow" : "w-wide";
  // p.title/p.description приходят RAW → экранируем здесь (как в исходном
  // build_songs: &<>" — для <title> и meta[content]). p.titleH1/p.articleInner — уже HTML.
  const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  let html = ctx.template;
  html = replaceAllLiteral(html, "{{THEME}}", theme);
  html = replaceAllLiteral(html, "{{WRAP_CLASS}}", wrapClass);
  html = replaceAllLiteral(html, "{{CSS_VERSION}}", CSS_VERSION);
  html = replaceAllLiteral(html, "{{TITLE_H1}}", p.titleH1);
  html = replaceAllLiteral(html, "{{TITLE}}", esc(p.title));
  html = replaceAllLiteral(html, "{{DESCRIPTION}}", esc(p.description));
  html = replaceAllLiteral(html, "{{ARTICLE_BODY}}", p.articleInner);
  html = replaceAllLiteral(html, "{{WORKER_URL}}",
    esc((ctx.siteConfig && ctx.siteConfig.workerUrl) || ""));
  // для клиентского ре-резолвинга у залогиненных (зеркало template_view).
  html = replaceAllLiteral(html, "{{FM_THEME}}", esc(fmTheme));
  html = replaceAllLiteral(html, "{{FM_WIDTH}}", esc(fmWidth));
  // индексируемость (url-unification): songs/index.html — публичный адрес, попадает
  // в Pagefind. Атрибут оставлен в шаблоне ради синка docs/editor/, из вывода убираем.
  html = replaceAllLiteral(html, ' data-pagefind-ignore="all"', '');
  return html;
}

// ════════════════════════════════════════════════════════════════════════════
// Ф10: главная + страницы разделов из structure.json (browser + Node — один код).
// Заголовки/даты статей берём из manifest (join по art) → нет дрейфа названий.
// ════════════════════════════════════════════════════════════════════════════

// Русское согласование числительного: one=«статья», few=«статьи», many=«статей».
function ruPlural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}
function fmtDateRu(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  return m ? `${m[3]}.${m[2]}.${m[1]}` : (iso || "");
}
function activeSections(structure) {
  return (structure.sections || [])
    .filter((s) => !s.archived)
    .slice()
    .sort((a, b) => a.order - b.order);
}

// ctx: { structure, manifestByArt, template, buildDate, cssVersion? }
export function renderIndexHtml(ctx) {
  const { structure, template, buildDate } = ctx;
  const cssV = ctx.cssVersion || CSS_VERSION;
  const secs = activeSections(structure);
  const live = (structure.articles || []).filter((a) => a.status !== "archived");
  const counts = {};
  for (const a of live) counts[a.section] = (counts[a.section] || 0) + 1;
  const total = live.length;
  const sc = secs.length;
  const lis = [];
  for (const s of secs) {
    const c = counts[s.slug] || 0;
    lis.push(`<li><a href="${s.slug}/index.html">${htmlEscape(s.name)}</a>` +
      `<span class="meta">${c} ${ruPlural(c, "статья", "статьи", "статей")}</span></li>`);
  }
  for (const sp of (structure.specials || [])) {
    lis.push(`<li><a href="${sp.href}">${htmlEscape(sp.name)}</a>` +
      `<span class="meta">${htmlEscape(sp.meta)}</span></li>`);
  }
  let html = template;
  html = replaceAllLiteral(html, "{{TOTAL_FULL}}", `${total} ${ruPlural(total, "статья", "статьи", "статей")}`);
  html = replaceAllLiteral(html, "{{SECTIONS_FULL}}", `${sc} ${ruPlural(sc, "раздел", "раздела", "разделов")}`);
  html = replaceAllLiteral(html, "{{SECTIONS_LOC}}", `${sc} ${(sc % 10 === 1 && sc % 100 !== 11) ? "разделе" : "разделах"}`);
  html = replaceAllLiteral(html, "{{SECTIONS_LIST}}", lis.join("\n"));
  html = replaceAllLiteral(html, "{{BUILD_DATE}}", buildDate);
  html = replaceAllLiteral(html, "{{CSS_VERSION}}", cssV);
  return html;
}

// ctx: { slug, structure, manifestByArt, template, buildDate, cssVersion? }
export function renderSectionIndexHtml(ctx) {
  const { slug, structure, manifestByArt, template, buildDate } = ctx;
  const cssV = ctx.cssVersion || CSS_VERSION;
  const secs = activeSections(structure);
  const pos = secs.findIndex((s) => s.slug === slug);
  if (pos < 0) return null;
  const sec = secs[pos];
  const arts = (structure.articles || [])
    .filter((a) => a.section === slug && a.status !== "archived")
    .sort((a, b) => (a.order - b.order) || (a.art < b.art ? -1 : 1));
  const lis = arts.map((a) => {
    const rec = manifestByArt[a.art] || {};
    // title/date: manifest приоритетно; для НОВОЙ (zml-only) статьи её в manifest
    // ещё нет → фолбэк на поля самой записи structure (a.title/a.date).
    const title = htmlEscape(rec.title || a.title || a.art);
    const date = fmtDateRu(rec.date_chosen || rec.date || a.date || "");
    // url-unification: единственный адрес статьи — NNN.html (форсы/default_view упразднены).
    const href = `../art/${a.art}.html`;
    return `<li><span class="num">#${htmlEscape(a.num || a.art)}</span>` +
      `<a href="${href}">${title}</a>` +
      `<span class="meta">${date}</span></li>`;
  });
  const parts = [];
  if (pos > 0) {
    const p = secs[pos - 1];
    parts.push(`<a class="prev" href="../${p.slug}/index.html">` +
      `<span class="dir">← Предыдущий раздел</span>` +
      `<span class="title">${htmlEscape(p.name)}</span></a>`);
  }
  if (pos < secs.length - 1) {
    const n = secs[pos + 1];
    parts.push(`<a class="next" href="../${n.slug}/index.html">` +
      `<span class="dir">Следующий раздел →</span>` +
      `<span class="title">${htmlEscape(n.name)}</span></a>`);
  }
  const nav = parts.length ? `<nav class="section-nav">\n${parts.join("\n")}\n</nav>` : "";
  const count = arts.length;
  let html = template;
  html = replaceAllLiteral(html, "{{SECTION_NAME}}", htmlEscape(sec.name));
  html = replaceAllLiteral(html, "{{SLUG}}", slug);
  html = replaceAllLiteral(html, "{{COUNT}}", String(count));
  html = replaceAllLiteral(html, "{{COUNT_FULL}}", `${count} ${ruPlural(count, "статья", "статьи", "статей")}`);
  html = replaceAllLiteral(html, "{{ARTICLES_LIST}}", lis.join("\n"));
  html = replaceAllLiteral(html, "{{SECTION_NAV}}", nav);
  html = replaceAllLiteral(html, "{{BUILD_DATE}}", buildDate);
  html = replaceAllLiteral(html, "{{CSS_VERSION}}", cssV);
  return html;
}
