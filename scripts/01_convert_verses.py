#!/usr/bin/env python3
"""
Convert Pandoc Markdown containing superscripted chapter/verse markers and
blockquote-indented poetry into USFM.

Features:
- ^CH:V^ (including bold/italic like ^**2**:1^) at block start => emits \\c CH, then starts verse \\v V
- ^V^ elsewhere => emits a new verse marker \\v V on its own line
- Poetry: lines starting with >, >>, >>> become \\q1, \\q2, \\q3 ...
- Dagger superscripts ^†^ ^‡^ are kept as literal characters
- Footnote superscripts ^[^n]^ are preserved as [^n] (for a later footnote conversion pass)
- Pandoc small caps spans [TEXT]{.smallcaps} => \\sc TEXT\\sc*
- Unescapes Markdown \\\' so contractions become normal apostrophes

Usage:
  python 01_convert_verses.py input.md output.usfm --id 1SA
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple


# Superscript matcher that can handle Pandoc footnote refs inside superscripts: ^[^3]^
SUP_RE = re.compile(r"(?<!\[)\^(\[\^[^\]]+\]|[^^]+)\^")

# Verse number (optionally 40a/40b etc)
VERSE_RE = re.compile(r"^\s*(\d+)([a-z])?\s*$", re.IGNORECASE)

# Plain CH:V after stripping emphasis
CHV_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")

# Poetry blockquote line: > text, >> text, etc
BQ_LINE_RE = re.compile(r"^(?P<level>>+)\s?(?P<text>.*)$")

# Pandoc small caps span: [text]{.smallcaps} or [text]{.small-caps}
SMALLCAPS_RE = re.compile(r"\[([^\]]+)\]\{\.(?:smallcaps|small-caps)\}")

WS_RE = re.compile(r"[ \t]+")

DAGGERS = {"†", "‡"}

# Markdown italics (Pandoc output): *text* or _text_
# Avoid bold (**...**) and __...__, and avoid escaped \* or \_
ITALIC_STAR_RE = re.compile(r"(?<!\\)\*(?!\*)([^*\n]+?)(?<!\\)\*(?!\*)")
ITALIC_UND_RE  = re.compile(r"(?<!\\)_(?!_)([^_\n]+?)(?<!\\)_(?!_)")

def convert_italics_to_add(s: str) -> str:
    """
    Convert Markdown italics to USFM \\add ...\\add*.
    Assumption (per user): all italics in the ODT are added words.
    """
    s = ITALIC_STAR_RE.sub(lambda m: rf"\add {m.group(1)}\add*", s)
    s = ITALIC_UND_RE.sub(lambda m: rf"\add {m.group(1)}\add*", s)
    return s

def strip_md_emphasis(s: str) -> str:
    """Remove simple Markdown emphasis markers from a short string: **...** and *...*."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"\*([^*]+)\*", r"\1", s)
    return s

# Divine-name convention recovered from ODT: "Lord" (capital L only) was small-caps LORD (YHWH).
# Lower-case "lord" refers to a human lord/master and must remain unchanged.
LORD_SC_RE = re.compile(r"\bLord\b")

def mark_divine_name_from_capital_lord(s: str) -> str:
    # Normalise to LORD to match standard convention in USFM
    return LORD_SC_RE.sub(r"\\nd Lord\\nd*", s)

def unescape_markdown_punct(s: str) -> str:
    """Remove Markdown backslash escaping of apostrophes (and a few other safe punctuations)."""
    # Keep this conservative; do NOT remove arbitrary backslashes (USFM uses backslashes!)
    return (
        s.replace("\\'", "'")
         .replace('\\"', '"')
    )


def convert_smallcaps_spans(s: str) -> str:
    """Convert Pandoc small-caps spans to USFM small-caps markers."""
    def repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        return r"\sc " + inner + r"\sc*"
    return SMALLCAPS_RE.sub(repl, s)


def normalise_spaces(s: str) -> str:
    """Collapse runs of spaces/tabs (but keep newlines meaningful)."""
    # normalise each line independently so we don't destroy intentional newlines
    lines = []
    for ln in s.splitlines():
        ln = WS_RE.sub(" ", ln).strip()
        lines.append(ln)
    return "\n".join([ln for ln in lines if ln != ""])


def extract_leading_chv(block_text: str) -> tuple[tuple[int, str] | None, str]:
    """
    Only detect a CH:V marker if it is the *first* thing in the block, in a
    Pandoc superscript ^...^ (possibly with **bold** inside).
    Footnote refs like [^4] elsewhere in the block must not affect this.
    """
#    print("BLOCK START:", repr(block_text[:60]))
    s = block_text.lstrip()
    if not s.startswith("^"):
        return None, block_text

    m = SUP_RE.match(s)  # SUP_RE must be the footnote-safe one
    if not m:
        return None, block_text

    raw = strip_md_emphasis(m.group(1)).strip()
    m2 = CHV_RE.match(raw)  # CHV_RE = r"^\s*(\d+)\s*:\s*(\d+)\s*$"
    if not m2:
        return None, block_text

    ch = int(m2.group(1))
    v = m2.group(2)
    rest = s[m.end():]  # remainder after the leading ^CH:V^
    return (ch, v), rest

