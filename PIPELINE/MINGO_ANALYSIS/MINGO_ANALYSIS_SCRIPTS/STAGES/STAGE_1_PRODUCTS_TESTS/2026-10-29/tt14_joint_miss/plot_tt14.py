import csv, datetime, collections, math
from pathlib import Path
root=Path('/home/mingo/mingo-computing/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1')
import bisect
hv=[]
for p in Path('/tmp/mingo_caen_scan_logs').glob('*.log'):
 for line in p.open():
  q=line.split()
  if len(q)>=65:
   try: hv.append((datetime.datetime.fromisoformat(q[0]),tuple(round(float(q[1+ch*8])/1000,4) for ch in range(8))))
   except ValueError: pass
hv.sort(); times=[x[0] for x in hv]
m=root/'EVENT_DATA/STEP_1/TASK_2_SELFTRIGGER/METADATA'
def read(p): return list(csv.DictReader(p.open()))
sp={r['filename_base']:r for r in read(m/'task_2_metadata_specific.csv')}
groups=collections.defaultdict(collections.Counter)
for r in read(m/'task_2_metadata_trigger_type.csv'):
 s=sp.get(r['filename_base'],{})
 try: start=datetime.datetime.fromisoformat(s['data_first_datetime']); end=datetime.datetime.fromisoformat(s['data_last_datetime'])
 except (ValueError,KeyError): continue
 i=bisect.bisect_right(times,start)-1; j=bisect.bisect_right(times,end)-1
 if i<0 or start<datetime.datetime(2026,10,19,9,27):continue
 key=hv[i][1]
 if any(v!=key for _,v in hv[i:j+1]):continue
 for t in ('1234','134','124','14'):groups[key][t]+=int(float(r.get(f'tt_task2_selftrigger_{t}_count') or 0))

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
out=Path(__file__).resolve().parent
rows=[]
for k,c in sorted(groups.items()):
    counts=np.array([c[t] for t in ('1234','134','124','14')],dtype=float)
    n=counts.sum()
    if n<50: continue
    p=counts/n
    q2=p[1]+p[3]; q3=p[2]+p[3]
    predicted=q2*q3; measured=p[3]
    covariance=(np.diag(p)-np.outer(p,p))/n
    gradient=np.array([0,q3,q2,q2+q3])
    sx=np.sqrt(gradient@covariance@gradient)
    sy=np.sqrt(covariance[3,3])
    covxy=gradient@covariance[:,3]
    rows.append(dict(p1_kv=k[0],p2_kv=k[1],p3_kv=k[2],p4_kv=k[3],N=int(n),
        N1234=int(counts[0]),N134=int(counts[1]),N124=int(counts[2]),N14=int(counts[3]),
        predicted_percent=100*predicted,measured_percent=100*measured,
        predicted_se_percent=100*sx,measured_se_percent=100*sy,
        covariance_percent_squared=10000*covxy))
with (out/'tt14_joint_miss.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
fig,ax=plt.subplots(figsize=(8,7))
norm=Normalize(min(r['p1_kv'] for r in rows),max(r['p1_kv'] for r in rows))
cmap=plt.get_cmap('viridis')
for i,r in enumerate(rows):
    x=r['predicted_percent'];y=r['measured_percent']
    ax.errorbar(x,y,xerr=r['predicted_se_percent'],yerr=r['measured_se_percent'],fmt='o',
        color=cmap(norm(r['p1_kv'])),capsize=3,markersize=6)
    ax.annotate(f"{r['p1_kv']:.3f}",(x,y),xytext=(7,6 if i%2 else -14),textcoords='offset points',fontsize=8)
limit=max(r['measured_percent']+r['measured_se_percent'] for r in rows)*1.12
ax.plot([0,limit],[0,limit],'--',color='0.4',lw=1.3,label='Measured = predicted')
ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='Predicted joint miss: (1 − e₂)(1 − e₃) [%]',
       ylabel='Measured joint miss: N(TT14) / N [%]',title='MINGO01 · self-trigger · one point per HV setting')
ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend(loc='lower right')
fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),ax=ax,label='Plane 1 HV [kV]',shrink=.75)
fig.text(.12,.025,'N = N1234 + N134 + N124 + N14; P2–P4 = 5.65 kV.\nError bars: 1σ counting errors; X and Y share events and are correlated.',fontsize=9)
fig.tight_layout(rect=(0,.075,1,1))
for ext in ('png','pdf'):fig.savefig(out/f'tt14_measured_vs_predicted.{ext}',dpi=180)
print('Generated',len(rows),'HV points in',out)
