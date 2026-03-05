#!/usr/bin/env python3
"""
02_parse_usfm.py

Parse USFM sources into verse-indexed JSON for 1 Sam, 2 Sam, 1 Kings, preserving:

- Verse boundaries (\\c, \\v)
- USFM footnotes (\\f ... \\f*) extracted from \ft, optionally prefixed by \fr
- Poetry structure (\\q, \\q1, \\q2, \\m, \\p) encoded into the verse text using STRUCT_DELIM markers

Output:
  build/json/prideaux_1SA.json
  build/json/prideaux_2SA.json
  build/json/prideaux_1KI.json
  build/json/web_1SA.json
  build/json/web_2SA.json
  build/json/web_1KI.json
  build/json/webbe_1SA.json
  build/json/webbe_2SA.json
  build/json/webbe_1KI.json

Notes:
- This script assumes you have already unpacked your USFM zips into build/usfm/* (for WEB) and 
- It is intentionally conservative: it preserves content but normalises spacing/markup artefacts.
"""

import json
import re
from pathlib import Path


# ----------------------------
# Paths
# ----------------------------
ROOT = Path(__file__).resolve().parents[1]
USFM_ROOT = ROOT / "build" / "usfm"
OUT = ROOT / "build" / "json"
OUT.mkdir(parents=True, exist_ok=True)


# ----------------------------
# USFM structural regexes
# ----------------------------
C_RE = re.compile(r"^\\c\s+(\d+)\s*$")
V_RE = re.compile(r"^\\v\s+(\d+)([a-z]?)\s+(.*)$")

# Poetry / paragraph markers (often appear on their own lines)
Q_RE = re.compile(r"^\\q(\d*)\s+(.*)$")   # \q, \q1, \q2 ...
M_RE = re.compile(r"^\\m\s+(.*)$")        # \m ...
P_RE = re.compile(r"^\\p\s+(.*)$")        # \p ...

TL_OPEN_RE  = re.compile(r"\\tl\b\s*")
TL_CLOSE_RE = re.compile(r"\\tl\*")

# ----------------------------
# Footnote extraction (USFM)
# ----------------------------
FOOTNOTE_BLOCK_RE = re.compile(r"\\f\b.*?\\f\*", re.DOTALL)
FR_RE = re.compile(r"\\fr\b\s*([^\\]+)")
FT_RE = re.compile(r"\\ft\b\s*([^\\]+)")

# Some footnotes contain inline “character style” runs like \\+wh ... \\+wh*
# These contain backslashes and will truncate naive \ft capture unless removed first.
PLUS_MARK_RE = re.compile(r"\\\+[A-Za-z]+[* ]?")  # matches \\+wh and \\+wh* etc.

# Markers inserted into verse strings so the LaTeX generator can turn them into \footnote{...}
FOOTNOTE_DELIM = "\u241EFOOTNOTE\u241E"  # ␞FOOTNOTE␞ (very unlikely in source)

ADD_OPEN = "\u241EADDOPEN\u241E"
ADD_CLOSE = "\u241EADDCLOSE\u241E"
SC_OPEN = "\u241ESCOPEN\u241E"
SC_CLOSE = "\u241ESCCLOSE\u241E"
SUP_OPEN = "\u241ESUPOPEN\u241E"
SUP_CLOSE = "\u241ESUPCLOSE\u241E"

def extract_usfm_footnotes(raw: str) -> str:
    """
    Return text with USFM footnote blocks replaced inline by FOOTNOTE_DELIM markers.

    Turns:  ... \f + \fr 1:2 \ft Note text...\f* ...
    Into:   ... ␞FOOTNOTE␞1:2: Note text...␞FOOTNOTE␞ ...

    - Extracts \ft content (concatenates multiple \ft pieces)
    - If \fr exists, prefixes note with 'ref: ' (your current behaviour)
    - Removes \\+xx / \\+xx* inline markers inside the footnote so \ft capture isn't truncated
    """

    def repl(match):
        block = match.group(0)

        # Remove inline character-style markers (e.g., \\+wh ... \\+wh*)
        block = PLUS_MARK_RE.sub("", block)
        block = TL_OPEN_RE.sub("", block)
        block = TL_CLOSE_RE.sub("", block)
        fr_m = FR_RE.search(block)
        fr = fr_m.group(1).strip() if fr_m else ""

        fts = [m.group(1).strip() for m in FT_RE.finditer(block)]
        ft = " ".join(fts).strip()

        if not ft:
            # Delete empty footnote blocks
            return " "

        note = f"{fr}: {ft}" if fr else ft

        # Inline footnote marker at the exact position
        return f"{FOOTNOTE_DELIM}{note}{FOOTNOTE_DELIM} "

    return FOOTNOTE_BLOCK_RE.sub(repl, raw)

