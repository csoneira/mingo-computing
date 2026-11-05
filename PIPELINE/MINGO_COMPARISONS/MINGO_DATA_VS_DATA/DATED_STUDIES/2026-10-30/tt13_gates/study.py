from pathlib import Path
import json,csv,collections,datetime as dt,math
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path('/home/mingo/mingo-computing/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE')
OUT=Path(__file__).resolve().parent
manifest=Path(__file__).resolve().parents[6]/'MINGO_DATA_VS_DATA'/'DATED_STUDIES'/'2026-10-29'/'tt13_closure'/'matched_source_records.json'
records=[r for r in json.loads(manifest.read_text()) if r['stage']=='Coincidence raw']
GATES={'baseline':'Task-5 available events','spatial_chi2_lt5':'Spatial χ² < 5 (exploratory; TT13 saturated fit)','timtrack_chi2_lt10':'TimTrack χ² < 10 (exploratory; TT-dependent dof)','middle_P1_P3':'P1 and P3: exactly one middle strip','middle_all_active':'Every active plane: exactly one middle strip (selection-dependent)'}
TT=[1234,134,123,13];summary=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64));times=[];audit=[];quality=[]
for index,r in enumerate(records):
 p=ROOT/f"postprocessed_{r['filename']}.parquet"
 if not p.exists():audit.append(dict(file=str(p),status='missing'));continue
 names=pq.read_schema(p).names
 qcols=[f'p{plane}_s{strip}_qsum_cal' for plane in range(1,5) for strip in range(1,5)]
 required=['tt_task0_raw','event_det_chi2_pos','event_tim_th_chi']+qcols
 missing=[c for c in required if c not in names]
 if missing:audit.append(dict(file=str(p),status='missing_columns',missing=missing));continue
 cols=required+(['tt_task3_list'] if 'tt_task3_list' in names else [])
 df=pd.read_parquet(p,columns=cols)
 # Keep all masks on exactly the same derived file population.
 tt=pd.to_numeric(df.tt_task0_raw,errors='coerce').to_numpy()
 target=np.isin(tt,TT)
 if not target.any():continue
 df=df.loc[target];tt=tt[target]
 charge=df[qcols].to_numpy(dtype=float).reshape(-1,4,4)
 hits=np.isfinite(charge)&(charge>0)
 middle=(hits.sum(axis=2)==1)&(hits[:,:,1]|hits[:,:,2])
 active=hits.any(axis=2)
 central_refs=middle[:,0]&middle[:,2]
 central_all=central_refs&np.all(~active|middle,axis=1)
 chi=df.event_det_chi2_pos.to_numpy(dtype=float);tim=df.event_tim_th_chi.to_numpy(dtype=float)
 masks={'baseline':np.ones(len(df),dtype=bool),'spatial_chi2_lt5':np.isfinite(chi)&(chi>=0)&(chi<5),'timtrack_chi2_lt10':np.isfinite(tim)&(tim>=0)&(tim<10),'middle_P1_P3':central_refs,'middle_all_active':central_all}
 key=tuple(r['hv'])
 for gate,mask in masks.items():
  counts=np.array([np.sum(mask&(tt==t)) for t in TT])
  summary[(key,gate)]+=counts
  times.append(dict(filename=r['filename'],start=r['start'],end=r['end'],gate=gate,hv=key,counts=counts.tolist()))
 for t in TT:
  v=chi[tt==t];v=v[np.isfinite(v)]
  quality.append(dict(filename=r['filename'],tt=t,N=int((tt==t).sum()),finite_spatial_chi2=len(v),spatial_chi2_near_zero=int((v<1e-12).sum()),finite_timing_chi2=int(np.isfinite(tim[tt==t]).sum())))
 audit.append(dict(file=str(p),status='used',rows=len(df),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns))
 if index%30==0:print('Read',index+1,'/',len(records),flush=True)
