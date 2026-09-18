import pandas as pd, re, itertools, collections
from rapidfuzz import fuzz
df = pd.read_csv('data/leads_seed.csv', dtype=str, keep_default_na=False)

LEGAL = r'\b(pte\.?\s*ltd\.?|ltd\.?|llc|inc\.?|corp\.?|gmbh|srl|ab|as|bv|nv|sa|plc|co\.?|and co|& co|holdings|group|partners|ventures|studio|labs|solutions|digital|trading|retail|freight|analytics|robotics|consulting|imports|logistics|textiles|biotech|legal|finance|fintech|enterprises|bros)\b'
def norm_comp(s):
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s&]',' ', s)
    s = re.sub(r'\s+&\s+',' and ', s)
    s = re.sub(LEGAL,' ', s)
    s = re.sub(r'\band\b',' ', s)
    return re.sub(r'\s+',' ', s).strip()

def name_of(r):
    f,l,fu = r['First Name'].strip(), r['Last Name'].strip(), r['Full Name'].strip()
    return (f+' '+l).strip() if (f or l) else fu

df['_name'] = df.apply(name_of, axis=1).str.lower()
df['_first'] = df['_name'].str.split().str[0]
df['_last']  = df['_name'].str.split().str[-1]
df['_initial'] = df['_first'].str[0]
df['_digits'] = df['Phone Number'].str.replace(r'\D','',regex=True)
df['_p9'] = df['_digits'].str[-9:]
df['_email'] = df['Email'].str.strip().str.lower()
df['_local'] = df['_email'].str.split('@').str[0]
df['_dom'] = df['_email'].str.split('@').str[1]
df['_droot'] = df['_dom'].str.split('.').str[0]
df['_comp'] = df['Company Name'].map(norm_comp)

# BLOCKING: union of 3 keys
blocks = collections.defaultdict(set)
for i,r in df.iterrows():
    blocks['p:'+r['_p9']].add(i)
    blocks['e:'+r['_email']].add(i)
    blocks['dl:'+r['_droot']+'|'+r['_last']].add(i)
    blocks['di:'+r['_droot']+'|'+r['_initial']+'|'+r['_last']].add(i)

pairs=set()
for k,v in blocks.items():
    if 1 < len(v) <= 50:
        for a,b in itertools.combinations(sorted(v),2): pairs.add((a,b))
print("candidate pairs after blocking:", len(pairs), "vs brute force:", len(df)*(len(df)-1)//2,
      f"= {len(pairs)/(len(df)*(len(df)-1)//2)*100:.3f}%")

def score(a,b):
    ra,rb = df.loc[a], df.loc[b]
    s={}
    s['email_exact'] = ra['_email']==rb['_email']
    s['local_sim'] = fuzz.ratio(ra['_local'], rb['_local'])/100
    s['dom_exact'] = ra['_dom']==rb['_dom']
    s['droot_exact'] = ra['_droot']==rb['_droot']
    s['phone_exact'] = ra['_p9']==rb['_p9'] and ra['_p9']!=''
    s['name_sim'] = fuzz.token_sort_ratio(ra['_name'], rb['_name'])/100
    # initial-aware name: "j. yoon" vs "ji-woo yoon"
    ini = (ra['_last']==rb['_last'] and ra['_initial']==rb['_initial'])
    s['name_ini'] = ini
    s['comp_sim'] = fuzz.token_set_ratio(ra['_comp'], rb['_comp'])/100
    s['country'] = ra['Country/Region'].strip().lower()==rb['Country/Region'].strip().lower()
    s['notes_sim'] = fuzz.ratio(ra['Notes'][:120], rb['Notes'][:120])/100
    conf = (0.30*s['email_exact'] + 0.15*s['local_sim'] + 0.10*s['droot_exact']
            + 0.20*s['phone_exact'] + 0.15*max(s['name_sim'], 0.92 if ini else 0)
            + 0.10*s['comp_sim'])
    return conf, s

rows=[]
for a,b in pairs:
    c,s = score(a,b)
    rows.append((c,a,b,s))
rows.sort(reverse=True, key=lambda x:x[0])
import numpy as np
cs = np.array([r[0] for r in rows])
print("\nconfidence distribution:")
for t in [0.9,0.85,0.8,0.75,0.7,0.6,0.5,0.4]:
    print(f"  >= {t}: {(cs>=t).sum()}")

print("\n=== TOP 12 pairs ===")
cols=['Record ID','First Name','Last Name','Full Name','Company Name','Email','Phone Number','Lead Status','Create Date']
for c,a,b,s in rows[:12]:
    print(f"\nconf={c:.3f} {s}")
    print(df.loc[[a,b],cols].to_string())

print("\n=== BORDERLINE 0.60-0.72 sample (12) ===")
bl = [r for r in rows if 0.60<=r[0]<0.72]
for c,a,b,s in bl[:12]:
    print(f"\nconf={c:.3f} email={s['email_exact']} phone={s['phone_exact']} name={s['name_sim']:.2f} comp={s['comp_sim']:.2f}")
    print(df.loc[[a,b],cols].to_string())

# connected components at >=0.72
import sys
par=list(range(len(df)))
def find(x):
    while par[x]!=x: par[x]=par[par[x]]; x=par[x]
    return x
def uni(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: par[ra]=rb
for c,a,b,s in rows:
    if c>=0.72: uni(a,b)
g=collections.defaultdict(list)
for i in range(len(df)): g[find(i)].append(i)
cl=[v for v in g.values() if len(v)>1]
print(f"\n=== clusters at conf>=0.72: {len(cl)} clusters covering {sum(len(v) for v in cl)} rows; redundant rows = {sum(len(v)-1 for v in cl)}")
print("cluster size dist:", dict(sorted(collections.Counter(len(v) for v in cl).items())))
# marker overlap
marked = set(df.index[df['Notes'].str.contains('possible duplicate', case=False)])
inclust = set(i for v in cl for i in v)
print("rows flagged 'possible duplicate' in Notes:", len(marked), "; of those captured in clusters:", len(marked & inclust))
df.to_pickle('analysis/df.pkl')
import pickle; pickle.dump(rows, open('analysis/pairs.pkl','wb'))
