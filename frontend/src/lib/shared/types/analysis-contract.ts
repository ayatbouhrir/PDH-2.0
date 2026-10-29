export type DetailsContext = "none" | "point" | "cluster" | "condensed_group" | "all";

export type ClusteringAlgorithm = "kmeans" | "dbscan" | "hdbscan" | "propos";
export type ReductionMethod = "none" | "pca" | "tsne" | "autoencoder" | "saint";
export type PreprocessingMethod = "none" | "standardize" | "normalize";

export type ClusterSummary = {
	clusterId: number;
	count: number;
	avgPfasSum: number;
	minPfasSum: number;
	maxPfasSum: number;
	centerLat: number;
	centerLon: number;

	distanceAvg?: number;
	distanceMin?: number;
	distanceMax?: number;
	dispersion?: number;
	relativeSize?: number;
	dominantPfas?: string | null;

	inertia?: number;
	clusterPersistence?: number | null;

	corePoints?: number;
	borderPoints?: number;
	clusterType?: string;

	centroidLat?: number | null;
	centroidLon?: number | null;

	minPointId?: string | number | null;
	minPointLat?: number | null;
	minPointLon?: number | null;

	maxPointId?: string | number | null;
	maxPointLat?: number | null;
	maxPointLon?: number | null;

	geoDistanceAvg?: number;
	geoDistanceMin?: number;
	geoDistanceMax?: number;
	geoDispersion?: number;
};

export type ViewportBounds = {
	south: number;
	west: number;
	north: number;
	east: number;
};

export type LassoPoint = {
	lat: number;
	lon: number;
};

export type SubstanceFilter = {
	name: string;
	unit: string;
	rangeMode?: "raw" | "filtered";
	filtered?: {
		min: number;
		max: number;
	};
	raw?: {
		min: number;
		max: number;
	};
	filteredRange?: [number, number];
	rawRange?: [number, number];
};

export type AnalysisFilters = {
	category?: string | null;
	datasetId: string[];
	matrix: string[];
	yearRange?: [number, number] | number[] | null;
	lassoRegion: LassoPoint[];
	substances: SubstanceFilter[];
};

export type AnalysisParams = {
	k: number;
	maxIterations: number;
	eps: number;
	minPts: number;
	minClusterSize: number;
	minSamples: number;
	clusterSelectionMethod: "eom" | "leaf";
	preprocessing: PreprocessingMethod;
	reduction: ReductionMethod;
	birchThreshold: number;
	birchBranchingFactor: number;
};

export type AnalysisRequest = {
	algorithm: ClusteringAlgorithm;
	filters: AnalysisFilters;
	viewport: ViewportBounds | null;
	params: AnalysisParams;
	selectedModelPfas: string[];
	mode: "simple" | "expert";
};

export type RawPoint = Record<string, unknown>;

export type ClusteredPoint = {
	pointId: string | number | null;
	lat: number;
	lon: number;
	pfasSum: number | null;
	clusterId: number;
	raw: RawPoint;
};

export type AnalysisSummary = {
	analyzedPoints: number;
	clusterCount: number;
	noiseCount: number;
	durationMs: number;
	tooMany: boolean;
	message: string;
};

export type ClusterAssignments = Record<string, number>;

export type GlobalMetrics = {
	algorithm: string;
	silhouetteScore?: number | null;
	daviesBouldinIndex?: number | null;
	calinskiHarabaszScore?: number | null;
	wcss?: number | null;
	noiseCount?: number;
	noiseRatio?: number;
	relativeValidity?: number | null;
	clusterPersistenceMean?: number | null;
	clusterSizes?: number[];
	avgClusterSize?: number | null;
	minClusterSize?: number | null;
	maxClusterSize?: number | null;
};

export type ClampDisplayMode = "points" | "heatmap";

export type ClampCondition = {
	feature: string;
	operator: string;
	value: number;
	unit?: string | null;
};

export type ClampRule = {
	id: string;
	cluster: number;
	rule: string;
	conditions: ClampCondition[];
	support: number;
	supportRatio: number;
	precision: number;
	coverageCluster: number;
	score: number;
	coveredPointIds: Array<string | number>;
	features: string[];
};

