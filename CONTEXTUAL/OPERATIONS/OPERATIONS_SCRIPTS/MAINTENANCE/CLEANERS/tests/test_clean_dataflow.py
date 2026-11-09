import importlib.util
from pathlib import Path
import tempfile
import os
import unittest
import time

SPEC=importlib.util.spec_from_file_location('cleaner',Path(__file__).resolve().parents[1]/'clean_dataflow.py')
c=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(c)

class CleanerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.rules={k:dict(enabled=False,min_age_hours=0,keep_newest=0) for k in c.CATEGORIES}
        self.task=self.root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1/EVENT_DATA/STEP_1/TASK_2_SELFTRIGGER'
    def file(self,path,age=100):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'payload');os.utime(path,(time.time()-age,)*2);return path
    def plan(self,*categories):return {p for _,p,_ in c.scan(self.root,set(categories),self.rules)}
    def test_nested_final_and_runtime_reports_retained_as_complete_runs(self):
        for kind in ['DEBUG_PLOTS','FINAL_PLOTS/TASK_2']:
            for run,age in [('old',100),('new',10)]:
                for name in ['minimal/a.png','maximal/b.png','report.pdf']:
                    self.file(self.task/'PLOTS'/kind/run/name,age)
        self.rules['plots']['keep_newest']=1
        paths=self.plan('plots');self.assertEqual(len(paths),6);self.assertTrue(all('old' in p.parts for p in paths))
    def test_pdf_only_never_deletes_png(self):
        png=self.file(self.task/'PLOTS/FINAL_PLOTS/TASK_2/old/minimal/a.png')
        pdf=self.file(self.task/'PLOTS/FINAL_PLOTS/TASK_2/old/report.pdf')
        self.assertEqual(self.plan('pdfs'),{pdf});self.assertNotIn(png,self.plan('pdfs'))
    def test_no_hidden_data_archive_or_metadata_deletions(self):
        for folder in ['COMPLETED_DIRECTORY','UNPROCESSED_DIRECTORY','PROCESSING_DIRECTORY']:
            self.file(self.task/'INPUT_FILES'/folder/'data.parquet')
        self.file(self.task/'METADATA/test.png');self.file(self.root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE/data.parquet')
        self.assertFalse(self.plan('plots'))
        self.assertEqual(len(self.plan('completed_data')),1);self.assertEqual(len(self.plan('unprocessed_data')),1)
    def test_symlink_to_outside_and_processing_directory_are_never_scanned(self):
        outside=self.file(self.root/'outside/secret.png');plot=self.task/'PLOTS';plot.mkdir(parents=True)
        (plot/'linked').symlink_to(outside.parent,target_is_directory=True)
        self.file(plot/'PROCESSING_DIRECTORY/current.png')
        self.assertFalse(self.plan('plots'))
    def test_recent_file_preserves_entire_bundle(self):
        self.rules['plots']['min_age_hours']=1
        self.file(self.task/'PLOTS/DEBUG_PLOTS/run/a.png',10000)
        self.file(self.task/'PLOTS/DEBUG_PLOTS/run/b.pdf',10)
        self.assertFalse(self.plan('plots'))
    def test_changed_file_is_not_deleted(self):
        p=self.file(self.task/'PLOTS/loose.png');before=p.stat();p.write_bytes(b'changed')
        self.assertFalse(c.delete_candidate(p,before,self.root));self.assertTrue(p.exists())
    def test_active_basename_protects_other_directories(self):
        name='mi0126299011736'
        self.file(self.task/'INPUT_FILES/PROCESSING_DIRECTORY'/f'processing_{name}.parquet')
        self.file(self.task/'INPUT_FILES/COMPLETED_DIRECTORY'/f'data_{name}.parquet')
        self.assertFalse(self.plan('completed_data'))
    def test_dry_run_cli_does_not_delete(self):
        import subprocess,json
        p=self.file(self.task/'PLOTS/loose.png');(self.root/"CONTEXTUAL" / "CONFIG").mkdir(parents=True)
        config=self.root/'rules.json';config.write_text(json.dumps(dict(version=1,disk_threshold_percent=0,check_archive_consistency=False,categories=self.rules)))
        env=dict(os.environ,DATAFLOW_CLEAN_LOCK_FILE=str(self.root/'lock'))
        result=subprocess.run(['python3',str(c.HERE/'clean_dataflow.py'),'--root',str(self.root),'--config',str(config),'--select','plots','--dry-run','--compact'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(p.exists());self.assertIn('1 files',result.stdout)
    def test_apply_deletes_only_explicitly_selected_plot_format(self):
        import subprocess,json
        png=self.file(self.task/'PLOTS/a.png');pdf=self.file(self.task/'PLOTS/b.pdf')
        (self.root/"CONTEXTUAL" / "CONFIG").mkdir(parents=True)
        config=self.root/'rules.json';config.write_text(json.dumps(dict(version=1,disk_threshold_percent=0,check_archive_consistency=False,categories=self.rules)))
        env=dict(os.environ,DATAFLOW_CLEAN_LOCK_FILE=str(self.root/'lock'))
        result=subprocess.run(['python3',str(c.HERE/'clean_dataflow.py'),'--root',str(self.root),'--config',str(config),'--select','pdfs','--apply','--compact'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(png.exists());self.assertFalse(pdf.exists())

    def test_tracked_generated_figure_is_protected(self):
        import subprocess
        p=self.file(self.task/'PLOTS/tracked.png')
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        subprocess.run(['git','-C',str(self.root),'add',str(p)],check=True)
        self.assertFalse(self.plan('plots'))
    def test_simulation_retains_whole_run_and_global_mesh(self):
        base=self.root/'PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2'
        for run,age in [('SIM_RUN_1',100),('SIM_RUN_2',10)]:
            self.file(base/run/'chunks/part_1.pkl',age)
            self.file(base/run/'manifest.json',age)
        self.file(base/'param_mesh.csv',100)
        self.rules['simulation_intermediates']['keep_newest']=1
        paths=self.plan('simulation_intermediates')
        self.assertEqual(len(paths),2);self.assertTrue(all('SIM_RUN_1' in p.parts for p in paths))

    def test_invalid_config_fails_closed(self):
        p=self.root/'config.json';p.write_text('{"version":1}')
        with self.assertRaises(ValueError):c.load_config(p)

if __name__=='__main__':unittest.main()
