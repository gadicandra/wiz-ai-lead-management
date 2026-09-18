import pandas as pd, re, collections
df = pd.read_csv('data/leads_seed.csv', dtype=str, keep_default_na=False)
ls = df['Lead Score'].str.strip()
nz = ls[ls!='']
print("Lead Score present:", len(nz), "numeric:", nz.str.fullmatch(r'\d+').sum(), "min/max:", nz.astype(float).min(), nz.astype(float).max())

# Create vs Modified consistency
def parse(s):
    s=s.strip()
    if not s: return pd.NaT
    for f in ('%Y-%m-%d','%Y-%m-%dT%H:%M:%SZ','%m/%d/%Y'):
        try: return pd.to_datetime(s, format=f)
        except: pass
    return pd.NaT
cd = df['Create Date'].map(parse); md = df['Last Modified Date'].map(parse)
print("\nCreate unparsed:", cd.isna().sum(), "Modified unparsed (incl blank):", md.isna().sum())
both = cd.notna() & md.notna()
print("modified < created:", (md[both] < cd[both]).sum(), "of", both.sum())
print("create range:", cd.min(), "->", cd.max())
print("future creates (> today 2026-09-17):", (cd > pd.Timestamp('2026-09-17')).sum())

# email domain vs company consistency
dom = df['Email'].str.split('@').str[1].str.split('.').str[0].str.lower()
comp = df['Company Name'].str.lower().str.replace(r'[^a-z0-9]','',regex=True)
print("\nemail-domain-root is prefix of company-slug:", sum(c.startswith(d) for c,d in zip(comp,dom)), "/", len(df))

# per-email-domain block sizes
fulldom = df['Email'].str.split('@').str[1].str.lower()
bs = fulldom.value_counts()
print("\nemail domain blocks: n=",len(bs)," max=",bs.max()," >1:",(bs>1).sum()," pairs if blocked by domain:", int((bs*(bs-1)//2).sum()))
# domain root (company) blocks
rootdom = fulldom.str.split('.').str[0]
bs2 = rootdom.value_counts()
print("domain-root blocks: n=",len(bs2)," max=",bs2.max()," pairs:", int((bs2*(bs2-1)//2).sum()))
print("full pairwise would be:", len(df)*(len(df)-1)//2)

# same normalized name + same company root => how many?
def nm(r):
    f,l,fu = r['First Name'].strip(), r['Last Name'].strip(), r['Full Name'].strip()
    return (f+' '+l).strip() if (f or l) else fu
names = df.apply(nm, axis=1).str.lower()
key = names + '|' + rootdom
k = key.value_counts()
print("\nexact (name|domainroot) collisions:", (k>1).sum(), "rows:", int(k[k>1].sum()))
