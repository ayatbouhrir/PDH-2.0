import { json } from '@sveltejs/kit';
import pool from '$lib/server/pool';
import { polygonContains } from 'd3-polygon';
import type { FiltersType } from '$lib/features/exploration/exploration.state.svelte';
import { Category } from '$lib/features/exploration/exploration.state.svelte';

export async function POST({ request }) {
	const {
		filters,
		areaMode
	}: {
		filters: FiltersType;
		areaMode: string;
	} = await request.json();

	console.log('[api/check-units]');

	let fromClause = 'pfas_points p';
	let joins: string[] = ['JOIN pfas_substances s ON p.id = s.point_id'];
	let whereClauses = ['p.category = $1'];
	let params: (string | number)[] = [filters.category];
	let paramIndex = 2;

	// --- NUTS
	if (areaMode === 'NUTS') {
		if (filters.nutsRegions.length > 0) {
			joins.push('JOIN pfas_nuts n ON p.id = n.point_id');
			const nutsConditions = filters.nutsRegions.map(() => `(n.version = $${paramIndex++} AND n.level = $${paramIndex++} AND n.nuts_id = $${paramIndex++})`);
			whereClauses.push(`(${nutsConditions.join(' OR ')})`);
			filters.nutsRegions.forEach((r) => {
				params.push(`nuts${r.year}`, r.level, r.id);
			});
		}
	}

	// --- Matrix
	if (filters.matrix.length > 0) {
		const matrixConditions = filters.matrix.map(() => `p.matrix = $${paramIndex++}`);
		whereClauses.push(`(${matrixConditions.join(' OR ')})`);
		params.push(...filters.matrix);
	}

	// --- Dataset
	if (filters.datasetId.length > 0) {
		const datasetConditions = filters.datasetId.map(() => `p.dataset_id = $${paramIndex++}`);
		whereClauses.push(`(${datasetConditions.join(' OR ')})`);
		params.push(...filters.datasetId.map((d) => parseInt(d)));
	}

	// --- Year range
	if (filters.category === Category.Sampling && filters.yearRange.length === 2) {
		whereClauses.push(`p.year >= $${paramIndex} AND p.year <= $${paramIndex + 1}`);
		params.push(filters.yearRange[0], filters.yearRange[1]);
		paramIndex += 2;
	}

	// --- Dernière substance sélectionnée
	const lastSub = filters.substances.at(-1);
	if (lastSub?.name) {
		whereClauses.push(`s.substance = $${paramIndex++}`);
		params.push(lastSub.name);
	}

	// --- SELECT adapté
	const selectClause =
		areaMode === 'LASSO' ? 'DISTINCT s.unit, p.lat, p.lon' : 'DISTINCT s.unit';

	const sql = `
		SELECT ${selectClause}
		FROM ${fromClause}
		${joins.join(' ')}
		WHERE s.value IS NOT NULL AND ${whereClauses.join(' AND ')}
	`;

	console.log('[api/check-units] SQL:', sql, params);

	const client = await pool.connect();
	try {
		const { rows } = await client.query(sql, params);

		if (areaMode === 'LASSO') {
			const polygon = filters.lassoRegion ?? [];
			if (polygon.length > 2) {
				const polygonXY: [number, number][] = polygon.map(({ lon, lat }) => [lon, lat]);

				const filteredUnits = rows
					.filter((r) => {
						const lat = parseFloat(r.lat);
						const lon = parseFloat(r.lon);
						return (
							lat != null &&
							lon != null &&
							!isNaN(lat) &&
							!isNaN(lon) &&
							polygonContains(polygonXY, [lon, lat])
						);
					})
					.map((r) => r.unit)
					.filter((u) => u !== null);

				console.log('[api/check-units] LASSO filtered units:', filteredUnits);
				return json(filteredUnits);
			}
		}

		const units = rows.map((r) => r.unit).filter((u) => u !== null);
		return json(units);
	} finally {
		client.release();
	}
}
