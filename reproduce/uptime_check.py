"""Real-data check of an uptime term. Usage: python3 reproduce/uptime_check.py sites34.csv. Result: the uptime term changes the median error by -2.3 to +2.2 points across six tests."""
import sys, numpy as np, pandas as pd, importlib.util, pathlib
spec=importlib.util.spec_from_file_location('rs',str(__import__('pathlib').Path(__file__).with_name('run_subsampling.py'))); rs=importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
rng=np.random.default_rng(5)
d=pd.read_csv(sys.argv[1],usecols=['device','bin','n_obs','n_unpowered','site_id'],parse_dates=['bin'])
d['down']=d.n_unpowered/d.n_obs>=0.5; d['month']=d.bin.dt.to_period('M'); rows=[]
for (s,m),g in d.groupby(['site_id','month']):
    cov=g.groupby('device').bin.nunique()/(m.days_in_month*48); devs=cov[cov>=.6].index.tolist()
    if len(devs)<8: continue
    g=g[g.device.isin(devs)]; dn=g[g.down].groupby('bin').device.apply(set)
    if dn.empty: continue
    items=list(dn.items()); E=[x for x in rs.build_events(items) if len(x)>=2]
    if not E: continue
    for k in (3,5,8):
        for _ in range(40):
            sub=list(rng.choice(devs,k,replace=False)); ss=set(sub)
            rb=[x for x in rs.build_events([(b,v&ss) for b,v in items if v&ss]) if len(x)>=2]
            rows.append(dict(site=s,month=str(m),k=k,N=len(E),S=len(rb),u=float(cov[sub].mean())))
R=pd.DataFrame(rows); print('uptime range of subsets (min,q10,median,q90,max):',R.u.quantile([0,.1,.5,.9,1]).round(2).tolist())
for k in (3,5,8):
    r=R[R.k==k].copy(); r['bin']=pd.qcut(r.u,3,labels=['low','mid','high'])
    t=r.groupby('bin',observed=True).apply(lambda x:pd.Series(dict(u=x.u.mean(),share=x.S.sum()/x.N.sum(),n=len(x))))
    print(k,t.round(3).to_dict('index'))
    c=r.S.sum()/r.N.sum(); 
    # uptime-aware: share as linear function of u, fitted on site 3 tested on site 4 and reverse
    for s,o in ((3,4),(4,3)):
        tr=r[r.site==o]; te=r[r.site==s]
        A=np.polyfit(tr.u,tr.S/tr.N,1); fac_u=np.clip(np.polyval(A,te.u),0.05,1); cfix=tr.S.sum()/tr.N.sum()
        e_fix=((te.S/cfix-te.N)/te.N); e_up=((te.S/fac_u-te.N)/te.N)
        print('   site',s,'fixed share: mean %.3f medabs %.3f | uptime-aware: mean %.3f medabs %.3f'%(e_fix.mean(),e_fix.abs().median(),e_up.mean(),e_up.abs().median()))
