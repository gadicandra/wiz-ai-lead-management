import pandas as pd, re, itertools, collections, pickle, numpy as np, json
from rapidfuzz import fuzz
df = pd.read_pickle('analysis/df.pkl')
marked = df['Notes'].str.contains('possible duplicate', case=False)

blocks = collections.defaultdict(set)
for i,r in df.iterrows():
    blocks['p:'+r['_p9']].add(i); blocks['e:'+r['_email']].add(i)
    blocks['l:'+r['_local']].add(i); blocks['dl:'+r['_droot']+'|'+r['_last']].add(i)
pairs=set()
for k,v in blocks.items():
    if 1<len(v)<=50:
        for a,b in itertools.combinations(sorted(v),2): pairs.add((a,b))

def anchor_and_conf(a,b):
    ra,rb=df.loc[a],df.loc[b]
    la,lb=ra['_local'],rb['_local']
    ca,cb=re.sub(r'[.\-_]','',la),re.sub(r'[.\-_]','',lb)
    same_dom = ra['_dom']==rb['_dom']
    email_exact = ra['_email']==rb['_email']
    local_np = (ca==cb) and same_dom
    phone = ra['_p9']==rb['_p9'] and ra['_p9']!=''
    local_sim = fuzz.ratio(la,lb)/100
    soft_email = same_dom and local_sim>=0.62
    anchors=[]
    if email_exact: anchors.append(('email_exact',1.00))
    elif local_np:  anchors.append(('email_normalized',0.97))
    if phone:       anchors.append(('phone_exact',0.95))
    if soft_email and not (email_exact or local_np): anchors.append(('email_same_domain_similar_local',0.70))
    ident = max([w for _,w in anchors], default=0.0)
    n_anchor = len([a for a in anchors if a[1]>=0.95])

    name_sim = fuzz.token_sort_ratio(ra['_name'],rb['_name'])/100
    ini = (ra['_last']==rb['_last'] and ra['_initial']==rb['_initial'] and
           (len(ra['_first'].rstrip('.'))<=2 or len(rb['_first'].rstrip('.'))<=2))
    person = max(name_sim, 0.95 if ini else 0.0)
    org = 1.0 if ra['_droot']==rb['_droot'] else fuzz.token_set_ratio(ra['_comp'],rb['_comp'])/100
    ctry = ra['Country/Region'].strip().lower()==rb['Country/Region'].strip().lower()

    c = 0.45*ident + 0.33*person + 0.12*org + 0.05*ctry + 0.05*(1 if n_anchor>=2 else 0)
    # HARD RULE: tanpa identity anchor kuat, nama+company tidak pernah cukup => cap
    if ident < 0.95: c = min(c, 0.45)
    # penalti: anchor kuat tapi orangnya beda jauh
    if ident>=0.95 and person<0.55: c = min(c, 0.55)
    ev = dict(email_exact=email_exact, email_normalized=local_np, phone_exact=phone,
              same_domain=same_dom, local_sim=round(local_sim,2), name_sim=round(name_sim,2),
              name_initial_match=ini, org_sim=round(org,2), same_country=bool(ctry), n_strong_anchor=n_anchor)
    return c, ev

rows=sorted(((*anchor_and_conf(a,b)[:1], a, b, anchor_and_conf(a,b)[1]) for a,b in pairs), reverse=True, key=lambda x:x[0])
cs=np.array([r[0] for r in rows])
print("candidate pairs:", len(rows))
print("buckets:")
for lo,hi in [(0.90,1.01),(0.80,0.90),(0.70,0.80),(0.60,0.70),(0.45,0.60),(0.0,0.45)]:
    print(f"  [{lo:.2f},{hi:.2f}) : {((cs>=lo)&(cs<hi)).sum()}")

for T in [0.90,0.80,0.75,0.70]:
    par=list(range(len(df)))
    def find(x):
        while par[x]!=x: par[x]=par[par[x]]; x=par[x]
        return x
    for c,a,b,f in rows:
        if c>=T:
            ra,rb=find(a),find(b)
            if ra!=rb: par[ra]=rb
    g=collections.defaultdict(list)
    for i in range(len(df)): g[find(i)].append(i)
    cl=[v for v in g.values() if len(v)>1]
    inc={i for v in cl for i in v}
    print(f"T={T}: clusters={len(cl)} rows={len(inc)} redundant={sum(len(v)-1 for v in cl)} sizes={dict(sorted(collections.Counter(len(v) for v in cl).items()))} marked={len(set(df.index[marked])&inc)}/{marked.sum()}")

print("\n=== pairs now in 0.45-0.90 (review zone) ===")
for c,a,b,f in [r for r in rows if 0.45<r[0]<0.90][:10]:
    print(f"\nconf={c:.3f} {f}")
    print(df.loc[[a,b],['Record ID','First Name','Last Name','Full Name','Company Name','Email','Phone Number','Country/Region']].to_string())

print("\n=== 3-member clusters sample (T=0.90) ===")
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
tri=[v for v in g.values() if len(v)==3]
for v in tri[:3]:
    print(df.loc[v,['Record ID','First Name','Last Name','Full Name','Company Name','Email','Phone Number','Lead Status','Create Date','Last Modified Date']].to_string()); print()
pickle.dump(rows, open('analysis/rows3.pkl','wb'))
