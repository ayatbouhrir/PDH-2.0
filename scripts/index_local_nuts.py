"""Index the bundled NUTS boundaries in the isolated project database."""
import json
import argparse
from pathlib import Path

import numpy as np
from local_database import connect_local
from shapely import points
from shapely.geometry import shape
from shapely.strtree import STRtree
from importlib.util import module_from_spec, spec_from_file_location

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("local_import", ROOT / "scripts" / "import_local_data.py")
helper = module_from_spec(spec)
spec.loader.exec_module(helper)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--batch-size', type=int, default=5000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('--batch-size doit etre positif')
    manifest = ROOT / '.local' / 'data-import.json'
    data = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    conn = connect_local(args.config)
    if data.get('nutsIndexed') and conn.run('SELECT EXISTS(SELECT 1 FROM pfas_nuts)')[0][0]:
        print('Index NUTS existant conserve.', flush=True)
        conn.close()
        return
    conn.run('CREATE TEMP TABLE nuts_stage (point_id integer, version text, level integer, nuts_id text)')
    for year in (2016, 2021, 2024):
        features = json.loads((ROOT / 'frontend' / 'static' / 'nuts' / f'NUTS_{year}.geojson').read_text(encoding='utf-8'))['features']
        tree = STRtree([shape(feature['geometry']) for feature in features])
        after = 0
        total = 0
        while True:
            source = conn.run('SELECT id, lon, lat FROM pfas_points WHERE id > :after AND lat IS NOT NULL AND lon IS NOT NULL ORDER BY id LIMIT :limit',
                              after=after, limit=args.batch_size)
            if not source:
                break
            coords = np.array(source, dtype=float)
            matching = tree.query(points(coords[:, 1], coords[:, 2]), predicate='intersects')
            associations = set()
            for point_index, region_index in zip(*matching):
                prop = features[int(region_index)]['properties']
                associations.add((int(coords[int(point_index), 0]), f'nuts{year}', int(prop['LEVL_CODE']), prop['NUTS_ID']))
            conn.run('BEGIN')
            try:
                conn.run('TRUNCATE pg_temp.nuts_stage')
                helper.copy_rows(conn, 'pg_temp.nuts_stage', ['point_id', 'version', 'level', 'nuts_id'], associations)
                conn.run('INSERT INTO pfas_nuts SELECT * FROM pg_temp.nuts_stage ON CONFLICT DO NOTHING')
                conn.run('COMMIT')
            except Exception:
                conn.run('ROLLBACK')
                raise
            after = int(source[-1][0])
            total += len(associations)
        print(f'NUTS {year}: {total:,} associations verifiees', flush=True)
    data['nutsIndexed'] = True
    manifest.write_text(json.dumps(data, indent=2), encoding='utf-8')
    conn.close()


if __name__ == '__main__':
    main()
