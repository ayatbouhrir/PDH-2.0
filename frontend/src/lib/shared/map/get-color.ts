import { interpolateRgb } from "d3";
import { colors, thresholds } from "$lib/shared/map/fsac-palette";
import { Category } from "$lib/features/exploration/exploration.state.svelte";

export function getColor(
	category: string,
	pfas_sum: number | string | null | undefined
): string {
	if (category === Category.Sampling) {
		let value: number | null = null;
		if (typeof pfas_sum === "number" && !isNaN(pfas_sum)) {
			value = pfas_sum;
		} else if (
			typeof pfas_sum === "string" &&
			!isNaN(parseFloat(pfas_sum))
		) {
			value = parseFloat(pfas_sum);
		}
		if (value === null) return "#888888";

		for (let i = 0; i < thresholds.length - 1; i++) {
			const min = thresholds[i];
			const max = thresholds[i + 1];
			if (value >= min && value < max) {
				const t = (value - min) / (max - min);
				return interpolateRgb(colors[i], colors[i + 1])(t);
			}
		}

		return colors[colors.length - 1];
	}

	// Autres catégories
	switch (category) {
		case "Presumptive":
			return "#40E0D0";
		case "Known PFAS user":
			return "#FFD700";
		case "PFAS production facility":
			return "#FF00FF";
		default:
			return "#888888";
	}
}
