#!/usr/bin/env python3
"""Task-5 P2/P3 joint-miss closure by topology gate and P1-P4 angle."""
from pathlib import Path
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path('/home/mingo/mingo-computing')
OUT=Path(__file__).resolve().parent
LAKE=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
FILES=['postprocessed_mi0226294103822.parquet','postprocessed_mi0226295061956.parquet','postprocessed_mi0226295084545.parquet','postprocessed_mi0226299002330.parquet','postprocessed_mi0226299012419.parquet']
GATES=[('all_events',None),('at_most_1_strip_per_plane','at_most_1_strip_per_plane'),('at_most_2_adjacent_strips_per_plane','at_most_2_adjacent_strips_per_plane'),('at_most_3_adjacent_strips_per_plane','at_most_3_adjacent_strips_per_plane'),('at_most_4_adjacent_strips_per_plane','at_most_4_adjacent_strips_per_plane'),('any_plane_has_nonadjacent_strips','any_plane_has_nonadjacent_strips')]
TT=(1234,134,124,14)
EDGES=[0,15,25,35,45,90]
LABELS=['0–15°','15–25°','25–35°','35–45°','45–90°']

def calc(counts):
    a,b,c,d=map(float,counts); n=a+b+c+d
    if n<=0: return (np.nan,)*7
    # Condition on P1 and P4 present: four mutually exclusive P2/P3 hit/miss states.
    e2=(a+c)/n; e3=(a+b)/n
    pred=(1-e2)*(1-e3)
    obs=d/n
    ratio=obs/pred if pred>0 else np.nan
    if not (d>0 and b+d>0 and c+d>0 and np.isfinite(ratio)):
        se=np.nan
    else:
        # Delta-method multinomial uncertainty for d*n / ((b+d)*(c+d)).
        p=np.array([a,b,c,d])/n
        grad=np.array([0.0,-ratio/(p[1]+p[3]),-ratio/(p[2]+p[3]),
                       ratio*(1/p[3]-1/(p[1]+p[3])-1/(p[2]+p[3]))])
        cov=(np.diag(p)-np.outer(p,p))/n
        se=math.sqrt(max(0.0,float(grad@cov@grad)))
    return e2,e3,pred,obs,ratio,se,n

def select_gate(frame,needle):
    return np.ones(len(frame),dtype=bool) if needle is None else frame.gate.fillna('').astype(str).str.contains(needle,regex=False).to_numpy()

