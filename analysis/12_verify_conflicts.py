import pandas as pd, pickle, collections, re
df = pd.read_pickle('analysis/df.pkl'); clusters=pickle.load(open('analysis/clusters.pkl','rb'))
def cs(s): return re.sub(r'\s+',' ',s.strip()).title()
stat=collections.Counter()
for v in clusters:
    sub=df.loc[v]
    for col,label in [('Lead Status','status'),('Lifecycle Stage','lifecycle'),('Original Source','source'),
                      ('Contact Owner','owner'),('Job Title','jobtitle'),('Lead Score','score'),
                      ('Country/Region','country'),('Notes','notes')]:
        vals=sub[col].str.strip()
        nb=vals[vals!='']
        if col in ('Lead Status','Country/Region','Contact Owner'): nb=nb.map(cs)
        if col=='Notes': nb=nb.str.replace(' possible duplicate — verify before contacting.','',regex=False).str.strip()
        if nb.nunique()>1: stat[label+': CONFLICT (differing non-blank values)']+=1
        if 0<len(nb)<len(v): stat[label+': PARTIAL (blank in some, filled in others)']+=1
print(f"clusters={len(clusters)}")
for k,v in sorted(stat.items()): print(f"  {k:55s} {v} ({v/len(clusters)*100:.0f}%)")

print("\n=== example PARTIAL clusters (info gained by merging) ===")
n=0
for v in clusters:
    sub=df.loc[v]
    if 0<(sub['Lead Score'].str.strip()!='').sum()<len(v) or 0<(sub['Job Title'].str.strip()!='').sum()<len(v) or 0<(sub['Original Source'].str.strip()!='').sum()<len(v):
        print(sub[['Record ID','First Name','Last Name','Full Name','Job Title','Company Name','Email','Lead Status','Lifecycle Stage','Original Source','Lead Score','Last Modified Date']].to_string()); print()
        n+=1
        if n>=5: break
print("total PARTIAL-info clusters:", sum(1 for v in clusters if any(0<(df.loc[v,c].str.strip()!='').sum()<len(v) for c in ['Lead Score','Job Title','Original Source','Lifecycle Stage','Last Modified Date'])))
