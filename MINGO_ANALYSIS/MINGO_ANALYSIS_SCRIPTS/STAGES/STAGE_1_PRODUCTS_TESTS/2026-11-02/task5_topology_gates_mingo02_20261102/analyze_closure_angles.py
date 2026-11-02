#!/usr/bin/env python3
"""Read-only Task-5 Mingo02 gate closure and angular diagnostics."""
from pathlib import Path
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path('/home/mingo/mingo-computing')
OUT = Path(__file__).resolve().parent
LAKE = ROOT / 'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
FILES = [
    'postprocessed_mi0226294103822.parquet',
    'postprocessed_mi0226295061956.parquet',
    'postprocessed_mi0226295084545.parquet',
    'postprocessed_mi0226299002330.parquet',
    'postprocessed_mi0226299012419.parquet',
]
GATES = [
    ('all_events', None),
    ('at_most_1_strip_per_plane', 'at_most_1_strip_per_plane'),
    ('at_most_2_adjacent_strips_per_plane', 'at_most_2_adjacent_strips_per_plane'),
    ('at_most_3_adjacent_strips_per_plane', 'at_most_3_adjacent_strips_per_plane'),
    ('at_most_4_adjacent_strips_per_plane', 'at_most_4_adjacent_strips_per_plane'),
    ('any_plane_has_nonadjacent_strips', 'any_plane_has_nonadjacent_strips'),
]
TT_CATS = (1234, 134, 123, 13)
THETA_EDGES = [0, 15, 25, 35, 45, 90]
THETA_LABELS = ['0–15°', '15–25°', '25–35°', '35–45°', '45–90°']
NEEDED = ['tt_task0_raw','tt_task5_post','gate','p1_xpos','p3_xpos','p1_ypos','p3_ypos','event_theta','event_phi']

def ratio(counts):
    a,b,c,d = map(float, counts)
    if a+b <= 0 or c+d <= 0 or a <= 0 or c <= 0:
        return np.nan, np.nan, np.nan, np.nan
    pred = b/(a+b)
    obs = d/(c+d)
    if pred <= 0:
        return pred, obs, np.nan, np.nan
    value = obs/pred
    sp = math.sqrt(pred*(1-pred)/(a+b))
    so = math.sqrt(obs*(1-obs)/(c+d))
    err = math.sqrt((so/pred)**2 + (obs*sp/pred**2)**2)
    return pred, obs, value, err

def gate_mask(frame, needle):
    if needle is None:
        return np.ones(len(frame), dtype=bool)
    return frame['gate'].fillna('').astype(str).str.contains(needle, regex=False).to_numpy()

def counts_for(frame, ttcol, selected):
    tt = pd.to_numeric(frame[ttcol], errors='coerce').to_numpy()
    return [int(np.count_nonzero(selected & (tt == code))) for code in TT_CATS]

def summarize(frame, filename, theta):
    rows=[]
    for gate_name, needle in GATES:
        selected=gate_mask(frame,needle)
        for stage, ttcol in [('task0_raw','tt_task0_raw'),('task5_post','tt_task5_post')]:
            n=counts_for(frame,ttcol,selected)
            p,o,r,e=ratio(n)
            rows.append(dict(filename=filename,gate=gate_name,tt_stage=stage,theta_bin='all',
                n1234=n[0],n134=n[1],n123=n[2],n13=n[3],predicted_p2_miss=p,observed_p2_miss=o,closure_observed_over_predicted=r,closure_se=e))
            tt=pd.to_numeric(frame[ttcol],errors='coerce').to_numpy()
            for i,label in enumerate(THETA_LABELS):
                in_bin=np.isfinite(theta)&(theta>=THETA_EDGES[i])&(theta<THETA_EDGES[i+1])
                nb=counts_for(frame,ttcol,selected&in_bin)
                p,o,r,e=ratio(nb)
                rows.append(dict(filename=filename,gate=gate_name,tt_stage=stage,theta_bin=label,
                    n1234=nb[0],n134=nb[1],n123=nb[2],n13=nb[3],predicted_p2_miss=p,observed_p2_miss=o,closure_observed_over_predicted=r,closure_se=e))
    return rows

