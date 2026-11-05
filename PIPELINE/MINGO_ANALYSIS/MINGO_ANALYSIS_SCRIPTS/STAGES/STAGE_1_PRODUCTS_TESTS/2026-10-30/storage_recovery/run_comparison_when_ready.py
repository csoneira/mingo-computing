from pathlib import Path
import time,subprocess,sys
import pyarrow.parquet as pq
root=Path('/home/mingo/mingo-computing')
p=root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE/postprocessed_mi0005199000000.parquet'
start=time.monotonic();last=-100
while time.monotonic()-start<1200:
 try:
  schema=pq.read_schema(p)
  required=['event_det_chi2_pos','event_tim_th_chi','p1_qsum','p1_s1_qsum_cal','param_hash']
  if not all(c in schema.names for c in required):raise ValueError('Required final columns absent')
  print('New MINGO00 Task-5 parquet ready:',p,'rows=',pq.ParquetFile(p).metadata.num_rows,flush=True)
  archive=root/'PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/TT13_STUDIES/DATED_STUDIES/2026-10-30'
  manifest=root/'PIPELINE/MINGO_COMPARISONS/MINGO_DATA_VS_DATA/DATED_STUDIES/2026-10-29/tt13_closure/matched_source_records.json'
  output=archive/'tt13_real_sim_gate_scan'
  cmd=[str(root/'.venv/bin/python'),'-u',str(root/'PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_DATA/TT13_STUDIES/TT13_GATE_SCAN/scan.py'),'--stations','0,1','--real-manifest',str(manifest),'--output',str(output)]
  sys.exit(subprocess.run(cmd,cwd=root).returncode)
 except (OSError,ValueError):pass
 if time.monotonic()-last>=60:print('Waiting for Task-5 output; elapsed seconds',int(time.monotonic()-start),flush=True);last=time.monotonic()
 time.sleep(5)
raise SystemExit('Task-5 output not ready within 20 minutes; no successful comparison claimed.')
