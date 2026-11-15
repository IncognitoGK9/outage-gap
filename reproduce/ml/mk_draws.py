"""Rebuild subset draws from the RAW dense Accra bins using only what a sparse site can see (its own readings)."""
import numpy as np, pandas as pd
rng=np.random.default_rng(7)
d=pd.read_pickle('../d34.pkl')
def events_from(D):
    """D: bool matrix (sensors x bins). Returns number of sensors seeing each event (runs of any-down bins merged if <=2 bins apart)."""
    anyd=D.any(0); idx=np.flatnonzero(anyd)
    if idx.size==0: return np.array([],int)
    cut=np.flatnonzero(np.diff(idx)>2)+1; starts=np.r_[0,cut]
    S=np.add.reduceat(D[:,idx].astype(np.int8),starts,axis=1)>0
    return S.sum(0)
rows=[]
for (s,m),g in d.groupby(['site_id','month']):
    nb=g.bin.dt.days_in_month.iloc[0]*48
    cov=g.groupby('device').bin.nunique()/nb; devs=cov[cov>=0.6].index.tolist()
    if len(devs)<8: continue
    g=g[g.device.isin(devs)]
    t0=g.bin.min().normalize().replace(day=1)
    bi=((g.bin-t0)/pd.Timedelta(minutes=30)).astype(int).values
    di=pd.Index(devs).get_indexer(g.device)
    D=np.zeros((len(devs),nb),bool); D[di,bi]=g.down.values
    R=np.zeros((len(devs),nb),bool); R[di,bi]=True
    full=int((events_from(D)>=2).sum())
    if full==0: continue
    for k in (3,4,5,6,7,8):
        for _ in range(40):
            sub=rng.choice(len(devs),k,replace=False); f=events_from(D[sub])
            rows.append(dict(site=s,month=m,k=k,full=full,n1=int((f==1).sum()),n2=int((f==2).sum()),n3=int((f==3).sum()),n4p=int((f>=4).sum()),
                             obs=int((f>=2).sum()),uptime=float(R[sub].mean())))
df=pd.DataFrame(rows); df.to_csv('draws_clean.csv',index=False)
print(len(df)); print(df.groupby(['site','k']).apply(lambda g:g.obs.sum()/g.full.sum()).unstack(0).round(3))
