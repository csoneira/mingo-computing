#!/usr/bin/env python3
"""Apply identical Task-5 topology gates and angle closures to M00 and M02."""
from pathlib import Path
import ast, math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path('/home/mingo/mingo-computing')
OUT=Path(__file__).resolve().parent
PARAMS=pd.read_csv(ROOT/'PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv')
SIM=ROOT/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
REAL=ROOT/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
REAL_FILES=['mi0226294103822','mi0226295055246','mi0226295061956','mi0226295084545','mi0226296163247','mi0226298202530','mi0226299002330','mi0226299012419','mi0226299022623','mi0226299071755']
GATES=['all_events','at_most_1_strip_per_plane','at_most_2_adjacent_strips_per_plane','at_most_3_adjacent_strips_per_plane','at_most_4_adjacent_strips_per_plane','any_plane_has_nonadjacent_strips']
TT13=[1234,134,123,13];TT14=[1234,134,124,14]
TH_EDGES=[0,15,25,35,45,90];TH_LABELS=['0–15°','15–25°','25–35°','35–45°','45–90°']

def load_frame(path):
 cols=[f'p{p}_s{s}_qsum' for p in range(1,5) for s in range(1,5)]
 cols += ['tt_task0_raw','tt_task5_post']+[f'p{p}_{xy}pos' for p in range(1,5) for xy in ('x','y')]
 before=path.stat();d=pd.read_parquet(path,columns=cols);after=path.stat()
 if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise RuntimeError(f'Input changed while reading: {path}')
 q=d[[f'p{p}_s{s}_qsum' for p in range(1,5) for s in range(1,5)]].apply(pd.to_numeric,errors='coerce').to_numpy(float).reshape(len(d),4,4)
 active=np.isfinite(q)&(q!=0);counts=active.sum(2);contig=np.ones((len(d),4),bool)
 for p in range(4):
  for i in range(len(d)):
   inds=np.flatnonzero(active[i,p]);contig[i,p]=(len(inds)<=1 or inds[-1]-inds[0]+1==len(inds))
 maxc=counts.max(1);alladj=contig.all(1);anynon=((counts>=2)&~contig).any(1)
 masks={'all_events':np.ones(len(d),bool),'at_most_1_strip_per_plane':maxc<=1,
 'at_most_2_adjacent_strips_per_plane':(maxc<=2)&alladj,'at_most_3_adjacent_strips_per_plane':(maxc<=3)&alladj,
 'at_most_4_adjacent_strips_per_plane':alladj,'any_plane_has_nonadjacent_strips':anynon}
 return d,counts,masks

def ratio13(c):
 a,b,c1,d=map(float,c);denp=a+b;deno=c1+d
 if denp<=0 or deno<=0:return np.nan,np.nan,np.nan,np.nan
 pred=b/denp;obs=d/deno
 if pred<=0:return pred,obs,np.nan,np.nan
 r=obs/pred;sp=math.sqrt(pred*(1-pred)/denp);so=math.sqrt(obs*(1-obs)/deno)
 return pred,obs,r,math.sqrt((so/pred)**2+(obs*sp/pred**2)**2)

def ratio14(c):
 a,b,c1,d=map(float,c);n=a+b+c1+d
 if n<=0:return np.nan,np.nan,np.nan,np.nan
 p=np.array([a,b,c1,d])/n;e2=p[0]+p[2];e3=p[0]+p[1];pred=(1-e2)*(1-e3);obs=p[3]
 if pred<=0:return pred,obs,np.nan,np.nan
 r=obs/pred
 if d<=0:return pred,obs,r,np.nan
 grad=np.array([0.,-r/(p[1]+p[3]),-r/(p[2]+p[3]),r*(1/p[3]-1/(p[1]+p[3])-1/(p[2]+p[3]))])
 cov=(np.diag(p)-np.outer(p,p))/n
 return pred,obs,r,math.sqrt(max(0.,float(grad@cov@grad)))

def counts_for(tt,mask,categories):return [int(np.count_nonzero(mask&(tt==c))) for c in categories]

sim_params=PARAMS[(PARAMS.z_plane_1==0)&(PARAMS.z_plane_2==145)&(PARAMS.z_plane_3==290)&(PARAMS.z_plane_4==435)].copy()
files=[]
for r in sim_params.itertuples(index=False):
 p=SIM/f'postprocessed_{str(r.file_name).removesuffix(".dat")}.parquet'
 if p.exists():files.append(('MINGO00',str(r.file_name).removesuffix('.dat'),p,[0.,145.,290.,435.]))
meta=ROOT/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_specific.csv'
mz=pd.read_csv(meta,usecols=lambda c:c in {'filename_base','z_p1','z_p2','z_p3','z_p4'})
for stem in REAL_FILES:
 p=REAL/f'postprocessed_{stem}.parquet';r=mz[mz.filename_base.astype(str).eq(stem)].iloc[-1]
 z=[float(r[f'z_p{i}']) for i in range(1,5)];z=[v-z[0] for v in z]
 files.append(('MINGO02',stem,p,z))
