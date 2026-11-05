from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

report=Path(__file__).resolve().parent
summary=pd.read_csv(report/'reference_pair_angle_summary.csv')
fig,ax=plt.subplots(figsize=(8,5))
for station,color,label in [('MINGO00','C0','MINGO00 simulation (8 separate settings)'),('MINGO01','C1','MINGO01 data (7 HV groups)')]:
    data=summary[summary.dataset==station]
    x=[]; med=[]; lo=[]; hi=[]
    for angle,g in data.groupby('theta_max_deg'):
        v=g.median_closure.dropna().to_numpy(float)
        if len(v):
            x.append(float(angle));med.append(float(np.median(v)));lo.append(float(np.quantile(v,.25)));hi.append(float(np.quantile(v,.75)))
    x=np.asarray(x);med=np.asarray(med);lo=np.asarray(lo);hi=np.asarray(hi)
    ax.fill_between(x,lo,hi,color=color,alpha=.16);ax.plot(x,med,marker='o',lw=2,color=color,label=label)
ax.axhline(1,color='.4',ls='--',label='closure = 1')
ax.set(xlabel='Common P1–P3 reference angle below [degrees]',ylabel='Observed TT13 closure',title='Closure versus angle gate; median and IQR across independent groups')
ax.grid(alpha=.25);ax.legend(fontsize=8);fig.tight_layout();fig.savefig(report/'reference_pair_angle_comparison.png',dpi=160);plt.close(fig)

pages=[('geometry_efficiency_model.png','Raw MINGO00 TT13 counts compared with the twin geometry and angle-response model.'),('gate_decomposition.png','Generated-angle gates and P4 active-area crossing gates.'),('theta_cut_scan.png','Cumulative generated-angle cuts; simulation settings kept separate.'),('reference_pair_angle_comparison.png','Common P1–P3 angle trend in simulation and real MINGO01 HV groups.'),('mingo00_task5_update_20261030/real_vs_simulation_closure.png','Updated Task-5 closure gates for eight MINGO00 settings.')]
with PdfPages(report/'report_frontmatter.pdf') as pdf:
    fig=plt.figure(figsize=(8.3,11.7));fig.gca().axis('off')
    fig.text(.08,.94,'TT13 closure: simulation and real-data gate study',fontsize=20,weight='bold',va='top')
    text=(
      '30 October 2026 · MINGO00 digital twin and MINGO01 HV scan\n\n'
      'Closure: R = [N13 / (N123 + N13)] / [N134 / (N1234 + N134)]. R=1 is closure.\n\n'
      'SIMULATION RESULT\nTwelve distinct 50,000-event MINGO00 samples were checked at raw Task 0, with one-to-one truth-sidecar joins. All 12 raw closure ratios are below one (median 0.885, range 0.716–0.992). The Task-2/3/4/5 pipeline did not create the effect.\n\n'
      'The twin predicts the same direction. Applying configured Step-2 active-area projection and Step-3 angle-dependent Poisson hit probability gives median closure 0.850. Observed four-category counts are compatible with the model at 5%, though borderline (chi-square 49.99 / 36 dof, p=0.061). Independent-efficiency and geometry-only ablations close at 1; angle response without P4 geometry is near 1; combining geometry and angle response moves below 1.\n\n'
      'GATE RESULT\nAt raw level, median closure is 0.994 for generated theta <15 degrees and 0.912 for <45 degrees. In 35–45 degrees, median closure is 0.767 and only about 1.7% of P1+P3 tracks geometrically cross P4. Above 45 degrees P4 has zero geometric crossings in the available samples. Higher-angle tracks have larger modeled P2 hit probability, while many do not reach P4.\n\n'
      'REAL-DATA COMPARISON\nUsing only P1/P3 positions for a common direction estimate, median closure across eight MINGO00 Task-5 settings falls from 0.974 (<15 degrees) to 0.908 (<45 degrees). Across seven separate MINGO01 HV groups it falls from 1.215 to 0.938. The downward trend is shared; the low-angle offset differs, so this does not show that the twin explains every real-data discrepancy.\n\n'
      'INTERPRETATION\nThe effect is not caused solely by random electronic noise: it occurs in simulated data and is reproduced by the current geometry/response model. This points to an acceptance/response correlation in this conditional-efficiency definition, not proof of a detector defect. Angle cuts are diagnostic, not a proposed physics correction.\n\n'
      'Detailed per-file counts, model tests, and current queue status are in the companion report directory. The remaining pages contain updated MINGO00 Task-5 gate summaries and charge spectra.'
    )
    fig.text(.08,.89,text,fontsize=10.2,va='top',linespacing=1.3,wrap=True);pdf.savefig(fig,bbox_inches='tight');plt.close(fig)
    for rel,caption in pages:
        path=report/rel
        if not path.is_file():continue
        image=Image.open(path).convert('RGB')
        fig=plt.figure(figsize=(11.7,8.3));ax=fig.add_axes([.04,.10,.92,.83]);ax.imshow(image);ax.axis('off')
        fig.text(.05,.045,caption,fontsize=10,va='bottom');pdf.savefig(fig,bbox_inches='tight');plt.close(fig)
print(report/'report_frontmatter.pdf')