export type ClampResult = {
	method: "clamp";
	status: "ok";
	rules: ClampRule[];
	rulesByCluster: Record<string, ClampRule[]>;
	coveredPointIds: Record<string, Array<string | number>>;
	bestRuleId: string | null;
	bestRulesByCluster: Record<string, string | null>;
	metadata: {
		nSamples: number;
		nFeatures: number;
		fitSamples?: number;
		clustersExplained: number[];
		ignoredNoise: number;
		sourceSpace: string;
		clusterSource: string;
		explainerType: string;
		boundingBoxSelection: string;
		targetClusterId?: number | null;
		filteredRules: number;
		totalRules: number;
	};
};

export type AnalysisStageMetadata = Record<string, unknown>;

export type AnalysisResponse = {
	points?: ClusteredPoint[];
	assignments?: ClusterAssignments;
	summary: AnalysisSummary;
	clusterSummaries: ClusterSummary[];
	condensedBubbles?: CondensedBubble[];
	globalMetrics?: GlobalMetrics;
	metricsSummary?: Record<string, unknown> | null;
	autoParams?: Record<string, unknown> | null;
	pointAnnotations?: Record<
		string,
		{
			membershipProbability?: number | null;
			outlierScore?: number | null;
		}
	> | null;
	effectiveParams?: {
		reduction?: ReductionMethod;
		k?: number;
		maxIterations?: number;
		eps?: number;
		minPts?: number;
		minClusterSize?: number;
		minSamples?: number;
		clusterSelectionMethod?: "eom" | "leaf";
		preprocessing?: PreprocessingMethod;
		birchThreshold?: number;
		birchBranchingFactor?: number;
	};
	requestSnapshot?: Record<string, unknown> | null;
	runMetadata?: Record<string, unknown> | null;
	reductionMeta?: AnalysisStageMetadata | null;
	clusteringMeta?: AnalysisStageMetadata | null;
	condensationMeta?: AnalysisStageMetadata | null;
	birchMeta?: {
		preprocessing?: PreprocessingMethod | string;
		threshold?: number;
		branchingFactor?: number;
	} | null;
	displayMode?: DisplayMode;
	analysisId?: string | null;
	cacheKey?: string | null;
	paramsHash?: string | null;
	status?: string | null;
	version?: string | null;
	hitCount?: number;
	historyEntry?: Record<string, unknown> | null;
	mapState?: Record<string, unknown> | null;
	panelState?: Record<string, unknown> | null;
	cached: boolean;
	error?: string;
};

export type AnalysisState = {
	analyzedPoints: number;
	clusterCount: number;
	noiseCount: number;
	durationMs: number;
	tooMany: boolean;
	message: string;
	cached: boolean;
};

export const DEFAULT_ANALYSIS_PARAMS: AnalysisParams = {
	k: 5,
	maxIterations: 100,
	eps: 0.008,
	minPts: 10,
	minClusterSize: 30,
	minSamples: 10,
	clusterSelectionMethod: "eom",
	preprocessing: "none",
	reduction: "saint",
	birchThreshold: 12.0,
	birchBranchingFactor: 50,
};

export const DEFAULT_ANALYSIS_PARAMS_BY_ALGORITHM: Record<
	ClusteringAlgorithm,
	AnalysisParams
> = {
	kmeans: {
		...DEFAULT_ANALYSIS_PARAMS,
		k: 5,
		maxIterations: 100,
		reduction: "saint",
	},
	dbscan: {
		...DEFAULT_ANALYSIS_PARAMS,
		eps: 0.008,
		minPts: 10,
		reduction: "saint",
	},
	hdbscan: {
		...DEFAULT_ANALYSIS_PARAMS,
		minClusterSize: 30,
		minSamples: 10,
		clusterSelectionMethod: "eom",
		reduction: "saint",
	},
	propos: {
		...DEFAULT_ANALYSIS_PARAMS,
		k: 5,
		maxIterations: 100,
		reduction: "saint",
	},
};

export const DEFAULT_ANALYSIS_FILTERS: AnalysisFilters = {
	category: "Measurement",
	datasetId: [],
	matrix: [],
	yearRange: [2003, 2025],
	lassoRegion: [],
	substances: [],
};

