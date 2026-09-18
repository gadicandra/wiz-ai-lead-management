import pandas as pd, json, re, collections
pd.set_option('display.width', 200)
df = pd.read_csv('data/leads_seed.csv', dtype=str, keep_default_na=False)
print("SHAPE:", df.shape)
print("\n=== COLUMN FILL RATE ===")
for c in df.columns:
    nonblank = (df[c].str.strip() != '').sum()
    print(f"{c:35s} {nonblank:5d}/{len(df)}  ({nonblank/len(df)*100:5.1f}%)  uniq={df[c].str.strip().replace('',pd.NA).nunique()}")
