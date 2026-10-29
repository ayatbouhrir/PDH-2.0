import type {
	AnalysisResponse,
	ClusterAssignments,
	ClusteredPoint,
	CondensedBubble,
} from "$lib/shared/types/analysis-contract";
import type { PfasPoint } from "$lib/shared/types/pfas";
import {
	runHistoryRune,
	type AnalysisHistoryMapState,
	type AnalysisHistoryPanelState,
	type RunHistoryEntry,
} from "$lib/features/history/run-history.state.svelte";

export type HistoryLoadResponse = AnalysisResponse & {
	analysisId?: string | null;
	cacheKey?: string | null;
	paramsHash?: string | null;
	condensedBubbles?: CondensedBubble[];
	effectiveParams?: {
		reduction?: string;
	};
	mapState?: AnalysisHistoryMapState | null;
	panelState?: AnalysisHistoryPanelState | null;
	historyEntry?: RunHistoryEntry | null;
	status?: string | null;
	version?: string | null;
	hitCount?: number;
};

export async function loadHistoryResult(
	entry: RunHistoryEntry,
	options: {
		syncHistoryEntry?: boolean;
	} = {},
): Promise<HistoryLoadResponse> {
	const { syncHistoryEntry = true } = options;

	if (entry.analysisId || entry.cacheKey) {
		const response = await fetch("/api/analysis/history/load", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				analysisId: entry.analysisId ?? null,
				cacheKey: entry.cacheKey ?? null,
			}),
		});

		const rawText = await response.text();

		let result: HistoryLoadResponse & {
			detail?: string;
			error?: string;
			message?: string;
		};

		try {
			result = JSON.parse(rawText);
		} catch {
			throw new Error(
				rawText?.trim()
					? `Réponse non JSON (HTTP ${response.status}) : ${rawText.slice(0, 200)}`
					: `Réponse invalide du serveur (HTTP ${response.status})`,
			);
		}

		if (!response.ok) {
			throw new Error(
				result?.detail ??
					result?.error ??
					result?.message ??
					"Erreur chargement historique.",
			);
		}

		if (syncHistoryEntry) {
			runHistoryRune.mergeServerEntry(result?.historyEntry ?? null);
		}
		return result;
	}

	if (entry.snapshot?.result) {
		return entry.snapshot.result as HistoryLoadResponse;
	}

	throw new Error("Aucun résultat disponible pour cette analyse.");
}

export async function loadHistoryFilteredPoints(
	entry: RunHistoryEntry,
): Promise<PfasPoint[]> {
	if (!entry.snapshot?.filters) {
		return [];
	}

	const response = await fetch("/api/filter-points", {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Accept: "application/json",
		},
		body: JSON.stringify({
			filters: {
				...entry.snapshot.filters,
				nutsRegions: [],
			},
			areaMode:
				(entry.snapshot.filters.lassoRegion?.length ?? 0) >= 3 ? "LASSO" : "NUTS",
		}),
	});

	const payload = await response.json().catch(() => null);

	if (!response.ok) {
		throw new Error(
			payload?.error ??
				payload?.message ??
				`Erreur lors du chargement des points (HTTP ${response.status})`,
		);
	}

	if (Array.isArray(payload)) {
		return payload;
	}

	return payload?.points ?? payload?.data ?? [];
}

export function buildClusteredPointsFromAssignments(
	points: PfasPoint[],
	assignments: ClusterAssignments,
	pointAnnotations?: AnalysisResponse["pointAnnotations"],
): ClusteredPoint[] {
	if (!points.length || !Object.keys(assignments).length) {
		return [];
	}

	return points
		.filter((point) => String(point.id) in assignments)
		.map((point) => ({
			pointId: point.id,
			lat: Number(point.lat),
			lon: Number(point.lon),
			pfasSum: point.pfas_sum ?? null,
			clusterId: assignments[String(point.id)],
			raw: {
				...(point as unknown as Record<string, unknown>),
				...(pointAnnotations?.[String(point.id)] ?? {}),
			},
		}));
}
