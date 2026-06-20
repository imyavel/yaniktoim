// ════════════════════════════════════════════════════════════════════════════
// faw_markup.js — авто-разметка [faw] при «Сохранить» в редакторе.
//
// Если внутри [faw]…[/faw] нет ни одного «|» (на верхнем уровне, вне «[…]»), это
// указание движку разметить содержимое алгоритмом verse_split.js (счёт слогов) и
// проставить границы строк знаком «|». Если хоть один «|» уже есть — текст считается
// размеченным вручную и НЕ трогается. Идемпотентно: повторный прогон уже размеченный
// блок пропускает.
//
// Подключается ze-core-редактором как opts.preprocess(zml) → zml (см. ya-edit.js).
// ════════════════════════════════════════════════════════════════════════════

import { markupFaw } from "./verse_split.js";

// Верхнеуровневый «|» (вне «[…]») — признак уже размеченного [faw]. «|» внутри
// [url|анкор] и пр. скобок границей строки не считается (как в render.js).
export function hasTopLevelPipe(s) {
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "[") depth++;
    else if (c === "]") { if (depth > 0) depth--; }
    else if (c === "|" && depth === 0) return true;
  }
  return false;
}

// [faw …]…[/faw] — атрибуты без «]» (meter=N), тело лениво до первого [/faw].
const FAW_RX = /\[faw\b([^\]]*)\]([\s\S]*?)\[\/faw\]/g;

// Размечает все «голые» [faw] в ZML-тексте. Возвращает новый текст (или исходный,
// если размечать нечего). Никогда не бросает на тексте — на любой ошибке блока
// оставляет его как был.
export function autoMarkupFaw(zml) {
  if (typeof zml !== "string" || zml.indexOf("[faw") === -1) return zml;
  return zml.replace(FAW_RX, function (m, attrs, inner) {
    attrs = attrs || "";
    if (hasTopLevelPipe(inner)) return m;                 // уже размечен — уважаем
    if (!inner.replace(/\s+/g, " ").trim()) return m;     // пусто
    const mm = /\bmeter\s*=\s*"?(\d+)"?/.exec(attrs);
    const opts = mm ? { meter: parseInt(mm[1], 10) } : {};
    let marked;
    try { marked = markupFaw(inner, opts); }
    catch (e) { return m; }                               // не смогли — оставляем как есть
    if (!marked || !hasTopLevelPipe(marked)) return m;    // ничего не разметилось
    return "[faw" + attrs + "]\n" + marked + "\n[/faw]";
  });
}