def result(key,gate,counts):
 a,b,c,d=map(int,counts)
 if not(a+b and c+d):return None
 x=b/(a+b);y=d/(c+d)
 return dict(p1_kv=key[0],p2_kv=key[1],gate=gate,N1234=a,N134=b,N123=c,N13=d,predicted_percent=100*x,observed_percent=100*y,xerr=100*math.sqrt(x*(1-x)/(a+b)),yerr=100*math.sqrt(y*(1-y)/(c+d)),ratio=y/x if x else float('nan'))
rows=[r for (key,g),counts in sorted(summary.items()) if (r:=result(key,g,counts))]
for name,data in [('by_hv',rows),('chi2_population_audit',quality)]:
 with (OUT/f'{name}.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
(OUT/'file_audit.json').write_text(json.dumps(audit,indent=2));(OUT/'per_file_counts.json').write_text(json.dumps(times,indent=2))
with PdfPages(OUT/'tt13_gate_comparison.pdf') as pdf:
 fig,axs=plt.subplots(2,3,figsize=(16,10))
 for ax,(gate,label) in zip(axs.flat,GATES.items()):
  rr=[r for r in rows if r['gate']==gate]
  for r in rr:
   ax.errorbar(r['predicted_percent'],r['observed_percent'],xerr=r['xerr'],yerr=r['yerr'],fmt='o',capsize=2)
   ax.annotate(f"{r['p1_kv']:.3f}",(r['predicted_percent'],r['observed_percent']),xytext=(4,4),textcoords='offset points',fontsize=8)
  hi=max(max(r['predicted_percent']+r['xerr'],r['observed_percent']+r['yerr']) for r in rr)*1.15
  ax.plot([0,hi],[0,hi],'--',color='.4');ax.set(xlim=(0,hi),ylim=(0,hi),title=label,xlabel='Predicted P2 miss [%]',ylabel='Observed P2 miss [%]');ax.grid(alpha=.2);ax.set_aspect('equal')
 axs.flat[-1].axis('off');axs.flat[-1].text(0,.9,'Same available Task-5 files in every panel.\nLabels: P1 HV [kV]; P2–P4 = 5.65 kV.\nError bars: 1σ counting uncertainties.\n\nTwo-plane spatial χ² is degenerate.\nRaw χ² also changes meaning with hit multiplicity.\nThese gates do not establish a pure muon sample.\n\nMiddle-strip selection: positive calibrated Qsum,\nexactly one hit strip, strip 2 or 3.',va='top',fontsize=11)
 fig.suptitle('TT13 closure: separate quality/topology selections on derived Task-5 data');fig.tight_layout(rect=(0,0,1,.96));fig.savefig(OUT/'tt13_gate_scatter.png',dpi=180);pdf.savefig(fig);plt.close(fig)
 fig,ax=plt.subplots(figsize=(12,6))
 for gate,label in GATES.items():
  rr=sorted([r for r in rows if r['gate']==gate],key=lambda r:r['p1_kv']);ax.errorbar([r['p1_kv'] for r in rr],[r['ratio'] for r in rr],yerr=[r['ratio']*math.sqrt((r['yerr']/r['observed_percent'])**2+(r['xerr']/r['predicted_percent'])**2) for r in rr],fmt='o-',capsize=3,label=gate)
 ax.axhline(1,ls='--',color='.4');ax.set(xlabel='P1 HV [kV]',ylabel='Observed / predicted P2 miss probability',title='Gate comparison at fixed HV settings');ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(OUT/'tt13_gate_ratios.png',dpi=180);pdf.savefig(fig);plt.close(fig)
print('Used files',sum(a['status']=='used' for a in audit),'missing',sum(a['status']!='used' for a in audit))
for r in rows:print(f"P1={r['p1_kv']:.4f} {r['gate']:25} pred={r['predicted_percent']:.3f} obs={r['observed_percent']:.3f} ratio={r['ratio']:.3f} counts={r['N1234']},{r['N134']},{r['N123']},{r['N13']}")
