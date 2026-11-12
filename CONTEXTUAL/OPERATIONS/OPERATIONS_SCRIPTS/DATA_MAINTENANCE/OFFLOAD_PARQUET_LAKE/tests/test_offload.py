"""Test parquet-lake offload path selection and copy behavior."""

import unittest,tempfile,importlib.util,io
from pathlib import Path
spec=importlib.util.spec_from_file_location('offload',Path(__file__).resolve().parents[1]/'offload_parquet_lake.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class OffloadTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.source=self.root/'lake';self.source.mkdir();self.dest=self.root/'disk';self.dest.mkdir()
 def file(self,name='a.parquet',content=b'PAR1samplePAR1'):
  p=self.source/name;p.write_bytes(content);return p
 def test_copy_verified_and_repeatable(self):
  p=self.file();m.sync_file(p,self.dest/p.name);self.assertEqual(p.read_bytes(),(self.dest/p.name).read_bytes());m.sync_file(p,self.dest/p.name)
 def test_invalid_source_never_removed(self):
  p=self.file(content=b'invalid')
  with self.assertRaises(ValueError):m.sync_file(p,self.dest/p.name)
  self.assertTrue(p.exists());self.assertFalse((self.dest/p.name).exists())
 def test_exchange_preserves_directory_access_for_scandir(self):
  p=self.file();v={p.name:m.sync_file(p,self.dest/p.name)}
  with (self.root/'journal').open('w') as journal:m.activate(self.source,self.dest,v,journal)
  self.assertTrue(self.source.is_symlink());self.assertEqual((self.source/p.name).read_bytes(),b'PAR1samplePAR1')
  import os
  with os.scandir(self.source) as items:self.assertTrue(next(items).is_file(follow_symlinks=False))
  self.assertFalse(list(self.root.glob('.offload-original*')))
 def test_changed_source_refuses_activation(self):
  p=self.file();v={p.name:m.sync_file(p,self.dest/p.name)};p.write_bytes(b'PAR1changedPAR1')
  with self.assertRaises(RuntimeError):m.activate(self.source,self.dest,v,io.StringIO())
  self.assertFalse(self.source.is_symlink());self.assertTrue(p.exists())
 def test_nonparquet_entries_are_not_silently_discarded(self):
  self.file('unknown.txt')
  with self.assertRaises(ValueError):m.entries(self.source)
if __name__=='__main__':unittest.main()
