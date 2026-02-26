#!/usr/bin/env python3
"""
Convert Pandoc Markdown footnote references in a USFM-ish file into proper USFM footnotes.

Inputs:
  1) A Pandoc Markdown file (for footnote definitions)
  2) A USFM-ish text file containing inline markers like [^4] (produced by your verse converter)

Output:
  A USFM file with inline \f + \ft ...\f* footnote blocks.

Footnote definition forms supported (Pandoc):
  [^4]: Footnote text...
      continuation line (4 spaces or tab)
      another continuation line

Also optionally supports:
  [4]: ...   (plain numeric)  -- if you enable --accept-plain-brackets

Usage:
  python 06_footnotes_md_to_usfm.py source.md in.usfm out.usfm
  python 06_footnotes_md_to_usfm.py source.md in.usfm out.usfm --accept-plain-brackets
"""

from __future__ import annotations

import bisect
import argparse
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set


# Footnote definitions in Pandoc Markdown
#   [^id]: text
FN_DEF_RE = re.compile(r"^\s*\[\^([^\]]+)\]\s*:\s*(.*)$")

# Optional plain-bracket definitions:
#   [4]: text
FN_DEF_PLAIN_RE = re.compile(r"^\s*\[(\d+)\]\s*:\s*(.*)$")

# Continuation lines: indented, optionally with a leading '>' quote marker
FN_CONT_RE = re.compile(r"^(?:\t| {4,})(?:>\s*)?(.*)$")

# Inline references in body/usfm
FN_REF_RE = re.compile(r"\[\^([^\]]+)\]")          # [^4]
FN_REF_PLAIN_RE = re.compile(r"\[(\d+)\]")         # [4] (optional)

# Replace "Moses I–V" with standard English book names
MOSES_BOOK_MAP = [
    (re.compile(r"\bMoses\s+V\b"),  "Deuteronomy"),
    (re.compile(r"\bMoses\s+IV\b"), "Numbers"),
    (re.compile(r"\bMoses\s+III\b"), "Leviticus"),
    (re.compile(r"\bMoses\s+II\b"), "Exodus"),
    (re.compile(r"\bMoses\s+I\b"),  "Genesis"),
]

def normalise_footnote_books(s: str) -> str:
    for pat, repl in MOSES_BOOK_MAP:
        s = pat.sub(repl, s)
    return s

def unescape_markdown_punct(s: str) -> str:
    # Keep conservative; do NOT remove arbitrary backslashes (USFM uses backslashes).
    return s.replace("\\'", "'").replace('\\"', '"')


def strip_md_emphasis(s: str) -> str:
    # Enough for footnotes; avoids bringing ** ** into USFM.
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"\*([^*]+)\*", r"\1", s)
    return s


def normalise_ws(s: str) -> str:
    # Convert internal newlines/tabs to spaces, collapse runs.
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# Hebrew letters + diacritics block

# Hard-coded correction for the one Hebrew instance in this document:
# Markdown contains (לבנ) but it should be נבל ("Nabal")
def fix_known_hebrew_typos(text: str) -> str:
    return text.replace("לבנ", "נבל")

HEBREW_RUN_RE = re.compile(r"([\u0590-\u05FF\uFB1D-\uFB4F]+)")

RLI = "\u2067"  # Right-to-Left Isolate
PDI = "\u2069"  # Pop Directional Isolate

def wrap_hebrew_usfm(text: str, marker: str = "tl") -> str:
    """
    Wrap Hebrew runs with RTL direction isolates and a USFM character style.
    Default marker: \\tl ...\\tl*
    """
    def repl(m: re.Match) -> str:
        heb = m.group(1)
        heb_rtl = f"{RLI}{heb}{PDI}" # this generates LATEX errors ... replace heb_rtl in the next line with heb
        return rf"\{marker} {heb}\{marker}*"
    return HEBREW_RUN_RE.sub(repl, text)

def parse_footnote_definitions(md_text: str, accept_plain: bool) -> Dict[str, str]:
    """
    Return {id: text} for footnotes defined in the Pandoc Markdown file.
    Joins multi-line definitions into a single string.
    """
    lines = md_text.splitlines()
    i = 0
    defs: Dict[str, str] = {}

    while i < len(lines):
        line = lines[i]
        m = FN_DEF_RE.match(line)
        m_plain = FN_DEF_PLAIN_RE.match(line) if accept_plain else None

        if not m and not m_plain:
            i += 1
            continue

        if m:
            fid = m.group(1).strip()
            first = m.group(2)
        else:
            fid = m_plain.group(1).strip()  # type: ignore[union-attr]
            first = m_plain.group(2)        # type: ignore[union-attr]

        parts: List[str] = [first] if first.strip() else []
        
        # capture indented continuation lines
        j = i + 1
        while j < len(lines):
            ln = lines[j]
            mcont = FN_CONT_RE.match(ln)
            if mcont:
                parts.append(mcont.group(1))
                j += 1
                continue
            # blank line: may still continue if next line is indented; Pandoc typically stops.
            if ln.strip() == "":
                # peek ahead: if next is indented, treat as continuation; else stop
                if j + 1 < len(lines) and FN_CONT_RE.match(lines[j + 1]):
                    j += 1
                    continue
                break
            break

        text = " ".join(parts)
        text = unescape_markdown_punct(text)
        text = strip_md_emphasis(text)
        text = normalise_ws(text)
        text = normalise_footnote_books(text)
        text = fix_known_hebrew_typos(text) 
        text = wrap_hebrew_usfm(text, marker="tl")

        if fid in defs and defs[fid] != text:
            print(f"WARNING: duplicate footnote id [^{fid}] with different text; keeping first.")

        defs.setdefault(fid, text)

        i = j + 1 if j > i else i + 1

    return defs

