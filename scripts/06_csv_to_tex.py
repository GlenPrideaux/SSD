import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def inp(job: str):
    return ROOT / "build" / f"{job}_parallel.csv"
def outfile(job: str):
    return ROOT / "tex" / f"{job}_parallel.tex"

FOOTNOTE_DELIM = "\u241EFOOTNOTE\u241E"

import re

HEBREW_RE = re.compile(r'[\u0590-\u05FF]+')
ADD_OPEN = "\u241EADDOPEN\u241E"
ADD_CLOSE = "\u241EADDCLOSE\u241E"
SC_OPEN = "\u241ESCOPEN\u241E"
SC_CLOSE = "\u241ESCCLOSE\u241E"
SUP_OPEN = "\u241ESUPOPEN\u241E"
SUP_CLOSE = "\u241ESUPCLOSE\u241E"

def wrap_hebrew(text):
    return HEBREW_RE.sub(lambda m: r'\texthebrew{' + m.group(0) + '}', text)

def inject_latex_footnotes(escaped_text: str) -> str:
    # escaped_text is already LaTeX-escaped
    parts = escaped_text.split(FOOTNOTE_DELIM)
    if len(parts) == 1:
        return escaped_text

    out = [parts[0]]
    # parts alternates: text, footnote, text, footnote, ...
    for i in range(1, len(parts), 2):
        fn = parts[i].strip()
        if fn:
            out.append(r"\footnote{" + fn + "}")
        if i + 1 < len(parts):
            out.append(parts[i + 1])
    return "".join(out)

