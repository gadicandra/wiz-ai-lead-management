import pandas as pd, pickle, collections, re, itertools
from rapidfuzz import fuzz, process
df = pd.read_pickle('analysis/df.pkl')
rows = pickle.load(open('analysis/rows3.pkl','rb'))

# --- RECALL CHECK: any 'possible duplicate'-marked row NOT in a cluster? ---
par=list(range(len(df)))
def find(x):
    while par[x]!=x: par[x]=par[par[x]]; x=par[x]
    return x
for c,a,b,f in rows:
    if c>=0.90:
        ra,rb=find(a),find(b)
        if ra!=rb: par[ra]=rb
g=collections.defaultdict(list)
for i in range(len(df)): g[find(i)].append(i)
clusters=[v for v in g.values() if len(v)>1]
inc={i for v in clusters for i in v}
marked=set(df.index[df['Notes'].str.contains('possible duplicate',case=False)])
print("marked not captured:", len(marked-inc))

# --- RECALL CHECK 2: brute-force name+company over ALL rows to find dupes blocking missed ---
key = df['_name']+'|'+df['_droot']
k = key.value_counts(); multi = set(k[k>1].index)
missed=[]
for kk in multi:
    idx = list(df.index[key==kk])
    for a,b in itertools.combinations(idx,2):
        if find(a)!=find(b): missed.append((a,b))
print("same name+domainroot but NOT clustered:", len(missed))
for a,b in missed[:6]:
    print(df.loc[[a,b],['Record ID','First Name','Last Name','Full Name','Company Name','Email','Phone Number','Country/Region','Create Date']].to_string()); print()

# --- CONFLICT ANALYSIS within clusters ---
def parse(s):
    s=s.strip()
    for f in ('%Y-%m-%d','%Y-%m-%dT%H:%M:%SZ','%m/%d/%Y'):
        try: return pd.to_datetime(s,format=f)
        except: pass
    return pd.NaT
df['_cdp']=df['Create Date'].map(parse); df['_mdp']=df['Last Modified Date'].map(parse)
def canon_status(s): return re.sub(r'\s+',' ',s.strip()).title()

conf=collections.Counter()
for v in clusters:
    sub=df.loc[v]
    if sub['Email'].str.lower().nunique()>1: conf['email differs']+=1
    if sub['Lead Status'].map(canon_status).nunique()>1: conf['status differs (after normalize)']+=1
    if sub['Company Name'].nunique()>1: conf['company string differs']+=1
    if sub['_comp'].nunique()>1: conf['company differs after suffix-strip']+=1
    if sub['Country/Region'].str.lower().str.strip().nunique()>1: conf['country differs']+=1
    if sub['Contact Owner'].str.strip().nunique()>1: conf['owner differs']+=1
    if sub['_cdp'].nunique()>1: conf['create date differs (real)']+=1
    if sub['Job Title'].replace('',pd.NA).dropna().nunique()>1: conf['job title differs']+=1
    jt = (sub['Job Title'].str.strip()!='').sum()
    if 0<jt<len(v): conf['job title only in some (mergeable gain)']+=1
    ls = (sub['Lead Score'].str.strip()!='').sum()
    if 0<ls<len(v): conf['lead score only in some (mergeable gain)']+=1
    if sub['Lead Score'].replace('',pd.NA).dropna().nunique()>1: conf['lead score differs']+=1
    if sub['Lifecycle Stage'].replace('',pd.NA).dropna().nunique()>1: conf['lifecycle differs']+=1
    lc=(sub['Lifecycle Stage'].str.strip()!='').sum()
    if 0<lc<len(v): conf['lifecycle only in some (mergeable gain)']+=1
    os_=(sub['Original Source'].str.strip()!='').sum()
    if 0<os_<len(v): conf['original source only in some (mergeable gain)']+=1
    if sub['Original Source'].replace('',pd.NA).dropna().nunique()>1: conf['original source differs']+=1
print(f"\n=== CONFLICTS across {len(clusters)} clusters ===")
for k2,v2 in conf.most_common(): print(f"  {k2:45s} {v2}  ({v2/len(clusters)*100:.0f}%)")

print("\n=== example: cluster with conflicting Original Source / owner ===")
shown=0
for v in clusters:
    sub=df.loc[v]
    if sub['Original Source'].replace('',pd.NA).dropna().nunique()>1 or sub['Contact Owner'].str.strip().nunique()>1:
        print(sub[['Record ID','First Name','Last Name','Company Name','Email','Lead Status','Lifecycle Stage','Original Source','Contact Owner','Lead Score','Job Title','Create Date']].to_string()); print()
        shown+=1
        if shown>=4: break
pickle.dump(clusters, open('analysis/clusters.pkl','wb'))
df.to_pickle('analysis/df.pkl')
