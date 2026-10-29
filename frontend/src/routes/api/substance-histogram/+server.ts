import { json } from '@sveltejs/kit';
import pool from '$lib/server/pool';
import { AreaSelectorMode, Category } from '$lib/features/exploration/exploration.state.svelte';
import { polygonContains } from 'd3-polygon';
import type { FiltersType } from '$lib/features/exploration/exploration.state.svelte';

export async function POST({ request }) {
    const start = performance.now();
    const {
        filters,
        substance,
        unit,
        rangeLimit,
        areaMode
    }: {
        filters: FiltersType;
        substance: string;
        unit: string;
        rangeLimit: [number, number];
        areaMode: string;
    } = await request.json();

    let fromClause = 'pfas_points p';
    let joins: string[] = [];
    let whereClauses = ['p.category = $1'];
    let params: (string | number)[] = [filters.category];
    let paramIndex = 2;

    // --- NUTS
    if (areaMode === AreaSelectorMode.nuts) {
        if (filters.nutsRegions.length > 0) {
            joins.push('JOIN pfas_nuts n ON p.id = n.point_id');
            const nutsConditions = filters.nutsRegions.map(() => {
                return `(n.version = $${paramIndex++} AND n.level = $${paramIndex++} AND n.nuts_id = $${paramIndex++})`;
            });
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
        params.push(...filters.datasetId);
    }

    // --- Year range
    if (filters.category === Category.Sampling && filters.yearRange.length === 2) {
        whereClauses.push(`p.year >= $${paramIndex} AND p.year <= $${paramIndex + 1}`);
        params.push(filters.yearRange[0], filters.yearRange[1]);
        paramIndex += 2;
    }

    // --- Substances
    joins.push('JOIN pfas_substances s ON p.id = s.point_id');
    whereClauses.push(`s.substance = $${paramIndex++} AND s.unit = $${paramIndex++}`);
    params.push(substance, unit);

    if (rangeLimit?.length === 2) {
        whereClauses.push(`s.value BETWEEN $${paramIndex} AND $${paramIndex + 1}`);
        params.push(rangeLimit[0], rangeLimit[1]);
        paramIndex += 2;
    }

    // --- Sélection conditionnelle des colonnes (ajouter lat/lon si lasso)
    const selectClause =
        areaMode === AreaSelectorMode.lasso
            ? 's.value, p.lat, p.lon'
            : 's.value';

    const sql = `
		SELECT ${selectClause}
		FROM ${fromClause}
		${joins.length ? joins.join(' ') : ''}
		WHERE s.value IS NOT NULL AND ${whereClauses.join(' AND ')}
	`;

    console.log('[api/substance-histogram] SQL Query:', sql, params);

    const client = await pool.connect();
    try {
        const { rows } = await client.query(sql, params);

        let values: number[] = [];

        console.log("################## dataRune.areaSelectorMode", areaMode);
        if (areaMode === AreaSelectorMode.lasso) {
            console.log("lasso on filtre")
            const polygon = filters.lassoRegion;
            if (polygon.length > 2) {
                const polygonXY: [number, number][] = polygon.map(({ lon, lat }) => [lon, lat]);

                for (const row of rows) {
                    const lat = parseFloat(row.lat);
                    const lon = parseFloat(row.lon);
                    const value = row.value;
                    if (
                        lat != null &&
                        lon != null &&
                        !isNaN(lat) &&
                        !isNaN(lon) &&
                        typeof value === 'number' &&
                        polygonContains(polygonXY, [lon, lat])
                    ) {
                        values.push(value);
                    }
                }
            }
        } else {
            values = rows.map((r) => r.value).filter((v) => typeof v === 'number');
        }

        // Calcul des bins
        const [min, max] = rangeLimit;
        const step = (max - min) / 60;
        const bins = Array.from({ length: 60 }, (_, i) => ({
            min: min + i * step,
            max: min + (i + 1) * step,
            count: 0
        }));

        for (const v of values) {
            const index = Math.min(Math.floor((v - min) / step), bins.length - 1);
            if (index >= 0) bins[index].count++;
        }

        const end = performance.now();
        console.log(
            `[api/substance-histogram] Query executed in ${((end - start) / 1000).toFixed(2)} s → ${values.length
            } values`
        );
        return json(bins);
    } catch (err) {
        console.error('[api/substance-histogram] Query error:', err);
        return json([], { status: 500 });
    } finally {
        client.release();
    }
}
