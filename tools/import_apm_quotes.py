#!/usr/bin/env python3
"""Fetch A Puritan's Mind "Puritan Quotations" page -> JSONL -> docs/quotes md.

Pipeline per RAG-NOTES.md / txt-to-md-rag skill:
  page HTML  ->  normalized records (sources/quotes/*.jsonl, canonical,
                 dedup by normalized-text hash)  ->  rendered markdown
                 (docs/quotes/*.md, generated artifact — do not hand-edit)

The page is a flat list of <p> quotes, each ending in a citation:
  "...quote text." Author, Work, (Crossville, TN: Puritan Publications, YYYY) N.
Variants seen: missing comma before the publisher paren, "Title, by Author"
order, "et al.", multi-author lists, "Surname, First" order, missing page.

Themes: no theme metadata exists at the source, so a keyword heuristic
(below) tags discriminating terms only — near-universal words (God,
Christ, Lord, heart, soul) are deliberately excluded as tag noise. It is
an enrichment starting point, not authoritative; edit the JSONL (never
the .md) to refine.

Usage:
    python3 tools/import_apm_quotes.py              # fetch + write all
    python3 tools/import_apm_quotes.py --report     # parse report only
    python3 tools/import_apm_quotes.py --offline    # use cached html
"""
import argparse
import hashlib
import html as h
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_HTML = REPO / 'sources' / 'quotes' / 'apuritansmind-puritan-quotes.html'
JSONL = REPO / 'sources' / 'quotes' / 'apuritansmind-puritan-quotes.jsonl'
OUT_MD = REPO / 'docs' / 'quotes' / 'apuritansmind-puritan-quotes.md'
URL = 'https://www.apuritansmind.com/puritan-quotes/'
UA = {'User-Agent': 'rag-quotes-illustrations fetch (personal use)'}

PUB = 'Puritan Publications'
SITE = "A Puritan's Mind"

# ---- citation parsing -------------------------------------------------

# terminal publisher paren + optional page, tolerating the page's typos:
# "Publ;ications", missing colon, missing comma, comma after the paren
# "(...) 2022), 13.", and multi-page "134, 139."
CITE = re.compile(
    r'\(\s*Crossville[^)]*?(\d{4})\s*\)[,\s]*'
    r'([\divxlc]+(?:\s*,\s*[\divxlc]+)*)\s*\.\s*')
# sentence boundary — but NOT after a single capital (initials "C. M.");
# whitespace optional since the source sometimes omits it ("man.Thomas")
SENT_END = re.compile(r'(?<![A-Z])[.!?][\u201d\u2019)\]]?\s*(?=[A-Z\u201c])')

NAME = re.compile(r"^[A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+){0,2}$")
INITIAL = re.compile(r'^[A-Z]\.\s')
TITLE_STARTERS = ('The ', 'A ', 'An ')
LIFESPAN = re.compile(r'\s*\([\d\-–, ]+\)')


def clean_author(names):
    joined = ', '.join(names[:-1]) + ' and ' + names[-1] if len(
        names) > 1 else names[0]
    return LIFESPAN.sub('', joined).strip()


def parse_cite_seg(cite_seg):
    """"Author, Work" / "Work, by Author" / "A, B, et al. Work" /
    "Surname, F. Name, Work" -> (author, work) or None."""
    fields = [f.strip() for f in cite_seg.split(', ') if f.strip()]
    for i, f in enumerate(fields):
        if f.startswith('by '):                      # "Title, by Author"
            return clean_author([f[3:]] + fields[i + 1:]), ', '.join(
                fields[:i])
        if 'et al' in f:                              # "Author, et al. Title"
            pre_et, _, post_et = re.split(r'(et al\.?)', f, maxsplit=1)
            names = fields[:i] + ([pre_et.strip()] if pre_et.strip()
                                  else [])
            work = ', '.join(([post_et.strip()] if post_et.strip()
                              else []) + fields[i + 1:]).strip(', ')
            return clean_author(names) + ' et al.', work
    lead = []
    for i, f in enumerate(fields):
        words = f.split()
        name_like = (NAME.match(f) and not f.startswith(TITLE_STARTERS)
                     and (len(words) >= 2
                          or (i == 0 and i + 1 < len(fields)
                              and INITIAL.match(fields[i + 1]))))
        if name_like:
            lead.append(f)
        else:
            break
    # every field name-like -> the tail is a name-shaped title
    # ("Rous, Puritan Meditations") — keep only the first as author
    if len(lead) == len(fields):
        lead = lead[:1]
    if not lead:
        # author inside a work title: "The Works of Henry Greenwood"
        m = re.search(
            r"\bof\s+([A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-]+)+)\s*$",
            fields[-1])
        if m:
            return m.group(1), ', '.join(fields)
        return None
    work = ', '.join(fields[len(lead):])
    if len(lead) == 2 and ' ' not in lead[0] and INITIAL.match(lead[1]):
        return f'{lead[1]} {lead[0]}', work          # "Surname, F. Name"
    if lead:
        return clean_author(lead), work
    return None


