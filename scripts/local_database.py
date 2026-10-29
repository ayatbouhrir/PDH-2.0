"""Database guard shared by the importer and NUTS indexer."""
from pathlib import Path

from dotenv import dotenv_values
from pg8000.native import Connection

ROOT = Path(__file__).resolve().parents[1]


def local_config(path=None):
    explicit = path is not None
    path = Path(path) if path else ROOT / '.local' / 'project.env'
    if not explicit and not path.exists():
        path = ROOT / 'frontend' / '.env'
    if not path.is_file():
        raise FileNotFoundError(f'Configuration locale introuvable: {path}')
    values = dict(dotenv_values(path))
    if (values.get('DB_HOST') != '127.0.0.1'
            or values.get('DB_NAME') != 'dae_pfas_local'
            or values.get('DB_USER') != 'pfas_app'
            or not 5434 <= int(values.get('DB_PORT', '0')) <= 5499):
        raise RuntimeError('Refusing to modify a database other than the separate local project database.')
    return values


def connect_local(path=None):
    config = local_config(path)
    return Connection(host=config['DB_HOST'], port=int(config['DB_PORT']),
                      database=config['DB_NAME'], user=config['DB_USER'],
                      password=config['DB_PASSWORD'], timeout=30)
