import type {
	ClusteringAlgorithm,
	ReductionMethod,
	PreprocessingMethod
} from "$lib/shared/types/analysis-contract";
import {
	DEFAULT_ANALYSIS_PARAMS,
	DEFAULT_ANALYSIS_PARAMS_BY_ALGORITHM,
} from "$lib/shared/types/analysis-contract";
import type { ClusterSummary, GlobalMetrics } from "$lib/shared/types/analysis-contract";
import type { DisplayMode } from "$lib/shared/types/analysis-contract";
import type { ClampDisplayMode, ClampResult, ClampRule } from "$lib/shared/types/analysis-contract";

export type VisualizationMode =
	| "none"
	| "temporal"
	| "radar-selected"
	| "radar-detected"
	| "radar-discriminant";

class AnalysisRune {
	#algorithm = $state<ClusteringAlgorithm>("kmeans");
	#k = $state<number>(DEFAULT_ANALYSIS_PARAMS.k);
	#maxIterations = $state<number>(DEFAULT_ANALYSIS_PARAMS.maxIterations);
	#eps = $state<number>(DEFAULT_ANALYSIS_PARAMS.eps);
	#minPts = $state<number>(DEFAULT_ANALYSIS_PARAMS.minPts);
	#minClusterSize = $state<number>(DEFAULT_ANALYSIS_PARAMS.minClusterSize);
	#minSamples = $state<number>(DEFAULT_ANALYSIS_PARAMS.minSamples);
	#clusterSelectionMethod = $state<"eom" | "leaf">(
		DEFAULT_ANALYSIS_PARAMS.clusterSelectionMethod,
	);
	#preprocessing = $state<PreprocessingMethod>(DEFAULT_ANALYSIS_PARAMS.preprocessing);
	#birchThreshold = $state<number>(DEFAULT_ANALYSIS_PARAMS.birchThreshold);
	#birchBranchingFactor = $state<number>(DEFAULT_ANALYSIS_PARAMS.birchBranchingFactor);

	#reduction = $state<ReductionMethod>(DEFAULT_ANALYSIS_PARAMS.reduction);
	#isRunning = $state<boolean>(false);
	#runToken = $state<number>(0);
	#clusterSummaries = $state<ClusterSummary[]>([]);
	#selectedClusterId = $state<number | null>(null);
	#noiseCount = $state(0);
	#clusterFocusIndex = $state<Record<number, number>>({});
	#visualization = $state<VisualizationMode>("none");
	#selectedVisualizationPfas = $state<string[]>(["All"]);
	#selectedModelPfas = $state<string[]>(["All"]);
	#displayMode = $state<DisplayMode>("points");
	#globalMetrics = $state<GlobalMetrics | null>(null);
	#expertMode = $state<boolean>(true);
	#clampResult = $state<ClampResult | null>(null);
	#isClampMapMode = $state<boolean>(false);
	#clampDisplayMode = $state<ClampDisplayMode>("points");
	#selectedClampClusterId = $state<number | null>(null);
	#selectedClampRuleId = $state<string | null>(null);

	#exploringClusterId = $state<number | null>(null);
	#exploringPointIds = $state<Array<string | number>>([]);
	#exploringIndex = $state<number>(0);

	get algorithm() {
		return this.#algorithm;
	}
	set algorithm(value: ClusteringAlgorithm) {
		this.#algorithm = value;
		this.applyDefaultsForAlgorithm(value);
	}

	get k() {
		return this.#k;
	}
	set k(value: number) {
		this.#k = Number.isFinite(value) ? Math.max(2, Math.floor(value)) : 5;
	}

	get maxIterations() {
		return this.#maxIterations;
	}
	set maxIterations(value: number) {
		this.#maxIterations = Number.isFinite(value)
			? Math.max(1, Math.floor(value))
			: 100;
	}

	get eps() {
		return this.#eps;
	}
	set eps(value: number) {
		this.#eps = Number.isFinite(value)
			? Math.max(0.0001, value)
			: DEFAULT_ANALYSIS_PARAMS.eps;
	}

	get minPts() {
		return this.#minPts;
	}
	set minPts(value: number) {
		this.#minPts = Number.isFinite(value)
			? Math.max(2, Math.floor(value))
			: 5;
	}

	get minClusterSize() {
		return this.#minClusterSize;
	}
	set minClusterSize(value: number) {
		this.#minClusterSize = Number.isFinite(value)
			? Math.max(2, Math.floor(value))
			: DEFAULT_ANALYSIS_PARAMS.minClusterSize;
	}

	get minSamples() {
		return this.#minSamples;
	}
	set minSamples(value: number) {
		this.#minSamples = Number.isFinite(value)
			? Math.max(1, Math.floor(value))
			: DEFAULT_ANALYSIS_PARAMS.minSamples;
	}

	get clusterSelectionMethod() {
		return this.#clusterSelectionMethod;
	}
	set clusterSelectionMethod(value: "eom" | "leaf") {
		this.#clusterSelectionMethod = value === "leaf" ? "leaf" : "eom";
	}

	get preprocessing() {
		return this.#preprocessing;
	}
	set preprocessing(value: PreprocessingMethod) {
		this.#preprocessing = value;
	}

	get reduction() {
		return this.#reduction;
	}
	set reduction(value: ReductionMethod) {
		this.#reduction = value;
	}

	get isRunning() {
		return this.#isRunning;
	}
	set isRunning(value: boolean) {
		this.#isRunning = Boolean(value);
	}

	get runToken() {
		return this.#runToken;
	}

	get clusterSummaries() {
		return this.#clusterSummaries;
	}
	set clusterSummaries(value: ClusterSummary[]) {
		this.#clusterSummaries = value;
	}

	get displayMode() {
		return this.#displayMode;
	}
	set displayMode(value: DisplayMode) {
		this.#displayMode = value;
	}

	get globalMetrics() {
		return this.#globalMetrics;
	}
	set globalMetrics(value: GlobalMetrics | null) {
		this.#globalMetrics = value;
	}

	get expertMode() {
		return this.#expertMode;
	}
	set expertMode(value: boolean) {
		this.#expertMode = Boolean(value);
	}

	get clampResult() {
		return this.#clampResult;
	}
	set clampResult(value: ClampResult | null) {
		this.#clampResult = value;
	}

	get isClampMapMode() {
		return this.#isClampMapMode;
	}
	set isClampMapMode(value: boolean) {
		this.#isClampMapMode = Boolean(value);
	}

	get clampDisplayMode() {
		return this.#clampDisplayMode;
	}
	set clampDisplayMode(value: ClampDisplayMode) {
		this.#clampDisplayMode = value === "heatmap" ? "heatmap" : "points";
	}

	get selectedClampClusterId() {
		return this.#selectedClampClusterId;
	}
	set selectedClampClusterId(value: number | null) {
		this.#selectedClampClusterId = value == null ? null : Number(value);
	}

	get selectedClampRuleId() {
		return this.#selectedClampRuleId;
	}
	set selectedClampRuleId(value: string | null) {
		this.#selectedClampRuleId = value ? String(value) : null;
	}

	get activeClampRule(): ClampRule | null {
		if (!this.#clampResult) return null;

		if (this.#selectedClampRuleId) {
			const selected =
				this.#clampResult.rules.find((rule) => rule.id === this.#selectedClampRuleId) ??
				null;
			if (selected) return selected;
		}

		if (this.#clampResult.bestRuleId) {
			return (
				this.#clampResult.rules.find(
					(rule) => rule.id === this.#clampResult?.bestRuleId,
				) ?? null
			);
		}

		return this.#clampResult.rules[0] ?? null;
	}

	get selectedClampCoveredPointIds(): Array<string | number> {
		return this.activeClampRule?.coveredPointIds ?? [];
	}

	get isAllSelectedModelPfas(): boolean {
		return this.#selectedModelPfas.length === 1 && this.#selectedModelPfas[0] === "All";
	}

	get effectiveReductionForUi(): ReductionMethod {
		if (this.#algorithm === "propos") {
			return "saint";
		}
		return this.#reduction;
	}

	requestRun() {
		if (this.#isRunning) return;
		this.#runToken += 1;
	}

	activateClampResult(result: ClampResult, clusterId: number | null = null) {
		this.#clampResult = result;
		this.#selectedClampClusterId = clusterId;
		this.#selectedClampRuleId =
			(clusterId != null ? result.bestRulesByCluster[String(clusterId)] : null) ??
			result.bestRuleId ??
			result.rules[0]?.id ??
			null;
		this.#clampDisplayMode = "points";
		this.#isClampMapMode = this.#selectedClampRuleId != null;
	}

	selectClampRule(clusterId: number | null, ruleId: string | null) {
		this.#selectedClampClusterId = clusterId;
		this.#selectedClampRuleId = ruleId;
		this.#isClampMapMode = Boolean(ruleId);
	}

	resetClampState() {
		this.#clampResult = null;
		this.#isClampMapMode = false;
		this.#clampDisplayMode = "points";
		this.#selectedClampClusterId = null;
		this.#selectedClampRuleId = null;
	}

	reset() {
		this.#algorithm = "kmeans";
		this.#k = DEFAULT_ANALYSIS_PARAMS.k;
		this.#maxIterations = DEFAULT_ANALYSIS_PARAMS.maxIterations;
		this.#eps = DEFAULT_ANALYSIS_PARAMS.eps;
		this.#minPts = DEFAULT_ANALYSIS_PARAMS.minPts;
		this.#minClusterSize = DEFAULT_ANALYSIS_PARAMS.minClusterSize;
		this.#minSamples = DEFAULT_ANALYSIS_PARAMS.minSamples;
		this.#clusterSelectionMethod = DEFAULT_ANALYSIS_PARAMS.clusterSelectionMethod;
		this.#preprocessing = DEFAULT_ANALYSIS_PARAMS.preprocessing;
		this.#reduction = DEFAULT_ANALYSIS_PARAMS.reduction;
		this.#isRunning = false;
		this.#runToken = 0;
		this.#clusterSummaries = [];
		this.#selectedClusterId = null;
		this.#noiseCount = 0;
		this.#clusterFocusIndex = {};
		this.#visualization = "none";
		this.#selectedVisualizationPfas = ["All"];
		this.#selectedModelPfas = ["All"];
		this.#displayMode = "points";
		this.#globalMetrics = null;
		this.#expertMode = true;
		this.resetClampState();
		this.stopExploring();
		this.#birchThreshold = DEFAULT_ANALYSIS_PARAMS.birchThreshold;
		this.#birchBranchingFactor = DEFAULT_ANALYSIS_PARAMS.birchBranchingFactor;
	}

	private applyDefaultsForAlgorithm(algorithm: ClusteringAlgorithm) {
		const defaults = DEFAULT_ANALYSIS_PARAMS_BY_ALGORITHM[algorithm];
		if (!defaults) return;

		this.#k = defaults.k;
		this.#maxIterations = defaults.maxIterations;
		this.#eps = defaults.eps;
		this.#minPts = defaults.minPts;
		this.#minClusterSize = defaults.minClusterSize;
		this.#minSamples = defaults.minSamples;
		this.#clusterSelectionMethod = defaults.clusterSelectionMethod;
		this.#preprocessing = defaults.preprocessing;
		this.#reduction = defaults.reduction;
		this.#birchThreshold = defaults.birchThreshold;
		this.#birchBranchingFactor = defaults.birchBranchingFactor;
	}

	get selectedClusterId() {
		return this.#selectedClusterId;
	}
	set selectedClusterId(value: number | null) {
		this.#selectedClusterId = value;
	}

	toggleSelectedCluster(clusterId: number) {
		if (this.#selectedClusterId === clusterId) {
			this.#selectedClusterId = null;
		} else {
			this.#selectedClusterId = clusterId;
		}
	}

	get noiseCount() {
		return this.#noiseCount;
	}
	set noiseCount(value: number) {
		this.#noiseCount = value;
	}

	get clusterFocusIndex() {
		return this.#clusterFocusIndex;
	}
	set clusterFocusIndex(value: Record<number, number>) {
		this.#clusterFocusIndex = value;
	}

	nextClusterFocusIndex(clusterId: number, size: number) {
		const current = this.#clusterFocusIndex[clusterId] ?? 0;
		const next = size > 0 ? (current + 1) % size : 0;
		this.#clusterFocusIndex = {
			...this.#clusterFocusIndex,
			[clusterId]: next,
		};
		return current;
	}

	resetClusterFocusIndex(clusterId: number) {
		const copy = { ...this.#clusterFocusIndex };
		delete copy[clusterId];
		this.#clusterFocusIndex = copy;
	}

	get visualization() {
		return this.#visualization;
	}
	set visualization(value: VisualizationMode) {
		this.#visualization = value;
	}

	get selectedVisualizationPfas() {
		return this.#selectedVisualizationPfas;
	}
	set selectedVisualizationPfas(value: string[]) {
		const normalized = Array.from(new Set((value ?? []).filter(Boolean)));

		if (normalized.length === 0) {
			this.#selectedVisualizationPfas = ["All"];
			return;
		}

		if (normalized.includes("All")) {
			this.#selectedVisualizationPfas = ["All"];
			return;
		}

		this.#selectedVisualizationPfas = normalized;
	}

	get selectedModelPfas() {
		return this.#selectedModelPfas;
	}
	set selectedModelPfas(value: string[]) {
		const normalized = Array.from(new Set((value ?? []).filter(Boolean)));

		if (normalized.length === 0) {
			this.#selectedModelPfas = ["All"];
			return;
		}

		if (normalized.includes("All")) {
			this.#selectedModelPfas = ["All"];
			return;
		}

		this.#selectedModelPfas = normalized;
	}

	get exploringClusterId() {
		return this.#exploringClusterId;
	}

	get exploringPointIds() {
		return this.#exploringPointIds;
	}

	get exploringIndex() {
		return this.#exploringIndex;
	}
	set exploringIndex(value: number) {
		this.#exploringIndex = value;
	}

	get isExploring() {
		return this.#exploringClusterId != null && this.#exploringPointIds.length > 0;
	}

	get birchThreshold() {
		return this.#birchThreshold;
	}
	set birchThreshold(value: number) {
		this.#birchThreshold = Number.isFinite(value) ? Math.max(0.0001, value) : 0.7;
	}

	get birchBranchingFactor() {
		return this.#birchBranchingFactor;
	}
	set birchBranchingFactor(value: number) {
		this.#birchBranchingFactor = Number.isFinite(value)
			? Math.max(2, Math.floor(value))
			: 50;
	}




	startExploring(clusterId: number, pointIds: Array<string | number>) {
		this.#exploringClusterId = clusterId;
		this.#exploringPointIds = [...pointIds];
		this.#exploringIndex = 0;
	}

	stopExploring() {
		this.#exploringClusterId = null;
		this.#exploringPointIds = [];
		this.#exploringIndex = 0;
	}

	nextExploringPoint() {
		if (this.#exploringPointIds.length === 0) return;
		this.#exploringIndex =
			(this.#exploringIndex + 1) % this.#exploringPointIds.length;
	}

	prevExploringPoint() {
		if (this.#exploringPointIds.length === 0) return;
		this.#exploringIndex =
			(this.#exploringIndex - 1 + this.#exploringPointIds.length) %
			this.#exploringPointIds.length;
	}

	get currentExploringPointId(): string | number | null {
		if (this.#exploringPointIds.length === 0) return null;
		return this.#exploringPointIds[this.#exploringIndex] ?? null;
	}
}

export const analysisRune = new AnalysisRune();