CV_TOKEN_RE = re.compile(r"\\c\s+(\d+)|\\v\s+(\d+[a-z]?)", re.IGNORECASE)

def build_ref_index(usfm_text: str) -> tuple[list[int], list[str]]:
    r"""
    Return (positions, refs) where refs[i] is the active 'CH:V' starting at positions[i].
    We record an entry at each \v occurrence (using the most recent \c).
    """
    ch: str | None = None
    positions: list[int] = []
    refs: list[str] = []

    for m in CV_TOKEN_RE.finditer(usfm_text):
        if m.group(1):  # \c
            ch = m.group(1)
        elif m.group(2):  # \v
            v = m.group(2)
            if ch is not None:
                positions.append(m.start())
                refs.append(f"{ch}:{v}")

    return positions, refs


def ref_at(pos: int, positions: list[int], refs: list[str]) -> str | None:
    """
    Find the most recent verse ref whose position <= pos.
    """
    i = bisect.bisect_right(positions, pos) - 1
    if i >= 0:
        return refs[i]
    return None

def usfm_footnote_block(text: str, ref: str | None = None) -> str:
    """
    Produce an inline USFM footnote.
    If ref is available, include \fr CH:V.
    """
    if ref:
        return rf"\f + \fr {ref} \ft {text}\f*"
    return rf"\f + \ft {text}\f*"

def replace_refs(usfm_text: str, defs: Dict[str, str], accept_plain: bool) -> Tuple[str, Set[str], Set[str]]:
    used: Set[str] = set()

    positions, refs = build_ref_index(usfm_text)
    def repl(m: re.Match) -> str:
        fid = m.group(1)
        if fid in defs:
            used.add(fid)
            r = ref_at(m.start(), positions, refs)
            return usfm_footnote_block(defs[fid], r)
        # Leave marker in place if missing, but make it obvious in output/log
        return m.group(0)

    out = FN_REF_RE.sub(repl, usfm_text)

    if accept_plain:
        # Only replace [4] if we actually have a definition "4" (avoid eating normal bracket numbers)
        def repl_plain(m: re.Match) -> str:
            fid = m.group(1)
            if fid in defs:
                used.add(fid)
                r = ref_at(m.start(), positions, refs)
                return usfm_footnote_block(defs[fid], r)
            return m.group(0)

        out = FN_REF_PLAIN_RE.sub(repl_plain, out)

    unused = set(defs.keys()) - used
    missing = set()

    # compute missing by scanning what remains
    for m in FN_REF_RE.finditer(out):
        missing.add(m.group(1))
    if accept_plain:
        for m in FN_REF_PLAIN_RE.finditer(out):
            # only count as missing if it looks like a footnote id we might expect
            if m.group(1) in defs:
                # would have been replaced, so shouldn't happen
                continue

    return out, used, unused


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_md", type=Path, help="Pandoc markdown containing footnote definitions")
    ap.add_argument("input_usfm", type=Path, help="USFM-ish file containing [^id] markers")
    ap.add_argument("output_usfm", type=Path, help="Output USFM with \\f ...\\f* footnotes inserted")
    ap.add_argument("--accept-plain-brackets", action="store_true",
                    help="Also treat [4] (no caret) as footnote refs/defs if matching ids exist")
    args = ap.parse_args()

    md_text = args.source_md.read_text(encoding="utf-8", errors="ignore")
    usfm_text = args.input_usfm.read_text(encoding="utf-8", errors="ignore")

    defs = parse_footnote_definitions(md_text, accept_plain=args.accept_plain_brackets)
    if not defs:
        print("WARNING: no footnote definitions found in markdown.")

    out, used, unused = replace_refs(usfm_text, defs, accept_plain=args.accept_plain_brackets)

    # Report
    # Missing refs: any [^id] still present after replacement
    still = set(FN_REF_RE.findall(out))
    if still:
        print(f"WARNING: {len(still)} footnote refs had no definition and were left as-is: "
              f"{', '.join(sorted(still)[:20])}" + (" ..." if len(still) > 20 else ""))

    if unused:
        print(f"NOTE: {len(unused)} footnote definitions were never referenced: "
              f"{', '.join(sorted(unused)[:20])}" + (" ..." if len(unused) > 20 else ""))

    args.output_usfm.write_text(out.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
