#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Переписать внутритекстовые proza.ru-ссылки, ведущие на наш же корпус,
в относительные ссылки {art}.html (docs/art/*.html).

Логика анкора для ссылок с СЫРЫМ URL в видимом тексте:
  - ABSENT  : названия статьи рядом нет -> анкор = «Заголовок»
  - PRESENT-ADJ : заголовок (по основам слов, с учётом морфологии) стоит прямо
                  перед ссылкой -> заворачиваем существующий текст в ссылку,
                  сырой URL (и разделитель) убираем — без дубля
  - PRESENT-FAR : заголовок есть в предложении, но не вплотную -> фолбэк «Заголовок»
Ссылки с уже человекочитаемым анкором: только меняем href.

Автор у нас зовётся по-разному (Элиягу Бар Малей / Зеир Арихович Анпин / ЭБМ /
ЗАА) — эти токены в матчинге заголовка игнорируются.

  python -X utf8 tools/relink_corpus.py            # dry-run + отчёт tools/relink_report.txt
  python -X utf8 tools/relink_corpus.py --apply     # бэкап + правка
"""
import json,re,glob,os,sys,shutil,datetime
ROOT=os.path.join(os.path.dirname(__file__),'..')
ART=os.path.join(ROOT,'docs','art')

def norm_url(u):
    u=u.strip().lower();u=re.sub(r'^https?://','',u);u=re.sub(r'^(www\.|m\.)','',u)
    return u.split('?')[0].split('#')[0].rstrip('/')

m=json.load(open(os.path.join(ROOT,'manifest.json'),encoding='utf-8'))
URL2ART={norm_url(r['url']):r['art'] for r in m if r.get('url')}
ART2TITLE={r['art']:r.get('title','') for r in m}

STOP=set('и в во на не что как к по за из о от до он она см смотри также его её также'.split())
AUTHOR=set('зеир арихович анпин элиягу бар малей эбм заа автор круг жизни бней адам'.split())

# Утверждённые оператором анкоры для вариантных названий (src, target_art) -> фраза.
# Тул найдёт эту фразу в тексте перед ссылкой и завернёт её, убрав голый URL.
OVERRIDE={
 ('0CA','11H'):'Катнут «Образа Всесильного»',
 ('11UA','11H'):'Катнут свойства «ЦЕЛЕМ Элоким»',
 ('163A','11H'):'«Катнут» свойства «ЦЕЛЕМ Элоким» (Образ Всесильного)',
 ('184','11H'):'Катнут свойства «ЦЕЛЕМ Элоким»',
 ('185','11H'):'Катнут свойства ЦЕЛЕМ Элоким',
 ('186A','11H'):'Катнут свойства ЦЕЛЕМ Элоким',
 ('1AA','11H'):'Катнут свойства ЦЕЛЕМ Элоким',
 ('1AS','11H'):'Катнут Образа Всесильного',
 ('1CF','11H'):'Катнут свойства «Целем Элоким»',
 ('2C3','11H'):'Катнут «Образа Всесильного»',
 ('53K','15D'):'Комплексная модель ТС',
 ('176','163'):'Онтология единства человеческой Души (краткая)',
 ('21K','163A'):'Онтология единства человеческой Души',
 ('176','185A'):'22 буквы Пути Воина-Исраэль (Кли «Средней линии»)',
 ('18MB','18MA'):'Сделаем и услышим!',
 ('19N','19E'):'Меняем восприятие Реальности',
 ('1AA','19E'):'Меняем восприятие Реальности',
 ('0CA','19UA'):'Гадлут «Образа Всесильного»',
 ('53J','1BN'):'Очерки об эволюции человека, часть 1',
 ('1C8C','1C8B'):'Моя ТьМа',
 ('237','1C8B'):'Моя ТьМа',
 ('1B5','1CI'):'Откуда берутся дети',
 ('O4Q','237'):'Дано Творцу, Свят Благословен Он, Право Любить',
 ('23TA','247'):'Конфронтология Духа',
 ('28MA','247'):'Конфронтология Самовоспроисхождения Человеческого Духа',
 ('2BC','247'):'Конфронтология Духа',
 ('2C3','247'):'Конфронтология Самовоспроисхождения Человеческого Духа',
 ('2CG','247'):'Конфронтология самовоспроисхождения человеческого Духа',
 ('55D','247'):'Конфронтология Самовоспроисхождения Человеческого Духа',
 ('237','255A'):'Предисловие к серии Добрая Речь',
 ('2CI','28M'):'Методика Трех Линий, п. 111-115',
 ('2C7','2C3'):'ДНА (1): По воле каждого',
 ('2CG','2C3'):'ДНА (1): По воле каждого',
 ('2CG','2C7'):'ДНА (2): МЕЧТА',
 ('341A','32F'):'Дорогу Осилит Идущий',
 ('61H','357'):'Нейрогеникологическое',
 ('61H','532'):'Заметки путешественника по времени',
}

def stem(w): return w[:5]
def words(t):
    t=re.sub(r'[«»"„“”\(\)\.,;:!\?\-–—\[\]/]',' ',t.lower())
    return [w for w in t.split() if len(w)>=3 and w not in STOP and w not in AUTHOR]

def title_present(title, win):
    tw=words(title); ws=[stem(w) for w in words(win)]
    if not tw: return 0.0
    hit=sum(1 for w in tw if stem(w) in ws)
    return hit/len(tw)

def title_regex(title):
    """гибкий паттерн для ЛОКАЛИЗАЦИИ заголовка в тексте: ВСЕ слова заголовка по
    порядку (длинные — по основе + морфологические окончания), между словами —
    любые пробелы/кавычки/знаки препинания (но не буквы)."""
    tw=[w for w in re.split(r'[\s«»"„“”\(\)\.,;:!\?\-–—\[\]/]+',title) if w]
    parts=[]
    for w in tw:
        if len(w)>=5 and re.search(r'[а-яёa-z]',w,re.I):
            parts.append(re.escape(w[:-2])+r'[а-яёa-z]*')   # основа + окончание
        else:
            parts.append(re.escape(w))
    sep=r'[^0-9A-Za-zА-Яа-яЁё]*'   # между словами — любые не-буквенно-цифровые
    return sep.join(parts)

def relink_file(path, report):
    s=open(path,encoding='utf-8').read()
    art=os.path.basename(path)[:-5]
    edits=[]  # (start,end,replacement,cat,info)
    used=[]   # занятые диапазоны (для контроля пересечений с WRAP)
    for mt in re.finditer(r'<a\b([^>]*)href="([^"]*proza\.ru[^"]*)"([^>]*)>(.*?)</a>',s,re.I|re.S):
        href=mt.group(2); inner=mt.group(4)
        T=URL2ART.get(norm_url(href))
        if not T: continue
        title=ART2TITLE.get(T,'') or T
        anchor_txt=re.sub(r'<[^>]+>','',inner).strip()
        raw = re.search(r'proza\.ru',anchor_txt,re.I) is not None
        a1,a3=mt.group(1),mt.group(3)
        if not raw:
            edits.append((mt.start(),mt.end(),f'<a{a1}href="{T}.html"{a3}>{inner}</a>','HREF-ONLY',anchor_txt[:40]))
            continue
        wbase=max(0,mt.start()-160)
        win_src=s[wbase:mt.start()]
        win=re.sub(r'<[^>]+>',' ',win_src)            # всё окно (без обрезки по точке)
        def try_wrap(phrase,cat):
            rx=r'(?<![а-яёa-zА-ЯЁA-Z])'+title_regex(phrase)+r'(?![а-яёa-zА-ЯЁA-Z])'
            for cm in reversed(list(re.finditer(rx, win_src, re.I))):
                ms,me=wbase+cm.start(),wbase+cm.end()
                seg=s[ms:me]
                if '<' in seg or '>' in seg: continue
                ctx=s[max(0,ms-400):ms]
                if ctx.rfind('<a')>ctx.rfind('</a>'): continue
                if len(seg.strip())<6: continue
                between=re.sub(r'<[^>]+>','',s[me:mt.start()])
                drop_start = me if re.fullmatch(r'[\s«»"„“”:\-–—·,]*', between or '') \
                             else mt.start()-len(re.search(r'[\s«»"„“”:\-–—·,]*$',s[me:mt.start()]).group(0))
                if drop_start<me: drop_start=me
                edits.append((ms,me,f'<a href="{T}.html">{seg}</a>',cat,seg.strip()[:40]))
                edits.append((drop_start,mt.end(),'','WRAP-DROP',''))
                return True
            return False
        # 1) обычный WRAP по title манифеста
        if title_present(title,win)>=0.55 and try_wrap(title,'WRAP'):
            continue
        # 2) спец-случай 255A: «вечный Апрель (URL) вечной Весны» -> одна ссылка
        if (art,T)==('255A','1C1'):
            pm=re.search(r'вечн\w*\s+Апрель\s*\(?\s*$',win_src,re.I)
            qm=re.match(r'\s*\)?\s*вечн\w*\s+Весны',s[mt.end():],re.I)
            if pm and qm:
                edits.append((wbase+pm.start(),mt.end()+qm.end(),
                              f'<a href="{T}.html">вечный Апрель вечной Весны</a>','WRAP-255A',''))
                continue
        # 3) override — утверждённый оператором анкор для вариантного названия
        ov=OVERRIDE.get((art,T))
        if ov and try_wrap(ov,'WRAP-OVR'):
            continue
        # 4) не получилось завернуть. Если заголовок виден рядом -> REVIEW (не трогаем)
        imm=re.sub(r'<[^>]+>','',s[max(0,mt.start()-95):mt.start()])
        if title_present(title,imm)>=0.45 or ov:
            edits.append((mt.start(),mt.end(),mt.group(0),'REVIEW',f'{T} | …{re.sub(chr(92)+"s+"," ",imm)[-38:]}'))
            continue
        # 5) заголовка рядом нет -> читаемый анкор «Title»
        edits.append((mt.start(),mt.end(),f'<a{a1}href="{T}.html"{a3}>«{title}»</a>','ANCHOR«»',title[:40]))
    # применяем справа налево, пропуская пересечения
    edits.sort(key=lambda e:-e[0]); res=s; floor=len(s)+1; applied=[]
    for st,en,rep,cat,info in edits:
        if en>floor:   # пересекается с уже применённой правкой правее
            report.append((art,'SKIP-OVERLAP',info)); continue
        res=res[:st]+rep+res[en:]; floor=st; applied.append(cat)
        report.append((art,cat,info))
    return res, sum(1 for c in applied if c not in ('WRAP-DROP','REVIEW'))

def main():
    apply='--apply' in sys.argv
    files=sorted(glob.glob(os.path.join(ART,'*.html')))
    report=[]; total=0; files_changed=0
    bdir=os.path.join(ROOT,'_backups','relink_'+datetime.datetime.now().strftime('%y%m%d_%H%M%S')) if apply else None
    if bdir: os.makedirs(bdir,exist_ok=True)
    for f in files:
        res,ch=relink_file(f,report)
        if ch:
            total+=ch; files_changed+=1
            if apply:
                shutil.copy2(f,os.path.join(bdir,os.path.basename(f)))
                open(f,'w',encoding='utf-8').write(res)
    from collections import Counter
    cats=Counter(r[1] for r in report)
    rp=os.path.join(os.path.dirname(__file__),'relink_report.txt')
    with open(rp,'w',encoding='utf-8') as fh:
        for r in report: fh.write(' | '.join(map(str,r))+'\n')
    print(f"ссылок переписано: {total} в {files_changed} файлах")
    print("категории:",dict(cats))
    print("отчёт:",rp,"| apply:",apply, (f"бэкап {bdir}" if apply else ""))

if __name__=='__main__': main()
