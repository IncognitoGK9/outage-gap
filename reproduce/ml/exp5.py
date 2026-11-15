"""Sierra Leone check (6 site-months, reference = 8 sensors): sim-trained model (worlds with 8 sensors) vs division with Accra share."""
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
exec(open('exp4.py').read().split("rows=[]")[0].split("rng=np.random.default_rng(11)")[1].replace("def events_from","def events_from",1)) if False else None
rng=np.random.default_rng(5)
def events_from(D):
    anyd=D.any(0); idx=np.flatnonzero(anyd)
    if idx.size==0: return np.array([],int)
    cut=np.flatnonzero(np.diff(idx)>2)+1; starts=np.r_[0,cut]
    return (np.add.reduceat(D[:,idx].astype(np.int8),starts,axis=1)>0).sum(0)
def world_month(n,nb,up,wide,rate,dm):
    down=np.zeros((n,nb),bool)
    for _ in range(rng.poisson(rate)):
        s=rng.integers(0,nb); L=1+int(rng.lognormal(np.log(dm),0.8)); reach=rng.beta(8,2) if rng.random()<wide else rng.beta(0.6,2.7)
        down[rng.random(n)<reach,s:s+L]=True
    rep=rng.random((n,nb))<up; return down&rep,rep
def feats(f,R): return dict(n1=int((f==1).sum()),n2=int((f==2).sum()),n3=int((f==3).sum()),n4p=int((f>=4).sum()),obs=int((f>=2).sum()),uptime=float(R.mean()))
rows=[]
for w in range(900):
    n=8; D,R=world_month(n,1440,rng.uniform(.5,.97),rng.uniform(0,.6),rng.uniform(15,70),rng.uniform(1.5,6)); full=int((events_from(D)>=2).sum())
    if full==0: continue
    for k in (3,4,5):
        for _ in range(10):
            sub=rng.choice(n,k,replace=False); rows.append(dict(k=k,full=full,**feats(events_from(D[sub]),R[sub])))
S=pd.DataFrame(rows)
for x in (S,): x['o']=np.maximum(x.obs,1); x['ch']=x.n1**2/(2*x.n2+1)
F=lambda x:np.c_[x.k,x.n1,x.n2,x.n3,x.n4p,x.uptime,x.ch]
gb=GradientBoostingRegressor(n_estimators=250,max_depth=4,learning_rate=0.05,subsample=0.7,random_state=0).fit(F(S),np.log(S.full/S.o))
sl=pd.read_pickle('../sl/sl.pkl'); sl['down']=(sl.n_unpowered/sl.n_obs>=0.5); sl['month']=sl.bin.dt.to_period('M').astype(str)
out=[]
for (s,m),g in sl.groupby(['site_id','month']):
    nb=g.bin.dt.days_in_month.iloc[0]*48; cov=g.groupby('device').bin.nunique()/nb; devs=cov[cov>=0.6].index.tolist()
    if len(devs)<8: continue
    devs=list(cov[devs].sort_values(ascending=False).index[:8]); g=g[g.device.isin(devs)]
    t0=g.bin.min().normalize().replace(day=1); bi=((g.bin-t0)/pd.Timedelta(minutes=30)).astype(int).values; di=pd.Index(devs).get_indexer(g.device)
    D=np.zeros((8,nb),bool); R=np.zeros((8,nb),bool); D[di,bi]=g.down.values; R[di,bi]=True
    full=int((events_from(D)>=2).sum())
    if full==0: continue
    for _ in range(40):
        sub=rng.choice(8,3,replace=False); out.append(dict(site=s,month=m,full=full,k=3,**feats(events_from(D[sub]),R[sub])))
T=pd.DataFrame(out); T['o']=np.maximum(T.obs,1); T['ch']=T.n1**2/(2*T.n2+1)
T['gb']=T.o*np.exp(gb.predict(F(T))); T['acc']=T.obs/0.374
e=lambda v:round(100*np.median(np.abs(v-T.full)/T.full),1); b=lambda v:round(100*np.median((v-T.full)/T.full),1)
print('site-months',T.groupby(['site','month']).ngroups,'| median abs error %: raw',e(T.obs),'accra-share',e(T.acc),'sim-trained',e(T.gb),'| median bias %: accra-share',b(T.acc),'sim-trained',b(T.gb))
