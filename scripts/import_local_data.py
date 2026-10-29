"""Import a PDH CSV into ONLY this project's separate PostgreSQL instance.

The downloaded test extract contains real observations, not generated data.
Pass a complete full.csv later to import the complete dataset into a NEW database.
An already populated database is deliberately never replaced.
"""
import argparse
import collections
import csv
import io
import json
import math
from pathlib import Path

from local_database import connect_local

ROOT = Path(__file__).resolve().parents[1]


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def copy_rows(conn, table, columns, records):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in records:
        writer.writerow(["\\N" if value is None else value for value in row])
    buffer.seek(0)
    cols = ", ".join(f'"{col}"' for col in columns)
    conn.run(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", stream=buffer)


def iter_rows(path, partial=False):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        required = {"pfas_values", "category", "lat", "lon", "year"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV PDH invalide: colonnes manquantes {sorted(required - set(reader.fieldnames or []))}")
        try:
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    if partial:
                        continue
                    raise ValueError(f"Ligne CSV incomplete vers la ligne {reader.line_num}.")
                row["_values"] = json.loads(row["pfas_values"] or "[]")
                if not isinstance(row["_values"], list) or any(not isinstance(m, dict) for m in row["_values"]):
                    raise ValueError(f"pfas_values invalide vers la ligne {reader.line_num}.")
                yield row
        except csv.Error:
            if not partial:
                raise


def substance_key(measure):
    return tuple(str(measure.get(k) or "").strip() for k in ("substance", "cas_id", "isomer", "unit"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--partial", action="store_true", help="Extrait borne; ignorer uniquement la derniere ligne tronquee.")
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size doit etre positif")
    conn = connect_local(args.config)
    if conn.run("SELECT to_regclass('public.pfas_points')")[0][0]:
        raise SystemExit("Database already has data; refusing to replace it.")
    csv.field_size_limit(16 * 1024 * 1024)
    seen = set()
    counts = collections.Counter()
    total = 0
    print("Passe 1/2: identification des substances (lecture par flux)...", flush=True)
    for row in iter_rows(args.csv_file, args.partial):
        total += 1
        counts[row["category"]] += 1
        seen.update(substance_key(m) for m in row["_values"] if m.get("substance") or m.get("cas_id"))
        if total % 100000 == 0:
            print(f"  {total:,} lignes inspectees", flush=True)
    keys = sorted(seen)
    if not total or not keys:
        raise SystemExit("Le CSV ne contient pas de points et de mesures PFAS exploitables. Aucune table creee.")
    if len(keys) >= 1600:
        raise SystemExit("Trop de substances pour le schema PostgreSQL vectoriel actuel (limite 1599).")
    mapping = {value: i + 1 for i, value in enumerate(keys)}
    metadata = ["lat", "lon", "date", "year", "matrix", "unit", "category", "type", "sector",
                "country", "city", "name", "source_type", "data_collection_method", "source_text",
                "source_url", "dataset_id", "dataset_name", "pfas_sum", "pfas_values", "details"]
    numeric = {"lat", "lon", "pfas_sum"}
    integers = {"year", "dataset_id"}
    definitions = [f'"{col}" ' + ("double precision" if col in numeric else "integer" if col in integers else "text")
                   for col in metadata]
    conn.run("BEGIN")
    try:
        conn.run("CREATE TABLE pfas_points (id integer PRIMARY KEY, " + ", ".join(definitions) + ")")
        conn.run("CREATE TABLE substance_ref (pfas_index integer PRIMARY KEY, substance_name text, cas_id text, isomer text, unit_ref text)")
        conn.run("CREATE TABLE point (point_id integer PRIMARY KEY REFERENCES pfas_points(id), " +
                 ", ".join(f"pfas_{i} double precision" for i in mapping.values()) + ")")
        conn.run("CREATE TABLE pfas_substances (point_id integer REFERENCES pfas_points(id), substance text, unit text, value double precision, less_than boolean)")
        conn.run("CREATE TABLE pfas_nuts (point_id integer REFERENCES pfas_points(id), version text, level integer, nuts_id text, PRIMARY KEY(point_id, version, level, nuts_id))")
        copy_rows(conn, "substance_ref", ["pfas_index", "substance_name", "cas_id", "isomer", "unit_ref"],
                  ([i, *(part or None for part in k)] for k, i in mapping.items()))
        point_rows, vector_rows, substance_rows = [], [], []
        substance_count = 0
        loaded = 0

        def flush():
            copy_rows(conn, "pfas_points", ["id", *metadata], point_rows)
            copy_rows(conn, "point", ["point_id", *(f"pfas_{i}" for i in mapping.values())], vector_rows)
            copy_rows(conn, "pfas_substances", ["point_id", "substance", "unit", "value", "less_than"], substance_rows)
            point_rows.clear()
            vector_rows.clear()
            substance_rows.clear()

        print(f"Passe 2/2: import de {total:,} points par lots de {args.batch_size:,}...", flush=True)
        for i, row in enumerate(iter_rows(args.csv_file, args.partial), 1):
            values = []
            for col in metadata:
                value = row.get(col) or None
                if col in numeric:
                    value = number(value)
                elif col in integers:
                    value = number(value)
                    value = int(value) if value is not None else None
                values.append(value)
            point_rows.append([i, *values])
            vector = [None] * len(keys)
            for m in row["_values"]:
                idx = mapping.get(substance_key(m))
                less = str(m.get("less_than", False)).lower() in ("true", "1", "yes")
                value = None if less else number(m.get("value"))
                if idx:
                    vector[idx - 1] = value
                substance_rows.append([i, m.get("substance"), m.get("unit"), value, less])
                substance_count += 1
            vector_rows.append([i, *vector])
            loaded = i
            if i % args.batch_size == 0:
                flush()
                print(f"  {i:,}/{total:,} points charges", flush=True)
        if point_rows:
            flush()
        if loaded != total:
            raise ValueError("Le fichier CSV a change pendant l'import; transaction annulee.")
        conn.run("CREATE VIEW metadonnee AS SELECT id AS point_id, " + ", ".join(f'"{c}"' for c in metadata) + " FROM pfas_points")
        conn.run("CREATE MATERIALIZED VIEW mv_matrix_counts_for_init AS SELECT matrix, count(*) FROM pfas_points WHERE matrix IS NOT NULL GROUP BY matrix")
        conn.run("CREATE MATERIALIZED VIEW mv_datasets_counts_for_init AS SELECT dataset_id, dataset_name, count(*) FROM pfas_points WHERE dataset_id IS NOT NULL GROUP BY dataset_id, dataset_name")
        conn.run("CREATE MATERIALIZED VIEW mv_substance_counts_for_init AS SELECT substance, count(*), array_agg(DISTINCT unit) AS units FROM pfas_substances GROUP BY substance")
        conn.run("CREATE INDEX ON pfas_points(category, year)")
        conn.run("CREATE INDEX ON pfas_points(matrix)")
        conn.run("CREATE INDEX ON pfas_points(dataset_id)")
        conn.run("CREATE INDEX ON pfas_substances(point_id)")
        conn.run("CREATE INDEX ON pfas_substances(substance, unit)")
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise
    summary = {"source": "https://pdh.cnrs.fr/download/full.csv", "file": str(args.csv_file.resolve()),
               "isPartialExtract": args.partial, "points": total,
               "categories": dict(counts), "substanceReferences": len(keys), "substanceMeasurements": substance_count,
               "nutsIndexed": False}
    (ROOT / ".local" / "data-import.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    conn.close()


if __name__ == "__main__":
    main()
