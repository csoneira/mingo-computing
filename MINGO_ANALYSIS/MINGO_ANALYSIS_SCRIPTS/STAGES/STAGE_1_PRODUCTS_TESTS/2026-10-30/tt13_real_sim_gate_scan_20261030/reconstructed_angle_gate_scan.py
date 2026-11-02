#!/usr/bin/env python3
"""Read-only TT13 closure by reconstructed detector angle; no HV mixing."""
from pathlib import Path
import math
import numpy as np
import pandas as pd
ROOT=Path('/home/mingo/mingo-computing')
OUT=Path(__file__).resolve().parent
manifest=pd.read_csv(OUT/'per_file_closure.csv')
manifest=manifest[manifest.gate=='baseline'].copy()
real_map={r.filename:r for r in manifest[manifest.dataset=='MINGO01'].itertuples(index=False)}
# Includes measured P1 HV values; one group per full four-plane setting.
def real_group(row):
    return 'HV_'+'_'.join(f'{float(getattr(row,f"p{i}_hv_kv")):.4f}' for i in range(1,5))
limits=[15,20,25,30,35,40,45]
rows=[]
TT=(1234,134,123,13)
for station in ['MINGO00','MINGO01']:
    lake=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS'/station/'STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
    for path in sorted(lake.glob('postprocessed_*.parquet')):
        filename=path.stem.removeprefix('postprocessed_')
        if station=='MINGO01' and filename not in real_map: continue
        before=path.stat()
        try:
            frame=pd.read_parquet(path,columns=['tt_task0_raw','event_det_theta'])
        except Exception as e:
            print('SKIP',station,filename,str(e));continue
        after=path.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise RuntimeError(f'Input changed while reading {path}')
        theta=frame.event_det_theta.to_numpy(float)
        tt=frame.tt_task0_raw.to_numpy(dtype=float)
        valid=np.isfinite(theta)&(theta>=0)&np.isfinite(tt)
        theta_deg=np.degrees(theta[valid]); tt=tt[valid].astype(int)
        if station=='MINGO00':
            hashes=frame.get('param_hash')
            group=filename # keep simulated files separate
            if filename in {r.filename for r in manifest[manifest.dataset=='MINGO00'].itertuples(index=False)}:
                group=manifest[(manifest.dataset=='MINGO00')&(manifest.filename==filename)].parameter_group.iloc[0]
        else:
            group=real_group(real_map[filename])
        target=np.isin(tt,TT);theta_deg=theta_deg[target];tt=tt[target]
        for limit in limits:
            keep=theta_deg<limit
            n=np.array([(tt[keep]==v).sum() for v in TT],dtype=float)
            a,b,c,d=n
            if a+b>0 and c+d>0 and b>0:
                p=b/(a+b);o=d/(c+d);ratio=o/p
                sx=math.sqrt(p*(1-p)/(a+b));sy=math.sqrt(o*(1-o)/(c+d))
                se=math.sqrt((sy/p)**2+(o*sx/p**2)**2)
            else:p=o=ratio=se=np.nan
            rows.append(dict(dataset=station,filename=filename,group=group,theta_max_deg=limit,n=int(n.sum()),
                N1234=int(a),N134=int(b),N123=int(c),N13=int(d),
                predicted_P2_miss_pct=100*p,observed_P2_miss_pct=100*o,closure=ratio,closure_se=se))

out=pd.DataFrame(rows)
out.to_csv(OUT/'reconstructed_angle_gate_scan.csv',index=False)
summary=out.groupby(['dataset','group','theta_max_deg'],as_index=False).agg(
    files=('filename','nunique'),median_closure=('closure','median'),
    closure_q25=('closure',lambda x:x.quantile(.25)),closure_q75=('closure',lambda x:x.quantile(.75)),
    total_events=('n','sum'))
summary.to_csv(OUT/'reconstructed_angle_gate_summary.csv',index=False)
print('Files:',out.groupby('dataset').filename.nunique().to_dict())
print(summary.to_string(index=False))
