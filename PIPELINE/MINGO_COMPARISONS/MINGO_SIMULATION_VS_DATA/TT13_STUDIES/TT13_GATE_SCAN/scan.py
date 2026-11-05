#!/usr/bin/env python3
"""Read-only per-setting TT13 closure, gate sensitivity and per-plane/TT charge spectra."""
from pathlib import Path
import argparse,csv,json,collections,math
import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh').exists())
TT=(1234,134,123,13)
def masks(frame,config):
 q=frame[[f'p{p}_s{s}_qsum_cal' for p in range(1,5) for s in range(1,5)]].to_numpy(float).reshape(-1,4,4)
 hit=np.isfinite(q)&(q>0);central=(hit.sum(2)==1)&(hit[:,:,1]|hit[:,:,2]);active=hit.any(2)
 spatial=frame.event_det_chi2_pos.to_numpy(float);tim=frame.event_tim_th_chi.to_numpy(float)
 low=lambda values,limit: np.isfinite(values)&(values>=0)&(values<limit)
 refs=central[:,0]&central[:,2]
 gates={'baseline':np.ones(len(frame),bool),'spatial_chi2_lt5':low(spatial,config['spectrum_spatial_chi2_max']),
        'timtrack_chi2_lt10':low(tim,config['spectrum_timtrack_chi2_max']),
        'middle_P1_P3':refs,'middle_all_active':refs&np.all(~active|central,axis=1)}
 scans={}
 for kind,values in [('spatial',spatial),('timtrack',tim)]:
  for limit in config[kind+'_chi2_thresholds']:scans[(kind,float(limit))]=low(values,limit)
 p1=frame.p1_qsum.to_numpy(float);p3=frame.p3_qsum.to_numpy(float)
 for limit in config['reference_charge_minimums']:
  scans[('reference_charge_min',float(limit))]=np.isfinite(p1)&np.isfinite(p3)&(p1>limit)&(p3>limit)&(p1<config['reference_charge_maximum'])&(p3<config['reference_charge_maximum'])
 return gates,scans

def named_selections(gates, scans):
 """Return every named gate and scanned threshold as a stable plot label."""
 selections=dict(gates)
 for (kind,threshold),mask in sorted(scans.items()):
  value=f'{threshold:g}'.replace('.','p').replace('-','m')
  selections[f'{kind}_chi2_lt_{value}' if kind in ('spatial','timtrack') else f'{kind}_{value}']=mask
 return selections