# ----------------------------
# Inline cleanup / normalisation
# ----------------------------
PIPE_ATTR_RE = re.compile(r'\|[A-Za-z]+="[^"]*"\\w\*')   # |strong="H3068", |lemma="..."
W_OPEN_RE = re.compile(r'\\w ')
USFM_MARK_RE = re.compile(r'\\[A-Za-z]+\d*\*?')     # \w, \w*, \add, \add*, etc.
STAR_RE = re.compile(r"\*+")                        # stray * markers (some editions)

def normalise_line(line: str) -> str:
    """
    Clean a fragment of verse text (not the whole verse structure).
    IMPORTANT: Footnotes should already be extracted before calling this.
    """

    # Normalise non-breaking spaces
    line = line.replace("\u00A0", " ")

    line = line.replace("\\add*", ADD_CLOSE)
    line = line.replace("\\add ", ADD_OPEN)
    line = line.replace("\\sc*", SC_CLOSE)
    line = line.replace("\\sc ", SC_OPEN)
    line = line.replace("\\nd*", SC_CLOSE)
    line = line.replace("\\nd ", SC_OPEN)
    line = line.replace("\\sup*", SUP_CLOSE)
    line = line.replace("\\sup ", SUP_OPEN)

    line = TL_OPEN_RE.sub("", line)
    line = TL_CLOSE_RE.sub("", line)
    # Remove pipe attributes (Strong’s/lemma/etc.)
    line = PIPE_ATTR_RE.sub("", line)
    line = W_OPEN_RE.sub("", line)
    
    # Remove leftover star markers
    line = STAR_RE.sub("", line)

    # Remove USFM inline markers (used to replace with a space to preserve word breaks ... not needed)
    line = USFM_MARK_RE.sub("", line)

    # Remove stray pipes
    line = line.replace("|", "")

    # Collapse whitespace early
    line = re.sub(r"\s+", " ", line).strip()

    return line




# ----------------------------
# Poetry structure encoding
# ----------------------------
# We encode structure into verse text so the LaTeX generator can render poetry lines:
#
#   ␞Q:2␞line text   (poetry line with indent level 2)
#   ␞P␞prose text    (prose chunk)
#
STRUCT_DELIM = "\u241E"  # ␞ (record separator symbol)
STYLE_HDG = f"{STRUCT_DELIM}STYLE:HDG{STRUCT_DELIM}"
STYLE_PARA = f"{STRUCT_DELIM}STYLE:PARA{STRUCT_DELIM}"

def encode_chunk(kind: str, indent: int, text: str) -> str:
    if kind == "q":
        return f"{STRUCT_DELIM}Q:{indent}{STRUCT_DELIM}{text}"
    return f"{STRUCT_DELIM}P{STRUCT_DELIM}{text}"


