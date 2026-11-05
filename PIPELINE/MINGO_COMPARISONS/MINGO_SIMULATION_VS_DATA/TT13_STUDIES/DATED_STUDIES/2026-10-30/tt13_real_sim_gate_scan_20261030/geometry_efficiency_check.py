#!/usr/bin/env python3
"""Read-only MINGO00 raw TT13 geometry/efficiency model check."""
from pathlib import Path
import json, math
import numpy as np
import pandas as pd
from scipy.stats import chi2 as chi2_dist
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path('/home/mingo/mingo-computing')
OUT=Path(__file__).resolve().parent
TASK_ROOT=ROOT/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1/EVENT_DATA/STEP_1'
RAW_DIRS=[TASK_ROOT/'TASK_1/INPUT_FILES/COMPLETED_DIRECTORY',TASK_ROOT/'TASK_0/OUTPUT_FILES']
SIDECARS=ROOT/'PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES_SIDECARS'
PARAMS=pd.read_csv(ROOT/'PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv')
PARAMS={r.file_name:r for r in PARAMS.itertuples(index=False)}
BOUNDS=(-116.0,116.0,-143.5,143.5)
Z_GEN_MM=100.0
RNG=np.random.default_rng(20261030)

def closure(n):
    a,b,c,d=map(float,n)
    if a+b<=0 or c+d<=0 or b<=0: return (np.nan,)*4
    pmiss_p4=b/(a+b); pmiss_notp4=d/(c+d)
    ratio=pmiss_notp4/pmiss_p4
    sx=math.sqrt(pmiss_p4*(1-pmiss_p4)/(a+b))
    sy=math.sqrt(pmiss_notp4*(1-pmiss_notp4)/(c+d))
    se=math.sqrt(sy**2*squared(1/pmiss_p4)+sx**2*squared(pmiss_notp4/(pmiss_p4**2)))
    return pmiss_p4,pmiss_notp4,ratio,se

def squared(x): return x*x

models=[]; gates=[]; cut_rows=[]
candidates={}
for raw_dir in RAW_DIRS:
    for raw in raw_dir.glob('*.parquet'):
        basename=raw.stem.removeprefix('raw_')+'.dat'
        # Prefer completed Task-1 output, then active Task-1 input, then Task-0 output.
        priority=2 if 'COMPLETED_DIRECTORY' in str(raw) else (1 if 'PROCESSING_DIRECTORY' in str(raw) else 0)
        if basename not in candidates or priority>candidates[basename][0]: candidates[basename]=(priority,raw)