def estimate(counts):
 a,b,c,d=map(int,counts)
 if not(a+b and c+d):return dict(predicted_percent=np.nan,observed_percent=np.nan,ratio=np.nan,ratio_se=np.nan)
 x=b/(a+b);y=d/(c+d);sx=math.sqrt(x*(1-x)/(a+b));sy=math.sqrt(y*(1-y)/(c+d))
 ratio=y/x if x else np.nan
 se=math.sqrt(sy**2/x**2+y**2*sx**2/x**4) if x and all(v>0 for v in (a,b,c,d)) else np.nan
 return dict(predicted_percent=100*x,observed_percent=100*y,ratio=ratio,ratio_se=se)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--real-manifest',type=Path,help='Previous per-file HV assignment; prevents mixing scan settings')
 parser.add_argument('--config',type=Path,default=Path(__file__).with_name('config.yaml'));parser.add_argument('--stations',default='0,1')
 args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True);cfg=yaml.safe_load(args.config.read_text())
 if cfg['charge_bins']<1 or not cfg['charge_limits'][0]<cfg['charge_limits'][1]:raise ValueError('Invalid bins/limits')
 mapping={}
 truth={}
 parameters=ROOT/'PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv'
 if parameters.exists():
  for r in csv.DictReader(parameters.open()):
   try:truth['param_'+r['param_hash'][:16]]=json.loads(r['efficiencies'])
   except (KeyError,ValueError,TypeError):continue
 if args.real_manifest:
  mapping={r['filename']:r for r in json.loads(args.real_manifest.read_text()) if r['stage']=='Coincidence raw'}
 bins=np.linspace(*cfg['charge_limits'],int(cfg['charge_bins'])+1)
 counts=collections.defaultdict(lambda:np.zeros(4,dtype=np.int64))
 # Population axis: 0 passes the gate, 1 fails it.  Keeping both makes the
 # selection's effect visible without changing the exact-TT denominator.
 hist=collections.defaultdict(lambda:np.zeros((2,4,4,len(bins)-1),np.int64))
 samples=collections.defaultdict(lambda:np.zeros((2,4,4),np.int64));exposure=collections.defaultdict(float);missing_exposure=set();audit=[];used=collections.Counter()
 needed=['tt_task0_raw','param_hash','event_det_chi2_pos','event_tim_th_chi']+[f'p{p}_qsum' for p in range(1,5)]+[f'p{p}_s{s}_qsum_cal' for p in range(1,5) for s in range(1,5)]
 for station in map(int,args.stations.split(',')):
  stationroot=ROOT/f'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO{station:02d}'
  lake=stationroot/'STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
  metadata=stationroot/'STAGE_1/EVENT_DATA/STEP_1/TASK_0/METADATA/task_0_metadata_specific.csv'
  metadata={r['filename_base']:r for r in csv.DictReader(metadata.open())} if metadata.exists() else {}
  for path in sorted(lake.glob('postprocessed_*.parquet')):
   fn=path.stem.removeprefix('postprocessed_')
   if station!=0 and mapping and fn not in mapping:continue
   try:
    before=path.stat();frame=pd.read_parquet(path,columns=needed)
   except Exception as e:audit.append(dict(path=str(path),status='unavailable',detail=str(e)));continue
   # Do not mix differing simulated parameter sets or real HV settings.
   if station==0:
    hashes=frame.param_hash.dropna().astype(str).unique()
    if len(hashes)!=1:raise ValueError(f'Expected one simulation parameter set in {path}')
    group='param_'+hashes[0][:16]
   elif fn in mapping:group='HV_'+'_'.join(f'{float(x):.4f}' for x in mapping[fn]['hv'][:4])
   else:group=fn
   dataset=f'MINGO{station:02d}';key=(dataset,group)
   seconds=float(metadata.get(fn,{}).get('coincidence_active_seconds') or 0)
   exposure[key]+=seconds
   if seconds<=0:missing_exposure.add(key)
   target=frame.tt_task0_raw.isin(TT);frame=frame.loc[target];tt=frame.tt_task0_raw.to_numpy()
   gates,scans=masks(frame,cfg)
   # Full threshold scans are kept in the numeric CSV.  The charge-spectrum
   # report compares pass/fail for each distinct named gate, avoiding dozens of
   # near-duplicate spectrum pages per setting.
   selections=named_selections(gates,{})
   for gate,mask in gates.items():
    counts[(dataset,group,'gate',gate,0)]+=np.array([np.sum(mask&(tt==t)) for t in TT])
   for label,mask in selections.items():
    for col,t in enumerate(TT):
     tt_mask=tt==t
     for population,pop_mask in enumerate((mask,~mask)):
      selected=frame.loc[tt_mask&pop_mask]
      for plane in range(4):
       q=selected[f'p{plane+1}_qsum'].to_numpy(float);valid=np.isfinite(q)&(q!=0)
       hist[(dataset,group,label)][population,plane,col]+=np.histogram(q[valid],bins)[0]
       samples[(dataset,group,label)][population,plane,col]+=valid.sum()
   for (kind,value),mask in scans.items():counts[(dataset,group,'scan',kind,value)]+=np.array([np.sum(mask&(tt==t)) for t in TT])
   used[dataset]+=1
   after=path.stat()
   if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise RuntimeError(f'Input changed while reading: {path}')
   audit.append(dict(path=str(path),status='used',dataset=dataset,group=group,seconds=seconds))
   if used[dataset]%30==0:print(dataset,'read',used[dataset],flush=True)
 rows=[]
 for (dataset,group,kind,gate,value),n in sorted(counts.items()):
  baseline=counts[(dataset,group,'gate','baseline',0)]
  retention={f'retention_TT{t}_percent':100*int(count)/int(total) if total else np.nan for t,count,total in zip(TT,n,baseline)}
  retention['retention_selected_TTs_percent']=100*int(n.sum())/int(baseline.sum()) if baseline.sum() else np.nan
  truth_fields={f'simulation_input_eff_P{p+1}_percent':100*truth[group][p] if dataset=='MINGO00' and group in truth else np.nan for p in range(4)}
  rows.append(dict(dataset=dataset,group=group,kind=kind,gate=gate,threshold=value,**truth_fields,**dict(zip(['N1234','N134','N123','N13'],map(int,n))),**estimate(n),**retention))
 if rows:
  with (out/'closure_and_scan.csv').open('w') as f:
   writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 (out/'input_audit.json').write_text(json.dumps(audit,indent=2));(out/'config_used.yaml').write_text(yaml.safe_dump(cfg))
 with PdfPages(out/'charge_spectra_and_gate_scan.pdf') as pdf:
  for (dataset,group,gate),h in sorted(hist.items()):
   fig,axes=plt.subplots(4,4,figsize=(15,12),sharex=True)
   seconds=0 if (dataset,group) in missing_exposure else exposure[(dataset,group)]
   for plane in range(4):
    for col,t in enumerate(TT):
     ax=axes[plane,col]
     pass_values=h[0,plane,col]/np.diff(bins);fail_values=h[1,plane,col]/np.diff(bins)
     if seconds>0:pass_values=pass_values/seconds;fail_values=fail_values/seconds
     if np.any(pass_values>0):
      ax.stairs(pass_values,bins,color=f'C{plane}',label=f'Passed (N={samples[(dataset,group,gate)][0,plane,col]})')
     if np.any(fail_values>0):
      ax.stairs(fail_values,bins,color=f'C{plane}',linestyle='--',label=f'Failed (N={samples[(dataset,group,gate)][1,plane,col]})')
     ax.set_yscale('log')
     positive=np.concatenate((pass_values[pass_values>0],fail_values[fail_values>0]))
     if positive.size:ax.set_ylim(bottom=max(float(positive.min())*.5,1e-12))
     else:ax.set_ylim(1e-8 if seconds>0 else .1,1)
     if not positive.size:ax.text(.5,.5,'No nonzero entries in display range',transform=ax.transAxes,ha='center',fontsize=8)
     ax.set_title(f'P{plane+1} · TT{t}',fontsize=9)
     ax.grid(alpha=.15)
     if positive.size:ax.legend(fontsize=6,loc='best')
     if col==0:ax.set_ylabel('Hz / charge unit' if seconds>0 else 'Counts / charge unit')
     if plane==3:ax.set_xlabel('Canonical plane charge (pN_qsum)')
   fig.suptitle(f'{dataset} · {group}\n{gate}: solid = passes, dashed = fails · zero/nonfinite charges omitted; active exposure {seconds:.0f} s')
   fig.tight_layout(rect=(0,0,1,.94));directory=out/dataset/group;directory.mkdir(parents=True,exist_ok=True)
   fig.savefig(directory/f'{gate}_charge_spectra.png',dpi=130);pdf.savefig(fig);plt.close(fig)
  for dataset,group in sorted(exposure):
   rr=[r for r in rows if r['dataset']==dataset and r['group']==group and r['kind']=='scan']
   fig,axes=plt.subplots(1,3,figsize=(14,4))
   for ax,kind in zip(axes,['spatial','timtrack','reference_charge_min']):
    selected=[r for r in rr if r['gate']==kind and np.isfinite(r['ratio']) and np.isfinite(r['ratio_se'])]
    ax.errorbar([r['threshold'] for r in selected],[r['ratio'] for r in selected],yerr=[r['ratio_se'] for r in selected],fmt='o-',capsize=3)
    if kind!='reference_charge_min':ax.set_xscale('log')
    ax.axhline(1,ls='--',color='.4');ax.set(title=kind,xlabel='Gate threshold',ylabel='Observed / predicted miss');ax.grid(alpha=.2)
   fig.suptitle(f'{dataset} · {group} · exploratory gate sensitivity; no automatic cut optimization')
   fig.tight_layout(rect=(0,0,1,.9));directory=out/dataset/group;directory.mkdir(parents=True,exist_ok=True);fig.savefig(directory/'gate_scan.png',dpi=140);pdf.savefig(fig);plt.close(fig)
  datasets=sorted(used)
  if datasets:
   gate_names=['baseline','spatial_chi2_lt5','timtrack_chi2_lt10','middle_P1_P3','middle_all_active']
   fig,axes=plt.subplots(len(gate_names),len(datasets),figsize=(6*len(datasets),4*len(gate_names)),squeeze=False)
   for row_index,gate in enumerate(gate_names):
    for col_index,dataset in enumerate(datasets):
     ax=axes[row_index,col_index];rr=[r for r in rows if r['dataset']==dataset and r['kind']=='gate' and r['gate']==gate and np.isfinite(r['ratio'])]
     limit=max([max(r['predicted_percent'],r['observed_percent']) for r in rr]+[1])*1.2
     for r in rr:
      a,b,c,d=[r[k] for k in ['N1234','N134','N123','N13']]
      x=b/(a+b);y=d/(c+d)
      ax.errorbar(100*x,100*y,xerr=100*math.sqrt(x*(1-x)/(a+b)),yerr=100*math.sqrt(y*(1-y)/(c+d)),fmt='o',capsize=2)
     ax.plot([0,limit],[0,limit],'--',color='.4');ax.set(xlim=(0,limit),ylim=(0,limit),title=f'{dataset}: {gate}',xlabel='Predicted P2 miss [%]',ylabel='Observed P2 miss [%]');ax.grid(alpha=.2);ax.set_aspect('equal')
   fig.suptitle('TT13 closure: real HV settings and separate simulated parameter sets\nEach point is one setting; no pooling of differing efficiencies')
   fig.tight_layout(rect=(0,0,1,.96));fig.savefig(out/'real_vs_simulation_closure.png',dpi=130);pdf.savefig(fig);plt.close(fig)
 print('Completed files:',dict(used),'groups:',len(exposure),'output:',out,flush=True)
if __name__=='__main__':main()