rows=[]
with PdfPages(OUT/'MINGO02_task5_joint_miss_closure_by_gate_angle_2026-11-02.pdf') as pdf:
  for filename in FILES:
    path=LAKE/filename
    before=path.stat()
    d=pd.read_parquet(path,columns=['tt_task5_post','gate','p1_xpos','p4_xpos','p1_ypos','p4_ypos'])
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns): raise RuntimeError(f'Input changed: {path}')
    tt=pd.to_numeric(d.tt_task5_post,errors='coerce').to_numpy()
    dx=pd.to_numeric(d.p4_xpos,errors='coerce').to_numpy(float)-pd.to_numeric(d.p1_xpos,errors='coerce').to_numpy(float)
    dy=pd.to_numeric(d.p4_ypos,errors='coerce').to_numpy(float)-pd.to_numeric(d.p1_ypos,errors='coerce').to_numpy(float)
    theta=np.degrees(np.arctan2(np.hypot(dx,dy),435.0))
    phi=(np.degrees(np.arctan2(dy,dx))+180)%360-180
    fid=filename.removeprefix('postprocessed_').removesuffix('.parquet')
    for gate,needle in GATES:
      gm=select_gate(d,needle)
      for angle_bin in ['all']+LABELS:
        am=np.ones(len(d),dtype=bool) if angle_bin=='all' else ((theta>=EDGES[LABELS.index(angle_bin)])&(theta<EDGES[LABELS.index(angle_bin)+1]))
        mask=gm&am
        counts=[int(np.count_nonzero(mask&(tt==code))) for code in TT]
        e2,e3,pred,obs,r,se,n=calc(counts)
        rows.append(dict(filename=fid,gate=gate,theta_bin=angle_bin,theta_source='P1-P4 positions',z14_mm=435,
          n1234=counts[0],n134=counts[1],n124=counts[2],n14=counts[3],conditional_events=sum(counts),
          eff2=e2,eff3=e3,predicted_joint_miss=pred,observed_joint_miss=obs,observed_over_predicted_joint_miss=r,delta_se=se))

    # Page 1: direct joint-miss closure per gate.
    fig,ax=plt.subplots(figsize=(12,6))
    overall=[r for r in rows if r['filename']==fid and r['theta_bin']=='all']
    x=np.arange(len(GATES));vals=np.array([r['observed_over_predicted_joint_miss'] for r in overall]);err=np.array([r['delta_se'] for r in overall])
    ax.errorbar(x,vals,yerr=err,fmt='o',capsize=3,color='#6a3d9a')
    ax.axhline(1,color='black',ls='--',lw=1);ax.set_xticks(x,[g[0].replace('_','\n') for g in GATES],fontsize=8)
    ax.set_ylabel('Observed / independent prediction for P2&P3 joint miss')
    ax.set_title(f'{fid}: joint-miss closure, conditional on P1 and P4')
    ax.grid(axis='y',alpha=.25);fig.tight_layout();pdf.savefig(fig);plt.close(fig)

    # Page 2: P1-P4-angle slices for each gate.
    fig,axes=plt.subplots(2,3,figsize=(15,9),sharex=True,sharey=True)
    for ax,(gate,_) in zip(axes.flat,GATES):
      part=[r for r in rows if r['filename']==fid and r['gate']==gate and r['theta_bin']!='all']
      y=np.array([r['observed_over_predicted_joint_miss'] for r in part]); e=np.array([r['delta_se'] for r in part])
      ax.errorbar(np.arange(len(y)),y,yerr=e,fmt='o-',capsize=2,color='#6a3d9a')
      ax.axhline(1,color='black',ls='--',lw=1);ax.set_title(gate.replace('_',' '),fontsize=9)
      ax.set_xticks(range(len(LABELS)),LABELS,rotation=25);ax.grid(alpha=.2)
    fig.suptitle(f'{fid}: P2/P3 joint-miss closure vs P1–P4 reference θ',y=.98)
    axes[0,0].set_ylabel('Observed / predicted');axes[1,0].set_ylabel('Observed / predicted')
    fig.tight_layout(rect=(0,0,1,.94));pdf.savefig(fig);plt.close(fig)

    # Page 3: direct measured-vs-predicted joint miss, matching the earlier study.
    fig,ax=plt.subplots(figsize=(7.5,7))
    overall=[r for r in rows if r['filename']==fid and r['theta_bin']=='all']
    for r in overall:
      if not np.isfinite(r['predicted_joint_miss']) or not np.isfinite(r['observed_joint_miss']):
        continue
      n=r['conditional_events']; p_obs=r['observed_joint_miss']
      yerr=100*math.sqrt(max(0,p_obs*(1-p_obs)/n)) if n else np.nan
      # Delta uncertainty for the predicted independent joint miss.
      q2=(r['n134']+r['n14'])/n; q3=(r['n124']+r['n14'])/n
      prob=np.array([r['n1234'],r['n134'],r['n124'],r['n14']],dtype=float)/n
      cov=(np.diag(prob)-np.outer(prob,prob))/n
      grad=np.array([0.0,q3,q2,q2+q3])
      xerr=100*math.sqrt(max(0.0,float(grad@cov@grad)))
      ax.errorbar(100*r['predicted_joint_miss'],100*p_obs,xerr=xerr,yerr=yerr,fmt='o',capsize=3,label=r['gate'].replace('_',' '))
      ax.annotate(r['gate'].replace('_',' '),(100*r['predicted_joint_miss'],100*p_obs),xytext=(5,4),textcoords='offset points',fontsize=7)
    finite=[r for r in overall if np.isfinite(r['predicted_joint_miss']) and np.isfinite(r['observed_joint_miss'])]
    lim=max([100*(r['observed_joint_miss']+0.01) for r in finite]+[100*(r['predicted_joint_miss']+0.01) for r in finite]) if finite else 1
    ax.plot([0,lim],[0,lim],'--',color='.4',lw=1)
    ax.set(xlim=(0,lim),ylim=(0,lim),xlabel='Predicted joint miss: (1−e₂)(1−e₃) [%]',ylabel='Measured TT14 / selected TT total [%]',title=f'{fid}: measured vs predicted P2/P3 double miss')
    ax.set_aspect('equal');ax.grid(alpha=.2)
    fig.text(.10,.015,'N = TT1234 + TT134 + TT124 + TT14; conditional on P1 and P4. Error bars are 1σ counting estimates; x/y are correlated.',fontsize=8)
    fig.tight_layout(rect=(0,.04,1,1));pdf.savefig(fig);plt.close(fig)

    # Page 4: P1-P4 common reference angle distributions per gate, four TT classes overlaid.
    fig,axes=plt.subplots(len(GATES),2,figsize=(13,15),sharex='col')
    for row,(gate,needle) in enumerate(GATES):
      gm=select_gate(d,needle)
      for col,values,bins,label in [(0,theta,np.linspace(0,70,36),'P1–P4 θ (degrees)'),(1,phi,np.linspace(-180,180,37),'P1–P4 φ (degrees)')]:
        ax=axes[row,col]
        for code,color in zip(TT,['#222222','#1f77b4','#ff7f0e','#2ca02c']):
          vals=values[gm&(tt==code)&np.isfinite(values)]
          if len(vals): ax.hist(vals,bins=bins,density=True,histtype='step',lw=1.1,label=f'TT{code} (N={len(vals):,})',color=color)
        ax.set_ylabel(gate.replace('_',' ')+'\nDensity',fontsize=8)
        if row==0: ax.set_title(label)
        if row==0 and col==1: ax.legend(fontsize=7)
        ax.grid(alpha=.18)
    fig.suptitle(f'{fid}: common P1–P4 reference angles across TT1234, TT134, TT124, TT14',y=1.005)
    fig.tight_layout();pdf.savefig(fig);plt.close(fig)

out=pd.DataFrame(rows)
out.to_csv(OUT/'joint_miss_closure_by_gate_angle.csv',index=False)
print('Wrote',OUT/'joint_miss_closure_by_gate_angle.csv','rows=',len(out))
print('per-file median closure across gates:')
print(out[out.theta_bin=='all'].groupby('gate').observed_over_predicted_joint_miss.agg(['median','min','max']).round(3).to_string())
