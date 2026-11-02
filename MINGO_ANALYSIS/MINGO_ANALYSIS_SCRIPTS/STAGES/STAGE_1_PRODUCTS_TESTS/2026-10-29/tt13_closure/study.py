from pathlib import Path
import csv,datetime as dt,collections,bisect,math,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
from scipy.stats import fisher_exact,pearsonr
ROOT=Path('/home/mingo/mingo-computing/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1/EVENT_DATA/STEP_1')
OUT=Path(__file__).resolve().parent
SNAP=OUT/'inputs';SNAP.mkdir(exist_ok=True)
def read(task,kind):
 p=ROOT/f'TASK_{task}/METADATA/task_{task[0]}_metadata_{kind}.csv'
 text=p.read_text();(SNAP/f'{task}_{kind}.csv').write_text(text)
 return {r['filename_base']:r for r in csv.DictReader(text.splitlines())}
hv=[]
for p in Path('/tmp/mingo_caen_scan_logs').glob('*.log'):
 (SNAP/p.name).write_bytes(p.read_bytes())
 for line in p.open():
  q=line.split()
  if len(q)<65:continue
  try:hv.append((dt.datetime.fromisoformat(q[0]),tuple(round(float(q[1+8*c])/1000,4) for c in range(8))))
  except ValueError:pass
hv.sort();times=[t for t,k in hv]
co=read('0','execution');cs=read('0','specific')
s1=read('1_SELFTRIGGER','trigger_type');s2=read('2_SELFTRIGGER','trigger_type');ss=read('2_SELFTRIGGER','specific')
records=[];excluded=collections.Counter()
def add(stage,fn,row,specific,prefix,first,last):
 try:a=dt.datetime.fromisoformat(specific[first]);b=dt.datetime.fromisoformat(specific[last])
 except (ValueError,KeyError):excluded['missing_time']+=1;return
 if a<dt.datetime(2026,10,19,9,27) or b<a:return
 i=bisect.bisect_right(times,a)-1;j=bisect.bisect_right(times,b)-1
 if i<0 or (a-times[i]).total_seconds()>180:excluded['missing_HV']+=1;return
 key=hv[i][1]
 if any(v!=key for _,v in hv[i:j+1]):excluded['HV_boundary']+=1;return
 counts=[int(float(row.get(f'{prefix}_{tt}_count') or 0)) for tt in ('1234','134','123','13')]
 if sum(counts)==0:return
 records.append(dict(stage=stage,filename=fn,start=a.isoformat(),end=b.isoformat(),hv=key,counts=counts))
for fn in co.keys()&cs.keys():add('Coincidence raw',fn,co[fn],cs[fn],'tt_task0_raw','coincidence_first_datetime','coincidence_last_datetime')
for fn in s1.keys()&s2.keys()&ss.keys():
 add('Self-trigger Task 1',fn,s1[fn],ss[fn],'tt_task0_raw','data_first_datetime','data_last_datetime')
 add('Self-trigger Task 2',fn,s2[fn],ss[fn],'tt_task2_selftrigger','data_first_datetime','data_last_datetime')
