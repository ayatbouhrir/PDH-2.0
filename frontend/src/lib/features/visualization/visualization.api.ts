import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
import { ANALYSIS_LIMITS } from "$lib/shared/types/analysis-contract";

const VISUALIZATION_DEFAULTS = {
	normalizeRadar: true,
} as const;

export type TemporalSeriesPoint = {
	x: number;
	y: number;
};

export type TemporalSeries = {
	label: string;
	points: TemporalSeriesPoint[];
};

export type TemporalVisualizationResponse = {
	mode: "temporal";
	series: TemporalSeries[];
	meta?: {
		count?: number;
		clusterId?: number | null;
		error?: string;
	};
};

export type RadarSeries = {
	label: string;
	values: number[];
	rawValues?: number[];
};

export type RadarVisualizationResponse = {
	mode: "radar";
	axes: string[];
	series: RadarSeries[];
	meta?: {
		count?: number;
		clusterId?: number | null;
		error?: string;
		normalized?: boolean;
	};
};

export async function fetchTemporalVisualization(
	assignments: Record<string, number>,
	clusterId: number | null,
	pointIds: number[],
	temporalMode: "global" | "cluster",
	selectedPfas: string[],
	aggregation: "mean" | "median" = "mean",
): Promise<TemporalVisualizationResponse> {
	const normalizedSelectedPfas = Array.from(
		new Set((selectedPfas ?? []).filter(Boolean)),
	);

	if (temporalMode === "cluster") {
		if (!assignments || Object.keys(assignments).length === 0) {
			throw new Error("Le mode cluster nécessite des assignments.");
		}

		if (
			normalizedSelectedPfas.length !== 1 ||
			normalizedSelectedPfas[0] === "All"
		) {
			throw new Error(
				"Le mode cluster nécessite exactement un seul PFAS sélectionné.",
			);
		}
	}

	const res = await fetch(`/api/visualization/temporal`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			selectedPfas:
				normalizedSelectedPfas.length > 0 ? normalizedSelectedPfas : ["All"],
			assignments,
			clusterId,
			pointIds,
			temporalMode,
			aggregation,
			topN: ANALYSIS_LIMITS.temporalTopN,
		}),
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Erreur temporal visualization: ${res.status}`);
	}

	return await res.json();
}

export async function fetchRadarVisualization(
	assignments: Record<string, number>,
	clusterId: number | null,
	pointIds: number[],
	mode: "selected" | "detected" | "discriminant",
	selectedVisualizationPfas: string[] = [],
): Promise<RadarVisualizationResponse> {
	const axesPfas =
		mode === "selected"
			? selectedVisualizationPfas.includes("All")
				? []
				: selectedVisualizationPfas
			: undefined;

	const res = await fetch(`/api/visualization/radar`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			mode,
			axesPfas,
			assignments,
			clusterId,
			pointIds,
			normalize: VISUALIZATION_DEFAULTS.normalizeRadar,
			topN: ANALYSIS_LIMITS.radarTopN,
		}),
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Erreur radar visualization: ${res.status}`);
	}

	return await res.json();
}

export async function fetchRadarVisualizationFromState(
	assignments: Record<string, number>,
	clusterId: number | null,
	pointIds: number[],
	mode: "selected" | "detected" | "discriminant",
): Promise<RadarVisualizationResponse> {
	return fetchRadarVisualization(
		assignments,
		clusterId,
		pointIds,
		mode,
		analysisRune.selectedVisualizationPfas,
	);
}



/*import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";

const PYTHON_API_URL =
	import.meta.env.VITE_PYTHON_API_URL ?? "http://127.0.0.1:8000";

export type TemporalSeriesPoint = {
	x: number;
	y: number;
};

export type TemporalSeries = {
	label: string;
	points: TemporalSeriesPoint[];
};

export type TemporalVisualizationResponse = {
	mode: "temporal";
	series: TemporalSeries[];
	meta?: {
		count?: number;
		clusterId?: number | null;
		error?: string;
	};
};

export type RadarSeries = {
	label: string;
	values: number[];
	rawValues?: number[];
};

export type RadarVisualizationResponse = {
	mode: "radar";
	axes: string[];
	series: RadarSeries[];
	meta?: {
		count?: number;
		clusterId?: number | null;
		error?: string;
		normalized?: boolean;
	};
};

export async function fetchTemporalVisualization(
	assignments: Record<string, number>,
	clusterId: number | null,
	pointIds: number[],
	temporalMode: "global" | "cluster",
	selectedPfas: string[],
	aggregation: "mean" | "median" = "mean",
): Promise<TemporalVisualizationResponse> {
	const normalizedSelectedPfas = Array.from(
		new Set((selectedPfas ?? []).filter(Boolean)),
	);

	if (temporalMode === "cluster") {
		if (!assignments || Object.keys(assignments).length === 0) {
			throw new Error("Le mode cluster nécessite des assignments.");
		}

		if (
			normalizedSelectedPfas.length !== 1 ||
			normalizedSelectedPfas[0] === "All"
		) {
			throw new Error("Le mode cluster nécessite exactement un seul PFAS sélectionné.");
		}
	}

	const res = await fetch(`${PYTHON_API_URL}/visualization/temporal`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			selectedPfas:
				normalizedSelectedPfas.length > 0 ? normalizedSelectedPfas : ["All"],
			assignments,
			clusterId,
			pointIds,
			temporalMode,
			aggregation,
			topN: 5,
		}),
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Erreur temporal visualization: ${res.status}`);
	}

	return await res.json();
}



export async function fetchRadarVisualization(
	assignments: Record<string, number>,
	clusterId: number | null,
	pointIds: number[],
	mode: "selected" | "detected" | "discriminant",
): Promise<RadarVisualizationResponse> {
	const axesPfas =
		mode === "selected"
			? analysisRune.selectedVisualizationPfas.includes("All")
				? []
				: analysisRune.selectedVisualizationPfas
			: undefined;

	const res = await fetch(`${PYTHON_API_URL}/visualization/radar`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			mode,
			axesPfas,
			assignments,
			clusterId,
			pointIds,
			normalize: true,
			topN: 10,
		}),
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Erreur radar visualization: ${res.status}`);
	}

	return await res.json();
}
*/