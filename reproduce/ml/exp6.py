"""Sim-trained estimator + range from held-out simulated WORLDS (shift between worlds is what the range must cover). Tested on real Accra. 3 seeds."""
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
src=open('exp4.py').read().split("rows=[]")[0]
exec(src.replace("rng=np.random.default_rng(11)","rng=np.random.default_rng(0)"))
real=pd.read_csv('draws_clean.csv'); real=real[real.full>0].copy(); real['o']=np.maximum(real.obs,1); real['ch']=real.n1**2/(2*real.n2+1)
F=lambda x:np.c_[x.k,x.n1,x.n2,x.n3,x.n4p,x.uptime,x.ch]
def sim(seed,nw=900):
    rng=np.random.default_rng(seed); rows=[]
    for w in range(nw):
        n=int(rng.integers(12,21)); up=rng.uniform(.55,.97); wide=rng.uniform(0,.6); rate=rng.uniform(15,70); dm=rng.uniform(1.5,6)
        D,R=world_month(n,1440,up,wide,rate,dm,rng); full=int((events_from(D)>=2).sum())
        if full==0: continue
        for k in (3,4,5,6,7,8):
            for _ in range(8):
                sub=rng.choice(n,k,replace=False); f=events_from(D[sub])
                rows.append(dict(world=w,k=k,full=full,n1=int((f==1).sum()),n2=int((f==2).sum()),n3=int((f==3).sum()),n4p=int((f>=4).sum()),obs=int((f>=2).sum()),uptime=float(R[sub].mean())))
    S=pd.DataFrame(rows); S['o']=np.maximum(S.obs,1); S['ch']=S.n1**2/(2*S.n2+1); return S
out=[]
for seed in (1,2,3):
    S=sim(seed); ids=S.world.unique(); fitw=ids[:len(ids)*2//3]; calw=ids[len(ids)*2//3:]
    tr,cal=S[S.world.isin(fitw)],S[S.world.isin(calw)]
    gb=GradientBoostingRegressor(n_estimators=250,max_depth=4,learning_rate=0.05,subsample=0.7,random_state=seed).fit(F(tr),np.log(tr.full/tr.o))
    e=np.log(cal.full/(cal.o*np.exp(gb.predict(F(cal))))); q={k:(e[cal.k==k].quantile(.1),e[cal.k==k].quantile(.9)) for k in range(3,9)}
    r=real.copy(); r['gb']=r.o*np.exp(gb.predict(F(r))); r['lo']=r.gb*np.exp(r.k.map(lambda k:q[k][0])); r['hi']=r.gb*np.exp(r.k.map(lambda k:q[k][1]))
    for site in (3,4):
        for k in (3,5,8):
            s=r[(r.site==site)&(r.k==k)]
            out.append(dict(seed=seed,site=site,k=k,err=100*np.median(np.abs(s.gb-s.full)/s.full),cov=100*((s.full>=s.lo)&(s.full<=s.hi)).mean(),width=np.median((s.hi-s.lo)/s.full)))
O=pd.DataFrame(out); print(O.groupby(['site','k']).agg(err=('err','mean'),err_min=('err','min'),err_max=('err','max'),cov=('cov','mean'),width=('width','mean')).round(1))