def split_citation(par):
    """Split a cleaned paragraph into (quote_text, author, work, year,
    page) or return None. The caller splits multi-quote paragraphs on
    each CITE match first."""
    m = CITE.search(par)
    if not m:
        return None
    year, page, pre = m.group(1), m.group(2), par[:m.start()].rstrip(' ,')
    # citation segment = after a sentence end inside `pre`; try
    # boundaries last-to-first and take the first that parses
    bounds = list(SENT_END.finditer(pre)) or [None]
    for b in reversed(bounds):
        start = b.end() if b else 0
        parsed = parse_cite_seg(pre[start:].strip())
        if parsed and parsed[0] and parsed[1]:
            quote = pre[:start].strip()
            if quote:
                return (quote, *parsed, year, page)
    return None


# ---- enrichment -------------------------------------------------------

THEME_WORDS = {
    'affliction': r'afflict|miser', 'affections': r'affection',
    'anger': r'\banger|wrath of man',
    'assurance': r'assur', 'atonement': r'atonement',
    'baptism': r'baptis', 'children': r'child(ren)?\b',
    'church': r'church', 'comfort': r'comfort', 'conscience': r'conscience',
    'contentment': r'content', 'covenant': r'covenant',
    'death': r'\bdeath\b|\bdie\b|\bdying\b', 'discipline': r'discipl|chastis',
    'election': r'\belect',
    'eternity': r'etern', 'faith': r'faith',
    'family': r'famil|parents|own hous|household',
    'fear': r'\bfear', 'fellowship': r'fellowship',
    'forgiveness': r'forgiv|pardon', 'glory': r'glorif|\bglory\b',
    'grace': r'grace', 'gratitude': r'thank(ful|sgiving)',
    'heaven': r'heaven', 'hell': r'\bhell\b', 'holiness': r'holin|holy\b',
    'holy-spirit': r'holy spirit|spirit of god|\bspirit\b|spiritual',
    'hope': r'\bhope', 'humility': r'humbl|self-abas|self-denial',
    'joy': r'\bjoy\b',
    'judgment': r'judg(e)?ment|day of judg', 'justice': r'justice',
    'justification': r'justif', 'law': r'\blaw\b|commandment',
    'love': r'\blove[ds]?\b|loving', 'meditation': r'meditat',
    'mercy': r'merc', 'ministry': r'\bminist(?:ry|ers?|ration)\b|pastor',
    'obedience': r'obedien|obey', 'patience': r'patien',
    'peace': r'\bpeace\b', 'persecution': r'persecut',
    'praise': r'\bprais', 'prayer': r'prayer|pray\b',
    'preaching': r'preach|sermon', 'pride': r'pride|proud',
    'promises': r'promise',
    'providence': r'providence|predetermin|foreordain|permitted by',
    'reformation': r'reform', 'regeneration': r'regenerat|born again',
    'repentance': r'repent', 'riches': r'\briches\b|\bwealth',
    'righteousness': r'righteous', 'sabbath': r'sabbath|lord.s day',
    'sanctification': r'sanctif', 'satan': r'satan|devil',
    'scripture': r'scripture|word of god|the word\b|bible',
    'sin': r'\bsins?\b', 'sovereignty': r'sovereign|decree',
    'submission': r'\bsubmit', 'suffering': r'suffer|enduring pain',
    'temptation': r'tempt',
    'truth': r'\btruth\b', 'wisdom': r'wisdom|wise\b',
    'world': r'\bworld\b', 'worship': r'worship',
    'wrath': r'\bwrath\b', 'arminianism': r'arminian',
}
THEME_RE = {k: re.compile(v, re.I) for k, v in THEME_WORDS.items()}

