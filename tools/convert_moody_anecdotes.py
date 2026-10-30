#!/usr/bin/env python3
"""Convert Moody's Anecdotes and Illustrations (Gutenberg #19830) to
docs/illustrations/moody-anecdotes-and-illustrations.md.

Source: sources/moody-anecdotes-and-illustrations.txt (Gutenberg plain
text). Structure of the book:
  - title block, prefaces (PREFACE., REVISED EDITION., REVISED EDITION
    1896), four evangelist bios (caps names), CONTENTS (alphabetical
    anecdote titles), then the body:
      D. L. MOODY'S / Anecdotes and Illustrations.
      <TOPIC IN CAPS>          -> ### topic heading
      GOLD.                    -> #### Gold  (Moody's terse declarations,
                                  rendered as "--" items -> **N.**)
      <Anecdote title.>        -> #### title (matched against CONTENTS)
      paragraphs               -> joined one line per paragraph
      indented verse           -> kept line-per-line, 2-space breaks
  - tail: PUBLISHED BY ads, [Illustration:] captions, Gutenberg license —
    all dropped. [Illustration:] markers dropped throughout.

Per the txt-to-md-rag skill: arrangement: topic, tradition: evangelical
(Moody the revivalist — broad evangelical, nothing else fits), genre:
illustration. The Contents rendered is the book's topic index (subject
coverage map) rather than the 330-title alphabetical TOC.

Usage: python3 tools/convert_moody_anecdotes.py
"""
import difflib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / 'sources' / 'moody-anecdotes-and-illustrations.txt'
OUT = REPO / 'docs' / 'illustrations' / 'moody-anecdotes-and-illustrations.md'

TOPIC = re.compile(r"^[A-Z][A-Z' \-]{2,}\.?$")
ILLUS = re.compile(r'^\s*\[Illustration:')
GOLD = re.compile(r'^\s*--\s*')


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def norm_title(s):
    """norm() with a leading article removed — TOC lists 'A Commercial
    Traveler' while the body prints 'Commercial Traveler.' Leading
    quote/bracket characters are dropped first so '"A Day ..."' also
    normalizes."""
    s = re.sub(r'^[^a-z0-9]+', '', s.lower())
    return norm(re.sub(r'^(a|an|the)\s+', '', s))


def title_case(s):
    return ' '.join(w.capitalize() if not any(c.islower() for c in w)
                    else w for w in s.rstrip('.').split())


def join_para(lines):
    out = []
    for ln in lines:
        if out and out[-1].endswith(('-', '\u2010')):
            out[-1] = out[-1][:-1] + ln
        else:
            out.append(ln)
    return ' '.join(out)