def esc(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\\", r"\textbackslash{}")
    s = s.replace("&", r"\&").replace("%", r"\%").replace("$", r"\$")
    s = s.replace("#", r"\#").replace("_", r"\_").replace("{", r"\{").replace("}", r"\}")
    s = s.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")
    return s

STRUCT_DELIM = "\u241E"
STYLE_HDG = f"{STRUCT_DELIM}STYLE:HDG{STRUCT_DELIM}"
STYLE_PARA = f"{STRUCT_DELIM}STYLE:PARA{STRUCT_DELIM}"


def render_markers(escaped_text: str) -> str:
    return (escaped_text
            .replace(ADD_OPEN, r"\textit{")
            .replace(ADD_CLOSE, "}")
            .replace(SC_OPEN, r"\textsc{")
            .replace(SC_CLOSE, "}")
            .replace(SUP_OPEN, r"\textsuperscript{")
            .replace(SUP_CLOSE, "}")
           )

def texify_double_quotes(s: str) -> str:
    out = []
    prev = ""  # previous character (including space/punct)
    for ch in s:
        if ch == '"':
#            print(f"prev is [{prev}] in {s}")
            if prev == "" or prev.isspace() or prev in "([{\n—–-"+STRUCT_DELIM:
                out.append("``{}")
            else:
                out.append("''{}")
            # don't update prev to '"'
            continue
        if ch == "'":
#            print(f"prev is [{prev}] in {s}")
            if prev == "" or prev.isspace() or prev in "([{\n—–-"+STRUCT_DELIM:
                out.append("`{}")
            else:
                out.append("'{}")
            # don't update prev to '"'
            continue
        out.append(ch)
        prev = ch
    return "".join(out)

def render_structured_to_latex(escaped_text: str) -> str:
    if STRUCT_DELIM not in escaped_text:
        return escaped_text

    def render_heading_verse(text: str) -> str:
        # Space above + bold, but still stays in the column (not spanning both)
        return r"\DescriptiveHeading{" + text.strip() + r"}"

    parts = escaped_text.split(STRUCT_DELIM)
    out = []
    i = 0
    pending_heading = False
    PILCROW = r"{\small\textparagraph\thinspace}"
    
    while i < len(parts):
        token = parts[i]

        # Our style marker is a standalone token after splitting
        if token == "STYLE:HDG":
            pending_heading = True
            i += 1
            continue

        if token.startswith("Q:"):
            indent = int(token[2:]) if token[2:].isdigit() else 1
            if i + 1 < len(parts):
                line = parts[i + 1].strip()
                # If you ever tag a poem line as heading, you can decide what to do here.
                out.append(rf"\poemline{{{indent}}}{{{line}}}")
                i += 2
            else:
                i += 1

        elif token == "P":
            if i+2 < len(parts) and parts[i+2] == "STYLE:PARA":
                i += 2
                if len(out):
                    out.append(r"\par" + PILCROW)
                else:
                    out.append(PILCROW)
                
            if i + 1 < len(parts):
                seg = parts[i + 1].strip()

                # Sometimes seg is empty because the verse starts with ␞STYLE:HDG␞
                # In that case, just skip the empty payload.
                if seg:
                    if pending_heading:
                        out.append(render_heading_verse(seg) + " ")
                        pending_heading = False
                    else:
                        out.append(seg + " ")
                i += 2
            else:
                i += 1

        else:
            # Fallback: plain text token
            if token.strip():
                if pending_heading:
                    out.append(render_heading_verse(token) + " ")
                    pending_heading = False
                else:
                    out.append(token.strip() + " ")

            i += 1

    rendered = "".join(out).strip()

    if r"\poemline" in rendered:
        rendered = r"{\raggedright " + rendered + "}"
    return rendered


def parse_ref(ref: str) -> tuple[int, int]:
    # ref like "12:7" (ignore any suffixes if you later add them)
    ch_s, v_s = ref.split(":", 1)
    # if you ever use 7a/7* etc, keep only leading digits for verse
    v_digits = "".join(c for c in v_s if c.isdigit())
    return int(ch_s), int(v_digits) if v_digits else 0

jobs = [
    ("1_samuel","Samuel, Saul and David, First part called First Samuel"),
    ("2_samuel", "Samuel, Saul and David, Second part called Second Samuel"),
    ("1_kings", "Samuel, Saul and David, Third part called First Kings"),
    ]

def main():
    for job, name in jobs:
        rows = []
        with inp(job).open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        outfile(job).parent.mkdir(parents=True, exist_ok=True)
        with outfile(job).open("w", encoding="utf-8") as out:
            out.write(fr"""
\vspace{{10pt}}\Needspace{{10\baselineskip}}\begin{{center}}\small The word concerning\vspace{{-10pt}}
\section*{{{name}}}
\end{{center}}
\nobreak\nointerlineskip\penalty10000
""")

            current_ch = None
            for r in rows:
                ch, _ = parse_ref(r["lxx_ref"])
                if ch != current_ch:
                    if current_ch is not None:
                        out.write("\\end{paracol}\par\n")
                    out.write(f"\\ChapterHeading{{{ch}}}\n")
                    out.write("\\begin{paracol}{2}\n")
                    out.write(r"\columnAHead\switchcolumn[1]\columnBHead\switchcolumn[0]*")
                    current_ch = ch

                lxx_ref = esc(r["lxx_ref"])
                mt_ref  = esc(r["mt_ref"])
                lxx_txt=r["lxx_text"]
                if lxx_txt.count('"') % 2 == 1:
                    print(f"WARNING: Check for unbalanced quotes in {lxx_ref}")
                lxx_txt = render_structured_to_latex(inject_latex_footnotes(render_markers(wrap_hebrew(texify_double_quotes(esc(lxx_txt))))))
                mt_txt  = render_structured_to_latex(inject_latex_footnotes(render_markers(wrap_hebrew(esc(r["mt_text"])))))
                out.write(f"\\VersePair{{{lxx_ref}}}{{{lxx_txt}}}{{{mt_ref}}}{{{mt_txt}}}\n")

            out.write(r"""\end{paracol}""")
        print(f"Wrote {outfile(job)}")

if __name__ == "__main__":
    main()
