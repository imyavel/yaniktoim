// ZML → HTML renderer (spec v0.1). SINGLE SOURCE OF TRUTH for rendering.
// Runs unchanged in Node (build: tools/build.mjs) and in the browser
// (live preview + save inside the gh-pages editor) → same code, no drift.
// Ported from the now-retired Python src/4_render.py (archived in _backups/).

// ════════════════════════════════════════════════════════════════════════════
// CONSTANTS  (keep in sync with 4_render.py)
// ════════════════════════════════════════════════════════════════════════════

export const CSS_VERSION = "20260529-05";

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
  "", "А", "Я", "У", "Ю", "Е", "Ы", "И", "ОМ", "ЕМ", "ЁМ",
  "ОВ", "ЕВ", "АМ", "ЯМ", "АМИ", "ЯМИ", "АХ", "ЯХ",
  "ОЙ", "ЕЙ", "ОЮ", "ЕЮ", "Ь", "Й",
]);

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

const PAIRED = ["poem", "epi", "epil", "quote", "num", "mus", "sub"];
const PAIRED_ALT = PAIRED.join("|");

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

const SECTION_RX = /^##\s+(.*?)(?:\s+\{([^}]+)\})?\s*$/;
const FN_BODY_RX = /^\[\^(\d+|\|[^\]]*)?\]:\s?(.*)$/;

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
      if (fid === undefined) {
        kind = "anon";
      } else if (fid.startsWith("|")) {
        kind = "anon";
        prefix = fid.slice(1).trim() || null;
      } else {
        idInt = parseInt(fid, 10);
      }
      cur = { kind, id: idInt, prefix };
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
  const singleRx = new RegExp(
    "\\[(" + PAIRED_ALT + ")(=?[^\\]]*)?\\](.*?)\\[\\/\\1\\]\\s*(?=\\n|$)",
    "y",
  );
  const openRx = new RegExp(
    "\\[(" + PAIRED_ALT + ")(=?[^\\]]*)?\\]\\s*\\n",
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
        text: mh[1].trim(),
        slug: (mh[2] || "").trim() || null,
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
    const m = /^="([^"]*)"/.exec(s);
    if (m) { out.label = m[1]; s = s.slice(m[0].length); }
  }
  const re = /(\w+)="([^"]*)"/g;
  let m;
  while ((m = re.exec(s)) !== null) out[m[1]] = m[2];
  return out;
}

// ════════════════════════════════════════════════════════════════════════════
// INLINE CASCADE
// ════════════════════════════════════════════════════════════════════════════

export function resolveInline(text, inline) {
  const capsPass = inline.capsPass !== false;
  let s = htmlEscape(text);
  s = resolveFootnotes(s);
  s = resolveInternals(s, inline.manifestByArt);
  s = resolveZohar(s, inline.zoharIndex);
  s = resolveExternal(s);
  s = resolveItalic(s);
  if (capsPass) s = resolveCaps(s, inline.matchProperNoun);
  return s;
}

function resolveFootnotes(s) {
  const seen = {};
  return s.replace(/\[\^(\d+)\]/g, (_, d) => {
    const nid = parseInt(d, 10);
    seen[nid] = (seen[nid] || 0) + 1;
    const suffix = seen[nid] === 1 ? "" : `-extra${seen[nid] - 1}`;
    return `<sup id="cite_ref-${nid}${suffix}"><a href="#cite_note-${nid}">[${nid}]</a></sup>`;
  });
}

function resolveInternals(s, manifestByArt) {
  return s.replace(/\[\[([A-Za-z0-9]+)\]\]/g, (_, art) => {
    const rec = manifestByArt[art];
    if (!rec) return `<a class="broken" href="#">[[${art}]]</a>`;
    const title = rec.title || art;
    // Flat layout: all articles live in docs/art/<art>.html → same dir.
    const href = `${art}.html`;
    return `<a class="internal" href="${href}">${htmlEscape(title)}</a>`;
  });
}

