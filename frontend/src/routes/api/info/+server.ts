import { json } from '@sveltejs/kit';
import pool from '$lib/server/pool';

export async function GET() {
	const totalStart = performance.now();

	const client = await pool.connect();
	
	try {

		const { rows: matrixRows } = await client.query(`SELECT * FROM mv_matrix_counts_for_init`);
		const { rows: datasetRows } = await client.query(`SELECT * FROM mv_datasets_counts_for_init`);

		const allDatasets: Record<string, { id: number; count: number }> = {};
		for (const row of datasetRows) {
			allDatasets[row.dataset_name] = {
				id: parseInt(row.dataset_id),
				count: parseInt(row.count),
			};
		}

		const { rows: substanceRows } = await client.query(`SELECT * FROM mv_substance_counts_for_init`);

		const allSubstances: Record<string, { count: number; units: string[] }> = {};
		for (const row of substanceRows) {
			allSubstances[row.substance] = {
				count: parseInt(row.count),
				units: row.units.filter((u: string) => u !== null)
			};
		}

		const totalEnd = performance.now();
		console.log(`[✅] Total GET /api/info exécuté en ${(totalEnd - totalStart).toFixed(2)} ms`);

		return json({
			allMatrixes: Object.fromEntries(matrixRows.map(row => [row.matrix, parseInt(row.count)])),
			allDatasets,
			allSubstances
		});
	} finally {
		client.release();
	}
}