for basename,(_,raw) in sorted(candidates.items()):
    param=PARAMS.get(basename)
    side=SIDECARS/f'sidecar_{basename[:-4]}.parquet'
    if param is None or not side.exists(): continue
    before=raw.stat()
    df=pd.read_parquet(raw,columns=['event_id','tt_task0_raw'])
    truth=pd.read_parquet(side,columns=['event_id','X_gen','Y_gen','Theta_gen','Phi_gen'])
    after=raw.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise RuntimeError(f'Raw input changed during read: {raw}')
    frame=df.merge(truth,on='event_id',how='inner',validate='one_to_one')
    if len(frame)!=len(df): raise RuntimeError(f'Incomplete sidecar join in {basename}: {len(frame)}/{len(df)}')
    tt=frame.tt_task0_raw.to_numpy(dtype=int)
    cohort=np.isin(tt,[1234,134,123,13])
    frame=frame.loc[cohort].reset_index(drop=True); tt=tt[cohort]
    theta=frame.Theta_gen.to_numpy(float); phi=frame.Phi_gen.to_numpy(float)
    zraw=np.array([param.z_plane_1,param.z_plane_2,param.z_plane_3,param.z_plane_4],float)
    z=zraw-zraw[0] # exact Step-2 normalize_to_first_plane=true behavior
    dz=Z_GEN_MM+z[None,:]
    x=frame.X_gen.to_numpy(float)[:,None]+dz*np.tan(theta[:,None])*np.cos(phi[:,None])
    y=frame.Y_gen.to_numpy(float)[:,None]+dz*np.tan(theta[:,None])*np.sin(phi[:,None])
    crosses=(x>=BOUNDS[0])&(x<=BOUNDS[1])&(y>=BOUNDS[2])&(y<=BOUNDS[3])
    eff=np.asarray(json.loads(param.efficiencies),float)
    q=np.zeros_like(x)
    angle=1/np.maximum(np.abs(np.cos(theta)),1e-3)
    for j in range(4):
        # Step 3 Poisson avalanche model: P(Nions>0)=1-exp(-[-ln(1-eff)]/|cos(theta)|)
        q[:,j]=crosses[:,j]*(1-np.power(1-eff[j],angle))
    q2,q4=q[:,1],q[:,3]
    q2_geom=crosses[:,1]*eff[1]; q4_geom=crosses[:,3]*eff[3]
    q2_angle=1-np.power(1-eff[1],angle); q4_angle=1-np.power(1-eff[3],angle)
    q2_const=np.full(len(frame),eff[1]); q4_const=np.full(len(frame),eff[3])
    def model_closure_for(a,b):
        return closure(np.array([(a*b).sum(),((1-a)*b).sum(),(a*(1-b)).sum(),((1-a)*(1-b)).sum()]))[2]
    ratio_geom=model_closure_for(q2_geom,q4_geom)
    ratio_angle=model_closure_for(q2_angle,q4_angle)
    ratio_const=model_closure_for(q2_const,q4_const)
    actual=np.array([(tt==v).sum() for v in (1234,134,123,13)],dtype=float)
    probability=np.column_stack((q2*q4,(1-q2)*q4,q2*(1-q4),(1-q2)*(1-q4)))
    expected=probability.sum(axis=0)
    obs=closure(actual); mod=closure(expected)
    stat=float(np.sum((actual-expected)**2/np.maximum(expected,1e-12)))
    pval=float(chi2_dist.sf(stat,3))
    # Bootstrap the conditional truth-track sample to quantify the finite truth sample uncertainty.
    boots=[]; n=len(frame)
    for _ in range(500):
        ix=RNG.integers(0,n,n)
        boots.append(closure(probability[ix].sum(axis=0))[2])
    model_se=float(np.nanstd(boots,ddof=1))
    combined_se=math.sqrt(obs[3]**2+model_se**2)
    zscore=(obs[2]-mod[2])/combined_se if combined_se else np.nan
    source_status=('task1_completed' if 'COMPLETED_DIRECTORY' in str(raw) else ('task1_processing' if 'PROCESSING_DIRECTORY' in str(raw) else 'task0_output'))
    models.append(dict(file=basename,source_status=source_status,param_hash=param.param_hash,raw_events=len(df),p1p3_cohort=n,
        tt1234=int(actual[0]),tt134=int(actual[1]),tt123=int(actual[2]),tt13=int(actual[3]),
        observed_p2_miss_given_p4_hit=obs[0],observed_p2_miss_given_p4_miss=obs[1],observed_closure=obs[2],observed_closure_se=obs[3],
        model_p2_miss_given_p4_hit=mod[0],model_p2_miss_given_p4_miss=mod[1],model_closure=mod[2],model_track_bootstrap_se=model_se,
        observed_minus_model_z=zscore,geometry_only_closure=ratio_geom,angle_only_closure=ratio_angle,constant_eff_closure=ratio_const,category_chi2=stat,category_pvalue=pval,
        input_eff_p2=eff[1],input_eff_p4=eff[3],theta_median_deg=float(np.degrees(np.median(theta))),
        p2_cross_pct=100*crosses[:,1].mean(),p4_cross_pct=100*crosses[:,3].mean()))
    # Gates in generated theta and P4 geometrical crossing. Do not mix settings.
    theta_deg=np.degrees(theta)
    for limit in [15,20,25,30,35,40,45]:
        mask=theta_deg<limit
        counts=np.array([(tt[mask]==v).sum() for v in (1234,134,123,13)])
        c=closure(counts)
        cut_rows.append(dict(file=basename,param_hash=param.param_hash,theta_max=limit,n=int(mask.sum()),
            tt1234=int(counts[0]),tt134=int(counts[1]),tt123=int(counts[2]),tt13=int(counts[3]),
            predicted_miss=c[0],observed_miss=c[1],closure=c[2],closure_se=c[3]))
    for lo,hi in [(0,15),(15,25),(25,35),(35,45),(45,90)]:
        mask=(theta_deg>=lo)&(theta_deg<hi)
        if mask.sum()<100: continue
        counts=np.array([(tt[mask]==v).sum() for v in (1234,134,123,13)])
        c=closure(counts)
        gates.append(dict(file=basename,param_hash=param.param_hash,gate='theta_deg',low=lo,high=hi,n=int(mask.sum()),
            tt1234=int(counts[0]),tt134=int(counts[1]),tt123=int(counts[2]),tt13=int(counts[3]),
            observed_p2_miss_given_p4_hit=c[0],observed_p2_miss_given_p4_miss=c[1],closure=c[2],closure_se=c[3],
            p4_cross_pct=100*crosses[mask,3].mean(),model_p2_miss=float((1-q2[mask]).mean())))
    for label,mask in [('p4_geometry_crosses',crosses[:,3]),('p4_geometry_misses',~crosses[:,3])]:
        counts=np.array([(tt[mask]==v).sum() for v in (1234,134,123,13)])
        p2miss=int(counts[1]+counts[3]); ngrp=int(counts.sum())
        gates.append(dict(file=basename,param_hash=param.param_hash,gate=label,low=np.nan,high=np.nan,n=ngrp,
            tt1234=int(counts[0]),tt134=int(counts[1]),tt123=int(counts[2]),tt13=int(counts[3]),
            observed_p2_miss_fraction=p2miss/ngrp if ngrp else np.nan,
            closure=np.nan,closure_se=np.nan,p4_cross_pct=100*crosses[mask,3].mean() if ngrp else np.nan,
            model_p2_miss=(1-q2[mask]).mean() if ngrp else np.nan))