# human-tagged themes, keyed by record id — merged with (never replaced
# by) the keyword heuristic above. For quotes the heuristic can't reach
# without inventing taxonomy; add entries here rather than editing the
# JSONL, which is regenerated on every run.
THEME_OVERRIDES = {
    'q_72b46dd3': ['judgment', 'mercy', 'wrath', 'rebellion'],
    'q_a76ee710': ['regeneration', 'unbelief', 'depravity'],
    'q_75ed1c8c': ['faith', 'eternity', 'heaven'],
    'q_363e4888': ['sin', 'backsliding', 'reformation'],
    'q_d1052401': ['rebellion', 'sovereignty', 'submission', 'lordship'],
    'q_65d1d67f': ['meditation', 'atheism'],
    'q_7ecd11a3': ['mediator', 'covenant'],
}

OSIS = {
    'genesis': 'Gen', 'exodus': 'Exod', 'leviticus': 'Lev',
    'numbers': 'Num', 'deuteronomy': 'Deut', 'joshua': 'Josh',
    'judges': 'Judg', 'ruth': 'Ruth', '1 samuel': '1Sam',
    '2 samuel': '2Sam', '1 kings': '1Kgs', '2 kings': '2Kgs',
    '1 chronicles': '1Chr', '2 chronicles': '2Chr', 'ezra': 'Ezra',
    'nehemiah': 'Neh', 'esther': 'Esth', 'job': 'Job', 'psalm': 'Ps',
    'psalms': 'Ps', 'proverbs': 'Prov', 'ecclesiastes': 'Eccl',
    'song of solomon': 'Song', 'song of songs': 'Song', 'isaiah': 'Isa',
    'jeremiah': 'Jer', 'lamentations': 'Lam', 'ezekiel': 'Ezek',
    'daniel': 'Dan', 'hosea': 'Hos', 'joel': 'Joel', 'amos': 'Amos',
    'obadiah': 'Obad', 'jonah': 'Jonah', 'micah': 'Mic', 'nahum': 'Nah',
    'habakkuk': 'Hab', 'zephaniah': 'Zeph', 'haggai': 'Hag',
    'zechariah': 'Zech', 'malachi': 'Mal', 'matthew': 'Matt',
    'mark': 'Mark', 'luke': 'Luke', 'john': 'John', 'acts': 'Acts',
    'romans': 'Rom', '1 corinthians': '1Cor', '2 corinthians': '2Cor',
    'galatians': 'Gal', 'ephesians': 'Eph', 'philippians': 'Phil',
    'colossians': 'Col', '1 thessalonians': '1Thess',
    '2 thessalonians': '2Thess', '1 timothy': '1Tim',
    '2 timothy': '2Tim', 'titus': 'Titus', 'philemon': 'Phlm',
    'hebrews': 'Heb', 'james': 'Jas', '1 peter': '1Pet',
    '2 peter': '2Pet', '1 john': '1John', '2 john': '2John',
    '3 john': '3John', 'jude': 'Jude', 'revelation': 'Rev',
}
# parenthetical scripture citations inside quote text: "(Judges 4:21)",
# "(Ephesians 1:3-4)", "(Psalm 119:105)"
REF = re.compile(
    r'\(([123]?\s?[A-Z][a-z]+(?:\s+of\s+[A-Z][a-z]+)*)\s+'
    r'(\d+:\d+(?:\s*[-\u2013,]\s*\d+(?::\d+)?)*)\)')


def scripture_refs(text):
    out = []
    for m in REF.finditer(text):
        book = OSIS.get(m.group(1).lower())
        if not book:
            continue
        rng = re.sub(r'\s+', '', m.group(2)).replace('-', '\u2013')
        out.append(f'{book} {rng}')
    return out


def themes(text):
    return sorted(k for k, r in THEME_RE.items() if r.search(text))