(OUT/'matched_source_records.json').write_text(json.dumps(records,indent=2))
def aggregate(bytime=False):
 bins={}
 for r in records:
  start=dt.datetime.fromisoformat(r['start']);mid=start+(dt.datetime.fromisoformat(r['end'])-start)/2
  hours=1 if r['stage']=='Coincidence raw' else 6
  bucket=mid.replace(hour=mid.hour//hours*hours,minute=0,second=0,microsecond=0).isoformat() if bytime else ''
  key=(r['stage'],tuple(r['hv']),bucket)
  entry=bins.setdefault(key,dict(counts=np.zeros(4,dtype=int),files=0,start=r['start'],end=r['end']))
  entry['counts']+=r['counts'];entry['files']+=1;entry['start']=min(entry['start'],r['start']);entry['end']=max(entry['end'],r['end'])
 rows=[]
 for (stage,hv,bucket),v in sorted(bins.items()):
  a,b,c,d=map(int,v['counts'])
  if not (a+b and c+d):continue
  pred=b/(a+b);obs=d/(c+d)
  sx=math.sqrt(pred*(1-pred)/(a+b));sy=math.sqrt(obs*(1-obs)/(c+d))
  predicted_n=c*b/a if a else float('nan')
  predicted_n_se=predicted_n*math.sqrt(1/a+1/b+1/c) if a*b*c else float('nan')
  ratio=obs/pred if pred else float('nan')
  odds=d*a/(c*b) if c*b else float('nan')
  logse=math.sqrt(sum(1/n for n in (a,b,c,d))) if a*b*c*d else float('nan')
  fisherp=fisher_exact([[a,b],[c,d]]).pvalue
  row=dict(stage=stage,p1_kv=hv[0],p2_kv=hv[1],p3_kv=hv[2],p4_kv=hv[3],bucket=bucket,start=v['start'],end=v['end'],files=v['files'],N1234=a,N134=b,N123=c,N13=d,e2_percent=100*(1-pred),predicted_miss_percent=100*pred,observed_miss_percent=100*obs,xerr_percent=100*sx,yerr_percent=100*sy,observed_over_predicted=ratio,predicted_N13=predicted_n,predicted_N13_se=predicted_n_se,odds_ratio=odds,odds_ratio_low95=odds*math.exp(-1.96*logse),odds_ratio_high95=odds*math.exp(1.96*logse),fisher_p=fisherp)
  rows.append(row)
 return rows
hvrows=aggregate();timerows=aggregate(True)
for name,rows in [('by_hv',hvrows),('time_series',timerows)]:
 with (OUT/f'{name}.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
stages=['Coincidence raw','Self-trigger Task 1','Self-trigger Task 2'];colors=['tab:blue','tab:orange','tab:green']
with PdfPages(OUT/'tt13_closure_report.pdf') as pdf:
 fig,axs=plt.subplots(1,3,figsize=(15,5))
 for ax,stage,color in zip(axs,stages,colors):
  rr=[r for r in hvrows if r['stage']==stage]
  limit=max(max(r['predicted_miss_percent']+r['xerr_percent'],r['observed_miss_percent']+r['yerr_percent']) for r in rr)*1.15
  for r in rr:
   x=r['predicted_miss_percent'];y=r['observed_miss_percent']
   ax.errorbar(x,y,xerr=r['xerr_percent'],yerr=r['yerr_percent'],fmt='o',color=color,capsize=2)
   ax.annotate(f"P1 {r['p1_kv']:.3f}" if r['p2_kv']==5.65 else f"P2 {r['p2_kv']:.3f}",(x,y),xytext=(4,4),textcoords='offset points',fontsize=7)
  ax.plot([0,limit],[0,limit],'--',color='.4');ax.set(xlim=(0,limit),ylim=(0,limit),title=stage,xlabel='Predicted P2 miss: N134 / (N1234 + N134) [%]',ylabel='Observed P2 miss: N13 / (N123 + N13) [%]');ax.set_aspect('equal');ax.grid(alpha=.2)
 fig.suptitle('TT13 closure by HV setting · 1σ counting uncertainties');fig.tight_layout();fig.savefig(OUT/'tt13_by_hv.png',dpi=180);pdf.savefig(fig);plt.close(fig)
 fig,axs=plt.subplots(3,1,figsize=(13,10),sharex=True)
 for ax,stage,color in zip(axs,stages,colors):
  rr=sorted([r for r in timerows if r['stage']==stage],key=lambda r:r['start']);x=[dt.datetime.fromisoformat(r['start'])+(dt.datetime.fromisoformat(r['end'])-dt.datetime.fromisoformat(r['start']))/2 for r in rr]
  for field,err,marker,col,label in [('predicted_miss_percent','xerr_percent','o','.3','Predicted (P4 present)'),('observed_miss_percent','yerr_percent','s',color,'Observed (P4 absent)')]:
   ax.errorbar(x,[r[field] for r in rr],yerr=[r[err] for r in rr],fmt=marker,ms=3,color=col,alpha=.8,capsize=2,label=label)
  ax.set(title=stage,ylabel='P2 miss probability [%]');ax.grid(alpha=.2);ax.legend(fontsize=8)
 axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b %d'));fig.suptitle('TT13 closure over acquisition time · 1 h coincidence / 6 h self-trigger bins, split at HV changes\nWhole-file counts assigned by midpoint; no interpolation within files');fig.tight_layout(rect=(0,0,1,.94));fig.savefig(OUT/'tt13_time_series.png',dpi=180);pdf.savefig(fig);plt.close(fig)
 fig,axs=plt.subplots(2,1,figsize=(13,8),sharex=True)
 for stage,color in zip(stages,colors):
  rr=sorted([r for r in timerows if r['stage']==stage],key=lambda r:r['start']);x=[dt.datetime.fromisoformat(r['start']) for r in rr]
  valid=[(t,r) for t,r in zip(x,rr) if math.isfinite(r['odds_ratio_low95'])]
  axs[0].plot(x,[r['observed_over_predicted'] for r in rr],'.',color=color,label=stage)
  axs[1].errorbar([t for t,r in valid],[r['odds_ratio'] for t,r in valid],yerr=[[r['odds_ratio']-r['odds_ratio_low95'] for t,r in valid],[r['odds_ratio_high95']-r['odds_ratio'] for t,r in valid]],fmt='.',color=color,alpha=.6)
 for ax,label in zip(axs,['Observed / predicted miss probability','Odds ratio; 95% intervals']):ax.axhline(1,color='.4',ls='--');ax.set_ylabel(label);ax.grid(alpha=.2)
 axs[0].legend();axs[1].set_yscale('log');axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b %d'));fig.suptitle('P2–P4 association conditional on P1 and P3\nIndependence predicts ratio = 1; time variation and acceptance may also create association');fig.tight_layout(rect=(0,0,1,.94));fig.savefig(OUT/'tt13_association_time_series.png',dpi=180);pdf.savefig(fig);plt.close(fig)
correlations=[]
for stage in stages:
 for hv in sorted({(r['p1_kv'],r['p2_kv']) for r in timerows if r['stage']==stage}):
  rr=[r for r in timerows if r['stage']==stage and (r['p1_kv'],r['p2_kv'])==hv]
  if len(rr)<3:continue
  x=[r['predicted_miss_percent'] for r in rr];y=[r['observed_miss_percent'] for r in rr]
  result=pearsonr(x,y) if np.std(x)>0 and np.std(y)>0 else (float('nan'),float('nan'))
  correlations.append(dict(stage=stage,p1_kv=hv[0],p2_kv=hv[1],bins=len(rr),pearson_r=float(result[0]),p_value=float(result[1])))
with (OUT/'within_hv_correlations.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(correlations[0]));w.writeheader();w.writerows(correlations)
print('Source records',len(records),'excluded',dict(excluded),'time bins',len(timerows))
for r in hvrows:
 print(f"{r['stage']:22} P1={r['p1_kv']:.4f} P2={r['p2_kv']:.4f} N13={r['N13']} predN13={r['predicted_N13']:.1f} pred={r['predicted_miss_percent']:.3f}% obs={r['observed_miss_percent']:.3f}% ratio={r['observed_over_predicted']:.3f} OR={r['odds_ratio']:.3f} p={r['fisher_p']:.3g}")
rr=[r for r in timerows if r['stage']=='Coincidence raw']
settings=sorted({r['p1_kv'] for r in rr})
fig,axs=plt.subplots(2,4,figsize=(15,8))
for ax,h in zip(axs.flat,settings):
 subset=[r for r in rr if r['p1_kv']==h]
 ax.errorbar([r['predicted_miss_percent'] for r in subset],[r['observed_miss_percent'] for r in subset],xerr=[r['xerr_percent'] for r in subset],yerr=[r['yerr_percent'] for r in subset],fmt='o',ms=3,capsize=2)
 lo=min(min(r['predicted_miss_percent'],r['observed_miss_percent']) for r in subset)*.85;hi=max(max(r['predicted_miss_percent'],r['observed_miss_percent']) for r in subset)*1.15
 ax.plot([lo,hi],[lo,hi],'--',color='.4');ax.set(xlim=(lo,hi),ylim=(lo,hi),xlabel='Predicted miss [%]',ylabel='Observed miss [%]');ax.grid(alpha=.2)
 corr=next((r for r in correlations if r['stage']=='Coincidence raw' and r['p1_kv']==h),None)
 ax.set_title(f'P1 {h:.3f} kV · n={len(subset)}'+(f" · r={corr['pearson_r']:.2f}" if corr else ''),fontsize=10)
for ax in list(axs.flat)[len(settings):]:ax.set_visible(False)
fig.suptitle('Coincidence TT13: hourly correlations within each fixed HV setting\nPearson r is descriptive; rates can correlate without agreeing with the diagonal')
fig.tight_layout(rect=(0,0,1,.93));fig.savefig(OUT/'tt13_within_hv_correlations.png',dpi=180);plt.close(fig)
