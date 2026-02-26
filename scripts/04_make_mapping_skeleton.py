import json
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_JSON = ROOT / "build" / "json" 
OUT = ROOT / "data" 

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

def sort_key(ref: str):
    return ref_sort_key(ref)

def sanity(ref: str, prev_ref: str):
    if prev_ref == '':
        return
    prev_ch, prev_v, prev_suf = sort_key(prev_ref)
    ch, v, suf = sort_key(ref)
    if not (ch == prev_ch + 1 and v == 1 or ch == prev_ch and v == prev_v + 1 or ch == prev_ch and v == prev_v and suf == prev_suf + 1):
        print(f"WARNING: {ref} follows {prev_ref} out of sequence")
    
jobs = [
    "1SA",
    "2SA",
    "1KI",
    ]

def main():
    for job in jobs:
        json_path = WEB_JSON / f"web_{job}.json"
        out_path = OUT / f"mapping_{job}.csv"
        verses = json.loads(json_path.read_text(encoding="utf-8"))
        refs = sorted(verses.keys(), key=sort_key)
        rowcount = 0
        
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            prev_key = ""
            w = csv.writer(f)
            w.writerow(["lxx_ref", "mt_ref"])
            for r in refs:
                sanity(r, prev_key)
                prev_key = r
                w.writerow([r, r])  # identity placeholder
                rowcount += 1
                if job == "1KI" and rowcount == 64:
                    break
            print(f"Wrote skeleton mapping with {rowcount} rows -> {out_path}")

if __name__ == "__main__":
    main()
