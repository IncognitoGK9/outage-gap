"""Sim-trained point estimate + range calibrated on ONE real site, tested on the OTHER real site (same protocol as the shipped tool)."""
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
exec(open('exp6.py').read().split("out=[]")[0])
rows=[]
for seed in (1,2,3):
    S=sim(seed)
    gb=GradientBoostingRegressor(n_estimators=250,max_depth=4,learning_rate=0.05,subsample=0.7,random_state=seed).fit(F(S),np.log(S.full/S.o))
    r=real.copy(); r['gb']=r.o*np.exp(gb.predict(F(r))); r['e']=np.log(r.full/r.gb)
    c=lambda tr:tr.groupby('k').apply(lambda g:g.obs.sum()/g.full.sum())
    for site in (3,4):
        cal=r[r.site!=site]; te=r[r.site==site]; q={k:(cal[cal.k==k].e.quantile(.1),cal[cal.k==k].e.quantile(.9)) for k in range(3,9)}
        cs=c(cal)
        for k in (3,5,8):
            s=te[te.k==k]; lo=s.gb*np.exp(q[k][0]); hi=s.gb*np.exp(q[k][1]); dv=s.obs/cs[k]
            # division range from the same single calibration site
            ed=np.log(cal.full/np.maximum(cal.obs/cal.k.map(cs),.5)); dq=(ed[cal.k==k].quantile(.1),ed[cal.k==k].quantile(.9)); dlo=dv*np.exp(dq[0]); dhi=dv*np.exp(dq[1])
            rows.append(dict(seed=seed,site=site,k=k,err_gb=100*np.median(np.abs(s.gb-s.full)/s.full),err_div=100*np.median(np.abs(dv-s.full)/s.full),
              cov_gb=100*((s.full>=lo)&(s.full<=hi)).mean(),cov_div=100*((s.full>=dlo)&(s.full<=dhi)).mean(),w_gb=np.median((hi-lo)/s.full),w_div=np.median((dhi-dlo)/s.full)))
print(pd.DataFrame(rows).groupby(['site','k']).mean().drop(columns='seed').round(1))
