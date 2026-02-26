#!/usr/bin/env python3
"""
Split a single Pandoc-generated Markdown file (build/md/SSD.md) into:

- SSD_preface.md                       : before the first ^1:1^
- Prideaux-1SA.md                              : 1 Samuel from 1:1 through 31:13
- between_1sam_2sam.md                 : material between end of 1 Sam and start of 2 Sam
- Prideaux-2SA.md                              : 2 Samuel from 1:1 through 24:25
- between_2sam_1kings.md               : material between end of 2 Sam and start of 1 Kings
- Prideaux-1KI.md                : 1 Kings from 1:1 through 2:11 (partial)
- SSD_footnotes.md                     : footnote definitions extracted from end of SSD.md

Handles Pandoc quirks:
- Chapter/verse markers as superscripts: ^1:1^, ^13^, etc
- Bold chapter in superscript: ^**2**:12^
- Footnote refs inside superscripts at starts: ^[^52]^ ^1:1^...
- Inline footnote refs [^4] must not break caret scanning (SUP_RE forbids starting inside [^ ])

Usage:
  python 00_split_ssd_md.py build/md/SSD.md
  python 00_split_ssd_md.py build/md/SSD.md --outdir build/md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple


# Superscripts: ^...^ but do NOT start on the caret inside [^4]
SUP_RE = re.compile(r"(?<!\[)\^(\[\^[^\]]+\]|[^^]+)\^")

CHV_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")
V_RE = re.compile(r"^\s*(\d+)([a-z])?\s*$", re.IGNORECASE)

# Footnote definitions block begins like: [^4]:
FN_DEF_START_RE = re.compile(r"(?m)^\[\^\d+\]:")
LEADING_FN_REF_RE = re.compile(r"^\[\^([^\]]+)\]\s*")  # matches leading [^52] (optionally followed by spaces)


def strip_md_emphasis(s: str) -> str:
    """Remove simple Markdown emphasis markers: **...** and *...*."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"\*([^*]+)\*", r"\1", s)
    return s


def split_footnote_definitions(md: str) -> Tuple[str, str]:
    """Split Markdown into (body, footnote_definitions_block)."""
    m = FN_DEF_START_RE.search(md)
    if not m:
        return md, ""
    body = md[: m.start()].rstrip() + "\n"
    fndefs = md[m.start() :].lstrip()
    return body, fndefs


def split_blocks(md_body: str) -> List[str]:
    """Split on blank lines (1+ empty lines)."""
    blocks = re.split(r"\n\s*\n+", md_body.strip(), flags=re.MULTILINE)
    return [b.strip("\n") for b in blocks if b.strip()]


def _skip_leading_footnote_superscripts(s: str) -> str:
    """
    Remove any number of leading footnote references, either:
      - superscripted: ^[^52]^
      - plain inline:  [^52]
    allowing spaces between them.

    Example:
      '^[^52]^ [^53]  ^1:1^And ...' -> '^1:1^And ...'
    """
    s2 = s
    while True:
        # First: skip any leading plain [^n] refs
        m_plain = LEADING_FN_REF_RE.match(s2)
        if m_plain:
            s2 = s2[m_plain.end():].lstrip()
            continue

        # Next: skip any leading superscripts whose content is a footnote ref [^n]
        m = SUP_RE.match(s2)
        if not m:
            break
        raw = strip_md_emphasis(m.group(1)).strip()
        if raw.startswith("[^") and raw.endswith("]"):
            s2 = s2[m.end():].lstrip()
            continue

        break

    return s2

def get_leading_chv(block: str) -> Optional[Tuple[int, int]]:
    """
    If block begins (possibly after leading footnote superscripts) with ^CH:V^, return (CH, V).
    """
    s = _skip_leading_footnote_superscripts(block.lstrip())
    if not s.startswith("^"):
        return None
    m = SUP_RE.match(s)
    if not m:
        return None
    raw = strip_md_emphasis(m.group(1)).strip()
    m2 = CHV_RE.match(raw)
    if not m2:
        return None
    return int(m2.group(1)), int(m2.group(2))


def scan_block_for_progress(block: str, current_ch: Optional[int]) -> Tuple[Optional[int], List[Tuple[int, str]]]:
    """
    Scan superscripts in a block, updating current chapter when CH:V appears, and collecting hits.
    Returns (new_current_chapter, hits) where hits are (chapter, verse_str).
    """
    hits: List[Tuple[int, str]] = []

    # Update from leading CH:V if present
    lead = get_leading_chv(block)
    if lead:
        current_ch = lead[0]
        hits.append((lead[0], str(lead[1])))

    for m in SUP_RE.finditer(block):
        raw = strip_md_emphasis(m.group(1)).strip()

        # ignore footnote superscripts ^[^52]^
        if raw.startswith("[^") and raw.endswith("]"):
            continue

        m_chv = CHV_RE.match(raw)
        if m_chv:
            current_ch = int(m_chv.group(1))
            hits.append((current_ch, m_chv.group(2)))
            continue

        m_v = V_RE.match(raw)
        if m_v and current_ch is not None:
            vnum = m_v.group(1) + (m_v.group(2) or "")
            hits.append((current_ch, vnum))

    return current_ch, hits


def find_first_book_start(blocks: List[str]) -> int:
    """Index of the first block that starts with ^1:1^ (allow leading ^[^n]^ or [^n])."""
    for i, b in enumerate(blocks):
        lead = get_leading_chv(b)
        if lead == (1, 1):
            return i
    raise RuntimeError("Could not find the first book start ^1:1^ in the document.")