rows=[]
for dataset,stem,path,z in files:
 d,strip_counts,gatemasks=load_frame(path)
 tt0=pd.to_numeric(d.tt_task0_raw,errors='coerce').to_numpy(float)
 tt5=pd.to_numeric(d.tt_task5_post,errors='coerce').to_numpy(float)
 def theta_phi(a,b):
  dx=pd.to_numeric(d[f'p{b}_xpos'],errors='coerce').to_numpy(float)-pd.to_numeric(d[f'p{a}_xpos'],errors='coerce').to_numpy(float)
  dy=pd.to_numeric(d[f'p{b}_ypos'],errors='coerce').to_numpy(float)-pd.to_numeric(d[f'p{a}_ypos'],errors='coerce').to_numpy(float)
  dz=z[b-1]-z[a-1];th=np.degrees(np.arctan2(np.hypot(dx,dy),dz));ph=(np.degrees(np.arctan2(dy,dx))+180)%360-180
  return th,ph
 th13,_=theta_phi(1,3);th14,_=theta_phi(1,4)
 for gate in GATES:
  base=gatemasks[gate]
  for angle_bin in ['all']+TH_LABELS:
   if angle_bin=='all':sel=base
   else:
    i=TH_LABELS.index(angle_bin);sel=base&np.isfinite(th13)&(th13>=TH_EDGES[i])&(th13<TH_EDGES[i+1])
   for stage,tt in [('task0_raw',tt0),('task5_post',tt5)]:
    c=counts_for(tt,sel,TT13);pred,obs,r,e=ratio13(c)
    rows.append(dict(dataset=dataset,filename=stem,gate=gate,closure='TT13_P2_miss',tt_stage=stage,angle_source='P1-P3',angle_bin=angle_bin,
      n1234=c[0],n134=c[1],n123=c[2],n13=c[3],predicted_miss=pred,observed_miss=obs,closure_ratio=r,closure_se=e))
  for angle_bin in ['all']+TH_LABELS:
   if angle_bin=='all':sel=base
   else:
    i=TH_LABELS.index(angle_bin);sel=base&np.isfinite(th14)&(th14>=TH_EDGES[i])&(th14<TH_EDGES[i+1])
   c=counts_for(tt5,sel,TT14);pred,obs,r,e=ratio14(c)
   rows.append(dict(dataset=dataset,filename=stem,gate=gate,closure='TT14_joint_P2P3_miss',tt_stage='task5_post',angle_source='P1-P4',angle_bin=angle_bin,
     n1234=c[0],n134=c[1],n124=c[2],n14=c[3],predicted_miss=pred,observed_miss=obs,closure_ratio=r,closure_se=e))

out=pd.DataFrame(rows);out.to_csv(OUT/'comparative_gate_closure_mingo00_mingo02.csv',index=False)

