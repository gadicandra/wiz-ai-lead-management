import pandas as pd, re, collections
df = pd.read_csv('data/leads_seed.csv', dtype=str, keep_default_na=False)

def datefmt(s):
    s=s.strip()
    if s=='': return 'BLANK'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s): return 'ISO date (YYYY-MM-DD)'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', s): return 'ISO datetime Z'
    if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', s): return 'M/D/YYYY (ambiguous)'
    if re.fullmatch(r'\d{1,2}-\d{1,2}-\d{4}', s): return 'D-M-YYYY'
    if re.fullmatch(r'[A-Za-z]{3,9} \d{1,2},? \d{4}', s): return 'Month D, YYYY'
    return 'OTHER: '+s

for c in ['Create Date','Last Modified Date']:
    print(f"=== {c} ===")
    for k,v in collections.Counter(df[c].map(datefmt)).most_common(): print(f"  {k:28s} {v}")
    print()

print("=== M/D/YYYY ambiguity check (is any day>12?) ===")
md = df['Create Date'][df['Create Date'].str.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}')]
parts = md.str.split('/')
a = parts.str[0].astype(int); b = parts.str[1].astype(int)
print("first component max:", a.max(), " second component max:", b.max(), " count:", len(md))
print("rows where first>12:", (a>12).sum(), " second>12:", (b>12).sum())
print("samples:", md.head(8).tolist())

print("\n=== EMAIL ===")
e = df['Email'].str.strip()
print("has uppercase:", (e!=e.str.lower()).sum())
print("has whitespace inside:", e.str.contains(r'\s').sum())
print("invalid-ish (no @ or no dot):", (~e.str.contains(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')).sum())
print("exact dup emails (case-insens):", e.str.lower().duplicated().sum())
print("distinct domains:", e.str.split('@').str[1].str.lower().nunique())
print("plus-addressing (+):", e.str.contains(r'\+').sum())
print("dots in localpart:", e.str.split('@').str[0].str.contains(r'\.').sum())
print("samples:", e.head(5).tolist())

print("\n=== PHONE ===")
p = df['Phone Number'].str.strip()
pat = collections.Counter()
for v in p:
    if v=='': pat['BLANK']+=1
    elif v.startswith('+') and (' ' in v or '-' in v): pat['+CC with separators']+=1
    elif v.startswith('+'): pat['+CC no separators']+=1
    elif v.startswith('00'): pat['00 prefix']+=1
    elif re.fullmatch(r'\d+', v): pat['digits only, no +']+=1
    elif v.startswith('('): pat['(area) style']+=1
    else: pat['OTHER']+=1
for k,v in pat.most_common(): print(f"  {k:26s} {v}")
digits = p.str.replace(r'\D','',regex=True)
print("dup on raw digits:", digits.duplicated().sum())
print("digit-length distribution:", dict(sorted(collections.Counter(digits.str.len()).items())))
print("samples:", p.head(8).tolist())
