import { json } from '@sveltejs/kit';
import pool from '$lib/server/pool';
import { polygonContains } from 'd3-polygon';
import { text } from '@sveltejs/kit';
import { Category, type FiltersType, type NutsRegion } from '$lib/features/exploration/exploration.state.svelte';
import { exportableFields } from '$lib/features/export/exportable-fields';

export async function POST({ request }) {
	const start = performance.now();

	const {
		filters,
		areaMode,
		exportMode,
		fields
	}: {
		filters: FiltersType;
		areaMode: string;
		exportMode?: boolean;
		fields?: string[];
	} = await request.json();


	let fromClause = 'pfas_points p';
	let joins: string[] = [];
	let params: (string | number)[] = [filters.category];
	let paramIndex = 2;
	let selectClause = 'p.id, p.pfas_sum, p.lat, p.lon, p.year';
	let groupClause = '';
	let whereClauses = [
		'p.category = $1',
		'p.lat IS NOT NULL',
		'p.lon IS NOT NULL'
	];

	if (exportMode && fields?.length) {
		const sanitizedFields = fields.filter(f => exportableFields.includes(f));

		const additionalFields = sanitizedFields.filter(
			(f) => !selectClause.includes(`p.${f}`)
		);
		if (additionalFields.length > 0) {
			selectClause += ', ' + additionalFields.map((f) => `p.${f}`).join(', ');
		}
	}


	// --- Nuts
	if (areaMode === 'NUTS') {
		if (filters.nutsRegions.length > 0) {
			joins.push('JOIN pfas_nuts n ON p.id = n.point_id');
			const nutsConditions = filters.nutsRegions.map((_r: NutsRegion, _i: number) => {
				const condition = `(n.version = $${paramIndex++} AND n.level = $${paramIndex++} AND n.nuts_id = $${paramIndex++})`;
				return condition;
			});
			whereClauses.push(`(${nutsConditions.join(' OR ')})`);
			filters.nutsRegions.forEach((r: NutsRegion) => {
				params.push(`nuts${r.year}`, r.level, r.id);
			});
		}
	}

	if (filters.category === Category.Sampling) {
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
			params.push(...filters.datasetId);
		}

		// --- Year range
		if (filters.category === Category.Sampling && filters.yearRange.length === 2) {
			whereClauses.push(`p.year >= $${paramIndex} AND p.year <= $${paramIndex + 1}`);
			params.push(filters.yearRange[0], filters.yearRange[1]);
			paramIndex += 2;
		}

		// --- Substances
		if (filters.substances && filters.substances.length > 0) {
			selectClause += `,
	  json_agg(
		json_build_object(
		  'substance', s.substance,
		  'unit', s.unit,
		  'value', s.value
		)
	  ) AS substances`;

			joins.push('JOIN pfas_substances s ON p.id = s.point_id');

			const substanceConditions = filters.substances.map(() =>
				`(s.substance = $${paramIndex++} AND s.unit = $${paramIndex++} AND s.value BETWEEN $${paramIndex++} AND $${paramIndex++})`
			);
			whereClauses.push(`(${substanceConditions.join(' OR ')})`);

			// filters.substances.forEach((s) => {
			// 	params.push(s.name, s.unit, s.range[0], s.range[1]);
			// });

			filters.substances.forEach((s) => {
				const [min, max] =
					s.rangeMode === "filtered" ? s.filteredRange : s.rawRange;
				params.push(s.name, s.unit, min, max);
			});


			groupClause = `GROUP BY p.id, p.pfas_sum, p.lat, p.lon, p.year`;
		}
	}

	// --- Query
	const sql = `
		SELECT ${selectClause}
		FROM ${fromClause}
		${joins.length ? joins.join(' ') : ''}
		WHERE ${whereClauses.join(' AND ')}
		${groupClause}
		limit 10000000
	`;

	console.log('[api/filter-points] SQL Query:', sql, params);

	const client = await pool.connect();
	try {
		const { rows } = await client.query(sql, params);

		let finalRows = rows;

		if (areaMode === 'LASSO') {
			const polygon = filters.lassoRegion ?? [];
			if (polygon.length > 2) {
				const polygonXY: [number, number][] = polygon.map(({ lon, lat }) => [lon, lat]);

				finalRows = rows.filter((p) =>
					p.lat != null &&
					p.lon != null &&
					!isNaN(parseFloat(p.lat)) &&
					!isNaN(parseFloat(p.lon)) &&
					polygonContains(polygonXY, [parseFloat(p.lon), parseFloat(p.lat)])
				);
			}
		}

		const end = performance.now();
		console.log(`[api/filter-points] Query executed in ${((end - start) / 1000).toFixed(2)} s =>`, rows.length, "rows");

		if (!exportMode) {
			return json(finalRows);
		}

		// --- export CSV ---
		const sanitizedFields = (fields ?? []).filter(f => exportableFields.includes(f));
		if (sanitizedFields.length === 0) {
			return text('Invalid fields', { status: 400 });
		}

		const csvLines = [sanitizedFields.join(',')];

		console.log('[api/filter-points] CSV lines:', csvLines);
		for (const row of finalRows) {
			const line = sanitizedFields.map((f) => {
				const value = row[f];
				if (typeof value === 'object') {
					return `"${JSON.stringify(value).replace(/"/g, '""')}"`;
				}
				return `"${String(value ?? '').replace(/"/g, '""')}"`;
			}).join(',');
			csvLines.push(line);
		}

		const csvContent = csvLines.join('\n');
		return text(csvContent, {
			headers: {
				'Content-Type': 'text/csv',
				'Content-Disposition': 'attachment; filename="export.csv"'
			}
		});
	} finally {
		client.release();
	}
}