def main():
    raw = SRC.read_text(encoding='ascii', errors='replace').splitlines()

    # ---- locate boundaries -------------------------------------------
    def find(pat, start=0):
        for i in range(start, len(raw)):
            if re.search(pat, raw[i], re.I):
                return i
        return -1

    i_title = find(r"^MOODY'S\s*$")
    i_preface = find(r'^PREFACE\.', i_title)
    i_rev1 = find(r'^REVISED EDITION\.', i_preface)
    i_rev2 = find(r'^REVISED EDITION 1896', i_rev1)
    i_moody = find(r'^DWIGHT L\. MOODY', i_rev2)
    i_sankey = find(r'^IRA D\. SANKEY', i_moody)
    i_whittle = find(r'^D\. W\. WHITTLE', i_sankey)
    i_bliss = find(r'^P\. P\. BLISS', i_whittle)
    i_contents = find(r'^CONTENTS\.', i_bliss)
    i_body = find(r"Anecdotes and Illustrations\.?$", i_contents)
    i_end = find(r'^PUBLISHED BY', i_body)
    bounds = {k: v for k, v in locals().items() if k.startswith('i_')}
    if -1 in bounds.values():
        raise SystemExit(f'boundary not found: {bounds}')

    # ---- TOC titles -> normalized set --------------------------------
    toc, cur = [], ''
    for ln in raw[i_contents + 1:i_body]:
        s = ln.strip()
        if not s or len(s) == 1:
            continue
        if s[:1].islower():
            cur += ' ' + s
        else:
            if cur:
                toc.append(cur)
            cur = s
    if cur:
        toc.append(cur)
    toc_keys = {norm(t) for t in toc}
    toc_keys_stripped = {norm_title(t) for t in toc}

    out = []

    def para(lines):
        t = join_para([l.strip() for l in lines if l.strip()])
        if t:
            out.extend(['', t, ''])

    # ---- front matter -------------------------------------------------
    out += [
        '---',
        'title: "Moody\'s Anecdotes and Illustrations"',
        'author: "Dwight L. Moody"',
        'tradition: "evangelical"',
        'genre: "illustration"',
        'arrangement: "topic"',
        'edition: "Revised edition (1899), ed. J. B. McClure"',
        'source: "https://www.gutenberg.org/ebooks/19830"',
        '---',
        '',
        "# Moody's Anecdotes and Illustrations",
        '',
        '*Dwight L. Moody*',
        '',
        '*Related in His Revival Work by the Great Evangelist — Revised '
        'Edition, edited by Rev. J. B. McClure. Chicago: Rhodes & '
        'McClure, 1899.*',
        '',
        '> Source: [Project Gutenberg eBook '
        '#19830](https://www.gutenberg.org/ebooks/19830). Public domain.',
        '',
    ]

    FRONT = [
        ('Preface', i_preface, i_rev1),
        ('To the Revised Edition', i_rev1, i_rev2),
        ('Revised Edition (1896)', i_rev2, i_moody),
        ('Dwight L. Moody', i_moody, i_sankey),
        ('Ira D. Sankey', i_sankey, i_whittle),
        ('D. W. Whittle', i_whittle, i_bliss),
        ('P. P. Bliss', i_bliss, i_contents),
    ]
    for name, a, b in FRONT:
        out += [f'## {name}', '']
        seg = [l for l in raw[a + 1:b] if not ILLUS.match(l)]
        # drop signature/publisher lines at section end
        while seg and (not seg[-1].strip()
                       or seg[-1].strip().startswith(('J. B.', 'Chicago'))):
            seg.pop()
        # prose paragraphs, indented runs -> verse lines
        paras, cur, verse_mode = [], [], False
        for ln in seg:
            if not ln.strip():
                if cur:
                    paras.append((verse_mode, cur))
                    cur = []
                verse_mode = False
            elif re.match(r'^\s{3,}\S', ln):
                if cur and not verse_mode:
                    paras.append((False, cur))
                    cur = []
                verse_mode = True
                cur.append(ln.strip())
            else:
                cur.append(ln.strip())
        if cur:
            paras.append((verse_mode, cur))
        for is_verse, ls in paras:
            if is_verse:
                out += [l + '  ' for l in ls] + ['']
            else:
                para(ls)

    # ---- topic index for Contents ------------------------------------
    topics = []
    for i in range(i_body, i_end):
        s = raw[i].strip()
        if TOPIC.match(s) and s != 'GOLD.':
            topics.append(title_case(s))
    out += ['## Contents', ''] + [f'- {t}' for t in topics] + ['']

    # ---- body ---------------------------------------------------------
    out += ['## Anecdotes and Illustrations', '']
    i = i_body + 1
    gold_n = 0
    seen_titles = set()
    emitted_titles = []
    while i < i_end:
        ln = raw[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        if ILLUS.match(ln):
            i += 1
            # a caption may wrap to a second line — skip to its closing ]
            while i < i_end and ']' not in raw[i - 1]:
                i += 1
            continue
        if s == 'GOLD.':
            out += ['#### Gold', '']
            gold_n = 0
            i += 1
            continue
        if TOPIC.match(s):
            out += [f'### {title_case(s)}', '']
            i += 1
            continue
        if GOLD.match(ln):
            item = [GOLD.sub('', ln).strip()]
            i += 1
            while i < i_end and raw[i].startswith(' '):
                item.append(raw[i].strip())
                i += 1
            gold_n += 1
            out += [f'**{gold_n}.** {join_para(item)}', '']
            continue
        # possible anecdote title: standalone line matching the TOC
        # (exact or article-stripped), a prefix variant (body titles are
        # sometimes longer than their TOC entry), or a title-shaped
        # heuristic
        n, nt = norm(s), norm_title(s)
        j = i + 1
        while j < i_end and not raw[j].strip():
            j += 1
        nxt = raw[j].strip() if j < i_end else ''
        # a title may wrap onto a second line (e.g. 'Young Moody ...
        # "Beware of / Pickpockets."') — try the joined form too
        s2 = (s + ' ' + raw[i + 1].strip()
              if i + 1 < i_end and raw[i + 1].strip() else s)
        n2, nt2 = norm(s2), norm_title(s2)
        is_title = (
            n in toc_keys or nt in toc_keys or nt in toc_keys_stripped
            or n2 in toc_keys or nt2 in toc_keys_stripped
            or any(len(k) > 8 and (n.startswith(k) or nt.startswith(k)
                                   or k.startswith(n))
                   for k in toc_keys_stripped)
            or (re.search(r'\.["\']?$', s) and len(s.split()) <= 12
                and sum(1 for w in s.split()
                        if w.lstrip('"\'(_')[:1].isupper())
                / max(len(s.split()), 1) >= 0.5
                and raw[i - 1].strip() == '' and nxt
                and not TOPIC.match(nxt)))
        if is_title:
            title_txt, adv = s, 1
            single_hit = (n in toc_keys or nt in toc_keys
                          or nt in toc_keys_stripped)
            wrap_hit = (n2 in toc_keys or nt2 in toc_keys_stripped)
            if wrap_hit and not single_hit:
                title_txt, adv = s2, 2
            seen_titles.add(norm_title(title_txt))
            emitted_titles.append(title_txt)
            out += [f'#### {title_txt.rstrip(".")}', '']
            i += adv
            continue
        # paragraph: consume until blank line
        buf = []
        while i < i_end and raw[i].strip():
            buf.append(raw[i])
            i += 1
        para(buf)

    topic_keys = {norm_title(t) for t in topics}
    topic_keys |= {norm_title(t) for t in
                   ("D. L. Moody's", 'Anecdotes and Illustrations',
                    'Gold')}
    # a TOC entry "misses" only if no emitted title shares most of its
    # words — spelling variants ('Erskine'/'Erkskine', 'Geo.'/'George')
    # and TOC entries split across lines land under their body titles
    def wordset(s):
        return set(re.findall(r'[a-z]+', s.lower()))

    def is_variant(e):
        w, ke = wordset(e), norm_title(e)
        if not w:
            return True
        return any(len(w & wordset(t)) / len(w) >= 0.7
                   or difflib.SequenceMatcher(
                       None, ke, norm_title(t)).ratio() >= 0.78
                   for t in emitted_titles)

    missing = sorted(
        e for e in toc
        if norm_title(e) not in seen_titles
        and norm_title(e) not in topic_keys
        and not is_variant(e))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(re.sub(r'\n{3,}', '\n\n', '\n'.join(out)) + '\n')
    n_gold = len(re.findall(r'^\*\*\d+\.\*\*', '\n'.join(out), re.M))
    print(f'wrote {OUT}')
    print(f'{len(topics)} topics, {len(emitted_titles)} titled anecdotes, '
          f'{n_gold} gold/declaration items')
    if missing:
        print(f'{len(missing)} TOC titles not seen as body headings:')
        for t in missing[:15]:
            print('  -', t)


if __name__ == '__main__':
    main()
