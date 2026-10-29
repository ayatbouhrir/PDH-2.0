import type {
	CondensedGroupInfo,
	DetailsContext,
	DisplayMode,
	GlobalMetrics,
	SavedAnalysisSnapshot,
	ViewportBounds,
} from "$lib/shared/types/analysis-contract";

export type AnalysisHistoryMapState = {
	viewport: ViewportBounds | null;
	displayMode?: DisplayMode;
	tileLayerIndex?: number;
};

export type AnalysisHistoryPanelState = {
	detailsContext?: DetailsContext;
	selectedClusterId?: number | null;
	selectedPointIds?: Array<string | number>;
	selectedBubblePointIds?: Array<string | number>;
	selectedCondensedGroup?: CondensedGroupInfo | null;
	clusterGeometryRequest?: {
		clusterId: number;
		showCentroid: boolean;
		showMin: boolean;
		showMax: boolean;
	} | null;
	showCondensation3D?: boolean;
};

export type RunHistoryEntry = {
	id: string;
	name?: string;
	timestamp: number;
	createdAt?: string | null;
	lastOpenedAt?: number | null;
	lastOpenedAtIso?: string | null;
	algorithm: "kmeans" | "dbscan" | "hdbscan" | "propos";
	params: {
		k?: number;
		eps?: number;
		minPts?: number;
		minClusterSize?: number;
		minSamples?: number;
		clusterSelectionMethod?: "eom" | "leaf" | string;
		maxIterations?: number;
		preprocessing: string;
		reduction: string;
		birchThreshold?: number;
		birchBranchingFactor?: number;
	};
	pfasSelected: string[];
	pointCount: number;
	clusterCount: number;
	noiseCount: number;
	durationMs: number;
	globalMetrics: GlobalMetrics | null;
	metricsSummary?: Record<string, unknown> | null;
	requestSnapshot?: Record<string, unknown> | null;
	runMetadata?: Record<string, unknown> | null;
	reductionMeta?: Record<string, unknown> | null;
	clusteringMeta?: Record<string, unknown> | null;
	condensationMeta?: Record<string, unknown> | null;
	analysisId?: string | null;
	cacheKey?: string | null;
	paramsHash?: string | null;
	cached?: boolean;
	status?: string | null;
	version?: string | null;
	hitCount?: number;
	mapState?: AnalysisHistoryMapState | null;
	panelState?: AnalysisHistoryPanelState | null;
	snapshot: SavedAnalysisSnapshot | null;
};

const COMPARISON_MIN_RUNS = 2;
const COMPARISON_MAX_RUNS = 4;

const STORAGE_KEY = "pdh-run-history-v5";
const MAX_ENTRIES = 10;

function normalizeSnapshot(snapshot: any): SavedAnalysisSnapshot | null {
	if (!snapshot || typeof snapshot !== "object") {
		return null;
	}

	return {
		filters: snapshot.filters ?? {
			category: null,
			datasetId: [],
			matrix: [],
			yearRange: null,
			lassoRegion: [],
			substances: [],
		},
		viewport: snapshot.viewport ?? null,
		params: {
			k: snapshot.params?.k,
			maxIterations: snapshot.params?.maxIterations,
			eps: snapshot.params?.eps,
			minPts: snapshot.params?.minPts,
			minClusterSize: snapshot.params?.minClusterSize,
			minSamples: snapshot.params?.minSamples,
			clusterSelectionMethod: snapshot.params?.clusterSelectionMethod,
			preprocessing: snapshot.params?.preprocessing ?? "none",
			reduction: snapshot.params?.reduction ?? "none",
			birchThreshold: snapshot.params?.birchThreshold,
			birchBranchingFactor: snapshot.params?.birchBranchingFactor,
		},
		selectedModelPfas: Array.isArray(snapshot.selectedModelPfas)
			? [...snapshot.selectedModelPfas]
			: ["All"],
		mode: snapshot.mode === "simple" ? "simple" : "expert",
		algorithm:
			snapshot.algorithm === "dbscan" ||
			snapshot.algorithm === "hdbscan" ||
			snapshot.algorithm === "propos"
				? snapshot.algorithm
				: "kmeans",
		displayMode:
			snapshot.displayMode === "condensed" ? "condensed" : "points",
		result: snapshot.result ?? null,
	};
}

