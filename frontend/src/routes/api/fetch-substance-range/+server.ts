import { json } from '@sveltejs/kit';
import pool from '$lib/server/pool';

export async function POST({ request }) {
	const { substance, unit, category } = await request.json();

	const client = await pool.connect();
	try {
		const sql = `
			WITH raw_data AS (
				SELECT s.value::float AS value
				FROM pfas_points p
				JOIN pfas_substances s ON p.id = s.point_id
				WHERE p.category = $1
				  AND s.substance = $2
				  AND s.unit = $3
				  AND s.value IS NOT NULL
			),
			stats AS (
				SELECT
					MIN(value) AS raw_min,
					MAX(value) AS raw_max,
					COUNT(*) AS raw_count,
					PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY value) AS q1,
					PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY value) AS q3
				FROM raw_data
			),
			filtered AS (
				SELECT value
				FROM raw_data, stats
				WHERE value BETWEEN (q1 - 1.5 * (q3 - q1)) AND (q3 + 1.5 * (q3 - q1))
			),
			filtered_stats AS (
				SELECT
					MIN(value) AS filtered_min,
					MAX(value) AS filtered_max,
					COUNT(*) AS filtered_count
				FROM filtered
			)
			SELECT
				stats.raw_min,
				stats.raw_max,
				stats.raw_count,
				filtered_stats.filtered_min,
				filtered_stats.filtered_max,
				filtered_stats.filtered_count
			FROM stats, filtered_stats;
		`;

		console.log('[fetch-substance-range] : ', sql, "args : ", [category, substance, unit]);

		const { rows } = await client.query(sql, [category, substance, unit]);
		const row = rows[0];

		console.log('[fetch-substance-range] Result:', row);

		if (!row || row.raw_count === 0) {
			return json({
				raw: { min: null, max: null, count: 0 },
				filtered: { min: null, max: null, count: 0 }
			});
		}

		return json({
			raw: {
				min: row.raw_min,
				max: row.raw_max,
				count: row.raw_count
			},
			filtered: {
				min: row.filtered_min,
				max: row.filtered_max,
				count: row.filtered_count
			}
		});
	} catch (err) {
		console.error('[fetch-substance-range] Error:', err);
		return json({
			raw: { min: null, max: null, count: 0 },
			filtered: { min: null, max: null, count: 0 }
		});
	} finally {
		client.release();
	}
}