def norm_key(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


# ---- pipeline ---------------------------------------------------------

def parse(html):
    seen, records, skipped = set(), [], []
    for p in re.findall(r'<p>(.*?)</p>', html, re.S):
        # block-level tags become spaces; inline tags merge (a stray
        # <em> boundary must not split "Meditation" into "Meditatio n")
        t = re.sub(r'<(?:br|/?p|/?div|/?li)[^>]*>', ' ', p)
        t = h.unescape(re.sub(r'<[^>]+>', '', t))
        t = re.sub(r'\s+', ' ', t).strip('\u00a0 ')
        t = re.sub(r'et\.?\s*,?\s*al\.?', 'et al.', t)  # "et. al.," -> "et al."
        if not t:
            continue
        # a <p> may contain several quotes — split after each citation
        ends = [m.end() for m in CITE.finditer(t)]
        if not ends:
            skipped.append(t)
            continue
        start = 0
        for end in ends:
            seg = t[start:end]
            start = end
            r = split_citation(seg)
            if not r:
                skipped.append(seg)
                continue
            quote, author, work, year, page = r
            key = norm_key(quote)
            if key in seen:
                continue
            seen.add(key)
            rid = f'q_{hashlib.sha256(key.encode()).hexdigest()[:8]}'
            records.append({
                'id': rid,
                'text': quote,
                'author': author,
                'work': work,
                'themes': sorted(set(themes(quote))
                                 | set(THEME_OVERRIDES.get(rid, []))),
                'scripture_refs': scripture_refs(quote),
                'source': {
                    'dataset': 'apuritansmind-puritan-quotes',
                    'page_url': URL,
                    'work': work,
                    'publisher': PUB,
                    'year': int(year),
                    'page': page,
                },
            })
        if t[start:].strip():
            skipped.append(t[start:])
    return records, skipped


def render(records):
    groups = []
    order = {}
    for r in records:
        k = (r['author'], r['work'])
        if k not in order:
            order[k] = len(groups)
            groups.append((k, []))
        groups[order[k]][1].append(r)
    lines = [
        '---',
        'title: "Puritan Quotations"',
        f'author: "{SITE}"',
        'tradition: "reformed"',
        'genre: "illustration"',
        'arrangement: "author"',
        f'source: "{URL}"',
        '---',
        '',
        '# Puritan Quotations',
        '',
        f'*{SITE}*',
        '',
        f'> Source: [{SITE} — Puritan Quotations]({URL}). Quotes compiled '
        f'from {PUB} editions; rendered from '
        '`sources/quotes/apuritansmind-puritan-quotes.jsonl`.',
        '',
        '## Contents',
        '',
    ]
    for (author, work), rs in groups:
        lines.append(f'- {author} — {work} ({len(rs)})')
    lines.append('')
    for (author, work), rs in groups:
        lines += [f'### {author} — {work}', '']
        for i, r in enumerate(rs, 1):
            entry = (f"**{i}.** {r['text']} "
                     f"— {r['author']}, *{r['work']}*, p. {r['source']['page']}")
            if r['themes']:
                entry += f" [themes: {', '.join(r['themes'])}]"
            lines += [entry, '']
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true')
    ap.add_argument('--offline', action='store_true')
    args = ap.parse_args()
    if args.offline or SRC_HTML.exists():
        doc = SRC_HTML.read_text()
    else:
        req = urllib.request.Request(URL, headers=UA)
        doc = urllib.request.urlopen(req, timeout=30).read().decode()
        SRC_HTML.parent.mkdir(parents=True, exist_ok=True)
        SRC_HTML.write_text(doc)
    records, skipped = parse(doc)
    print(f'{len(records)} quotes parsed, {len(skipped)} segments skipped')
    authors = {}
    for r in records:
        authors[r['author']] = authors.get(r['author'], 0) + 1
    for a in sorted(authors):
        print(f'  {authors[a]:3} {a}')
    for s in skipped:
        if len(s) > 40 and 'Puritan' in s:
            print('  SKIP-with-cite?:', s[:120])
    if args.report:
        return
    JSONL.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with JSONL.open('w') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    OUT_MD.write_text(render(records))
    print(f'wrote {JSONL} and {OUT_MD}')


if __name__ == '__main__':
    sys.exit(main())