function resolveZohar(s, zoharIndex) {
  const chapters = zoharIndex.chapters || {};
  const articles = zoharIndex.articles || {};
  const base = zoharIndex._url_base || "https://imyavel.github.io/zohar-sulam";
  return s.replace(/\{([a-z][a-z-]*)\|(\d+)\}/g, (_, ch, num) => {
    const chInfo = chapters[ch];
    if (!chInfo) return `<a class="broken" href="#">{${ch}|${num}}</a>`;
    const artTitle = (articles[ch] || {})[num];
    if (!artTitle) return `<a class="broken" href="#">{${ch}|${num}}</a>`;
    const href = `${base}/${ch}/${String(parseInt(num, 10)).padStart(3, "0")}.html`;
    const knigaHuman = chInfo.kniga_human || "";
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

function resolveItalic(s) {
  return s.replace(
    /(?<![A-Za-zА-Яа-яёЁ0-9_])_([^_\n]{1,60}?)_(?![A-Za-zА-Яа-яёЁ0-9_])/g,
    "<em>$1</em>",
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
  for (const b of blocks) {
    switch (b.type) {
      case "heading":   out.push(renderHeading(b, ctx)); break;
      case "paragraph": out.push(renderParagraph(b, ctx)); break;
      case "poem":      out.push(renderPoem(b, ctx)); break;
      case "epi":       out.push(renderEpigraph(b, ctx, "Эпиграф", "epigraph")); break;
      case "epil":      out.push(renderEpigraph(b, ctx, "Эпилог", "epilogue")); break;
      case "quote":     out.push(renderQuote(b, ctx)); break;
      case "num":       out.push(renderNum(b, ctx)); break;
      case "mus":       out.push(renderMusic(b, ctx)); break;
      case "sub":       out.push(renderSub(b, ctx)); break;
    }
  }
  return out.filter((p) => p).join("\n\n");
}

function renderHeading(b, ctx) {
  const text = resolveInline(b.text, ctx.inline);
  const slug = b.slug || makeSlug(b.text);
  const tocLabel = tocInline(b.text, ctx);
  ctx.toc.push([slug, tocLabel]);
  return (
    `<h2 id="${slug}">${text} ` +
    `<a class="back-to-toc" href="#article-title" title="К началу статьи">↑</a></h2>`
  );
}

function tocInline(text, ctx) {
  text = text.replace(/\[\^\d+\]/g, "");
  return resolveInline(text, ctx.inline);
}

function renderParagraph(b, ctx) {
  const text = b.text.replace(/\n+/g, " ").trim();
  return `<p>${resolveInline(text, ctx.inline)}</p>`;
}

function renderSub(b, ctx) {
  const text = b.inner.replace(/\n+/g, " ").trim();
  return `<h2 class="subtitle">${resolveInline(text, ctx.inline)}</h2>`;
}

function renderPoem(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const inlineCtx = Object.assign({}, ctx.inline, { capsPass: false });
  const lines = inner.split("\n").map((ln) => resolveInline(ln, inlineCtx));

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
  const body = outLines.join("\n");
  const title = b.attrs.title || "";
  const titleHtml = title ? `<div class="poem-title">${htmlEscape(title)}</div>` : "";
  return `<div class="poem">${titleHtml}${body}</div>`;
}

function renderEpigraph(b, ctx, label, cls) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const cite = b.attrs.cite || "";
  const paras = inner.split(/\n\s*\n/).filter((p) => p.trim());
  const paraHtml = paras
    .map((p) => `<p>${resolveInline(p.replace(/\n/g, " ").trim(), ctx.inline)}</p>`)
    .join("\n");
  const citeHtml = cite ? `\n<span class="cite">— ${htmlEscape(cite)}</span>` : "";
  return `<div class="${cls}" data-label="${label}">\n${paraHtml}${citeHtml}\n</div>`;
}

function renderQuote(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const cite = b.attrs.cite || "";
  const paras = inner.split(/\n\s*\n/).filter((p) => p.trim());
  const paraHtml = paras
    .map((p) => `<p>${resolveInline(p.replace(/\n/g, " ").trim(), ctx.inline)}</p>`)
    .join("\n");
  const citeHtml = cite ? `\n<span class="cite">— ${htmlEscape(cite)}</span>` : "";
  return `<blockquote class="q" data-label="Цитата">\n${paraHtml}${citeHtml}\n</blockquote>`;
}

function renderNum(b, ctx) {
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const items = inner.split(/\n\s*\n/).filter((p) => p.trim());
  const itemsHtml = items
    .map((p) => `<li>${resolveInline(p.replace(/\n/g, " ").trim(), ctx.inline)}</li>`)
    .join("\n");
  return `<ol class="num">\n${itemsHtml}\n</ol>`;
}

function extractYoutubeId(url) {
  const m = /(?:v=|youtu\.be\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{11})/.exec(url);
  return m ? m[1] : null;
}

function renderMusic(b, ctx) {
  const label = b.attrs.label || "Музыка под настроение";
  const inner = b.inner.replace(/^\n+/, "").replace(/\n+$/, "");
  const tracks = [];
  for (const rawLine of inner.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const m = /\[([^|\]]*)\|([^|\]]*)\|([^\]]*)\]/.exec(line);
    if (!m) {
      tracks.push(
        `<div class="music-noplayer"><div class="summary">` +
        `<span class="label">${htmlEscape(label)}:</span>` +
        `<span class="title">${htmlEscape(line)}</span>` +
        `</div></div>`,
      );
      continue;
    }
    const url = m[1], title = m[2], author = m[3];
    const ytId = extractYoutubeId(url);
    let trackLabel;
    if (author && title) trackLabel = `${author} — ${title}`;
    else trackLabel = author || title || url;
    if (ytId) {
      tracks.push(
        `<details class="music"><summary>` +
        `<span class="label">${htmlEscape(label)}:</span>` +
        `<span class="title">${htmlEscape(trackLabel)}</span>` +
        `<span class="caret">›</span>` +
        `<a class="ext" href="${url}" target="_blank" rel="noopener" ` +
        `title="Открыть на YouTube">↗</a></summary>` +
        `<div class="player">` +
        `<iframe data-src="https://www.youtube.com/embed/${ytId}" ` +
        `title="YouTube video player" ` +
        `allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" ` +
        `referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>` +
        `</div></details>`,
      );
    } else if (url) {
      tracks.push(
        `<div class="music-noplayer"><div class="summary">` +
        `<span class="label">${htmlEscape(label)}:</span>` +
        `<span class="title">${htmlEscape(trackLabel)}</span>` +
        `<a class="ext" href="${url}" target="_blank" rel="noopener">↗</a>` +
        `</div></div>`,
      );
    } else {
      tracks.push(
        `<div class="music-noplayer"><div class="summary">` +
        `<span class="label">${htmlEscape(label)}:</span>` +
        `<span class="title">${htmlEscape(trackLabel)}</span>` +
        `</div></div>`,
      );
    }
  }
  return (
    `<div class="music-group" data-label="${htmlEscape(label)}">\n` +
    tracks.join("\n") +
    `\n</div>`
  );
}

