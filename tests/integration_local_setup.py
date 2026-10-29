"""Exercise fresh PostgreSQL setup and batched import in an expendable sandbox.

Uses the already installed runtimes and the downloaded 8 MiB reference extract.
Never connects to the user's independent PostgreSQL service.
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import Launcher, port_available


def main():
    root_local = (ROOT / '.local').resolve()
    sandbox = Path(tempfile.mkdtemp(prefix='installer verification ', dir=root_local)).resolve()
    assert sandbox.is_relative_to(root_local)
    (sandbox / 'scripts').mkdir()
    for name in ('local_database.py', 'import_local_data.py', 'index_local_nuts.py'):
        shutil.copy2(ROOT / 'scripts' / name, sandbox / 'scripts' / name)
    boundaries = sandbox / 'frontend' / 'static' / 'nuts'
    boundaries.mkdir(parents=True)
    for source in (ROOT / 'frontend/static/nuts').glob('*.geojson'):
        shutil.copy2(source, boundaries / source.name)
    (sandbox / '.local').mkdir()
    shutil.copy2(ROOT / '.local/pfas-sample.csv', sandbox / '.local/pfas-sample.csv')
    original_config = (root_local / 'project.env').read_bytes()
    original_count = json.loads((root_local / 'data-import.json').read_text())['points']
    user_port_was_busy = not port_available(5433)
    app = Launcher(sandbox)
    app.python = ROOT / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    success = False
    stopped = False
    try:
        app.ensure_uv()
        app.ensure_node()
        app.ensure_postgres()
        app.ensure_database()
        assert app.config['DB_PORT'] not in ('5432', '5433', '5434')
        config_before_import = (sandbox / '.local/project.env').read_bytes()
        app.ensure_data('sample')
        assert int(app.sql('SELECT count(*) FROM pfas_points')) == original_count
        assert app.sql('SELECT count(*) FROM point') == str(original_count)
        assert int(app.sql('SELECT count(*) FROM pfas_nuts')) > 0
        first_counts = app.sql('SELECT count(*) FROM pfas_substances')
        app.ensure_database()
        app.ensure_data('sample')
        assert app.sql('SELECT count(*) FROM pfas_substances') == first_counts
        assert (sandbox / '.local/project.env').read_bytes() == config_before_import
        assert (root_local / 'project.env').read_bytes() == original_config
        assert (not port_available(5433)) == user_port_was_busy
        print('PASS: fresh private cluster, port conflict, streamed import, NUTS, repeat setup, existing database isolation.', flush=True)
        success = True
    finally:
        if app.pg and (sandbox / '.local/postgres/PG_VERSION').exists():
            result = app.pg_command('pg_ctl', '-D', sandbox / '.local/postgres', '-m', 'fast', '-w', 'stop', check=False)
            stopped = result.returncode == 0
        # Remove only our validated, disposable sandbox, and only after PostgreSQL stopped.
        if success and stopped:
            checked = sandbox.resolve()
            if checked.parent != root_local or not checked.name.startswith('installer verification '):
                raise RuntimeError('Unsafe test cleanup path')
            shutil.rmtree(checked)
        else:
            print(f'Diagnostic sandbox preserved: {sandbox}', flush=True)


if __name__ == '__main__':
    main()
