import type { CondensedBubble } from "$lib/shared/types/analysis-contract";

type Condensation3DItem = {
	position: [number, number];
	elevation: number;
	radius: number;
	fillColor: [number, number, number, number];
	lineColor: [number, number, number, number];
	isActive: boolean;
	raw: CondensedBubble;
};

function hexToRgba(
	hex: string,
	alpha = 220,
): [number, number, number, number] {
	const clean = hex.replace("#", "");
	const normalized =
		clean.length === 3
			? clean
					.split("")
					.map((c) => c + c)
					.join("")
			: clean;

	const num = Number.parseInt(normalized, 16);

	return [
		(num >> 16) & 255,
		(num >> 8) & 255,
		num & 255,
		alpha,
	];
}

export function build3DCondensationData(
	bubbles: CondensedBubble[],
	getClusterColor: (clusterId: number) => string,
	selectedClusterId: number | null,
): Condensation3DItem[] {
	return bubbles
		.filter(
			(b) =>
				Number.isFinite(Number(b.lat)) &&
				Number.isFinite(Number(b.lon)),
		)
		.map((b) => {
			const clusterId = Number(b.parentClusterId);
			const isActive =
				selectedClusterId === null ||
				clusterId === Number(selectedClusterId);

			const baseColor = getClusterColor(clusterId);

			const fillColor = isActive
				? hexToRgba(baseColor, 210)
				: hexToRgba(baseColor, 55);

			const lineColor: [number, number, number, number] = isActive
				? [17, 24, 39, 255]
				: [148, 163, 184, 120];

			const zValue = Number(b.avgDisplayPfasValue ?? b.avgPfasSum ?? 0);

			return {
				position: [Number(b.lon), Number(b.lat)],
				elevation: isActive
					? Math.max(30, Math.log1p(Math.max(0, zValue)) * 250)
					: Math.max(15, Math.log1p(Math.max(0, zValue)) * 140),
				radius: isActive
					? Math.max(1500, Math.sqrt(Math.max(1, Number(b.count))) * 900)
					: Math.max(1200, Math.sqrt(Math.max(1, Number(b.count))) * 700),
				fillColor,
				lineColor,
				isActive,
				raw: b,
			};
		});
}