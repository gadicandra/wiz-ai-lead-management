import pandas as pd, pickle, collections, re, json
from rapidfuzz import fuzz
df = pd.read_pickle('analysis/df.pkl'); clusters=pickle.load(open('analysis/clusters.pkl','rb'))
js=json.load(open('data/website_form_submissions.json'))

# 1. JSON entries NOT matching seed -> new leads
def p9(p): return re.sub(r'\D','',p)[-9:]
se=set(df['_email']); sp=set(df['_p9'])
new=[e for e in js if e['email'].lower() not in se and p9(e['phone']) not in sp]
print("JSON new leads:", len(new), " existing:", 90-len(new))

# 2. does JSON duplicate itself?
print("JSON internal email dupes:", len(js)-len({e['email'].lower() for e in js}))

# 3. seed row whose JSON counterpart is itself inside a dup cluster?
inc={i for v in clusters for i in v}
hit=0
for e in js:
    m=df.index[df['_email']==e['email'].lower()]
    if len(m) and any(i in inc for i in m): hit+=1
print("JSON matches landing on a row already in a dup cluster:", hit)

# 4. Lead Score vs status sanity
ls=df['Lead Score'].replace('',pd.NA).dropna().astype(int)
print("\nLead Score present rows:", len(ls), "; in clusters:", sum(1 for i in ls.index if i in inc))

# 5. lifecycle vs status contradiction
def cs(s): return re.sub(r'\s+',' ',s.strip()).title()
tab=pd.crosstab(df['Lead Status'].map(cs), df['Lifecycle Stage'].replace('','(blank)'))
print("\nLead Status x Lifecycle Stage:"); print(tab.to_string())

# 6. notes outcome vs Lead Status contradiction
out = df['Notes'].str.extract(r'(Qualifying now|Connected, sending proposal|Great fit, prioritizing|No response yet|Not interested for now|Very interested, wants pricing call|Left voicemail, will retry)')[0]
print("\nNotes-outcome x Lead Status (top mismatches):")
ct=pd.crosstab(out.fillna('(none)'), df['Lead Status'].map(cs))
print(ct.to_string())
