import csv, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def lxx(job :str):
    return ROOT / "build" / "json" / f"prideaux_{job}.json"
def out(name: str):
    return ROOT / "build" / f"{name}.csv" 

RANGE_RE = re.compile(r"^(\d+:\d+)\s*-\s*(\d+:\d+)$")

import re

REF_RE = re.compile(r'^(\d+):(\d+)([a-z]?)$', re.IGNORECASE)

def parse_ref(ref: str) -> tuple[int, int, str]:
    """
    Parses '24:40a' -> (24, 40, 'a')
           '24:40'  -> (24, 40, '')
    """
    ref = ref.strip()
    m = REF_RE.match(ref)
    if not m:
        raise ValueError(f"Bad ref format: {ref!r}")
    ch = int(m.group(1))
    v  = int(m.group(2))
    suf = (m.group(3) or "").lower()
    return ch, v, suf

def ref_sort_key(ref: str) -> tuple[int, int, int]:
    """
    Sort order: 40 < 40a < 40b < 41
    """
    ch, v, suf = parse_ref(ref)
    suf_ord = 0 if suf == "" else (ord(suf) - ord("a") + 1)
    return (ch, v, suf_ord)

def ref_to_tuple(ref: str):
    ch, v, suf = parse_ref(ref)
    suf_ord = 0 if suf == "" else (ord(suf) - ord("a") + 1)
    return (ch, v, suf_ord)

def expand_range(start: str, end: str):
    sc, sv, ss = parse_ref(start)
    ec, ev, es = parse_ref(end)
    if ss or es:
        raise ValueError(f"Ranges with suffixes not supported: {start}-{end}")
    if sc != ec:
        raise ValueError(f"Range crosses chapters: {start}-{end}")
    return [f"{sc}:{vv}" for vv in range(sv, ev + 1)]

def get_mt_text(mt_dict, mt_ref: str) -> str:
    if not mt_ref.strip():
        return ""
    m = RANGE_RE.match(mt_ref.strip())
    if m:
        start, end = m.group(1), m.group(2)
        parts = []
        for r in expand_range(start, end):
            t = mt_dict.get(r, "")
            if t:
                parts.append(t)
        return " ".join(parts).strip()
    return mt_dict.get(mt_ref.strip(), "")

def sort_key(ref: str):
    return ref_to_tuple(ref)

STRUCT_DELIM = "\u241E"
STYLE_PARA = f"{STRUCT_DELIM}STYLE:PARA{STRUCT_DELIM}"

jobs = [
    ("1_samuel", "1SA"),
    ("2_samuel", "2SA"),
    ("1_kings", "1KI"),
    ]

def main():
    for name, job in jobs:
        lxx_dict = json.loads(lxx(job).read_text(encoding="utf-8"))

        rows = []
        for lxx_ref, lxx_txt in lxx_dict.items():
            lxx_ref = lxx_ref.strip()
            ch, v, _ = parse_ref(lxx_ref)
            par = 1 if STYLE_PARA in lxx_txt else 0
            rows.append({
                "ref": lxx_ref,
                "ch": ch,
                "v": v,
                "par": par,
                "text": lxx_txt,
                })

            # Ensure LXX order
            rows.sort(key=lambda x: ref_sort_key(x["ref"]))

            out(name).parent.mkdir(parents=True, exist_ok=True)
            with out(name).open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["ref","ch","v","par","text"])
                w.writeheader()
                w.writerows(rows)

        print(f"Wrote {out(name)} ({len(rows)} rows)")

if __name__ == "__main__":
    main()