def find_next_book_start(blocks: List[str], start_idx: int) -> int:
    """Find next block after start_idx whose leading marker is ^1:1^ (allow leading ^[^n]^)."""
    for i in range(start_idx + 1, len(blocks)):
        lead = get_leading_chv(blocks[i])
        if lead == (1, 1):
            return i
    return len(blocks)


def cut_after_reaching(blocks: List[str], start_idx: int, target_ch: int, target_v: str) -> int:
    """
    Return index AFTER the first block in which we encounter target chapter:verse,
    even if the verse marker is mid-block.

    Robust: initialises chapter state from the earliest CH:V seen at/after start_idx.
    """
    current_ch: Optional[int] = None

    # Initialise chapter state by scanning forward until we see any CH:V
    # (at book starts we should see 1:1 very quickly)
    for i in range(start_idx, len(blocks)):
        current_ch, hits = scan_block_for_progress(blocks[i], current_ch)
        for ch, v in hits:
            if ch == target_ch and v == target_v:
                return i + 1
        if current_ch is not None:
            # we now have chapter state; continue normal scan from next block
            start_idx = i + 1
            break

    for i in range(start_idx, len(blocks)):
        current_ch, hits = scan_block_for_progress(blocks[i], current_ch)
        for ch, v in hits:
            if ch == target_ch and v == target_v:
                return i + 1

    return len(blocks)

def write_blocks(path: Path, blocks: List[str]) -> None:
    path.write_text("\n\n".join(blocks).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_md", type=Path, help="Path to build/md/SSD.md (Pandoc output)")
    ap.add_argument("--outdir", type=Path, default=None, help="Output directory (default: input file's folder)")
    args = ap.parse_args()

    in_path: Path = args.input_md
    outdir: Path = args.outdir if args.outdir is not None else in_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    md = in_path.read_text(encoding="utf-8", errors="ignore")
    body, fndefs = split_footnote_definitions(md)
    blocks = split_blocks(body)

    # 1 Samuel start
    i_1sam_start = find_first_book_start(blocks)
    preface = blocks[:i_1sam_start]

    # 1 Samuel end (after 31:13)
    i_1sam_end = cut_after_reaching(blocks, i_1sam_start, target_ch=31, target_v="13")

    # 2 Samuel start (next ^1:1^ after i_1sam_end)
    i_2sam_start = find_next_book_start(blocks, i_1sam_end)

    between_1_2 = blocks[i_1sam_end:i_2sam_start]
    one_sam = blocks[i_1sam_start:i_1sam_end]

    # 2 Samuel end (after 24:25)
    i_2sam_end = cut_after_reaching(blocks, i_2sam_start, target_ch=24, target_v="25") if i_2sam_start < len(blocks) else len(blocks)

    # 1 Kings start (next ^1:1^ after i_2sam_end)
    i_1k_start = find_next_book_start(blocks, i_2sam_end) if i_2sam_end < len(blocks) else len(blocks)

    between_2_k = blocks[i_2sam_end:i_1k_start]
    two_sam = blocks[i_2sam_start:i_2sam_end] if i_2sam_start < len(blocks) else []

    # 1 Kings partial end (after 2:11)
    i_1k_end = cut_after_reaching(blocks, i_1k_start, target_ch=2, target_v="11") if i_1k_start < len(blocks) else len(blocks)
    one_kings = blocks[i_1k_start:i_1k_end] if i_1k_start < len(blocks) else []

    # Write files
    write_blocks(outdir / "SSD_preface.md", preface)
    write_blocks(outdir / "Prideaux-1SA.md", one_sam)
    write_blocks(outdir / "between_1sam_2sam.md", between_1_2)
    write_blocks(outdir / "Prideaux-2SA.md", two_sam)
    write_blocks(outdir / "between_2sam_1kings.md", between_2_k)
    write_blocks(outdir / "Prideaux-1KI.md", one_kings)
    (outdir / "SSD_footnotes.md").write_text(fndefs.rstrip() + "\n", encoding="utf-8")

    # Report
    print("Wrote:")
    print(" -", outdir / "SSD_preface.md")
    print(" -", outdir / "1sam.md")
    print(" -", outdir / "between_1sam_2sam.md")
    print(" -", outdir / "2sam.md")
    print(" -", outdir / "between_2sam_1kings.md")
    print(" -", outdir / "1kings_1_1_to_2_11.md")
    print(" -", outdir / "SSD_footnotes.md")

    # Sanity warnings
    if not one_sam:
        print("WARNING: 1 Samuel slice is empty.")
    if i_2sam_start == len(blocks):
        print("WARNING: did not detect 2 Samuel start (^1:1^ after 1 Sam end).")
    if i_1k_start == len(blocks):
        print("WARNING: did not detect 1 Kings start (^1:1^ after 2 Sam end).")
    if i_1k_start < len(blocks) and not one_kings:
        print("WARNING: 1 Kings slice is empty (start detected but end may not have been found).")
    if i_1k_start < len(blocks) and i_1k_end == len(blocks):
        # verify whether the last block actually contains the target
        last_block = blocks[-1]
        if not re.search(r"(?<!\[)\^\s*11\s*\^", last_block):
            print("WARNING: did not find 1 Kings 2:11; wrote all remaining blocks to 1kings file.")


if __name__ == "__main__":
    main()
