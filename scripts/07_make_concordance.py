#!/usr/bin/env python3
"""
Build a concordance from build/1_samuel.csv, build/2_samuel.csv, and build/1_kings.csv.

Expected CSV columns:
    ref,text,ch,v

Features:
- strips structural delimiters such as ␞...␞
- removes footnote markers and simple markup
- tokenises words
- strips possessive 's / ’s so words index under their root form
- records one reference per word per verse
- capitalises a word in the index if it only ever appears capitalised
- ignores singletons only if they are not capitalised
- groups consecutive references into ranges using ch and v from the CSV
- prints contextual reference lists:
    first reference includes book (e.g. 1 Sam 9:1)
    later references in same book omit the book (e.g. 14:51, 25:39–40)
    when book changes, book label is shown again
- excludes words occurring in more than a threshold number of verses
- writes LaTeX output for inclusion in back matter

Usage:
    python make_concordance_from_csv.py --max-occurrences 50

Optional:
    python make_concordance_from_csv.py --stopwords stopwords.txt
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Optional, Set, Tuple


DEFAULT_INPUTS = [
    Path("build/1_samuel.csv"),
    Path("build/2_samuel.csv"),
    Path("build/1_kings.csv"),
]

BOOK_LABELS = {
    "1_samuel.csv": "1 Sam",
    "2_samuel.csv": "2 Sam",
    "1_kings.csv": "1 Kgs",
}

BOOK_ORDER = {
    "1 Sam": 1,
    "2 Sam": 2,
    "1 Kgs": 3,
}

STRUCT_DELIM_RE = re.compile(r"␞.*?␞")
BRACKET_FOOTNOTE_RE = re.compile(r"\[\^?[0-9]+\]")
DAGGER_MARK_RE = re.compile(r"[†‡]")
BACKSLASH_MARKER_RE = re.compile(r"\\[A-Za-z0-9*+\-]+")
TAG_RE = re.compile(r"<[^>]+>")
TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")

SPECIAL_FORMS = {
    "lord": "LORD",
}


@dataclass(frozen=True, order=True)
class VerseRef:
    book_order: int
    book_label: str
    chapter: int
    verse_num: int
    verse_suffix: str
    display_ref: str

    def full_display(self) -> str:
        return f"{self.book_label} {self.chapter}:{self.verse_num}{self.verse_suffix}"

    def short_display(self) -> str:
        return f"{self.chapter}:{self.verse_num}{self.verse_suffix}"


@dataclass(frozen=True)
class RefSpan:
    start: VerseRef
    end: VerseRef

    @property
    def book_label(self) -> str:
        return self.start.book_label

    def same_book(self, other: "RefSpan") -> bool:
        return self.book_label == other.book_label


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def load_stopwords(path: Optional[Path]) -> Set[str]:
    if path is None:
        return set()
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip().lower()
        if w and not w.startswith("#"):
            words.add(w)
    return words


def clean_text(text: str) -> str:
    text = STRUCT_DELIM_RE.sub(" ", text)
    text = BRACKET_FOOTNOTE_RE.sub(" ", text)
    text = DAGGER_MARK_RE.sub("", text)
    text = BACKSLASH_MARKER_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^A-Za-z0-9'\-\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalise_word(token: str) -> str:
    token = token.lower()

    # Strip possessive 's or ’s
    if token.endswith("'s"):
        token = token[:-2]
    elif token.endswith("s'"):
        token = token[:-1]

    return token


def infer_book_label(path: Path) -> str:
    name = path.name.lower()
    if name in BOOK_LABELS:
        return BOOK_LABELS[name]
    raise ValueError(f"Cannot infer book label from filename: {path.name}")


def parse_verse_num(v: str) -> Tuple[int, str]:
    m = re.fullmatch(r"(\d+)([a-z]?)", str(v).strip())
    if not m:
        raise ValueError(f"Could not parse verse number: {v!r}")
    return int(m.group(1)), m.group(2)


def iter_csv_rows(paths: Iterable[Path]) -> Iterable[Tuple[str, Dict[str, str]]]:
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        book_label = infer_book_label(path)
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield book_label, row


def should_display_capitalised(
    lemma: str,
    seen_capital: Set[str],
    seen_lower: Set[str],
) -> bool:
    return lemma in seen_capital and lemma not in seen_lower


def display_word(
    lemma: str,
    seen_capital: Set[str],
    seen_lower: Set[str],
) -> str:
    if lemma in SPECIAL_FORMS:
        return SPECIAL_FORMS[lemma]
    if should_display_capitalised(lemma, seen_capital, seen_lower):
        return lemma.capitalize()
    return lemma


def is_consecutive(a: VerseRef, b: VerseRef) -> bool:
    return (
        a.book_order == b.book_order
        and a.chapter == b.chapter
        and a.verse_suffix == b.verse_suffix
        and b.verse_num == a.verse_num + 1
    )


def group_consecutive_refs(refs: List[VerseRef]) -> List[RefSpan]:
    refs = sorted(refs)
    if not refs:
        return []

    spans: List[RefSpan] = []
    start = refs[0]
    end = refs[0]

    for ref in refs[1:]:
        if is_consecutive(end, ref):
            end = ref
        else:
            spans.append(RefSpan(start, end))
            start = ref
            end = ref

    spans.append(RefSpan(start, end))
    return spans


def format_span(span: RefSpan, include_book: bool) -> str:
    s = span.start
    e = span.end

    if s == e:
        if include_book:
            return s.full_display()
        return s.short_display()

    if s.chapter == e.chapter:
        if include_book:
            return f"{s.book_label} {s.chapter}:{s.verse_num}{s.verse_suffix}–{e.verse_num}{e.verse_suffix}"
        return f"{s.chapter}:{s.verse_num}{s.verse_suffix}–{e.verse_num}{e.verse_suffix}"

    if include_book:
        return f"{s.book_label} {s.chapter}:{s.verse_num}{s.verse_suffix}–{e.chapter}:{e.verse_num}{e.verse_suffix}"
    return f"{s.chapter}:{s.verse_num}{s.verse_suffix}–{e.chapter}:{e.verse_num}{e.verse_suffix}"


def format_spans_contextually(spans: List[RefSpan]) -> List[str]:
    """
    First span always includes book.
    Later spans include book only if book differs from previous span.
    """
    if not spans:
        return []

    out: List[str] = []
    previous_book: Optional[str] = None

    for i, span in enumerate(spans):
        include_book = (i == 0) or (span.book_label != previous_book)
        out.append(format_span(span, include_book=include_book))
        previous_book = span.book_label

    return out


def build_concordance(
    paths: List[Path],
    stopwords: Set[str],
) -> Tuple[Dict[str, List[VerseRef]], Set[str], Set[str]]:
    concordance: DefaultDict[str, List[VerseRef]] = defaultdict(list)
    seen_capital: Set[str] = set()
    seen_lower: Set[str] = set()

    for book_label, row in iter_csv_rows(paths):
        ref = (row.get("ref") or "").strip()
        text = row.get("text") or ""
        ch = (row.get("ch") or "").strip()
        v = (row.get("v") or "").strip()

        if not ref or not text or not ch or not v:
            continue

        verse_num, verse_suffix = parse_verse_num(v)

        verse_ref = VerseRef(
            book_order=BOOK_ORDER[book_label],
            book_label=book_label,
            chapter=int(ch),
            verse_num=verse_num,
            verse_suffix=verse_suffix,
            display_ref=ref,
        )

        cleaned = clean_text(text)
        if not cleaned:
            continue

        seen_in_verse: Set[str] = set()

        for m in TOKEN_RE.finditer(cleaned):
            token = m.group(0)
            lemma = normalise_word(token)

            if not lemma or lemma in stopwords:
                continue

            if token[0].isupper():
                seen_capital.add(lemma)
            else:
                seen_lower.add(lemma)

            if lemma not in seen_in_verse:
                concordance[lemma].append(verse_ref)
                seen_in_verse.add(lemma)

    return dict(concordance), seen_capital, seen_lower


def write_latex(
    concordance: Dict[str, List[VerseRef]],
    seen_capital: Set[str],
    seen_lower: Set[str],
    output_path: Path,
    max_occurrences: int,
) -> None:
    items: List[Tuple[str, List[str], str]] = []

    DICT = set()
    with open("/usr/share/dict/words") as f:
        for line in f:
            DICT.add(line.strip())
    force_lower = set()
    with open("data/force_lower.csv") as f:
        for line in f:
            force_lower.add(line.strip())
    
            
    for lemma in sorted(concordance.keys(), key=lambda w: (w.lower(), w)):
        refs = concordance[lemma]
        count = len(refs)

        if max_occurrences != None and count > max_occurrences:
            continue
        if len(lemma) == 1:
            continue

        if lemma in force_lower:
            shown = lemma
        else:
            shown = display_word(lemma, seen_capital, seen_lower)
        spans = group_consecutive_refs(refs)
        grouped_refs = format_spans_contextually(spans)

        if shown != lemma:
            if lemma in DICT:
                print(f"Warning: {lemma} appears only capitalised but may be a normal English word")
        items.append((shown, grouped_refs, lemma))

    with output_path.open("w", encoding="utf-8") as f:
        f.write("% Auto-generated concordance\n")
        f.write("% Generated from CSV verse files\n\n")
        if max_occurrences != None:
            f.write(f"This is not an exhaustive concordance. Words occuring more than {max_occurrences} times are excluded, as are prepositions, conjunctions, etc. that are of little value here.\\par\\vspace{{1cm}}")
        else:
            f.write(f"This is not an exhaustive concordance. Words such as prepositions, conjunctions, articles, etc. that are of little value here are excluded.\\par\\vspace{{1cm}}")
        f.write("\\begin{multicols}{2}\n")
        f.write("\\footnotesize\n")
        f.write("\\setlength{\\parindent}{0pt}\n")
        f.write("\\setlength{\\parskip}{0.2\\baselineskip}\n")


        current_initial = None

        for shown, grouped_refs, lemma in items:
            initial = shown[0].upper()

            if initial != current_initial:
                if current_initial is not None:
                    f.write("\n\\vspace{1em}\n")
                f.write(f"\\textbf{{\large {latex_escape(initial)}}}\\par\n")
                current_initial = initial

            refs_text = ", ".join(latex_escape(r) for r in grouped_refs)
            raw_count = len(concordance[lemma])

            f.write(
                f"\\concitem{{{latex_escape(shown)}}}{{({raw_count}): {refs_text}}}\n"
            )

        f.write("\\end{multicols}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build concordance from Samuel CSV files.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        type=Path,
        default=DEFAULT_INPUTS,
        help="Input CSV files. Defaults to build/1_samuel.csv build/2_samuel.csv build/1_kings.csv",
    )
    parser.add_argument(
        "--max-occurrences",
        type=int,
        default=None,
        help="Exclude words occurring in more than this many verses.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tex/concordance.tex"),
        help="Output LaTeX file. Default: tex/concordance.tex",
    )
    parser.add_argument(
        "--stopwords",
        type=Path,
        default="data/stoplist.csv",
        help="Optional file containing stopwords, one per line. Default: data/stoplist.csv",
    )

    args = parser.parse_args()

    stopwords = load_stopwords(args.stopwords)
    concordance, seen_capital, seen_lower = build_concordance(list(args.inputs), stopwords)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_latex(
        concordance=concordance,
        seen_capital=seen_capital,
        seen_lower=seen_lower,
        output_path=args.output,
        max_occurrences=args.max_occurrences,
    )

    print(f"Wrote concordance to {args.output}")


if __name__ == "__main__":
    main()