function normalizeMapState(state: any, snapshot: SavedAnalysisSnapshot | null) {
	if (!state && !snapshot) {
		return null;
	}

	return {
		viewport: state?.viewport ?? snapshot?.viewport ?? null,
		displayMode:
			state?.displayMode ??
			snapshot?.displayMode ??
			(snapshot?.result?.displayMode ?? "points"),
		tileLayerIndex:
			typeof state?.tileLayerIndex === "number" ? state.tileLayerIndex : undefined,
	} satisfies AnalysisHistoryMapState;
}

function normalizePanelState(state: any): AnalysisHistoryPanelState | null {
	if (!state || typeof state !== "object") {
		return null;
	}

	return {
		detailsContext: state.detailsContext ?? "none",
		selectedClusterId:
			typeof state.selectedClusterId === "number"
				? state.selectedClusterId
				: null,
		selectedPointIds: Array.isArray(state.selectedPointIds)
			? [...state.selectedPointIds]
			: [],
		selectedBubblePointIds: Array.isArray(state.selectedBubblePointIds)
			? [...state.selectedBubblePointIds]
			: [],
		selectedCondensedGroup: state.selectedCondensedGroup ?? null,
		clusterGeometryRequest: state.clusterGeometryRequest ?? null,
		showCondensation3D: Boolean(state.showCondensation3D),
	};
}

function normalizeEntry(entry: any): RunHistoryEntry {
	const snapshot = normalizeSnapshot(entry?.snapshot ?? null);
	const cacheIdentity =
		entry?.cacheKey ??
		entry?.analysisId ??
		entry?.paramsHash ??
		entry?.id ??
		crypto.randomUUID();

	return {
		id: entry?.id ?? cacheIdentity,
		name: entry?.name ?? undefined,
		timestamp: Number(entry?.timestamp ?? Date.now()),
		createdAt: entry?.createdAt ?? null,
		lastOpenedAt:
			entry?.lastOpenedAt != null ? Number(entry.lastOpenedAt) : null,
		lastOpenedAtIso: entry?.lastOpenedAtIso ?? null,
		algorithm:
			entry?.algorithm === "dbscan" ||
			entry?.algorithm === "hdbscan" ||
			entry?.algorithm === "propos"
				? entry.algorithm
				: "kmeans",
		params: {
			k: entry?.params?.k,
			eps: entry?.params?.eps,
			minPts: entry?.params?.minPts,
			minClusterSize: entry?.params?.minClusterSize,
			minSamples: entry?.params?.minSamples,
			clusterSelectionMethod: entry?.params?.clusterSelectionMethod,
			maxIterations: entry?.params?.maxIterations,
			preprocessing: entry?.params?.preprocessing ?? "none",
			reduction: entry?.params?.reduction ?? "none",
			birchThreshold: entry?.params?.birchThreshold,
			birchBranchingFactor: entry?.params?.birchBranchingFactor,
		},
		pfasSelected: Array.isArray(entry?.pfasSelected) ? [...entry.pfasSelected] : [],
		pointCount: Number(entry?.pointCount ?? 0),
		clusterCount: Number(entry?.clusterCount ?? 0),
		noiseCount: Number(entry?.noiseCount ?? 0),
		durationMs: Number(entry?.durationMs ?? 0),
		globalMetrics: entry?.globalMetrics ?? null,
		metricsSummary: entry?.metricsSummary ?? null,
		requestSnapshot: entry?.requestSnapshot ?? null,
		runMetadata: entry?.runMetadata ?? null,
		reductionMeta: entry?.reductionMeta ?? null,
		clusteringMeta: entry?.clusteringMeta ?? null,
		condensationMeta: entry?.condensationMeta ?? null,
		analysisId: entry?.analysisId ?? entry?.cacheKey ?? null,
		cacheKey: entry?.cacheKey ?? entry?.analysisId ?? null,
		paramsHash: entry?.paramsHash ?? entry?.cacheKey ?? entry?.analysisId ?? null,
		cached: Boolean(entry?.cached),
		status: entry?.status ?? null,
		version: entry?.version ?? null,
		hitCount: Number(entry?.hitCount ?? 0),
		mapState: normalizeMapState(entry?.mapState ?? null, snapshot),
		panelState: normalizePanelState(entry?.panelState ?? null),
		snapshot,
	};
}

