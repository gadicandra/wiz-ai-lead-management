import pandas as pd, pickle, collections, re
df = pd.read_pickle('analysis/df.pkl'); clusters=pickle.load(open('analysis/clusters.pkl','rb'))
def cs(s): return re.sub(r'\s+',' ',str(s).strip()).title()
stat=collections.Counter()
for v in clusters:
    sub=df.loc[v]
    for col in ['Lead Status','Lifecycle Stage','Original Source','Contact Owner','Job Title','Lead Score','Country/Region','Notes','Email','Phone Number','Create Date','Last Modified Date','Company Name']:
        vals=sub[col].astype(str).str.strip()
        if col in ('Lead Status','Country/Region','Contact Owner'): vals=vals.map(cs)
        if col=='Notes': vals=vals.str.replace(' possible duplicate — verify before contacting.','',regex=False).str.strip()
        if col=='Phone Number': vals=vals.str.replace(r'\D','',regex=True)
        if col in ('Create Date','Last Modified Date'):
            vals=vals.map(lambda s: next((str(pd.to_datetime(s,format=f).date()) for f in ('%Y-%m-%d','%Y-%m-%dT%H:%M:%SZ','%m/%d/%Y') if _try(s,f)), '') if s else '')
        nb=vals[vals!='']
        if nb.nunique()>1: stat[(col,'CONFLICT')]+=1
        if 0<len(nb)<len(v): stat[(col,'PARTIAL')]+=1
def _try(s,f):
    try: pd.to_datetime(s,format=f); return True
    except: return False
print(f"clusters={len(clusters)}")
for (c,k),n in sorted(stat.items()): print(f"  {c:22s} {k:9s} {n:4d} ({n/len(clusters)*100:5.1f}%)")