# ----------------------------
# Core parser
# ----------------------------
def parse_usfm_file(path: Path):
    """
    Parse a USFM file into a dict of verses keyed as "CH:V".

    - Captures \\c (chapter) and \\v (verse) markers.
    - Extracts USFM footnote blocks: \\f ... \\f* (keeps \ft content, optionally prefixed by \fr)
    - Preserves poetry structure via \\q/\\q1/\\q2, \\m, \\p (encoded into the verse string)
    - Normalises inline tags and spacing

    Returns: (book_id, verses_dict)
    """
    book = None
    chapter = None
    verses = {}  # key: "CH:V" -> encoded verse text with FOOTNOTE_DELIM markers

    current_v = None
    chunks = []    # list of encoded chunks (poetry/prose)
    after_d = False
    after_p = False
    
    def flush_current():
        nonlocal current_v, chunks
        if current_v is None:
            chunks = []
            return

        text = " ".join(chunks).strip()

        verses[current_v] = text
        chunks = []

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")

            # Book id
            if line.startswith("\\id "):
                parts = line.strip().split()
                if len(parts) >= 2:
                    book = parts[1].upper()
                continue

            s = line.strip()

            if s == r"\d" or s.startswith(r"\d "):
                # we don't need to store \d itself for our purposes; just remember it
                after_d = True
                continue
            if s == r"\p" or s == r"\p ":
                # we don't need to store \p itself for our purposes; just remember it
                after_p = True
                continue
            # Chapter marker
            m = C_RE.match(s)
            if m:
                flush_current()
                chapter = int(m.group(1))
                current_v = None
                continue

            # Verse marker
            m = V_RE.match(s)
            if m and chapter is not None:
                flush_current()

                vnum = int(m.group(1))
                vsuf = (m.group(2) or "").lower()   # '', 'a', 'b', ...
                current_v = f"{chapter}:{vnum}{vsuf}"

                # start verse with any pending headings (if you still have that feature)
                # if pending_headings:
                #     chunks.extend(pending_headings)
                #     pending_headings = []

                raw_text = m.group(3)
                is_heading_verse = False
                is_para = False
                # If it follows \d, treat as a heading-verse
                if after_d:
                    is_heading_verse = True
                    after_d = False  # consumed the \d context
                else:
                    after_d = False  # \d context only applies to the immediate next verse
                # If it follows \p, treat as a paragraph starter
                if after_p:
                    is_para = True
                    after_p = False  # consumed the \d context
                else:
                    after_p = False  # \d context only applies to the immediate next verse

                raw_text = extract_usfm_footnotes(raw_text)
                t = normalise_line(raw_text)
                if t:
                    if is_heading_verse:
                        t = STYLE_HDG + t
                    if is_para:
                        t = STYLE_PARA + t
                    chunks.append(encode_chunk("p", 0, t))
                continue
            
            # Continuation lines: may contain poetry markers or prose continuation
            if current_v is not None and s:
                # Poetry line?
                qm = Q_RE.match(s)
                if qm:
                    level = int(qm.group(1) or "1")
                    raw_text = qm.group(2)
                    raw_text = extract_usfm_footnotes(raw_text)
                    t = normalise_line(raw_text)
                    if t:
                        chunks.append(encode_chunk("q", level, t))
                    continue

                # Poetry paragraph (flush-left)
                mm = M_RE.match(s)
                if mm:
                    raw_text = mm.group(1)
                    raw_text = extract_usfm_footnotes(raw_text)
                    t = normalise_line(raw_text)
                    if t:
                        chunks.append(encode_chunk("q", 1, t))
                    continue

                # Prose paragraph marker
                pm = P_RE.match(s)
                if pm:
                    raw_text = STYLE_PARA + pm.group(1)
                    raw_text = extract_usfm_footnotes(raw_text)
                    t = normalise_line(raw_text)
                    if t:
                        chunks.append(encode_chunk("p", 0, t))
                    continue

                # Default continuation line (treat as prose continuation)
                raw_text = s
                raw_text = extract_usfm_footnotes(raw_text)
                t = normalise_line(raw_text)
                if t:
                    chunks.append(encode_chunk("p", 0, t))

    flush_current()
    return book, verses


# ----------------------------
# Locate Jeremiah in a USFM tree
# ----------------------------
def find_book_file(folder: Path, book_id: str) -> Path:
    """
    Find a USFM file whose \\id matches book_id (e.g. JER).
    Falls back to filename contains book_id.
    """
    for p in folder.rglob("*.usfm"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if txt.startswith("\\id " + book_id):
            return p
    for p in folder.rglob(f"*{book_id}*.usfm"):
        return p
    raise FileNotFoundError(f"Could not find {book_id} in {folder}")


# ----------------------------
# Main
# ----------------------------
def main():
    # Adjust book ids if your set uses a different code for Jeremiah.
    jobs = [
        ("Prideaux", "1SA"),
        ("web", "1SA"),
        ("webbe", "1SA"),
        ("Prideaux", "2SA"),
        ("web", "2SA"),
        ("webbe", "2SA"),
        ("Prideaux", "1KI"),
        ("web", "1KI"),
        ("webbe", "1KI"),
    ]

    folders = [p for p in USFM_ROOT.iterdir() if p.is_dir()]
    if not folders:
        raise RuntimeError(f"No unpacked USFM folders found under {USFM_ROOT}. Run 01_unpack_sources.py first.")

    for label, book_id in jobs:
        candidates = [p for p in folders if label.lower() in p.name.lower()]
        if candidates:
            base = candidates[0]
        else:
            raise RuntimeError(f"Not able to find a USFM file under {USFM_ROOT} matching {label}:{book_id}.")

        usfm_path = find_book_file(base, book_id)
        book, verses = parse_usfm_file(usfm_path)

        out_path = OUT / f"{label}_{book_id}.json"
        out_path.write_text(json.dumps(verses, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {out_path} ({len(verses)} verses) from {usfm_path}")

if __name__ == "__main__":
    main()
