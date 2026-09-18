import pandas as pd, pickle, collections, re
df = pd.read_pickle('analysis/df.pkl'); clusters=pickle.load(open('analysis/clusters.pkl','rb'))
v=clusters[0]; sub=df.loc[v]
print(type(sub), sub.shape)
for col in ['Lead Status','Lead Score','Job Title','Original Source','Lifecycle Stage','Last Modified Date','Contact Owner','Notes']:
    vals=sub[col].astype(str).str.strip()
    print(col, '->', repr(list(vals)))
