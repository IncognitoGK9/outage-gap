"""Usage: python3 end_to_end_check.py sites34.csv calibration/calibration_draws.csv
End-to-end test on REAL nLine rows: sample k sensors of a dense site-month, run the shipped counting script and the shipped estimator, compare with the full-site count."""
import sys, pathlib, numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from outage_gap.count_events import count_events
from outage_gap.core import estimate
d=pd.read_csv(sys.argv[1],usecols=['device','bin','n_obs','n_unpowered','site_id'],parse_dates=['bin'])
d['month']=d.bin.dt.to_period('M'); rng=np.random.default_rng(7)
R=pd.read_csv(sys.argv[2]); full=R.groupby(['site','month']).full.first()
rows=[]; chk=[]
for (s,m),g in d.groupby(['site_id','month']):
    if (s,str(m)) not in full.index: continue
    cov=g.groupby('device').bin.nunique()/(g.bin.dt.days_in_month.iloc[0]*48); devs=cov[cov>=.6].index.tolist()
    g=g[g.device.isin(devs)]; chk.append((count_events(g)['events_2plus'],int(full[(s,str(m))])))
    for k in (3,5,8):
        for _ in range(10):
            sub=rng.choice(devs,k,replace=False); gs=g[g.device.isin(sub)]
            r=count_events(gs); up=r['uptime_estimate']
            e=estimate(k,r['events_2plus'],None)
            rows.append(dict(site=s,month=str(m),k=k,S=r['events_2plus'],N=full[(s,str(m))],est=e.estimated_total))
chk=pd.DataFrame(chk,columns=['script','reference']); print('full-site count: script equals reference in',(chk.script==chk.reference).mean(),'of',len(chk),'site-months')
R2=pd.DataFrame(rows); R2['err']=(R2.est-R2.N)/R2.N
print(R2.groupby('k').agg(mean_err=('err','mean'),med_abs=('err',lambda x:x.abs().median()),n=('err','size')).round(3))
print('by site, k=3:',R2[R2.k==3].groupby('site').err.mean().round(3).to_dict())
