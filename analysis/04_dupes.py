import pandas as pd, re, collections
df = pd.read_csv('data/leads_seed.csv', dtype=str, keep_default_na=False)

e = df['Email'].str.strip().str.lower()
dupe_emails = e[e.duplicated(keep=False)].value_counts()
print("=== emails appearing >1 ===", len(dupe_emails), "distinct;", dupe_emails.sum(), "rows")
print(dupe_emails.head(10))
sample = dupe_emails.index[0]
cols=['Record ID','First Name','Last Name','Full Name','Company Name','Email','Phone Number','Country/Region','Lead Status','Create Date','Notes']
print("\n--- example email group ---")
print(df[e==sample][cols].to_string())

d = df['Phone Number'].str.replace(r'\D','',regex=True)
dupd = d[d.duplicated(keep=False)].value_counts()
print("\n=== phone digits appearing >1 ===", len(dupd),"distinct;",dupd.sum(),"rows")
print(dupd.head(8))
print("\n--- example phone group ---")
print(df[d==dupd.index[0]][cols].to_string())

# last9 digits blocking
l9 = d.str[-9:]
dl9 = l9[l9.duplicated(keep=False)].value_counts()
print("\n=== last-9-digit blocks >1 ===", len(dl9), "distinct;", dl9.sum(), "rows; max block:", dl9.max())

print("\n=== Full Name rows sample (all 107) ===")
print(df[df['Full Name'].str.strip()!=''][cols].head(20).to_string())
