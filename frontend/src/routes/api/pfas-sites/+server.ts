import { json } from "@sveltejs/kit";
import { polygonContains } from "d3-polygon";
import pool from "$lib/server/pool";
import {
	normalizePfasSiteCategory,
	type PfasSiteCategory,
} from "$lib/shared/types/pfas";

type NutsRegion = {
	id: string;
	year: string | number;
	level: number;
};

type LassoPoint = {
	lat: number;
	lon: number;
};

type SiteFilters = {
	nutsRegions?: NutsRegion[];
	lassoRegion?: LassoPoint[];
};

type SiteRequestBody = {
	categories?: string[];
	filters?: SiteFilters;
	areaMode?: string;
};

type SiteRow = {
	id: number;
	category: string;
	lat: number | string;
	lon: number | string;
	name?: string | null;
	city?: string | null;
	country?: string | null;
	type?: string | null;
	sector?: string | null;
	source_type?: string | null;
	data_collection_method?: string | null;
	source_text?: string | null;
	source_url?: string | null;
	dataset_id?: string | number | null;
	dataset_name?: string | null;
	details?: string | null;
	date?: string | null;
	year?: number | string | null;
};

function normalizeRequestedCategories(categories: string[] | undefined): PfasSiteCategory[] {
	const normalized = (categories ?? [])
		.map((category) => normalizePfasSiteCategory(category))
		.filter((category): category is PfasSiteCategory => category !== null);

	return Array.from(new Set(normalized));
}

export async function POST({ request }) {
	const { categories, filters = {}, areaMode } =
		(await request.json()) as SiteRequestBody;

	const normalizedCategories = normalizeRequestedCategories(categories);

	if (normalizedCategories.length === 0) {
		return json({ data: [], total: 0 });
	}

	const joins: string[] = [];
	const params: Array<string | number> = [];
	let paramIndex = 1;

	const categoryConditions = normalizedCategories.map(
		() => `LOWER(TRIM(p.category)) = $${paramIndex++}`,
	);
	params.push(...normalizedCategories.map((category) => category.trim().toLowerCase()));

	const whereClauses = [
		`(${categoryConditions.join(" OR ")})`,
		"p.lat IS NOT NULL",
		"p.lon IS NOT NULL",
	];

	if (areaMode === "NUTS" && (filters.nutsRegions?.length ?? 0) > 0) {
		joins.push("JOIN pfas_nuts n ON p.id = n.point_id");

		const nutsConditions = (filters.nutsRegions ?? []).map(() => {
			const condition =
				`(n.version = $${paramIndex++} AND n.level = $${paramIndex++} AND n.nuts_id = $${paramIndex++})`;
			return condition;
		});

		whereClauses.push(`(${nutsConditions.join(" OR ")})`);

		for (const region of filters.nutsRegions ?? []) {
			params.push(`nuts${region.year}`, region.level, region.id);
		}
	}

	const sql = `
		WITH filtered_sites AS (
			SELECT
				p.id,
				TRIM(p.category) AS category,
				p.lat,
				p.lon,
				p.name,
				p.city,
				p.country,
				p.type,
				p.sector,
				p.source_type,
				p.data_collection_method,
				p.source_text,
				p.source_url,
				p.dataset_id,
				p.dataset_name,
				p.details,
				p.date,
				p.year,
				ROW_NUMBER() OVER (
					PARTITION BY
						COALESCE(NULLIF(LOWER(TRIM(p.name)), ''), ''),
						p.lat,
						p.lon,
						LOWER(TRIM(p.category))
					ORDER BY p.id
				) AS row_num
			FROM pfas_points p
			${joins.length ? joins.join(" ") : ""}
			WHERE ${whereClauses.join(" AND ")}
		)
		SELECT
			id,
			category,
			lat,
			lon,
			name,
			city,
			country,
			type,
			sector,
			source_type,
			data_collection_method,
			source_text,
			source_url,
			dataset_id,
			dataset_name,
			details,
			date,
			year
		FROM filtered_sites
		WHERE row_num = 1
		ORDER BY category ASC, name ASC NULLS LAST, id ASC
	`;

	const client = await pool.connect();

	try {
		const { rows } = await client.query<SiteRow>(sql, params);

		let finalRows = rows.map((row) => ({
			...row,
			category: normalizePfasSiteCategory(row.category) ?? row.category,
		}));

		if (areaMode === "LASSO" && (filters.lassoRegion?.length ?? 0) > 2) {
			const polygon = (filters.lassoRegion ?? []).map(
				({ lon, lat }) => [lon, lat] as [number, number],
			);

			finalRows = finalRows.filter((row) => {
				const lat = Number(row.lat);
				const lon = Number(row.lon);

				return (
					Number.isFinite(lat) &&
					Number.isFinite(lon) &&
					polygonContains(polygon, [lon, lat])
				);
			});
		}

		return json({
			data: finalRows,
			total: finalRows.length,
		});
	} finally {
		client.release();
	}
}
