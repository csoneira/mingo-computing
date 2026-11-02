#!/usr/bin/env python3
"""Acceptance-controlled per-plane efficiency: Mingo02 data vs same-geometry Mingo00 MC."""
from pathlib import Path
import ast
import textwrap
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
ROOT=Path('/home/mingo/mingo-computing')
OUT=Path(__file__).resolve().parent
SIM_LAKE=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
REAL_LAKE=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
PARAMS=ROOT/'MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv'
REAL_FILES=['mi0226294103822','mi0226295055246','mi0226295061956','mi0226295084545','mi0226296163247','mi0226298202530','mi0226299002330','mi0226299012419','mi0226299022623','mi0226299071755']
EXPECTED_Z=(0.0,145.0,290.0,435.0)
THETA_MAX=15.0
FIDUCIAL={1:80.0,2:100.0,3:100.0,4:80.0}

def wilson(k,n,z=1.0):
    if n<=0:return np.nan,np.nan
    p=k/n;den=1+z*z/n;center=(p+z*z/(2*n))/den;half=z*np.sqrt(p*(1-p)/n+z*z/(4*n))/den
    return max(0.,center-half),min(1.,center+half)

def qsum_counts(frame):
    cols=[f'p{p}_s{s}_qsum' for p in range(1,5) for s in range(1,5)]
    x=frame[cols].apply(pd.to_numeric,errors='coerce').to_numpy(float).reshape(len(frame),4,4)
    return (np.isfinite(x)&(x!=0)).sum(axis=2)

def track_for_target(frame,ref_planes,z,target):
    x=np.column_stack([pd.to_numeric(frame[f'p{p}_xpos'],errors='coerce').to_numpy(float) for p in ref_planes])
    y=np.column_stack([pd.to_numeric(frame[f'p{p}_ypos'],errors='coerce').to_numpy(float) for p in ref_planes])
    zr=np.array([z[p-1] for p in ref_planes],float);zt=float(z[target-1])
    zbar=zr.mean();denom=np.sum((zr-zbar)**2)
    if denom<=0:raise ValueError('Reference planes do not span z.')
    xbar=x.mean(axis=1);ybar=y.mean(axis=1)
    sx=np.sum((zr-zbar)*(x-xbar[:,None]),axis=1)/denom
    sy=np.sum((zr-zbar)*(y-ybar[:,None]),axis=1)/denom
    xp=xbar+sx*(zt-zbar);yp=ybar+sy*(zt-zbar)
    theta=np.degrees(np.arctan(np.hypot(sx,sy)))
    finite=np.isfinite(x).all(axis=1)&np.isfinite(y).all(axis=1)&np.isfinite(xp)&np.isfinite(yp)&np.isfinite(theta)
    return xp,yp,theta,finite

