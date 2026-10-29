import type { PfasPoint } from "$lib/shared/types/pfas";
import { DEFAULT_ANALYSIS_FILTERS } from "$lib/shared/types/analysis-contract";
import type { ClusterSummary, DetailsContext, CondensedGroupInfo } from '$lib/shared/types/analysis-contract';

export type SelectedClusterInfo =
	| (ClusterSummary & {
			color: string;
			algorithm: string;
	  })
	| null;

export const Category = {
	Sampling: "Measurement",
	Presumptive: "Presumptive",
	KnownUser: "Known PFAS user",
	ProductionFacility: "PFAS production facility",
};

export const AreaSelectorMode = {
	nuts: "NUTS",
	lasso: "LASSO",
};

export type NutsRegion = {
	id: string;
	year: string | number;
	level: number;
};

export type Substances = {
	name: string;
	unit: string;
	rangeMode: "raw" | "filtered";
	raw: { min: number; max: number; count: number };
	filtered: { min: number; max: number; count: number };
	filteredRange: number[];
	rawRange: number[];
};

export type FiltersType = {
	category: string;
	datasetId: string[];
	matrix: string[];
	yearRange: number[];
	nutsRegions: NutsRegion[];
	lassoRegion: { lat: number; lon: number }[];
	substances: Substances[];
};

class DataRune {
	allMatrixes = $state<Record<string, number>>({});
	allDatasets = $state<Record<string, { id: number; count: number }>>({});
	allSubstances = $state<Record<string, { count: number; units: string[] }>>({});

	nbFilteredPoints = $state<number>(0);

	selectedPoints = $state<PfasPoint[]>([]);
	selectedBubblePointIds = $state<Array<string | number>>([]);
	selectedClusterInfo = $state<SelectedClusterInfo>(null);
	selectedCondensedGroup = $state<CondensedGroupInfo | null>(null);

	detailsContext = $state<DetailsContext>("none");

	clusterGeometryRequest = $state<{
		clusterId: number;
		showCentroid: boolean;
		showMin: boolean;
		showMax: boolean;
	} | null>(null);

	filters = $state<FiltersType>({
		category: DEFAULT_ANALYSIS_FILTERS.category ?? Category.Sampling,
		datasetId: [...DEFAULT_ANALYSIS_FILTERS.datasetId],
		matrix: [...DEFAULT_ANALYSIS_FILTERS.matrix],
		yearRange: Array.isArray(DEFAULT_ANALYSIS_FILTERS.yearRange)
			? [...DEFAULT_ANALYSIS_FILTERS.yearRange]
			: [2003, 2025],
		nutsRegions: [],
		lassoRegion: [...DEFAULT_ANALYSIS_FILTERS.lassoRegion],
		substances: [],
	});

	areaSelectorMode = $state<string>(AreaSelectorMode.nuts);
	lassoEnabled = $state(false);

	initialize(data: {
		allMatrixes: Record<string, number>;
		allDatasets: Record<string, { id: number; count: number }>;
		allSubstances: Record<string, { count: number; units: string[] }>;
	}) {
		this.allMatrixes = data.allMatrixes;
		this.allDatasets = data.allDatasets;
		this.allSubstances = data.allSubstances;
	}
}

export let dataRune = new DataRune();