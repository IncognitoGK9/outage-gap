"""Simulation-trained estimator -> real Accra. Worlds vary uptime, share of wide outages, outage rate, outage length."""
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
rng=np.random.default_rng(11)
def events_from(D):
    anyd=D.any(0); idx=np.flatnonzero(anyd)
    if idx.size==0: return np.array([],int)
    cut=np.flatnonzero(np.diff(idx)>2)+1; starts=np.r_[0,cut]
    return (np.add.reduceat(D[:,idx].astype(np.int8),starts,axis=1)>0).sum(0)
def world_month(n,nb,up,wide,rate,dur_mu,rng):
    down=np.zeros((n,nb),bool)
    for _ in range(rng.poisson(rate)):
        s=rng.integers(0,nb); L=1+int(rng.lognormal(np.log(dur_mu),0.8))
        reach=rng.beta(8,2) if rng.random()<wide else rng.beta(0.6,2.7)
        down[rng.random(n)<reach,s:s+L]=True
    rep=rng.random((n,nb))<up
    return down&rep,rep
rows=[]
for w in range(700):
    n=int(rng.integers(12,21)); up=rng.uniform(0.55,0.97); wide=rng.uniform(0.0,0.6); rate=rng.uniform(15,70); dm=rng.uniform(1.5,6); nb=30*48
    D,R=world_month(n,nb,up,wide,rate,dm,rng); full=int((events_from(D)>=2).sum())
    if full==0: continue
    for k in (3,4,5,6,7,8):
        for _ in range(8):
            sub=rng.choice(n,k,replace=False); f=events_from(D[sub])
            rows.append(dict(world=w,k=k,full=full,n1=int((f==1).sum()),n2=int((f==2).sum()),n3=int((f==3).sum()),n4p=int((f>=4).sum()),obs=int((f>=2).sum()),uptime=float(R[sub].mean())))
S=pd.DataFrame(rows); S.to_csv('draws_sim.csv',index=False); print('sim draws',len(S))
d=pd.read_csv('draws_clean.csv'); d=d[d.full>0].copy()
for x in (S,d): x['o']=np.maximum(x.obs,1); x['ch']=x.n1**2/(2*x.n2+1)
F=lambda x:np.c_[x.k,x.n1,x.n2,x.n3,x.n4p,x.uptime,x.ch]
S=S[S.full>0]
gb=GradientBoostingRegressor(n_estimators=250,max_depth=4,learning_rate=0.05,subsample=0.7,random_state=0).fit(F(S),np.log(S.full/S.o))
d['gb']=d.o*np.exp(gb.predict(F(d)))
real_c=d.groupby('k').apply(lambda g:g.obs.sum()/g.full.sum())
res=[]
for site in (3,4):
    o=d[d.site==site]; c=d[d.site!=site].groupby('k').apply(lambda g:g.obs.sum()/g.full.sum())
    for k in (3,5,8):
        s=o[o.k==k]; m=lambda v:round(100*np.median(np.abs(v-s.full)/s.full),1)
        res.append(dict(test_site=site,k=k,raw=m(s.obs),divide_from_other_site=m(s.obs/c[k]),sim_trained_gb=m(s.gb),bias_pct=round(100*np.median((s.gb-s.full)/s.full),1)))
print(pd.DataFrame(res).to_string(index=False))