export const ANALYSIS_LIMITS = {
	maxPointDetails: 500,
	temporalTopN: 5,
	radarTopN: 10,
} as const;

export const DEFAULT_ANALYSIS_STATE: AnalysisState = {
	analyzedPoints: 0,
	clusterCount: 0,
	noiseCount: 0,
	durationMs: 0,
	tooMany: false,
	message: "Clique sur Run analysis.",
	cached: false,
};

export function isClusterNoise(clusterId: number): boolean {
	return clusterId === -1;
}

export function isKMeansAlgorithm(
	algorithm: ClusteringAlgorithm,
): algorithm is "kmeans" {
	return algorithm === "kmeans";
}

export function isDbscanAlgorithm(
	algorithm: ClusteringAlgorithm,
): algorithm is "dbscan" {
	return algorithm === "dbscan";
}

export function isHdbscanAlgorithm(
	algorithm: ClusteringAlgorithm,
): algorithm is "hdbscan" {
	return algorithm === "hdbscan";
}

export function isProposAlgorithm(
	algorithm: ClusteringAlgorithm,
): algorithm is "propos" {
	return algorithm === "propos";
}

export type DisplayMode = "points" | "condensed";

export type GenericGroupId = number | string;

export type CondensedBubble = {
	groupId: string | number;
	parentClusterId: number;
	subgroupId?: number;
	lat: number;
	lon: number;
	count: number;
	pointIds: Array<string | number>;
	groupType?: "cluster" | "noise" | "outlier" | "unknown";

	producerCount?: number;
	userCount?: number;
	presumedCount?: number;

	avgPfasSum?: number;
	avgDisplayPfasValue?: number;
	displayPfasName?: string | null;

	dominantPfas?: string | null;
	spatialDispersion?: number;
};

export type BubbleContextItem = {
	pointId: number | string | null;
	name: string;
	datasetName: string;
	category: string;
	lat: number | null;
	lon: number | null;
	distanceKm: number | null;
};

export type BubbleContextResponse = {
	summary: {
		measurementCount: number;
		producerCount: number;
		userCount: number;
		presumedCount: number;
		maxDistanceKm: number;
	};
	producers: BubbleContextItem[];
	users: BubbleContextItem[];
	presumptives: BubbleContextItem[];
};

export type LocalPopulationSnapshot = {
	population1km?: number | null;
	population5km?: number | null;
	annualSeries?: Array<{ year: number; value: number }>;
};

export type LocalTerritorialContext = {
	riverNearby?: boolean | null;
	lakeNearby?: boolean | null;
	forestNearby?: boolean | null;
	distanceToNearestRiverKm?: number | null;
	distanceToNearestLakeKm?: number | null;
	forestCoverage1kmPct?: number | null;
};

export type LocalSensitivitySnapshot = {
	level?: "low" | "moderate" | "high" | null;
	reasons?: string[];
};

export type CondensedGroupInfo = {
	groupId: number | string;
	lat: number;
	lon: number;
	count: number;
	producerCount: number;
	userCount: number;
	presumedCount: number;
	groupType?: "cluster" | "noise" | "outlier" | "unknown";
};

export type SavedAnalysisSnapshot = {
	filters: AnalysisFilters;
	viewport: ViewportBounds | null;
	params: {
		k?: number;
		maxIterations?: number;
		eps?: number;
		minPts?: number;
		minClusterSize?: number;
		minSamples?: number;
		clusterSelectionMethod?: "eom" | "leaf" | string;
		preprocessing: PreprocessingMethod | string;
		reduction: ReductionMethod | string;
		birchThreshold?: number;
		birchBranchingFactor?: number;
	};
	selectedModelPfas: string[];
	mode: "simple" | "expert";
	algorithm: ClusteringAlgorithm;
	displayMode?: DisplayMode;
	result: AnalysisResponse | null;
};

export type BirchCondensationResponse = {
	condensedBubbles: CondensedBubble[];
	condensationMeta?: AnalysisStageMetadata | null;
	summary: {
		groupCount: number;
		message: string;
	};
};