function normalizeEntries(entries: any[]): RunHistoryEntry[] {
	return (entries ?? []).map((entry) => normalizeEntry(entry));
}

function getEntryIdentity(entry: Pick<RunHistoryEntry, "id" | "cacheKey" | "analysisId">) {
	return entry.cacheKey ?? entry.analysisId ?? entry.id;
}

function mergeEntries(
	existing: RunHistoryEntry | undefined,
	incoming: RunHistoryEntry,
): RunHistoryEntry {
	if (!existing) {
		return incoming;
	}

	const snapshot = incoming.snapshot
		? {
				...incoming.snapshot,
				result: incoming.snapshot.result ?? existing.snapshot?.result ?? null,
			}
		: existing.snapshot;

	return {
		...existing,
		...incoming,
		id: existing.id,
		snapshot,
		mapState: incoming.mapState ?? existing.mapState ?? null,
		panelState: incoming.panelState ?? existing.panelState ?? null,
	};
}

function upsertEntries(
	entries: RunHistoryEntry[],
	incoming: RunHistoryEntry,
): RunHistoryEntry[] {
	const identity = getEntryIdentity(incoming);
	const existing = entries.find((entry) => getEntryIdentity(entry) === identity);
	const merged = mergeEntries(existing, incoming);
	const rest = entries.filter((entry) => getEntryIdentity(entry) !== identity);
	return [merged, ...rest].slice(0, MAX_ENTRIES);
}

function loadFromSession(): RunHistoryEntry[] {
	try {
		const raw = sessionStorage.getItem(STORAGE_KEY);
		return raw ? normalizeEntries(JSON.parse(raw)) : [];
	} catch {
		return [];
	}
}

function saveToSession(entries: RunHistoryEntry[]) {
	try {
		sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
	} catch {
		// sessionStorage indisponible ou plein
	}
}

export function isComparableHistoryEntry(entry: RunHistoryEntry | null | undefined) {
	return Boolean(entry?.cacheKey || entry?.analysisId || entry?.snapshot?.result);
}

async function readErrorMessage(response: Response): Promise<string> {
	const fallback = `Historique indisponible (HTTP ${response.status})`;
	const contentType = response.headers.get("content-type") ?? "";

	try {
		if (contentType.includes("application/json")) {
			const payload = await response.json();
			return payload?.detail ?? payload?.error ?? payload?.message ?? fallback;
		}

		const text = await response.text();
		return text?.trim() || fallback;
	} catch {
		return fallback;
	}
}

class RunHistoryRune {
	#entries = $state<RunHistoryEntry[]>([]);
	#loading = $state(false);
	#comparisonSelection = $state<string[]>([]);
	pendingLoadEntry = $state<RunHistoryEntry | null>(null);

	constructor() {
		if (typeof window !== "undefined") {
			this.#entries = loadFromSession();
			void this.refreshFromServer();
		}
	}

	get entries() {
		return this.#entries;
	}

	get isLoading() {
		return this.#loading;
	}

	get comparisonSelection() {
		return this.#comparisonSelection;
	}

