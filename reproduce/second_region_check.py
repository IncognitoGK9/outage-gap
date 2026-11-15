"""Exploratory second-region check. Usage: python3 second_region_check.py sites34.csv sierra_leone.csv
Both CSVs have columns device,bin,n_obs,n_unpowered,site_id. Sierra Leone has few site-months with 8+ sensors, so the reference is 8 sensors in BOTH regions (Accra: random 8 of the dense site).
Only 6 Sierra Leone site-months qualified in our data: treat the result as a warning, not a calibration."""
import sys, numpy as np, pandas as pd
import importlib.util, pathlib
spec=importlib.util.spec_from_file_location('rs',pathlib.Path(__file__).with_name('run_subsampling.py')); rs=importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
rng=np.random.default_rng(3)
REF=8
def prep(d,site_col='site_id'):
    d=d.copy(); d['bin']=pd.to_datetime(d.bin); d['down']=d.n_unpowered/d.n_obs>=0.5; d['month']=d.bin.dt.to_period('M'); return d
def site_months(d):
    for (s,m),g in d.groupby(['site_id','month']):
        cov=g.groupby('device').bin.nunique()/(m.days_in_month*48); devs=cov[cov>=.6].index.tolist()
        if len(devs)>=REF: yield s,m,g[g.device.isin(devs)],devs
def run(d,refsets,ks,draws):
    rows=[]
    for s,m,g,devs in site_months(d):
        for _ in range(refsets):
            ref=list(rng.choice(devs,REF,replace=False)); gg=g[g.device.isin(ref)]
            dn=gg[gg.down].groupby('bin').device.apply(set)
            if dn.empty: continue
            items=list(dn.items()); E=[x for x in rs.build_events(items) if len(x)>=2]
            if not E: continue
            for k in ks:
                for _ in range(draws):
                    sub=set(rng.choice(ref,k,replace=False))
                    rb=[x for x in rs.build_events([(b,v&sub) for b,v in items if v&sub]) if len(x)>=2]
                    rows.append(dict(site=s,month=str(m),k=k,N=len(E),S=len(rb)))
    return pd.DataFrame(rows)
sl=prep(pd.read_csv(sys.argv[2],usecols=['device','bin','n_obs','n_unpowered','site_id']))
ac=prep(pd.read_csv(sys.argv[1],usecols=['device','bin','n_obs','n_unpowered','site_id']))
A=run(ac,3,(3,4,5),5); S=run(sl,1,(3,4,5),20)
print('Accra site-months',A.groupby(['site','month']).ngroups,'Sierra site-months',S.groupby(['site','month']).ngroups, S.groupby('site').month.nunique().to_dict())
out={}
for k in (3,4,5):
    a=A[A.k==k]; s=S[S.k==k]; ca=a.S.sum()/a.N.sum(); cs=s.S.sum()/s.N.sum()
    e=(s.S/ca-s.N)/s.N
    sm=s.groupby(['site','month'])[['S','N']].sum().reset_index(); bs=[sm.iloc[rng.integers(0,len(sm),len(sm))] for _ in range(1000)]; ci=np.percentile([b.S.sum()/b.N.sum() for b in bs],[2.5,97.5])
    out[k]=dict(accra8=ca,sierra=cs,sierra_ci=ci.tolist(),mean_err=float(e.mean()),med_abs=float(e.abs().median()),raw_med=float(((s.S-s.N)/s.N).abs().median()),sl_by_site={x:float(g.S.sum()/g.N.sum()) for x,g in s.groupby('site')})
    print(k,{a:(round(b,3) if isinstance(b,float) else b) for a,b in out[k].items()})
import json; json.dump(out,open('second_region.json','w'),indent=1,default=float)
