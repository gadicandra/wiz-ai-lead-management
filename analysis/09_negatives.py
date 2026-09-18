import pandas as pd, pickle, collections, re
from rapidfuzz import fuzz
df = pd.read_pickle('analysis/df.pkl')
(rows,) = pickle.load(open('analysis/rows2.pkl','rb'))
cols=['Record ID','First Name','Last Name','Full Name','Company Name','Email','Phone Number','Country/Region','Lead Status','Create Date']

print("=== ZONE 0.60-0.95 (all) ===")
for c,a,b,f in [r for r in rows if 0.60<=r[0]<0.95]:
    print(f"\nconf={c:.3f} email={f['email_exact']} localnp={f['local_same_nopunct']} phone={f['phone']} name={f['name_sim']:.2f} ini={f['name_ini']} comp={f['comp_sim']:.2f} droot={f['droot']}")
    print(df.loc[[a,b],cols].to_string())

print("\n\n=== HARD NEGATIVES: same company root, high name sim, different phone AND different email ===")
hn=[r for r in rows if r[0]<0.60 and r[3]['droot'] and r[3]['name_sim']>=0.60]
hn.sort(key=lambda x:-x[3]['name_sim'])
print("count:", len(hn))
for c,a,b,f in hn[:18]:
    print(f"\nconf={c:.3f} name_sim={f['name_sim']:.2f} last_exact={f['last_exact']} first_exact={f['first_exact']} phone={f['phone']} local_sim={f['local_sim']:.2f}")
    print(df.loc[[a,b],cols].to_string())
