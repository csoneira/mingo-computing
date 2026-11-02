#!/usr/bin/env python3
"""Reference-track plane efficiency for vertical, single-strip Mingo02 events."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path('/home/mingo/mingo-computing')
OUT=Path(__file__).resolve().parent
BASE=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1/EVENT_DATA/STEP_1'
LAKE=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
FILES=['mi0226294103822','mi0226295061956','mi0226295084545','mi0226299002330','mi0226299012419']
BOUNDS={'x_min':-116.0,'x_max':116.0,'y_min':-143.5,'y_max':143.5}
THETA_MAX_DEG=15.0

def wilson(k,n,z=1.0):
    if not n:return np.nan,np.nan
    p=k/n; den=1+z*z/n
    ctr=(p+z*z/(2*n))/den
    half=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0.,ctr-half),min(1.,ctr+half)

def active_strip_counts(frame):
    arr=frame[[f'p{p}_s{s}_qsum' for p in range(1,5) for s in range(1,5)]].apply(pd.to_numeric,errors='coerce').to_numpy(float).reshape(len(frame),4,4)
    return (np.isfinite(arr)&(arr!=0)).sum(axis=2)

def fit3(frame, refs, z):
    x=np.column_stack([pd.to_numeric(frame[f'p{p}_xpos'],errors='coerce').to_numpy(float) for p in refs])
    y=np.column_stack([pd.to_numeric(frame[f'p{p}_ypos'],errors='coerce').to_numpy(float) for p in refs])
    zr=np.array([z[p-1] for p in refs],dtype=float)
    valid=np.isfinite(x).all(axis=1)&np.isfinite(y).all(axis=1)
    zbar=zr.mean(); denom=np.sum((zr-zbar)**2)
    sx=np.full(len(frame),np.nan);sy=np.full(len(frame),np.nan)
    if denom<=0:return sx,sy,np.full(len(frame),np.nan)
    ax=np.sum((zr-zbar)*(x-x.mean(axis=1,keepdims=True)),axis=1)/denom
    ay=np.sum((zr-zbar)*(y-y.mean(axis=1,keepdims=True)),axis=1)/denom
    bx=x.mean(axis=1)-ax*zbar;by=y.mean(axis=1)-ay*zbar
    target=next(iter(set(range(1,5))-set(refs)))
    zt=z[target-1]
    xp=ax*zt+bx;yp=ay*zt+by
    theta=np.degrees(np.arctan(np.hypot(ax,ay)))
    valid &= np.isfinite(xp)&np.isfinite(yp)&np.isfinite(theta)
    xp[~valid]=np.nan;yp[~valid]=np.nan;theta[~valid]=np.nan
    return xp,yp,theta

def read_z(file_id):
    path=BASE/'TASK_5/METADATA/task_5_metadata_specific.csv'
    d=pd.read_csv(path,usecols=lambda c:c in {'filename_base','z_p1','z_p2','z_p3','z_p4'})
    row=d[d.filename_base.astype(str).eq(file_id)]
    if row.empty:return [0.,145.,290.,435.]
    vals=[pd.to_numeric(row.iloc[-1].get(f'z_p{i}'),errors='coerce') for i in range(1,5)]
    if any(pd.isna(v) for v in vals):return [0.,145.,290.,435.]
    vals=np.asarray(vals,dtype=float);vals-=vals[0]
    return vals.tolist()

rows=[]
with PdfPages(OUT/'MINGO02_vertical_fiducial_single_reference_efficiency_2026-11-02.pdf') as pdf:
 for file_id in FILES:
    path=LAKE/f'postprocessed_{file_id}.parquet'
    before=path.stat()
    cols=[f'p{p}_s{s}_qsum' for p in range(1,5) for s in range(1,5)]
    cols += [f'p{p}_{xy}pos' for p in range(1,5) for xy in ('x','y')]
    d=pd.read_parquet(path,columns=cols)
    after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise RuntimeError(f'Input changed: {path}')
    sc=active_strip_counts(d)
    z=read_z(file_id)
    # Estimate target-plane crossings from the other three planes only.
    file_rows=[]
    for target in range(1,5):
      refs=[p for p in range(1,5) if p!=target]
      xp,yp,theta=fit3(d,refs,z)
      ref_one=(sc[:,np.array(refs)-1]==1).all(axis=1)
      fid=(xp>=BOUNDS['x_min'])&(xp<=BOUNDS['x_max'])&(yp>=BOUNDS['y_min'])&(yp<=BOUNDS['y_max'])
      selected=ref_one&fid&np.isfinite(theta)&(theta<THETA_MAX_DEG)
      n=int(selected.sum())
      target_strips=sc[:,target-1]
      k_any=int(np.count_nonzero(selected&(target_strips>=1)))
      k_one=int(np.count_nonzero(selected&(target_strips==1)))
      k_multi=int(np.count_nonzero(selected&(target_strips>1)))
      lo,hi=wilson(k_any,n); lo1,hi1=wilson(k_one,n)
      row=dict(filename=file_id,target_plane=target,reference_planes=''.join(map(str,refs)),theta_max_deg=THETA_MAX_DEG,
        reference_single_strip_tracks=n,fiducial_tracks=n,target_hit_any_strip=k_any,target_hit_exactly_one_strip=k_one,target_hit_multiple_strips=k_multi,
        efficiency_any_hit=(k_any/n if n else np.nan),efficiency_any_hit_wilson68_low=lo,efficiency_any_hit_wilson68_high=hi,
        single_strip_response_fraction=(k_one/n if n else np.nan),single_strip_response_wilson68_low=lo1,single_strip_response_wilson68_high=hi1,
        target_multi_fraction_of_fiducial=(k_multi/n if n else np.nan))
      rows.append(row);file_rows.append(row)
    # Per-file plot: per-plane efficiency and single-strip response, preserving source separation.
    fig,ax=plt.subplots(figsize=(10,6))
    x=np.arange(1,5)
    for key,label,color,lo_key,hi_key,offset in [
      ('efficiency_any_hit','Target plane fired (≥1 strip)','#1464a5','efficiency_any_hit_wilson68_low','efficiency_any_hit_wilson68_high',-.08),
      ('single_strip_response_fraction','Target fired in exactly 1 strip','#d17a00','single_strip_response_wilson68_low','single_strip_response_wilson68_high',.08)]:
      vals=np.array([r[key] for r in file_rows],float)
      low=np.array([r[lo_key] for r in file_rows],float);high=np.array([r[hi_key] for r in file_rows],float)
      err=np.vstack([vals-low,high-vals])
      ax.errorbar(x+offset,vals,yerr=err,fmt='o',capsize=3,label=label,color=color)
    ax.set(xticks=x,xticklabels=[f'P{i}' for i in x],ylim=(0,1.05),ylabel='Fraction of fiducial reference tracks',
      title=f'{file_id}: vertical fiducial efficiency from three single-strip reference planes')
    ax.text(.02,.02,'θ < 15°; reference planes each have exactly one active Q_sum strip.\nTrack fitted using the other three planes; target predicted point must lie within ±116 × ±143.5 mm.\nAny-strip hit is plane efficiency; exactly-one-strip fraction is shown separately.',transform=ax.transAxes,fontsize=8,va='bottom')
    ax.grid(axis='y',alpha=.25);ax.legend(loc='best');fig.tight_layout();pdf.savefig(fig);plt.close(fig)

out=pd.DataFrame(rows)
out.to_csv(OUT/'vertical_fiducial_single_reference_efficiency.csv',index=False)
summary=[]
summary.append('Mingo02 vertical-fiducial per-plane efficiency')
summary.append('Selection: theta < 15 degrees; target fiducial acceptance from a straight-line fit through the other three planes; each reference plane has exactly one active strip (finite nonzero Q_sum).')
summary.append('Target hit means >=1 active Q_sum strip; target multi-strip hits remain detected, avoiding biasing efficiency low. Exactly-one-strip target fraction is reported separately.')
summary.append('Active bounds: x=[-116,116] mm, y=[-143.5,143.5] mm. All values are per source file, not pooled.')
summary.append('')
for p in range(1,5):
 x=out[out.target_plane==p]
 vals=x.efficiency_any_hit.dropna();svals=x.single_strip_response_fraction.dropna()
 summary.append(f'P{p}: any-strip efficiency median={vals.median():.3f}, range={vals.min():.3f}–{vals.max():.3f}; exact-one-strip response median={svals.median():.3f}; per-file denominators={", ".join(map(str,x.reference_single_strip_tracks.tolist()))}')
(OUT/'VERTICAL_FIDUCIAL_EFFICIENCY_SUMMARY.txt').write_text('\n'.join(summary)+'\n')
print('\n'.join(summary))
