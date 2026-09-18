import pandas as pd, json, re, collections
from rapidfuzz import fuzz
df = pd.read_pickle('analysis/df.pkl')
js = json.load(open('data/website_form_submissions.json'))
print("json entries:", len(js))
print("keys:", sorted({k for e in js for k in e}))
allk = {'form_id','form_name','page_url','submitted_at','name','email','phone','company','country','message'}
print("missing-keys pattern:", collections.Counter(tuple(sorted(allk-set(e))) for e in js))
pairs=collections.Counter((e['form_id'],e['form_name']) for e in js)
print("\nform_id x form_name combos:", len(pairs))
for k,v in pairs.most_common(12): print("  ",k,v)
msgs=collections.Counter(e['message'] for e in js)
print("\ndistinct messages:", len(msgs), "of", len(js))
for k,v in msgs.most_common(3): print(f"   {v:3d}  {k[:80]}")
ph=[e['phone'] for e in js]
print("\nphones without '+':", [p for p in ph if not p.startswith('+')])
print("country casing anomalies:", [e['country'] for e in js if e['country'] != e['country'][0].upper()+e['country'][1:]])
def p9(p):
    d=re.sub(r'\D','',p); return d[-9:]
seed_email=set(df['_email']); seed_p9=set(df['_p9'])
hit_e=[e for e in js if e['email'].lower() in seed_email]
hit_p=[e for e in js if p9(e['phone']) in seed_p9]
print("\nJSON email found in seed:", len(hit_e))
print("JSON phone(last9) found in seed:", len(hit_p))
for e in hit_p[:4]:
    m=df[df['_p9']==p9(e['phone'])]
    print(f"\n  JSON: {e['name']} | {e['email']} | {e['phone']} | {e['company']} | {e['country']}")
    print(m[['Record ID','First Name','Last Name','Full Name','Company Name','Email','Phone Number','Country/Region']].to_string())
seed_idx=collections.defaultdict(list)
for i,r in df.iterrows(): seed_idx[r['_droot']].append(i)
ex=[]
for e in js:
    dr=e['email'].split('@')[1].split('.')[0].lower()
    for i in seed_idx.get(dr,[]):
        if fuzz.token_sort_ratio(e['name'].lower(), df.at[i,'_name'])>=88:
            ex.append((e,i)); break
print("\nJSON soft-match (domain-root + name>=88):", len(ex))
for e,i in ex[:6]:
    print(f"  JSON {e['name']:24s} {e['email']:38s} {e['phone']:20s} || SEED {df.at[i,'Record ID']} {df.at[i,'_name']:22s} {df.at[i,'Email']:38s} {df.at[i,'Phone Number']}")
