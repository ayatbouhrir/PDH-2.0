import { json } from '@sveltejs/kit';
import pool from '$lib/server/pool';

export async function POST({ request }) {
	const start = performance.now();
	const { pointIds } = await request.json();

	if (!pointIds || !Array.isArray(pointIds) || pointIds.length === 0) {
		return json({ error: 'Missing or invalid pointIds' }, { status: 400 });
	}

	const client = await pool.connect();
	try {
		let result;

		if (pointIds.length === 1) {
			// Cas simple : un seul point, on retourne ses détails
			const sql = `SELECT * FROM pfas_points WHERE id = $1`;
			const { rows } = await client.query(sql, [pointIds[0]]);
			result = rows;
		} else {
			// Cas multiple : requête groupée sur les substances
			const placeholders = pointIds.map((_, i) => `$${i + 1}`).join(', ');
			const sql = `
				SELECT
					s.substance,
					s.unit,
					COUNT(*) AS count,
					COUNT(*) FILTER (WHERE s.value IS NOT NULL) AS detected,
					AVG(s.value) FILTER (WHERE s.value IS NOT NULL) AS detected_mean,
					MIN(s.value) FILTER (WHERE s.value IS NOT NULL) AS min_value,
					MAX(s.value) FILTER (WHERE s.value IS NOT NULL) AS max_value,
					STDDEV_SAMP(s.value) FILTER (WHERE s.value IS NOT NULL) AS std_dev,
					PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY s.value) FILTER (WHERE s.value IS NOT NULL) AS q1,
					PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY s.value) FILTER (WHERE s.value IS NOT NULL) AS median,
					PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY s.value) FILTER (WHERE s.value IS NOT NULL) AS q3
				FROM
					pfas_points p
				JOIN
					pfas_substances s ON p.id = s.point_id
				WHERE 
					p.id IN (${placeholders})
				GROUP BY
					s.substance, s.unit
				ORDER BY count DESC;
			`;
			const { rows } = await client.query(sql, pointIds);
			result = rows;
		}

		const end = performance.now();
		console.log(
			`[api/point-details] Query for ${pointIds.length} IDs in ${(end - start).toFixed(2)} ms => ${Array.isArray(result) ? result.length : 0} rows`
		);

		return json(result);
	} catch (err) {
		console.error('[api/point-details] Query failed:', err);
		return json({ error: 'Internal Server Error' }, { status: 500 });
	} finally {
		client.release();
	}
}
