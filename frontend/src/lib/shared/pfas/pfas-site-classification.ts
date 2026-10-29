

export type BusinessClass = "producer" | "user" | "presumptive" | "other";

export function getBusinessClass(raw: Record<string, unknown> | undefined): BusinessClass {
	if (!raw) return "other";

	const type = String(raw.type ?? "").toLowerCase();
	const sector = String(raw.sector ?? "").toLowerCase();
	const sourceType = String(raw.source_type ?? "").toLowerCase();
	const name = String(raw.name ?? "").toLowerCase();
	const datasetName = String(raw.dataset_name ?? raw.datasetName ?? "").toLowerCase();
	const category = String(raw.category ?? "").toLowerCase();

	const details =
		raw.details_json && typeof raw.details_json === "object"
			? JSON.stringify(raw.details_json).toLowerCase()
			: String(raw.details_json ?? "").toLowerCase();

	const text = [type, sector, sourceType, name, datasetName, category, details].join(" ");

	if (
		text.includes("producer") ||
		text.includes("producteur") ||
		text.includes("manufactur") ||
		text.includes("fabricant") ||
		text.includes("industrial producer") ||
		text.includes("pfas production")
	) {
		return "producer";
	}

	if (
		text.includes("known pfas user") ||
		text.includes("user") ||
		text.includes("utilisateur") ||
		text.includes("usage site") ||
		text.includes("industrial user") ||
		text.includes("consumer use")
	) {
		return "user";
	}

	if (
		text.includes("presumed") ||
		text.includes("presumptive") ||
		text.includes("présumé") ||
		text.includes("presume") ||
		text.includes("suspected") ||
		text.includes("supposed") ||
		text.includes("potentiel") ||
		text.includes("eprtr")
	) {
		return "presumptive";
	}

	return "other";
}

export function getBusinessFlags(raw: Record<string, unknown> | undefined): {
	producer: boolean;
	user: boolean;
	presumed: boolean;
} {
	const cls = getBusinessClass(raw);
	return {
		producer: cls === "producer",
		user: cls === "user",
		presumed: cls === "presumptive",
	};
}
