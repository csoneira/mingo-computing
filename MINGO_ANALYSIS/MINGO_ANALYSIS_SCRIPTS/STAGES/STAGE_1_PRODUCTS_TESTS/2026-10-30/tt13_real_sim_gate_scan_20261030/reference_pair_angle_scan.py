#!/usr/bin/env python3
"""TT13 closure gated on a common P1-P3 angle estimate (read-only)."""
from pathlib import Path
import math, json
import numpy as np
import pandas as pd
ROOT=Path('/home/mingo/mingo-computing')
OUT=Path(__file__).resolve().parent
PARAMS=pd.read_csv(ROOT/'MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv')
PARAMS={r.file_name:r for r in PARAMS.itertuples(index=False)}
MAN=pd.read_csv(OUT/'per_file_closure.csv'); MAN=MAN[MAN.gate=='baseline']
REAL={r.filename:r for r in MAN[MAN.dataset=='MINGO01'].itertuples(index=False)}
TT=(1234,134,123,13); LIMITS=[15,20,25,30,35,40,45]
rows=[]
def ratio(counts):
    a,b,c,d=map(float,counts)
    if a+b==0 or c+d==0 or b==0:return (np.nan,np.nan,np.nan)
    pred=b/(a+b); obs=d/(c+d); r=obs/pred
    sx=math.sqrt(pred*(1-pred)/(a+b));sy=math.sqrt(obs*(1-obs)/(c+d))
    se=math.sqrt((sy/pred)**2+(obs*sx/pred**2)**2)
    return pred,obs,r,se
for station in ['MINGO00','MINGO01']:
    lake=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS'/station/'STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
    for p in sorted(lake.glob('postprocessed_*.parquet')):
        filename=p.stem.removeprefix('postprocessed_')
        if station=='MINGO01' and filename not in REAL:continue
        before=p.stat(); d=pd.read_parquet(p,columns=['tt_task0_raw','p1_xpos','p3_xpos','p1_ypos','p3_ypos'])
        after=p.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise RuntimeError(f'Input changed: {p}')
        if station=='MINGO00':
            prm=PARAMS.get(filename+'.dat')
            if prm is None:continue
            dz=float(prm.z_plane_3-prm.z_plane_1)
            group='param_'+prm.param_hash[:16]
        else:
            # Current MINGO01 geometry config (valid for acquisition date ranges in this sample).
            dz=190.0
            m=REAL[filename]
            group='HV_'+'_'.join(f'{float(getattr(m,f"p{i}_hv_kv")):.4f}' for i in range(1,5))
        dx=pd.to_numeric(d.p3_xpos,errors='coerce').to_numpy(float)-pd.to_numeric(d.p1_xpos,errors='coerce').to_numpy(float)
        dy=pd.to_numeric(d.p3_ypos,errors='coerce').to_numpy(float)-pd.to_numeric(d.p1_ypos,errors='coerce').to_numpy(float)
        theta=np.degrees(np.arctan2(np.hypot(dx,dy),dz))
        tt=pd.to_numeric(d.tt_task0_raw,errors='coerce').to_numpy(float)
        valid=np.isfinite(theta)&np.isfinite(tt)&np.isin(tt,TT)
        theta=theta[valid];tt=tt[valid].astype(int)
        for limit in LIMITS:
            keep=theta<limit
            n=np.array([(tt[keep]==v).sum() for v in TT])
            pred,obs,r,se=ratio(n)
            rows.append(dict(dataset=station,filename=filename,group=group,z13_mm=dz,theta_source='P1-P3 only',theta_max_deg=limit,n=int(n.sum()),
                N1234=int(n[0]),N134=int(n[1]),N123=int(n[2]),N13=int(n[3]),predicted_miss_pct=100*pred,observed_miss_pct=100*obs,closure=r,closure_se=se))
out=pd.DataFrame(rows);out.to_csv(OUT/'reference_pair_angle_scan.csv',index=False)
summary=out.groupby(['dataset','group','theta_max_deg'],as_index=False).agg(files=('filename','nunique'),median_closure=('closure','median'),
    closure_q25=('closure',lambda x:x.quantile(.25)),closure_q75=('closure',lambda x:x.quantile(.75)),total_events=('n','sum'))
summary.to_csv(OUT/'reference_pair_angle_summary.csv',index=False)
for station in ['MINGO00','MINGO01']:
    d=summary[summary.dataset==station]
    print('\n'+station+' — common P1-P3 angle')
    print(d.groupby('theta_max_deg').median_closure.agg(['median','min','max']).round(3).to_string())
