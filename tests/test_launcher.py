"""Safety and portability checks for the automatic launcher (no installation)."""
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import run as launcher
from local_database import local_config

spec = importlib.util.spec_from_file_location('service_control', ROOT / 'scripts/service_control.py')
services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(services)
spec = importlib.util.spec_from_file_location('data_import', ROOT / 'scripts/import_local_data.py')
data_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(data_import)


class LauncherTests(unittest.TestCase):
    def test_platform_targets(self):
        self.assertEqual(launcher.system_target('Windows', 'AMD64'), ('win', 'x64'))
        self.assertEqual(launcher.system_target('Darwin', 'arm64'), ('darwin', 'arm64'))
        self.assertEqual(launcher.system_target('Linux', 'x86_64'), ('linux', 'x64'))
        self.assertEqual(launcher.system_target('Linux', 'aarch64'), ('linux', 'arm64'))
        with self.assertRaises(launcher.SetupError):
            launcher.system_target('Windows', 'i386')

    def test_does_not_use_an_occupied_port(self):
        with socket.socket() as held:
            held.bind(('127.0.0.1', 0))
            held.listen()
            occupied = held.getsockname()[1]
            self.assertFalse(launcher.port_available(occupied))
            with self.assertRaises(launcher.SetupError):
                launcher.choose_port(occupied, occupied)
            self.assertFalse(launcher.port_available(occupied))

    def test_zip_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for bad in ('../escape', '..\\escape', 'C:/escape'):
                archive = root / 'archive.zip'
                with zipfile.ZipFile(archive, 'w') as source:
                    source.writestr(bad, 'not allowed')
                with self.assertRaises(launcher.SetupError):
                    launcher.extract_archive(archive, root / 'out')
                self.assertFalse((root / 'escape').exists())

    def test_tar_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'archive.tar.gz'
            with tarfile.open(archive, 'w:gz') as source:
                link = tarfile.TarInfo('outside')
                link.type = tarfile.SYMTYPE
                link.linkname = '../../outside'
                source.addfile(link)
            with self.assertRaises(tarfile.FilterError):
                launcher.extract_archive(archive, root / 'out')

    def test_checksum_failure_never_publishes_download(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'download'
            class Response(io.BytesIO):
                headers = {'Content-Length': '5'}
            with patch.object(launcher.urllib.request, 'urlopen', side_effect=lambda *a, **kw: Response(b'hello')), patch.object(launcher.time, 'sleep'):
                with self.assertRaises(launcher.SetupError):
                    launcher.download('https://example.invalid/archive', destination, expected_hash='0' * 64)
            self.assertFalse(destination.exists())

    def test_sample_download_is_bounded_even_if_server_ignores_range(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'sample'
            class Response(io.BytesIO):
                headers = {'Content-Length': '10000'}
            with patch.object(launcher.urllib.request, 'urlopen', return_value=Response(b'x' * 10000)):
                launcher.download('https://example.invalid/data', destination, limit=100)
            self.assertEqual(destination.stat().st_size, 100)

    def test_foreign_database_config_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local = root / '.local'
            local.mkdir()
            config = local / 'project.env'
            original = 'DB_HOST=production.example\nDB_USER=postgres\nDB_PORT=5432\nDB_NAME=important\n'
            config.write_text(original)
            app = launcher.Launcher(root)
            with patch.object(app, 'command') as command:
                with self.assertRaises(launcher.SetupError):
                    app.ensure_database()
                command.assert_not_called()
            self.assertEqual(config.read_text(), original)
            with self.assertRaises(RuntimeError):
                local_config(config)

    def test_existing_cluster_without_credentials_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            version = root / '.local/postgres/PG_VERSION'
            version.parent.mkdir(parents=True)
            version.write_text('18')
            app = launcher.Launcher(root)
            with patch.object(app, 'command') as command:
                with self.assertRaises(launcher.SetupError):
                    app.ensure_database()
                command.assert_not_called()
            self.assertEqual(version.read_text(), '18')
            self.assertFalse((root / '.local/project.env').exists())

    def test_missing_explicit_config_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                local_config(Path(temp) / 'missing.env')

    def test_process_identity_rejects_unrelated_service(self):
        class Process:
            def cwd(self): return '/another/project/model'
            def cmdline(self): return ['python', '-m', 'uvicorn', 'main:app']
        self.assertFalse(services.belongs_to_project(Process(), ROOT, 'backend'))

    def test_reused_pid_is_not_stopped(self):
        class Process:
            def create_time(self): return 2000
        with patch.object(services.psutil, 'Process', return_value=Process()):
            self.assertIsNone(services.known_process({'pid': 42, 'created': 1000}, ROOT, 'backend'))

    def test_setup_lock_prevents_two_installations(self):
        with tempfile.TemporaryDirectory() as temp:
            with launcher.setup_lock(Path(temp)):
                with self.assertRaises(launcher.SetupError):
                    with launcher.setup_lock(Path(temp)):
                        self.fail('Concurrent installation was allowed')

    def test_partial_csv_preserves_only_complete_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sample.csv'
            path.write_text('category,lat,lon,year,pfas_values\nMeasurement,1,2,2020,[]\nMeasurement,3,', encoding='utf-8')
            self.assertEqual(len(list(data_import.iter_rows(path, partial=True))), 1)
            with self.assertRaises(ValueError):
                list(data_import.iter_rows(path, partial=False))

    def test_importer_rejects_unknown_csv_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'other.csv'
            path.write_text('name,value\nA,1\n')
            with self.assertRaises(ValueError):
                list(data_import.iter_rows(path))

    def test_daemon_output_does_not_keep_launcher_waiting(self):
        import re
        import psutil
        with tempfile.TemporaryDirectory() as temp:
            app = launcher.Launcher(Path(temp))
            script = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print('TEST_DAEMON_PID',p.pid,flush=True)"
            started = time.monotonic()
            result = app.command([sys.executable, '-c', script], capture=True, file_output=True, no_window=True)
            pid = int(re.search(r'TEST_DAEMON_PID (\d+)', result.stdout)[1])
            try:
                self.assertLess(time.monotonic() - started, 5)
                self.assertTrue(psutil.pid_exists(pid))
            finally:
                process = psutil.Process(pid)
                process.terminate()
                process.wait(timeout=10)

    def test_launcher_overrides_legacy_windows_output_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'PFAS \u2713 \u6f22'
            root.mkdir()
            script = root / 'run.py'
            script.write_bytes((ROOT / 'run.py').read_bytes())
            environment = os.environ.copy()
            environment.update({'PYTHONUTF8': '0', 'PYTHONIOENCODING': 'cp1252'})
            result = subprocess.run([sys.executable, '-X', 'utf8=0', str(script), '--doctor'],
                                    env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
            self.assertIn('PFAS \u2713 \u6f22', result.stdout.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
