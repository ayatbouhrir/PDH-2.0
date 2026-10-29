/*import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";

export type TimeSeriesPoint = {
	year: number;
	substance: string;
	value: number;
};

export async function fetchPfasTimeSeries(): Promise<TimeSeriesPoint[]> {
	const res = await fetch("/api/pfas-time-series", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			selectedPfas: analysisRune.selectedVisualizationPfas,
		}),
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Erreur série temporelle: ${res.status}`);
	}

	return await res.json();
}


import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";

export type TimeSeriesPoint = {
	year: number;
	substance: string;
	value: number;
};
*/

import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";

export type TimeSeriesPoint = {
	year: number;
	substance: string;
	value: number;
};

export async function fetchPfasTimeSeries(
	selectedPfas: string[],
): Promise<TimeSeriesPoint[]> {
	const res = await fetch("/api/pfas-time-series", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			selectedPfas,
		}),
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Erreur série temporelle: ${res.status}`);
	}

	return await res.json();
}

export async function fetchPfasTimeSeriesFromState(): Promise<TimeSeriesPoint[]> {
	return fetchPfasTimeSeries(analysisRune.selectedVisualizationPfas);
}