	get comparisonSelectionEntries() {
		return this.#comparisonSelection
			.map((id) => this.#entries.find((entry) => entry.id === id) ?? null)
			.filter((entry): entry is RunHistoryEntry => Boolean(entry));
	}

	get comparisonSelectionCount() {
		return this.comparisonSelectionEntries.length;
	}

	get canCompareSelection() {
		const comparableEntries = this.comparisonSelectionEntries.filter((entry) =>
			isComparableHistoryEntry(entry),
		);
		return (
			comparableEntries.length >= COMPARISON_MIN_RUNS &&
			comparableEntries.length <= COMPARISON_MAX_RUNS
		);
	}

	isSelectedForComparison(id: string) {
		return this.#comparisonSelection.includes(id);
	}

	canSelectForComparison(id: string) {
		return (
			this.isSelectedForComparison(id) ||
			this.#comparisonSelection.length < COMPARISON_MAX_RUNS
		);
	}

	toggleComparisonSelection(id: string) {
		if (this.#comparisonSelection.includes(id)) {
			this.#comparisonSelection = this.#comparisonSelection.filter(
				(selectedId) => selectedId !== id,
			);
			return;
		}

		const entry = this.#entries.find((candidate) => candidate.id === id) ?? null;
		if (!entry || !isComparableHistoryEntry(entry)) {
			return;
		}

		if (this.#comparisonSelection.length >= COMPARISON_MAX_RUNS) {
			return;
		}

		this.#comparisonSelection = [...this.#comparisonSelection, id];
	}

	clearComparisonSelection() {
		this.#comparisonSelection = [];
	}

	#syncComparisonSelection() {
		const validIds = new Set(
			this.#entries
				.filter((entry) => isComparableHistoryEntry(entry))
				.map((entry) => entry.id),
		);

