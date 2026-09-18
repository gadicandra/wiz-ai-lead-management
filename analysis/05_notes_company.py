import pandas as pd, re, collections
df = pd.read_csv('data/leads_seed.csv', dtype=str, keep_default_na=False)
n = df['Notes'].str.strip()
print("=== Notes: 'possible duplicate' marker ===", n.str.contains('possible duplicate', case=False).sum())
print("=== Notes blank ===", (n=='').sum())
print("\n=== Notes: distinct 'story' sentence heads (first clause) ===")
head = n.str.split(r'(?<=[.!?])\s+').str[0]
for k,v in head.value_counts().head(40).items(): print(f"  {v:5d}  {k}")
print("\n=== Notes: tail clause (outcome) ===")
tail = n.str.replace(' possible duplicate — verify before contacting.','',regex=False).str.rstrip()
tails = tail.str.split(r'(?<=[.!?])\s+').str[-1]
for k,v in tails.value_counts().head(20).items(): print(f"  {v:5d}  {k}")

print("\n=== Company suffix tokens ===")
c = df['Company Name'].str.strip()
sus = c[c.str.contains(r'\band\b.*\b(and|&)\b|and (Co|Inc|Ltd|Pte|Group|Digital|Solutions|Holdings)', case=False, regex=True)]
print("suspicious 'and' companies:", len(sus)); print(sus.drop_duplicates().head(20).tolist())
print("\nsuffix freq:")
suf = c.str.extract(r'((?:&|and)?\s*(?:Pte\.?\s*Ltd\.?|Pte Ltd|Inc\.?|Ltd\.?|LLC|GmbH|SRL|AB|Co\.?|Corp\.?|Group|Holdings|Partners|Ventures|Studio|Labs|Solutions|Digital|Trading|Retail|Freight|Analytics|Robotics|Consulting)\.?)\s*$', flags=re.I)[0]
for k,v in suf.fillna('(none)').value_counts().head(30).items(): print(f"  {repr(k):28s} {v}")