pd.DataFrame(models).to_csv(OUT/'geometry_efficiency_model.csv',index=False)
cut_df=pd.DataFrame(cut_rows)
cut_df.to_csv(OUT/'theta_cut_scan.csv',index=False)
cut_summary=cut_df.groupby('theta_max',as_index=False).agg(settings=('file','count'),median_closure=('closure','median'),
    closure_q25=('closure',lambda x:x.quantile(.25)),closure_q75=('closure',lambda x:x.quantile(.75)),median_events=('n','median'))
cut_summary.to_csv(OUT/'theta_cut_summary.csv',index=False)
fig,ax=plt.subplots(figsize=(8,5))
for _,group in cut_df.groupby('file'):
    ax.plot(group.theta_max,group.closure,'-',alpha=.35,color='C0')
for _,r in cut_summary.iterrows():
    ax.errorbar(r.theta_max,r.median_closure,yerr=[[r.median_closure-r.closure_q25],[r.closure_q75-r.median_closure]],fmt='D',color='black',capsize=3)
ax.axhline(1,ls='--',color='.4');ax.set(xlabel='Require generated θ below [degrees]',ylabel='Observed TT13 closure',title='Cumulative angular cuts, per simulated setting')
ax.grid(alpha=.2);fig.tight_layout();fig.savefig(OUT/'theta_cut_scan.png',dpi=160);plt.close(fig)
gate_df=pd.DataFrame(gates)
gate_df.to_csv(OUT/'geometry_and_angle_gates.csv',index=False)
theta_df=gate_df[gate_df.gate=='theta_deg']
summary=theta_df.groupby(['low','high'],as_index=False).agg(
    settings=('file','count'),median_closure=('closure','median'),closure_q25=('closure',lambda x:x.quantile(.25)),
    closure_q75=('closure',lambda x:x.quantile(.75)),median_p4_cross_pct=('p4_cross_pct','median'),
    median_events=('n','median'))
