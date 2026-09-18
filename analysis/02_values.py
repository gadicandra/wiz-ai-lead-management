import pandas as pd, re, collections
df = pd.read_csv('data/leads_seed.csv', dtype=str, keep_default_na=False)
S = lambda c: df[c]

print("=== Record ID duplicates ===", df['Record ID'].duplicated().sum())
print("Record ID sample:", df['Record ID'].head(3).tolist(), "len range:", df['Record ID'].str.len().unique())

print("\n=== Name field pattern ===")
has_fl = (df['First Name'].str.strip()!='') | (df['Last Name'].str.strip()!='')
has_fn = df['Full Name'].str.strip()!=''
print("first/last only:", (has_fl & ~has_fn).sum())
print("fullname only  :", (~has_fl & has_fn).sum())
print("both           :", (has_fl & has_fn).sum())
print("neither        :", (~has_fl & ~has_fn).sum())
print("First only (no last):", ((df['First Name'].str.strip()!='') & (df['Last Name'].str.strip()=='')).sum())
print("Last only (no first):", ((df['First Name'].str.strip()=='') & (df['Last Name'].str.strip()!='')).sum())
print("\nFull Name samples:"); print(df.loc[has_fn,'Full Name'].head(15).tolist())

for c in ['Lead Status','Lifecycle Stage','Original Source','Contact Owner','Job Title']:
    print(f"\n=== {c} value_counts (repr) ===")
    vc = df[c].value_counts(dropna=False)
    for k,v in vc.items(): print(f"  {repr(k):45s} {v}")

print("\n=== Country/Region distinct ===")
for k,v in df['Country/Region'].value_counts().items(): print(f"  {repr(k):28s} {v}")