def convert_superscripts_to_usfm(text: str, poetry_level: Optional[int] = None) -> str:
    """
    Convert superscripts in text:
      ^26^ -> newline + \\v 26 (or \\v 26 \\qN in poetry)
      ^‡^  -> literal ‡ superscripted
      ^[^3]^ -> literal [^3] (kept for later footnote pass)
    """
    out = []
    pos = 0
    for m in SUP_RE.finditer(text):
        out.append(text[pos:m.start()])
        raw = m.group(1).strip()

        # Pandoc footnote reference like [^1] inside superscript
        if raw.startswith("[^") and raw.endswith("]"):
            out.append(raw)
        else:
            plain = strip_md_emphasis(raw).strip()

            if plain in DAGGERS:
                out.append(fr"\sup {plain}\sup*")
            else:
                mv = VERSE_RE.match(plain)
                if mv:
                    vnum = mv.group(1) + (mv.group(2) or "")
                    if poetry_level is None:
                        out.append(f"\n\\v {vnum} ")
                    else:
                        out.append(f"\n\\v {vnum} \\q{poetry_level} ")
                else:
                    # unknown superscript content: keep literal
                    out.append(plain)

        pos = m.end()

    out.append(text[pos:])
    return "".join(out)


def attach_q_to_v_line(line: str, level: int) -> str:
    """
    If a line begins with '\\v N ' and doesn't already include a \\q marker,
    ensure it becomes '\\v N \\q<level> ...' for poetry.
    """
    if not line.startswith(r"\v "):
        return line
    # if it already has \\qN early, leave it
    if r"\q" in line[:20]:
        return line
    m = re.match(r"^(\\v\s+\S+\s+)(.*)$", line)
    if not m:
        return line
    return m.group(1) + rf"\q{level} " + m.group(2).lstrip()


def split_blocks(md: str) -> List[str]:
    """Split the markdown into blocks separated by blank lines."""
    blocks = re.split(r"\n\s*\n+", md.strip(), flags=re.MULTILINE)
    return [b.strip("\n") for b in blocks if b.strip()]


def block_is_poetry(block: str) -> bool:
    """A block is poetry if every nonblank line starts with one or more '>'."""
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return False
    return all(BQ_LINE_RE.match(ln) is not None for ln in lines)


def render_prose_block(block: str, current_chapter: Optional[int]) -> Tuple[Optional[int], List[str]]:
    """
    Convert a prose block (Pandoc-wrapped lines) into USFM:
      optional \\c, then \\p, then each \\v on its own line.
    """
    # join wrapped lines with spaces
    joined = " ".join(ln.strip() for ln in block.splitlines() if ln.strip())

    joined = unescape_markdown_punct(joined)
    joined = convert_smallcaps_spans(joined)

    lead, rest = extract_leading_chv(joined)

    out_lines: List[str] = []

    if lead:
        ch, v = lead
        if current_chapter != ch:
            out_lines.append(rf"\c {ch}")
            current_chapter = ch
        out_lines.append(r"\p")
        working = rf"\v {v} " + rest
    else:
        out_lines.append(r"\p")
        working = joined

    working = convert_italics_to_add(working)
    working = convert_superscripts_to_usfm(working, poetry_level=None)
    working = mark_divine_name_from_capital_lord(working)
    working = normalise_spaces(working)

    # ensure each \v starts a new output line (already inserted as \n\v)
    for ln in working.splitlines():
        ln = ln.strip()
        if ln:
            out_lines.append(ln)

    return current_chapter, out_lines


def render_poetry_block(block: str) -> List[str]:
    """
    Convert a poetry block (blockquote lines) into USFM \\qN lines.
    Verse markers inside poetry become '\\v N \\qN ...' on a new line.
    """
    out_lines: List[str] = []

    for raw_line in block.splitlines():
        if not raw_line.strip():
            continue

        m = BQ_LINE_RE.match(raw_line)
        if not m:
            # safety fallback; treat as q1
            level = 1
            text = raw_line.strip()
        else:
            level = len(m.group("level"))
            text = m.group("text")

        text = unescape_markdown_punct(text)
        text = convert_smallcaps_spans(text)
        text = convert_superscripts_to_usfm(text, poetry_level=level)
        text = convert_italics_to_add(text)
        text = mark_divine_name_from_capital_lord(text)
        text = normalise_spaces(text)

        # split into lines: may now include \v lines
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            ln = ln.strip()
            if not ln:
                continue
            if ln.startswith(r"\v "):
                out_lines.append(attach_q_to_v_line(ln, level))
            else:
                out_lines.append(rf"\q{level} {ln}")

    return out_lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_md", type=Path)
    ap.add_argument("output_usfm", type=Path)
    ap.add_argument("--id", dest="book_id", default="", help="USFM \\id, e.g. 1SA or 2SA")
    args = ap.parse_args()

    md = args.input_md.read_text(encoding="utf-8", errors="ignore")
    blocks = split_blocks(md)

    out: List[str] = []
    if args.book_id:
        out.append(rf"\id {args.book_id}")

    current_chapter: Optional[int] = None

    for block in blocks:
        if block_is_poetry(block):
            out.extend(render_poetry_block(block))
        else:
            current_chapter, lines = render_prose_block(block, current_chapter)
            out.extend(lines)

    args.output_usfm.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
