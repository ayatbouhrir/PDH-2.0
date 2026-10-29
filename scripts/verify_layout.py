"""Check portable layout and Python syntax without installing or starting services."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    required = (
        'frontend/package.json', 'frontend/package-lock.json',
        'frontend/src/lib/vendor/fsac/LICENSE', 'vendor/propos/tabular_adapter.py',
        'backend/main.py', 'backend/requirements.txt', 'backend/requirements-dev.txt',
        'scripts/import_local_data.py', 'scripts/index_local_nuts.py',
        'scripts/service_control.py', 'scripts/test_local.py',
        'research/experiments/compare_tabpfn_saint.py',
        'frontend/src/lib/features/exploration/exploration.state.svelte.ts',
        'frontend/src/lib/features/analysis/analysis.state.svelte.ts',
        'frontend/src/lib/features/history/run-history.state.svelte.ts',
    )
    for relative in required:
        assert (ROOT / relative).is_file(), f'Missing project file: {relative}'
    assert not (ROOT / 'backend/hdbscan.py').exists(), 'Local hdbscan would mask the dependency'
    assert not (ROOT / 'PDHv2').exists(), 'Old application directory is still active'
    assert not (ROOT / 'model').exists(), 'Old Python directory is still active'
    files = [ROOT / 'run.py']
    for directory in ('backend', 'scripts', 'tests', 'research/experiments', 'research/saint'):
        files.extend((ROOT / directory).rglob('*.py'))
    for path in files:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    print(f'PASS: portable layout and syntax of {len(files)} maintained Python files')


if __name__ == '__main__':
    main()