with PdfPages(OUT/'MINGO00_vs_MINGO02_task5_gate_closure_2026-11-02.pdf') as pdf:
 fig,ax=plt.subplots(figsize=(13,7))
 a=out[(out.closure=='TT13_P2_miss')&(out.angle_bin=='all')&(out.tt_stage=='task0_raw')]
 colors={'MINGO00':'#2878b5','MINGO02':'#c43c39'}
 for gi,g in enumerate(GATES):
  for ds,off in [('MINGO00',-.12),('MINGO02',.12)]:
   v=a[(a.gate==g)&(a.dataset==ds)].closure_ratio.dropna().to_numpy()
   if len(v):
    x=gi+off+np.linspace(-.05,.05,len(v))
    ax.scatter(x,v,s=18,alpha=.65,color=colors[ds],label=ds if gi==0 else None)
    ax.plot([gi+off-.10,gi+off+.10],[np.median(v)]*2,color=colors[ds],lw=2)
 ax.axhline(1,color='.25',ls='--');ax.set_xticks(range(len(GATES)),[g.replace('_','\n') for g in GATES],fontsize=8)
 ax.set_ylabel('TT13 closure: observed / predicted P2-miss fraction');ax.set_title('Raw Task-0 TT closure by Task-5 gate · every file is a separate point')
 ax.grid(axis='y',alpha=.2);ax.legend();fig.tight_layout();pdf.savefig(fig);plt.close(fig)

 # Task-5-stage TT13 closure by gate, all file-level measurements retained.
 fig,axes=plt.subplots(1,2,figsize=(15,6),sharey=True)
 for ax,ds in zip(axes,['MINGO00','MINGO02']):
  a=out[(out.dataset==ds)&(out.closure=='TT13_P2_miss')&(out.tt_stage=='task5_post')&(out.angle_bin=='all')]
  for gi,g in enumerate(GATES):
   v=a[a.gate==g].closure_ratio.dropna().to_numpy()
   if len(v):
    x=gi+np.linspace(-.18,.18,len(v));ax.scatter(x,v,s=16,alpha=.6,color=colors[ds]);ax.plot([gi-.2,gi+.2],[np.median(v)]*2,color=colors[ds],lw=2)
  ax.axhline(1,color='.25',ls='--');ax.set_xticks(range(len(GATES)),[g.replace('_','\n') for g in GATES],fontsize=7);ax.set_title(ds);ax.grid(axis='y',alpha=.2)
 axes[0].set_ylabel('TT13 closure (Task-5 TT)');fig.suptitle('Every file is a separate point; bold segments are per-file medians by gate')
 fig.tight_layout();pdf.savefig(fig);plt.close(fig)

 # Direct TT14 measured-vs-predicted, one panel per gate, per-file points.
 fig,axes=plt.subplots(2,3,figsize=(14,9),sharex=True,sharey=True)
 for ax,g in zip(axes.flat,GATES):
  a=out[(out.closure=='TT14_joint_P2P3_miss')&(out.angle_bin=='all')&(out.gate==g)]
  for ds in ['MINGO00','MINGO02']:
   q=a[a.dataset==ds]
   ax.scatter(100*q.predicted_miss,100*q.observed_miss,s=19,alpha=.65,color=colors[ds],label=ds if g==GATES[0] else None)
  lim=2.0;ax.plot([0,lim],[0,lim],'--',color='.35');ax.set_xlim(0,lim);ax.set_ylim(0,lim);ax.set_title(g.replace('_',' '),fontsize=9);ax.grid(alpha=.2)
 axes[0,0].set_ylabel('Measured TT14 double miss [%]');axes[1,0].set_ylabel('Measured TT14 double miss [%]')
 for ax in axes[1,:]:ax.set_xlabel('Independent prediction (1−e₂)(1−e₃) [%]')
 axes[0,0].legend(fontsize=8);fig.suptitle('P1/P4-conditioned joint miss · per-file estimates; no pooling')
 fig.tight_layout();pdf.savefig(fig);plt.close(fig)

 # TT13 closure vs exclusive P1-P3 angle; per-file medians summarized with points retained.
 fig,axes=plt.subplots(2,3,figsize=(15,9),sharex=True,sharey=True)
 for ax,g in zip(axes.flat,GATES):
  a=out[(out.closure=='TT13_P2_miss')&(out.tt_stage=='task0_raw')&(out.angle_bin!='all')&(out.gate==g)]
  for ds in ['MINGO00','MINGO02']:
   q=a[a.dataset==ds]
   for _,grp in q.groupby('filename'):
    ax.plot(range(len(TH_LABELS)),grp.set_index('angle_bin').reindex(TH_LABELS).closure_ratio.to_numpy(float),color=colors[ds],alpha=.12,lw=.7)
   med=q.groupby('angle_bin').closure_ratio.median().reindex(TH_LABELS)
   ax.plot(range(len(TH_LABELS)),med.to_numpy(float),marker='o',color=colors[ds],lw=2,label=ds if g==GATES[0] else None)
  ax.axhline(1,color='.35',ls='--');ax.set_xticks(range(len(TH_LABELS)),TH_LABELS,rotation=30);ax.set_title(g.replace('_',' '),fontsize=9);ax.grid(alpha=.2)
 axes[0,0].set_ylabel('TT13 closure');axes[1,0].set_ylabel('TT13 closure');axes[0,0].legend(fontsize=8)
 fig.suptitle('TT13 closure vs exclusive P1–P3 reference angle (z separation from per-file metadata)')
 fig.tight_layout();pdf.savefig(fig);plt.close(fig)

 # Direct TT14 closure vs P1-P4 angle. Sparse zero-count bins remain visible as undefined where denominator is absent.
 fig,axes=plt.subplots(2,3,figsize=(15,9),sharex=True,sharey=True)
 for ax,g in zip(axes.flat,GATES):
  a=out[(out.closure=='TT14_joint_P2P3_miss')&(out.angle_bin!='all')&(out.gate==g)]
  for ds in ['MINGO00','MINGO02']:
   q=a[a.dataset==ds]
   for _,grp in q.groupby('filename'):
    ax.plot(range(len(TH_LABELS)),grp.set_index('angle_bin').reindex(TH_LABELS).closure_ratio.to_numpy(float),color=colors[ds],alpha=.12,lw=.7)
   med=q.groupby('angle_bin').closure_ratio.median().reindex(TH_LABELS)
   ax.plot(range(len(TH_LABELS)),med.to_numpy(float),marker='o',color=colors[ds],lw=2,label=ds if g==GATES[0] else None)
  ax.axhline(1,color='.35',ls='--');ax.set_xticks(range(len(TH_LABELS)),TH_LABELS,rotation=30);ax.set_title(g.replace('_',' '),fontsize=9);ax.grid(alpha=.2)
 axes[0,0].set_ylabel('TT14 observed / predicted');axes[1,0].set_ylabel('TT14 observed / predicted');axes[0,0].legend(fontsize=8)
 fig.suptitle('Direct TT14 joint-miss closure vs P1–P4 reference angle; sparse cells are uncertain')
 fig.tight_layout();pdf.savefig(fig);plt.close(fig)

print('Files:',out.dataset.value_counts().to_dict(),'CSV rows:',len(out))
print('Created comparative closure CSV/PDF')