// ════════════════════════════════════════════════════════════════════════════
// FOOTNOTES + TOC
// ════════════════════════════════════════════════════════════════════════════

function renderFootnotes(footnotes, ctx) {
  if (!footnotes.length) return "";
  const items = [];
  for (const fn of footnotes) {
    const bodyHtml = resolveInline(fn.body.replace(/\n+/g, " ").trim(), ctx.inline);
    if (fn.kind === "numbered") {
      const nv = fn.id;
      items.push(
        `<li id="cite_note-${nv}" value="${nv}">` +
        `<a class="backref" href="#cite_ref-${nv}" ` +
        `title="Вернуться к месту в тексте">↑</a> ${bodyHtml}</li>`,
      );
    } else {
      const prefix = fn.prefix || "См. также";
      items.push(`<li class="anon">${htmlEscape(prefix)}: ${bodyHtml}</li>`);
    }
  }
  return (
    `<h2 id="notes">Примечания ` +
    `<a class="back-to-toc" href="#article-title" title="К началу статьи">↑</a></h2>\n` +
    `<ol class="notes">\n` + items.join("\n") + `\n</ol>`
  );
}

function renderToc(toc, hasNotes) {
  if (!toc.length && !hasNotes) return "";
  const items = toc.map(([slug, text]) => `<li><a href="#${slug}">${text}</a></li>`);
  if (hasNotes) items.push('<li><a href="#notes">Примечания</a></li>');
  return (
    `<details class="article-toc">\n<summary>Содержание</summary>\n` +
    `<ol>\n` + items.join("\n") + `\n</ol>\n</details>`
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

  const inline = {
    manifestByArt, zoharIndex, fnIdMap,
    matchProperNoun: compileProperNouns(ctx.properNouns),
  };
  const renderCtx = { inline, toc: [] };

  const bodyHtml = renderBlocks(blocks, renderCtx);
  const notesHtml = renderFootnotes(footnotes, renderCtx);
  const tocHtml = renderToc(renderCtx.toc, Boolean(notesHtml));

  let articleInner = bodyHtml;
  if (notesHtml) articleInner += "\n\n" + notesHtml;

  const title = fm.title || "";
  const description = fm.summary || "";
  const dateDisplay = fm.date || rec.date_chosen || "";
  // Attribution (§0.6): who last touched the article and when. Default editor
  // is "Иван Иванович" (built by AI, never hand-edited); the pipeline / editor
  // overwrite fm.editor/fm.edited on real edits.
  const editor = fm.editor || "Иван Иванович";
  const edited = fm.edited || "";
  const originUrl = rec.url || "";
  const originLabel = originUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  const [prevLink, nextLink] = siblings(rec, manifest);
  let illustration = "";
  if (fm.image) {
    illustration =
      `<img class="cover" src="../pics/${fm.image}" alt="${htmlEscape(title)}">\n`;
  }

  return {
    fm, title, description, dateDisplay, editor, edited, originUrl, originLabel,
    sectionHuman, illustration, tocHtml, articleInner, prevLink, nextLink,
  };
}

// ctx: { zml, rec, manifest, manifestByArt, zoharIndex, template }
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

  let html = template;
  html = replaceAllLiteral(html, "{{TITLE}}", htmlEscape(title));
  html = replaceAllLiteral(html, "{{DESCRIPTION}}", htmlEscape(description));
  html = replaceAllLiteral(html, "{{CSS_VERSION}}", CSS_VERSION);
  html = replaceAllLiteral(html, "{{SECTION_NAME}}", htmlEscape(sectionHuman));
  // Flat layout: article at docs/art/<art>.html → section index is one level up.
  html = replaceAllLiteral(html, "{{SECTION_HREF}}", `../${ctx.rec.section || "other"}/index.html`);
  html = replaceAllLiteral(html, "{{ILLUSTRATION}}", illustration);
  html = replaceAllLiteral(html, "{{NUMBER}}", ctx.rec.art);
  html = replaceAllLiteral(html, "{{DATE_DISPLAY}}", htmlEscape(dateDisplay));
  html = replaceAllLiteral(html, "{{ORIGIN_URL}}", originUrl);
  html = replaceAllLiteral(html, "{{ORIGIN_LABEL}}", htmlEscape(originLabel));
  html = replaceAllLiteral(html, "{{ARTICLE_TOC}}", tocHtml);
  html = replaceAllLiteral(html, "{{ARTICLE_BODY}}", articleInner);
  html = replaceAllLiteral(html, "{{PREV_LINK}}", prevLink);
  html = replaceAllLiteral(html, "{{NEXT_LINK}}", nextLink);
  html = replaceAllLiteral(html, "{{LAST_EDIT}}", lastEdit);
  return html;
}