closure_rows=[]
summary_lines=[
    'Mingo02 Task-5 topology gates: closure and angle study',
    'Closure definition copied from the previous Mingo01/Mingo00 study:',
    'predicted P2 miss = N134/(N1234+N134); observed P2 miss = N13/(N123+N13); closure = observed/predicted.',
    'Angle-gated closure uses exclusive P1–P3 reference-theta bins; dz=145 mm from the Task-5 z metadata.',
    'All results remain per source file; no HV/time intervals are pooled.', '',
]
with PdfPages(OUT/'MINGO02_task5_gate_closure_theta_phi_2026-11-02.pdf') as pdf:
  for filename in FILES:
    path=LAKE/filename
    before=path.stat()
    frame=pd.read_parquet(path,columns=NEEDED)
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
      raise RuntimeError(f'Input changed while reading: {path}')
    dx=pd.to_numeric(frame.p3_xpos,errors='coerce').to_numpy(float)-pd.to_numeric(frame.p1_xpos,errors='coerce').to_numpy(float)
    dy=pd.to_numeric(frame.p3_ypos,errors='coerce').to_numpy(float)-pd.to_numeric(frame.p1_ypos,errors='coerce').to_numpy(float)
    dz=145.0
    theta=np.degrees(np.arctan2(np.hypot(dx,dy),dz))
    phi=np.degrees(np.arctan2(dy,dx))
    phi=(phi+180)%360-180
    closure_rows.extend(summarize(frame,filename.removeprefix('postprocessed_').removesuffix('.parquet'),theta))

    # Page 1: overall closure by gate, comparing the original Task-0 TT and final Task-5 TT.
    fig, ax=plt.subplots(figsize=(12,6.5))
    x=np.arange(len(GATES)); width=.36
    for offset,stage,color in [(-width/2,'task0_raw','#2468a2'),(width/2,'task5_post','#d66b22')]:
      sub=[r for r in closure_rows if r['filename']==filename.removeprefix('postprocessed_').removesuffix('.parquet') and r['theta_bin']=='all' and r['tt_stage']==stage]
      values=np.array([r['closure_observed_over_predicted'] for r in sub])
      errors=np.array([r['closure_se'] for r in sub])
      ax.errorbar(x+offset,values,yerr=errors,fmt='o',capsize=3,label=stage.replace('_',' '),color=color)
    ax.axhline(1,color='black',lw=1,ls='--')
    ax.set_xticks(x,[g[0].replace('_','\n') for g in GATES],fontsize=8)
    ax.set_ylabel('TT13 closure (observed / predicted P2 miss)')
    ax.set_title(f'{filename}: overall closure by Task-5 topology gate')
    ax.grid(axis='y',alpha=.25);ax.legend();fig.tight_layout();pdf.savefig(fig);plt.close(fig)

    # Pages 2–3: exclusive P1-P3 theta bins; compare raw and final TT stages.
    file_id=filename.removeprefix('postprocessed_').removesuffix('.parquet')
    for page_gates in (GATES[:3], GATES[3:]):
      fig, axes=plt.subplots(1,3,figsize=(17,6),sharey=True)
      for ax,(gate_name,_) in zip(axes,page_gates):
        for stage,color,marker in [('task0_raw','#2468a2','o'),('task5_post','#d66b22','s')]:
          sub=[r for r in closure_rows if r['filename']==file_id and r['gate']==gate_name and r['tt_stage']==stage and r['theta_bin']!='all']
          vals=[r['closure_observed_over_predicted'] for r in sub]
          errs=[r['closure_se'] for r in sub]
          ax.errorbar(np.arange(len(vals)),vals,yerr=errs,fmt=marker+'-',capsize=2,label=stage.replace('_',' '),color=color)
        ax.axhline(1,color='black',lw=1,ls='--')
        ax.set_xticks(range(len(THETA_LABELS)),THETA_LABELS,rotation=30)
        ax.set_title(gate_name.replace('_',' '));ax.grid(alpha=.25);ax.set_xlabel('P1–P3 reference θ')
      fig.suptitle(f'{file_id}: closure by exclusive angle bin',y=.98)
      axes[0].set_ylabel('Closure (observed / predicted)')
      axes[-1].legend(fontsize=8)
      fig.tight_layout(rect=(0,0,1,.93));pdf.savefig(fig);plt.close(fig)

    # Page 4: P1-P3 reference and fitted Task-4 angle distributions per gate.
    fig,axes=plt.subplots(len(GATES),4,figsize=(16,15),sharex='col')
    tt0=pd.to_numeric(frame.tt_task0_raw,errors='coerce').to_numpy()
    tt5=pd.to_numeric(frame.tt_task5_post,errors='coerce').to_numpy()
    # Task-4's TimTrack event angles are stored in radians; plot in degrees.
    fit_theta=np.degrees(pd.to_numeric(frame.event_theta,errors='coerce').to_numpy(float))
    fit_phi=np.degrees(pd.to_numeric(frame.event_phi,errors='coerce').to_numpy(float))
    fit_phi=(fit_phi+180)%360-180
    for row,(gate_name,needle) in enumerate(GATES):
      gm=gate_mask(frame,needle)
      ref=gm & np.isin(tt0,TT_CATS) & np.isfinite(theta) & np.isfinite(phi)
      fit=gm & (tt5==1234) & np.isfinite(fit_theta) & np.isfinite(fit_phi)
      for col,values,mask,bins,label in [
        (0,theta,ref,np.linspace(0,70,36),'P1–P3 θ (degrees)'),
        (1,phi,ref,np.linspace(-180,180,37),'P1–P3 φ (degrees)'),
        (2,fit_theta,fit,np.linspace(0,70,36),'Task-4 fitted θ; TT1234'),
        (3,fit_phi,fit,np.linspace(-180,180,37),'Task-4 fitted φ; TT1234')]:
        ax=axes[row,col]; vals=values[mask]
        if len(vals):
          ax.hist(vals,bins=bins,density=True,histtype='step',lw=1.4,color='#2468a2')
        else: ax.text(.5,.5,'no valid entries',ha='center',va='center',transform=ax.transAxes)
        if col==0: ax.set_ylabel(f'{gate_name.replace("_"," ")}\nDensity')
        if row==0: ax.set_title(label)
        ax.grid(alpha=.18)
      axes[row,0].text(.98,.88,f'N={ref.sum():,}',ha='right',transform=axes[row,0].transAxes,fontsize=8)
      axes[row,2].text(.98,.88,f'N={fit.sum():,}',ha='right',transform=axes[row,2].transAxes,fontsize=8)
    fig.suptitle(f'{file_id}: angle distributions per topology gate\nReference distributions use same P1–P3 estimate for TT1234/134/123/13; fitted distributions use final TT1234 only',y=1.005)
    fig.tight_layout();pdf.savefig(fig);plt.close(fig)

    # Summary per source file, using median across five overlapping/new samples only for descriptive comparison.
    sub=[r for r in closure_rows if r['filename']==file_id and r['theta_bin']=='all']
    summary_lines.append(file_id)
    for r in sub:
      summary_lines.append(f"  {r['gate']} [{r['tt_stage']}]: N1234={r['n1234']}, N134={r['n134']}, N123={r['n123']}, N13={r['n13']}, closure={r['closure_observed_over_predicted']:.3f} ± {r['closure_se']:.3f}" if np.isfinite(r['closure_observed_over_predicted']) else f"  {r['gate']} [{r['tt_stage']}]: insufficient denominator")
    summary_lines.append('')

pd.DataFrame(closure_rows).to_csv(OUT/'closure_by_gate_and_angle.csv',index=False)
(OUT/'CLOSURE_ANGLE_SUMMARY.txt').write_text('\n'.join(summary_lines)+'\n')
print('Created',OUT/'MINGO02_task5_gate_closure_theta_phi_2026-11-02.pdf')
print('Rows',len(closure_rows))
