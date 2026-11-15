import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
d=pd.read_csv('draws_clean.csv'); d=d[d.full>0].copy(); d['o']=np.maximum(d.obs,1)
d['ch']=d.n1**2/(2*d.n2+1)
F=lambda x:np.c_[x.k,x.n1,x.n2,x.n3,x.n4p,x.uptime,x.ch]
FL=lambda x:np.c_[np.log(x.k),np.log1p(x.n1),np.log1p(x.n2),np.log1p(x.n3),np.log1p(x.n4p),x.uptime,np.log1p(x.ch)]
rows=[]
for test in (3,4):
    tr,te=d[d.site!=test],d[d.site==test].copy()
    c=tr.groupby('k').apply(lambda g:g.obs.sum()/g.full.sum()); te['dv']=te.obs/te.k.map(c)
    y=np.log(tr.full/tr.o)
    gb=GradientBoostingRegressor(n_estimators=150,max_depth=3,learning_rate=0.05,subsample=0.7,random_state=0).fit(F(tr),y)
    rg=Ridge(alpha=1).fit(FL(tr),y)
    te['gb']=te.o*np.exp(gb.predict(F(te))); te['rg']=te.o*np.exp(rg.predict(FL(te)))
    # ranges from training-site residuals (in-sample on training site; honest about shift: tested on other site)
    for nm,col,pr in (('dv','dv',None),('gb','gb',gb.predict(F(tr))),('rg','rg',rg.predict(FL(tr)))):
        base=(tr.obs/tr.k.map(c)) if nm=='dv' else tr.o*np.exp(pr)
        e=np.log(tr.full/np.maximum(base,.5)); q={k:(e[tr.k==k].quantile(.1),e[tr.k==k].quantile(.9)) for k in range(3,9)}
        te[nm+'_lo']=te[col]*np.exp(te.k.map(lambda k:q[k][0])); te[nm+'_hi']=te[col]*np.exp(te.k.map(lambda k:q[k][1]))
    for k in (3,5,8):
        s=te[te.k==k]; m=lambda c_:round(100*np.median(np.abs(s[c_]-s.full)/s.full),1)
        cv=lambda n:round(100*((s.full>=s[n+'_lo'])&(s.full<=s[n+'_hi'])).mean(),1)
        w=lambda n:round(np.median((s[n+'_hi']-s[n+'_lo'])/s.full),2)
        rows.append(dict(test=test,k=k,raw=m('obs'),divide=m('dv'),ridge=m('rg'),gboost=m('gb'),cov_dv=cv('dv'),cov_rg=cv('rg'),cov_gb=cv('gb'),w_dv=w('dv'),w_rg=w('rg'),w_gb=w('gb')))
print(pd.DataFrame(rows).to_string(index=False))
