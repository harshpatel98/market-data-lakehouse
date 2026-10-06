"""Generate the synthetic datasets (deterministic, seed 42).

Creates:
  data/prices_clean.csv             clean base data (used by the gold tests)
  data/raw/prices_part{1,2,3}.csv   dirty landing files with seeded defects (bronze input)
  data/expected_counts.json         row counts and late corrections the pipeline tests check

All data is SYNTHETIC. It is not real market data.
"""
import csv
import json
import os
import random
from datetime import date, timedelta

random.seed(42)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
os.makedirs(RAW, exist_ok=True)

SYMBOLS = {"QQQ": (400.0, 0.012, 40_000_000), "SPY": (480.0, 0.010, 70_000_000), "BTC": (42000.0, 0.03, 25_000)}
START, END = date(2024, 1, 1), date(2025, 6, 30)
FIELDS = ["symbol", "date", "open", "high", "low", "close", "volume"]

days = [START + timedelta(d) for d in range((END - START).days + 1)
        if (START + timedelta(d)).weekday() < 5]

# ---------- clean base ----------
clean = []
for sym, (start_px, vol, base_vol) in SYMBOLS.items():
    prev = start_px
    for d in days:
        o = prev * (1 + random.gauss(0, 0.003))
        c = o * (1 + random.gauss(0.0004, vol))
        h = max(o, c) * (1 + abs(random.gauss(0, 0.004)))
        l = min(o, c) * (1 - abs(random.gauss(0, 0.004)))
        clean.append({"symbol": sym, "date": d.isoformat(), "open": round(o, 2), "high": round(h, 2),
                      "low": round(l, 2), "close": round(c, 2),
                      "volume": int(random.uniform(0.5, 1.5) * base_vol)})
        prev = c
clean.sort(key=lambda r: (r["date"], r["symbol"]))

with open(os.path.join(DATA, "prices_clean.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(clean)

# ---------- split into three landing files ----------
n = len(days)
cuts = [days[0], days[n // 3], days[2 * n // 3]]
def part_of(r):
    d = date.fromisoformat(r["date"])
    return 0 if d < cuts[1] else (1 if d < cuts[2] else 2)

parts = [[], [], []]
for r in clean:
    parts[part_of(r)].append({k: str(v) for k, v in r.items()})

key = {}

# gap: remove 3 consecutive weekdays of BTC in part 2
btc_p2 = [i for i, r in enumerate(parts[1]) if r["symbol"] == "BTC"]
start_i = btc_p2[40]
gap_rows = [parts[1][i] for i in btc_p2[40:43]]
key["missing_days"] = [{"symbol": "BTC", "date": r["date"]} for r in gap_rows]
gap_ids = {id(r) for r in gap_rows}
parts[1] = [r for r in parts[1] if id(r) not in gap_ids]
used = set()
def pick(count, pools=(0, 1, 2)):
    cands = [(p, i) for p in pools for i in range(len(parts[p])) if (p, i) not in used]
    chosen = random.sample(cands, count)
    used.update(chosen)
    return chosen

# 1) late corrections: a later file restates an earlier row with a new close
corrections = []
for (p, i) in pick(10, pools=(0, 1)):
    r = parts[p][i]
    new_close = round(float(r["close"]) * (1 + random.choice([-1, 1]) * random.uniform(0.01, 0.03)), 2)
    fix = dict(r)
    fix["close"] = str(new_close)
    parts[2].append(fix)
    used.add((2, len(parts[2]) - 1))
    corrections.append({"symbol": r["symbol"], "trade_date": r["date"], "close": new_close})
key["late_corrections"] = corrections

# 2) exact duplicates (appended to same file)
dups = []
for (p, i) in pick(15):
    r = dict(parts[p][i])
    parts[p].append(r)
    used.add((p, len(parts[p]) - 1))
    dups.append({"symbol": r["symbol"], "date": r["date"], "file": f"prices_part{p+1}.csv"})
key["exact_duplicates"] = dups

# 3) non-positive close
bad_close = []
for (p, i) in pick(5):
    parts[p][i]["close"] = random.choice(["0", "-12.5", "0.00", "-1"])
    bad_close.append({"symbol": parts[p][i]["symbol"], "date": parts[p][i]["date"]})
key["non_positive_close"] = bad_close

# 4) null dates
null_dates = []
for (p, i) in pick(4):
    null_dates.append({"symbol": parts[p][i]["symbol"], "was": parts[p][i]["date"]})
    parts[p][i]["date"] = ""
key["null_date"] = null_dates

# 5) high < low (swapped)
swapped = []
for (p, i) in pick(5):
    r = parts[p][i]
    r["high"], r["low"] = r["low"], r["high"]
    swapped.append({"symbol": r["symbol"], "date": r["date"]})
key["high_below_low"] = swapped

# 6) US-style dates (valid after parsing)
us_dates = []
for (p, i) in pick(8):
    r = parts[p][i]
    d = date.fromisoformat(r["date"])
    r["date"] = d.strftime("%m/%d/%Y")
    us_dates.append({"symbol": r["symbol"], "as": r["date"]})
key["us_date_format"] = us_dates

# 7) price strings with $ and thousands separators (valid after parsing)
dollar = []
for (p, i) in pick(6):
    r = parts[p][i]
    r["close"] = f"${float(r['close']):,.2f}"
    dollar.append({"symbol": r["symbol"], "date": r["date"], "as": r["close"]})
key["dollar_strings"] = dollar

# 8) messy symbols (valid after standardizing)
messy = []
for (p, i) in pick(7):
    r = parts[p][i]
    r["symbol"] = random.choice([r["symbol"].lower(), f" {r['symbol']} ", r["symbol"].title()])
    messy.append({"as": r["symbol"], "date": r["date"]})
key["messy_symbols"] = messy

for idx, rows in enumerate(parts, start=1):
    with open(os.path.join(RAW, f"prices_part{idx}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

raw_rows = sum(len(p) for p in parts)
base_rows = len(clean)
missing = 3
rejected = len(bad_close) + len(null_dates) + len(swapped)
expected = {
    "raw_rows": raw_rows,
    "expected_silver_rows": base_rows - missing - rejected,
    "expected_quarantine_rows": rejected,
    "late_corrections": corrections,
}
with open(os.path.join(DATA, "expected_counts.json"), "w") as f:
    json.dump(expected, f, indent=2)
# `key` records every seeded defect while generating; it is not written to disk.
print("raw rows:", raw_rows, "| expected silver:", expected["expected_silver_rows"],
      "| expected quarantine:", rejected)