def analyze_one(path,source,file_id,z,true_eff=None):
    columns=[f'p{p}_s{s}_qsum' for p in range(1,5) for s in range(1,5)]
    columns += [f'p{p}_{xy}pos' for p in range(1,5) for xy in ('x','y')]
    before=path.stat();df=pd.read_parquet(path,columns=columns);after=path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise RuntimeError(f'Input changed while reading: {path}')
    counts=qsum_counts(df)
    q=df[[f'p{p}_s{s}_qsum' for p in range(1,5) for s in range(1,5)]].apply(pd.to_numeric,errors='coerce').to_numpy(float).reshape(len(df),4,4)
    active=np.isfinite(q)&(q!=0)
    contiguous=np.ones((len(df),4),dtype=bool)
    for p in range(4):
        for i in range(len(df)):
            inds=np.flatnonzero(active[i,p])
            contiguous[i,p]=(len(inds)<=1 or inds[-1]-inds[0]+1==len(inds))
    gates=['all_events','at_most_1_strip_per_plane','at_most_2_adjacent_strips_per_plane',
           'at_most_3_adjacent_strips_per_plane','at_most_4_adjacent_strips_per_plane',
           'any_plane_has_nonadjacent_strips']
    rows=[]
    for target in range(1,5):
        refs=[p for p in range(1,5) if p!=target]
        xp,yp,theta,finite=track_for_target(df,refs,z,target)
        refidx=np.asarray(refs)-1
        ref_hit=(counts[:,refidx]>=1).all(axis=1)
        bound=FIDUCIAL[target]
        common=finite&ref_hit&(theta<THETA_MAX)&(np.abs(xp)<=bound)&(np.abs(yp)<=bound)
        max_ref=counts[:,refidx].max(axis=1)
        adjacent_ref=contiguous[:,refidx].all(axis=1)
        nonadj_ref=((counts[:,refidx]>=2)&~contiguous[:,refidx]).any(axis=1)
        masks={
          'all_events':np.ones(len(df),dtype=bool),
          'at_most_1_strip_per_plane':max_ref<=1,
          'at_most_2_adjacent_strips_per_plane':(max_ref<=2)&adjacent_ref,
          'at_most_3_adjacent_strips_per_plane':(max_ref<=3)&adjacent_ref,
          'at_most_4_adjacent_strips_per_plane':adjacent_ref,
          'any_plane_has_nonadjacent_strips':nonadj_ref,
        }
        for gate in gates:
            selected=common&masks[gate]
            n=int(selected.sum());n_hit=int(np.count_nonzero(selected&(counts[:,target-1]>=1)))
            n_one=int(np.count_nonzero(selected&(counts[:,target-1]==1)))
            n_multi=int(np.count_nonzero(selected&(counts[:,target-1]>1)))
            lo,hi=wilson(n_hit,n);lo1,hi1=wilson(n_one,n)
            rows.append(dict(dataset=source,filename=file_id,target_plane=target,reference_planes=''.join(map(str,refs)),
                reference_only_gate=gate,z_p1=z[0],z_p2=z[1],z_p3=z[2],z_p4=z[3],theta_max_deg=THETA_MAX,
                target_fiducial_halfwidth_mm=bound,eligible_reference_tracks=n,
                target_hit_any_strip=n_hit,target_hit_exactly_one_strip=n_one,target_hit_multiple_strips=n_multi,
                efficiency_any_hit=n_hit/n if n else np.nan,efficiency_any_hit_low68=lo,efficiency_any_hit_high68=hi,
                target_one_strip_fraction=n_one/n if n else np.nan,target_one_strip_low68=lo1,target_one_strip_high68=hi1,
                simulation_input_efficiency=(true_eff[target-1] if true_eff is not None else np.nan)))
    return rows

params=pd.read_csv(PARAMS)
params['stem']=params.file_name.astype(str).str.removesuffix('.dat')
matching=params[(params.z_plane_1==0)&(params.z_plane_2==145)&(params.z_plane_3==290)&(params.z_plane_4==435)].copy()
sim_rows=[]
for row in matching.itertuples(index=False):
    f=SIM_LAKE/f'postprocessed_{row.stem}.parquet'
    if not f.exists():continue
    try: true_eff=ast.literal_eval(row.efficiencies) if isinstance(row.efficiencies,str) else row.efficiencies
    except Exception: true_eff=list(row.efficiencies)
    sim_rows.extend(analyze_one(f,'MINGO00',row.stem,[0.,145.,290.,435.],true_eff))
real_rows=[]
for file_id in REAL_FILES:
    f=REAL_LAKE/f'postprocessed_{file_id}.parquet'
    if not f.exists():raise FileNotFoundError(f)
    meta=ROOT/'MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO02/STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_specific.csv'
    mz=pd.read_csv(meta,usecols=lambda c:c in {'filename_base','z_p1','z_p2','z_p3','z_p4'})
    rr=mz[mz.filename_base.astype(str).eq(file_id)].iloc[-1]
    z=[float(rr[f'z_p{i}']) for i in range(1,5)]
    z=[v-z[0] for v in z]
    if tuple(z)!=EXPECTED_Z:raise ValueError(f'Unexpected Mingo02 geometry for {file_id}: {z}')
    real_rows.extend(analyze_one(f,'MINGO02',file_id,z))
