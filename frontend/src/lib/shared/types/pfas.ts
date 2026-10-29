export interface PfasPoint {
	id: number;
	category: string;
	lat: string;
	lon: string;
	name?: string;
	city?: string;
	country?: string;
	type?: string;
	sector?: string;
	status?: string;
	source_type?: string;
	data_collection_method?: string;
	source_text?: string;
	source_url?: string;
	dataset_id?: string;
	dataset_name?: string;
	pfas_values?: string;
	unit?: string;
	pfas_sum?: number;
	details?: string;
	matrix?: string;
	date?: string;
	year?: string;

	nuts?: {
		nuts2016?: NutsLevels;
		nuts2021?: NutsLevels;
		nuts2024?: NutsLevels;
	};
}

export interface PfasSitePoint extends PfasPoint {
	category: PfasSiteCategory | string;
	status?: string;
}

export const PFAS_SITE_CATEGORY_VALUES = [
	"PFAS production facility",
	"Known PFAS user",
	"Presumptive",
] as const;

export type PfasSiteCategory = (typeof PFAS_SITE_CATEGORY_VALUES)[number];

export const PFAS_SITE_CATEGORY_META: Record<
	PfasSiteCategory,
	{
		label: string;
		symbol: "■" | "◆" | "▲";
		color: string;
		borderColor: string;
	}
> = {
	"PFAS production facility": {
		label: "Producteurs PFAS",
		symbol: "■",
		color: "#FFD700",
		borderColor: "#000000",
	},
	"Known PFAS user": {
		label: "Utilisateurs PFAS",
		symbol: "◆",
		color: "#00E5FF",
		borderColor: "#000000",
	},
	Presumptive: {
		label: "Sites présumés",
		symbol: "▲",
		color: "#000000",
		borderColor: "#FFFFFF",
	},
};

const PFAS_SITE_CATEGORY_LOOKUP = Object.fromEntries(
	PFAS_SITE_CATEGORY_VALUES.map((category) => [
		category.trim().toLowerCase(),
		category,
	]),
) as Record<string, PfasSiteCategory>;

export function normalizePfasSiteCategory(
	value: unknown,
): PfasSiteCategory | null {
	if (typeof value !== "string") return null;
	return PFAS_SITE_CATEGORY_LOOKUP[value.trim().toLowerCase()] ?? null;
}

export function isPfasSiteCategory(value: unknown): value is PfasSiteCategory {
	return normalizePfasSiteCategory(value) !== null;
}

export interface NutsLevel {
	NUTS_ID: string;
	NUTS_NAME: string;
}

export interface NutsLevels {
	level0?: NutsLevel | null;
	level1?: NutsLevel | null;
	level2?: NutsLevel | null;
	level3?: NutsLevel | null;
}
