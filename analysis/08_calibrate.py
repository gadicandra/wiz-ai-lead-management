import pandas as pd, re, itertools, collections, pickle, numpy as np
from rapidfuzz import fuzz
df = pd.read_pickle('analysis/df.pkl')
marked = df['Notes'].str.contains('possible duplicate', case=False)
print("marked rows:", marked.sum())

blocks = collections.defaultdict(set)
for i,r in df.iterrows():
    blocks['p:'+r['_p9']].add(i)
    blocks['e:'+r['_email']].add(i)
    blocks['l:'+r['_local']].add(i)
    blocks['dl:'+r['_droot']+'|'+r['_last']].add(i)
pairs=set()
for k,v in blocks.items():
    if 1<len(v)<=50:
        for a,b in itertools.combinations(sorted(v),2): pairs.add((a,b))
print("candidate pairs:", len(pairs))

def feats(a,b):
    ra,rb=df.loc[a],df.loc[b]
    la,lb = ra['_local'], rb['_local']
    # localpart compare ignoring dots/dashes
    ca,cb = re.sub(r'[.\-_]','',la), re.sub(r'[.\-_]','',lb)
    f={}
    f['email_exact']= ra['_email']==rb['_email']
    f['local_same_nopunct']= ca==cb and ra['_dom']==rb['_dom']
    f['local_sim']= fuzz.ratio(la,lb)/100
    f['dom_exact']= ra['_dom']==rb['_dom']
    f['droot']= ra['_droot']==rb['_droot']
    f['phone']= ra['_p9']==rb['_p9'] and ra['_p9']!=''
    f['name_sim']= fuzz.token_sort_ratio(ra['_name'],rb['_name'])/100
    f['name_ini']= (ra['_last']==rb['_last'] and ra['_initial']==rb['_initial'] and
                    (len(ra['_first'].rstrip('.'))<=2 or len(rb['_first'].rstrip('.'))<=2))
    f['first_exact']= ra['_first']==rb['_first']
    f['last_exact']= ra['_last']==rb['_last']
    f['comp_sim']= fuzz.token_set_ratio(ra['_comp'],rb['_comp'])/100
    f['country']= ra['Country/Region'].strip().lower()==rb['Country/Region'].strip().lower()
    f['create_same']= ra['_cd']==rb['_cd']
    f['notes_sim']= fuzz.ratio(ra['Notes'][:100],rb['Notes'][:100])/100
    return f

def parse(s):
    s=s.strip()
    for fmt in ('%Y-%m-%d','%Y-%m-%dT%H:%M:%SZ','%m/%d/%Y'):
        try: return pd.to_datetime(s,format=fmt)
        except: pass
    return pd.NaT
df['_cd']=df['Create Date'].map(parse)

def conf(f):
    # identity evidence (strong): email OR phone
    ident = 0.0
    if f['email_exact'] or f['local_same_nopunct']: ident = max(ident, 1.0)
    if f['phone']: ident = max(ident, 0.95)
    if f['dom_exact'] and f['local_sim']>=0.75: ident = max(ident, 0.80)
    # person evidence
    person = max(f['name_sim'], 0.95 if f['name_ini'] else 0.0)
    # org evidence
    org = 1.0 if f['droot'] else f['comp_sim']
    c = 0.45*ident + 0.35*person + 0.12*org + 0.04*f['country'] + 0.04*f['create_same']
    return c

rows=[]
for a,b in pairs:
    f=feats(a,b); rows.append((conf(f),a,b,f))
rows.sort(reverse=True,key=lambda x:x[0])
cs=np.array([r[0] for r in rows])
print("\nconfidence buckets:")
for lo,hi in [(0.95,1.01),(0.90,0.95),(0.85,0.90),(0.80,0.85),(0.75,0.80),(0.70,0.75),(0.60,0.70),(0.0,0.60)]:
    print(f"  [{lo:.2f},{hi:.2f}) : {((cs>=lo)&(cs<hi)).sum()}")

for T in [0.95,0.90,0.85,0.80,0.75,0.70]:
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
    inc=set(i for v in cl for i in v)
    mk=set(df.index[marked])
    print(f"T={T}: clusters={len(cl):3d} rows={sum(len(v) for v in cl):4d} redundant={sum(len(v)-1 for v in cl):4d} "
          f"sizes={dict(sorted(collections.Counter(len(v) for v in cl).items()))} markedCaptured={len(mk&inc)}/{len(mk)}")
pickle.dump((rows,), open('analysis/rows2.pkl','wb'))
df.to_pickle('analysis/df.pkl')