summary.to_csv(OUT/'theta_gate_summary.csv',index=False)
# Paired geometry gate: per-track P2 miss fraction when P4 geometrically crosses or misses.
geo=gate_df[gate_df.gate.isin(['p4_geometry_crosses','p4_geometry_misses'])].pivot(index='file',columns='gate',values='observed_p2_miss_fraction')
fig,axs=plt.subplots(1,2,figsize=(12,5))
for _,r in theta_df.iterrows():
    axs[0].errorbar((r.low+r.high)/2,r.closure,yerr=r.closure_se,fmt='o',alpha=.55,color='C0')
for _,r in summary.iterrows():
    axs[0].errorbar((r.low+r.high)/2,r.median_closure,
        yerr=[[r.median_closure-r.closure_q25],[r.closure_q75-r.median_closure]],fmt='D',color='black',capsize=3)
axs[0].axhline(1,ls='--',color='.4');axs[0].set(xlabel='Generated θ bin center [degrees]',ylabel='Observed TT13 closure',title='Closure by angular gate')
axs[0].grid(alpha=.2)
for _,r in geo.iterrows():
    axs[1].plot([0,1],[100*r['p4_geometry_misses'],100*r['p4_geometry_crosses']],'-o',alpha=.25,color='.45',lw=1)
med=[100*geo['p4_geometry_misses'].median(),100*geo['p4_geometry_crosses'].median()]
axs[1].plot([0,1],med,'-o',color='black',lw=2.5,ms=7,label='median across 11 settings')
axs[1].annotate(f'{med[0]:.1f}%',(0,med[0]),xytext=(3,7),textcoords='offset points')
axs[1].annotate(f'{med[1]:.1f}%',(1,med[1]),xytext=(-38,7),textcoords='offset points')
axs[1].legend(fontsize=8)
axs[1].set_xticks([0,1],['P4 misses active area','P4 crosses active area']);axs[1].set_ylabel('Observed P2 miss fraction [%]')
axs[1].set_title('P2 miss fraction by P4 geometry');axs[1].grid(alpha=.2)
fig.suptitle('MINGO00 raw simulation: geometry and angular gates, each setting kept separate')
fig.tight_layout();fig.savefig(OUT/'gate_decomposition.png',dpi=160);plt.close(fig)
# Plot observed and model closures per parameter set; uncertainty bars are observed counting error.
fig,ax=plt.subplots(figsize=(7,6))
for r in models:
    ax.errorbar(r['model_closure'],r['observed_closure'],yerr=r['observed_closure_se'],fmt='o',capsize=3)
    ax.annotate(r['file'].replace('mi000',''),(r['model_closure'],r['observed_closure']),xytext=(4,3),textcoords='offset points',fontsize=7)
lim=max(1.15,max(max(r['model_closure'],r['observed_closure']+r['observed_closure_se']) for r in models)*1.08)
ax.plot([0,lim],[0,lim],'--',color='.4',label='model = observed');ax.axhline(1,color='.75');ax.axvline(1,color='.75')
ax.set(xlim=(0,lim),ylim=(0,lim),xlabel='Predicted TT13 closure from geometry + Step-3 response',ylabel='Observed raw TT13 closure',title='MINGO00: same trajectory sample, file by file');ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(OUT/'geometry_efficiency_model.png',dpi=160);plt.close(fig)
print(f'Files analyzed: {len(models)}')
print(pd.DataFrame(models)[['file','source_status','p1p3_cohort','observed_closure','model_closure','geometry_only_closure','angle_only_closure','constant_eff_closure','model_track_bootstrap_se','observed_minus_model_z','category_pvalue','p4_cross_pct']].to_string(index=False))
print('Median closures by model:',pd.DataFrame(models)[['observed_closure','model_closure','geometry_only_closure','angle_only_closure','constant_eff_closure']].median().to_dict())
print('Theta cut summary:\n',cut_summary.to_string(index=False))