all_rows=sim_rows+real_rows
out=pd.DataFrame(all_rows)
out.to_csv(OUT/'fiducial_efficiency_real_vs_simulation.csv',index=False)

# Keep every simulation setting and real file visible; no event pooling.
GATES=['all_events','at_most_1_strip_per_plane','at_most_2_adjacent_strips_per_plane',
       'at_most_3_adjacent_strips_per_plane','at_most_4_adjacent_strips_per_plane',
       'any_plane_has_nonadjacent_strips']
with PdfPages(OUT/'MINGO02_fiducial_plane_efficiency_vs_MINGO00_2026-11-02.pdf') as pdf:
    fig=plt.figure(figsize=(11,8.5));page_ax=fig.add_subplot(111);page_ax.axis('off')
    page_ax.text(.04,.975,"Acceptance-controlled per-plane efficiency: MINGO02 vs MINGO00",va='top',fontsize=17,weight='bold',transform=page_ax.transAxes)
    summary_rows=[]
    for plane in range(1,5):
      sim=out[(out.dataset=='MINGO00')&(out.target_plane==plane)&(out.reference_only_gate=='all_events')]
      real=out[(out.dataset=='MINGO02')&(out.target_plane==plane)&(out.reference_only_gate=='all_events')]
      summary_rows.append([f'P{plane}',f'{real.efficiency_any_hit.median():.3f}  ({real.efficiency_any_hit.min():.3f}–{real.efficiency_any_hit.max():.3f})',
        f'{sim.simulation_input_efficiency.median():.3f}  ({sim.simulation_input_efficiency.min():.3f}–{sim.simulation_input_efficiency.max():.3f})',
        f'{sim.efficiency_any_hit.median():.3f}',f'{(sim.efficiency_any_hit-sim.simulation_input_efficiency).median():+.3f}'])
    table=page_ax.table(cellText=summary_rows,colLabels=['Target','MINGO02 efficiency\nmedian (file range)','MINGO00 configured\nefficiency median (range)','MINGO00 measured\nmedian','MC median\n(measured − input)'],
      cellLoc='center',colLoc='center',bbox=[.035,.62,.93,.22],colWidths=[.09,.24,.25,.2,.22])
    table.auto_set_font_size(False);table.set_fontsize(9)
    txt=(f"Inputs: {out[out.dataset=='MINGO00'].filename.nunique()} distinct MINGO00 settings and "
      f"{out[out.dataset=='MINGO02'].filename.nunique()} separate MINGO02 Task-5 files. No events or files are pooled.\n\n"
      "Per target plane, fit a straight track from the other three planes and predict the target crossing. Require theta < 15° and "
      "|X|, |Y| <= 80 mm for P1/P4 or <= 100 mm for P2/P3. Each topology gate is applied only to the three reference planes, "
      "so the target response does not select its own denominator. A target is detected by >=1 finite, nonzero Q_sum strip; "
      "multi-strip hits count as detected. Error bars in following pages are Wilson 68% intervals.\n\n"
      "MINGO00 input efficiencies span deliberately different simulation settings; they are a method/baseline check, not a run-matched prediction. "
      "The median measured-minus-input bias is small, while the MINGO02 P2/P3 central values are higher than the MINGO00 input medians. "
      "Do not interpret the full MC range as a statistical uncertainty. The exact-one-reference gate has insufficient MINGO00 statistics "
      "in many settings; those empty estimates remain undefined. Geometry z=[0,145,290,435] mm.")
    wrapped='\n'.join(textwrap.fill(paragraph,width=112) for paragraph in txt.split('\n'))
    page_ax.text(.045,.56,wrapped,va='top',fontsize=10.5,linespacing=1.35,transform=page_ax.transAxes);pdf.savefig(fig);plt.close(fig)
    for plane in range(1,5):
      fig,axes=plt.subplots(2,3,figsize=(15,9),sharey=True)
      for ax,gate in zip(axes.flat,GATES):
        sim=out[(out.dataset=='MINGO00')&(out.target_plane==plane)&(out.reference_only_gate==gate)].copy().sort_values('filename')
        real=out[(out.dataset=='MINGO02')&(out.target_plane==plane)&(out.reference_only_gate==gate)].copy().sort_values('filename')
        sx=np.arange(len(sim));rx=np.arange(len(real))+len(sim)+1
        sv=sim.efficiency_any_hit.to_numpy(float);truth=sim.simulation_input_efficiency.to_numpy(float)
        serr=np.vstack([sv-sim.efficiency_any_hit_low68.to_numpy(float),sim.efficiency_any_hit_high68.to_numpy(float)-sv])
        ax.errorbar(sx,sv,yerr=serr,fmt='o',capsize=1.5,color='#2878b5',ms=3,label='MINGO00 estimated')
        ax.scatter(sx,truth,marker='x',s=17,color='#153f62',label='MINGO00 configured truth')
        rv=real.efficiency_any_hit.to_numpy(float)
        rerr=np.vstack([rv-real.efficiency_any_hit_low68.to_numpy(float),real.efficiency_any_hit_high68.to_numpy(float)-rv])
        ax.errorbar(rx,rv,yerr=rerr,fmt='s',capsize=2,color='#c43c39',ms=3,label='MINGO02 estimated')
        if len(sx):ax.axvline(len(sx)-.5,color='.6',lw=.8,ls=':')
        ax.set_title(gate.replace('_',' '),fontsize=9);ax.set_ylim(0,1.03);ax.grid(axis='y',alpha=.2)
        if len(rx):
          ticks=list(sx[::max(1,len(sx)//5)])+list(rx)
          labels=[f'MC{int(i)+1}' for i in ticks if i < len(sim)]+[f'D{str(s)[-4:]}' for s in real.filename]
          # Use compact identifiers: full filename-to-index mapping is in the CSV.
          ax.set_xticks(ticks,labels,rotation=65,fontsize=6)
      axes[0,0].legend(fontsize=7,loc='best')
      fig.suptitle(f'P{plane}: per-file efficiency within target fiducial ±{FIDUCIAL[plane]} mm; θ < 15°\nGate selection is reference-only to avoid cutting on target response',y=1.02)
      fig.tight_layout();pdf.savefig(fig);plt.close(fig)

summary=['Acceptance-controlled per-plane efficiency: MINGO02 vs MINGO00','',
 'Cuts: target-specific |X|,|Y| <=80 mm for P1/P4 and <=100 mm for P2/P3; theta<15 degrees; straight track fitted from the other three planes.',
 'Each gate is applied only to reference planes; target plane response is measured as >=1 active strip. Multi-strip target hits remain detections.',
 'All MINGO00 simulation settings and MINGO02 files remain separate; no event pooling.','']
for plane in range(1,5):
  for gate in GATES:
    s=out[(out.dataset=='MINGO00')&(out.target_plane==plane)&(out.reference_only_gate==gate)]
    r=out[(out.dataset=='MINGO02')&(out.target_plane==plane)&(out.reference_only_gate==gate)]
    sv=s[s.eligible_reference_tracks>=50];rv=r[r.eligible_reference_tracks>=50]
    if len(sv): bias=np.nanmedian(sv.efficiency_any_hit-sv.simulation_input_efficiency)
    else: bias=np.nan
    summary.append(f'P{plane} {gate}: usable M00 settings (Nref>=50)={len(sv)}/{len(s)}; median MC bias={bias:+.3f}; M02 usable files={len(rv)}/{len(r)}; M02 per-file efficiency median/range={rv.efficiency_any_hit.median():.3f}/{rv.efficiency_any_hit.min():.3f}-{rv.efficiency_any_hit.max():.3f}' if len(rv) else f'P{plane} {gate}: usable M00 settings={len(sv)}/{len(s)}; no M02 file with Nref>=50')
(OUT/'FIDUCIAL_REAL_SIM_SUMMARY.txt').write_text('\n'.join(summary)+'\n')
print('\n'.join(summary))
print('Rows:',len(out),'simulation settings:',out[out.dataset=='MINGO00'].filename.nunique(),'real files:',out[out.dataset=='MINGO02'].filename.nunique())