		this.#comparisonSelection = this.#comparisonSelection.filter((id) =>
			validIds.has(id),
		);
	}

	async refreshFromServer(limit = MAX_ENTRIES) {
		if (typeof window === "undefined") return;

		this.#loading = true;

		try {
			const response = await fetch(`/api/analysis/history/list?limit=${limit}`);
			if (!response.ok) {
				throw new Error(await readErrorMessage(response));
			}

			const payload = await response.json();
			const serverEntries = normalizeEntries(payload?.entries ?? []);
			const localFallbackEntries = this.#entries.filter(
				(entry) => !entry.cacheKey && !entry.analysisId,
			);
			const mergedServerEntries = serverEntries.map((serverEntry) => {
				const identity = getEntryIdentity(serverEntry);
				const existing = this.#entries.find(
					(entry) => getEntryIdentity(entry) === identity,
				);
				return mergeEntries(existing, serverEntry);
			});

			this.#entries = [...mergedServerEntries, ...localFallbackEntries].slice(
				0,
				MAX_ENTRIES,
			);
			this.#syncComparisonSelection();
			saveToSession(this.#entries);
		} catch (error) {
			console.error("[runHistoryRune.refreshFromServer]", error);
		} finally {
			this.#loading = false;
		}
	}

	addRun(entry: Omit<RunHistoryEntry, "id" | "timestamp">): RunHistoryEntry {
		const newEntry = normalizeEntry({
			...entry,
			id: entry.cacheKey ?? entry.analysisId ?? crypto.randomUUID(),
			timestamp: Date.now(),
			lastOpenedAt: Date.now(),
		});

		this.#entries = upsertEntries(this.#entries, newEntry);
		this.#syncComparisonSelection();
		saveToSession(this.#entries);
		return this.#entries[0];
	}

	mergeServerEntry(entry: RunHistoryEntry | Record<string, unknown> | null) {
		if (!entry) return null;

		const normalized = normalizeEntry(entry);
		this.#entries = upsertEntries(this.#entries, normalized);
		this.#syncComparisonSelection();
		saveToSession(this.#entries);
		return this.#entries[0] ?? null;
	}

	updateServerRefs(
		id: string,
		payload: {
			analysisId?: string | null;
			cacheKey?: string | null;
			paramsHash?: string | null;
			cached?: boolean;
			status?: string | null;
			version?: string | null;
			hitCount?: number;
		},
	) {
		this.#entries = this.#entries.map((entry) =>
			entry.id === id
				? {
						...entry,
						analysisId: payload.analysisId ?? entry.analysisId ?? null,
						cacheKey: payload.cacheKey ?? entry.cacheKey ?? null,
						paramsHash: payload.paramsHash ?? entry.paramsHash ?? null,
						cached: payload.cached ?? entry.cached ?? false,
						status: payload.status ?? entry.status ?? null,
						version: payload.version ?? entry.version ?? null,
						hitCount: payload.hitCount ?? entry.hitCount ?? 0,
					}
				: entry,
		);

		this.#syncComparisonSelection();
		saveToSession(this.#entries);
	}

	updateLocalState(
		cacheKey: string,
		payload: {
			mapState?: AnalysisHistoryMapState | null;
			panelState?: AnalysisHistoryPanelState | null;
		},
	) {
		this.#entries = this.#entries.map((entry) =>
			(entry.cacheKey ?? entry.analysisId) === cacheKey
				? {
						...entry,
						mapState: payload.mapState ?? entry.mapState ?? null,
						panelState: payload.panelState ?? entry.panelState ?? null,
						snapshot: entry.snapshot
							? {
									...entry.snapshot,
									viewport:
										payload.mapState?.viewport ?? entry.snapshot.viewport ?? null,
									displayMode:
										payload.mapState?.displayMode ??
										entry.snapshot.displayMode ??
										"points",
								}
							: entry.snapshot,
					}
				: entry,
		);

		this.#syncComparisonSelection();
		saveToSession(this.#entries);
	}

	requestLoad(id: string) {
		this.pendingLoadEntry = this.#entries.find((entry) => entry.id === id) ?? null;
	}

	clearPendingLoad() {
		this.pendingLoadEntry = null;
	}

	async remove(id: string) {
		const target = this.#entries.find((entry) => entry.id === id) ?? null;
		this.#entries = this.#entries.filter((entry) => entry.id !== id);
		this.#syncComparisonSelection();
		saveToSession(this.#entries);

		if (!target?.cacheKey && !target?.analysisId) {
			return;
		}

		try {
			await fetch("/api/analysis/history/delete", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					cacheKey: target.cacheKey ?? null,
					analysisId: target.analysisId ?? null,
				}),
			});
		} catch (error) {
			console.error("[runHistoryRune.remove]", error);
		}
	}

	async rename(id: string, name: string) {
		const clean = name.trim();
		const target = this.#entries.find((entry) => entry.id === id) ?? null;

		this.#entries = this.#entries.map((entry) =>
			entry.id === id ? { ...entry, name: clean || undefined } : entry,
		);
		this.#syncComparisonSelection();
		saveToSession(this.#entries);

		if (!target?.cacheKey && !target?.analysisId) {
			return;
		}

		try {
			const response = await fetch("/api/analysis/history/rename", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					cacheKey: target.cacheKey ?? null,
					analysisId: target.analysisId ?? null,
					name: clean || null,
				}),
			});

			if (!response.ok) {
				throw new Error(await readErrorMessage(response));
			}

			const payload = await response.json();
			this.mergeServerEntry(payload?.entry ?? null);
		} catch (error) {
			console.error("[runHistoryRune.rename]", error);
		}
	}

	async clear() {
		this.#entries = [];
		this.#comparisonSelection = [];
		this.pendingLoadEntry = null;
		saveToSession([]);

		try {
			await fetch("/api/analysis/history/clear", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
			});
		} catch (error) {
			console.error("[runHistoryRune.clear]", error);
		}
	}
}

export const runHistoryRune = new RunHistoryRune();
