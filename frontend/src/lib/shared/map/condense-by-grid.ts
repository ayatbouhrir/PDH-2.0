/*import type { ClusteredPoint, CondensedBubble, GenericGroupId } from "$lib/shared/types/analysis-contract";
import { getBusinessFlags } from "$lib/shared/pfas/pfas-site-classification";

type GroupType = "cluster" | "noise" | "outlier" | "unknown";

function normalizeGroupId(value: unknown): GenericGroupId | null {
	if (value === null || value === undefined) return null;
	if (typeof value === "number" || typeof value === "string") return value;
	return null;
}

function inferGroupType(groupId: GenericGroupId): GroupType {
	if (groupId === -1 || groupId === "noise" || groupId === "outlier") {
		return "noise";
	}
	return "cluster";
}

function getCellSizeDegrees(zoom: number): number {
	if (zoom >= 13) return 0.05;
	if (zoom >= 11) return 0.08;
	if (zoom >= 9) return 0.15;
	if (zoom >= 7) return 0.25;
	if (zoom >= 5) return 0.4;
	return 0.6;
}

export function condenseByGrid(
	points: ClusteredPoint[],
	zoom: number,
	options?: {
		excludeNoise?: boolean;
	},
): CondensedBubble[] {
	const excludeNoise = options?.excludeNoise ?? true;
	const cellSize = getCellSizeDegrees(zoom);

	const buckets = new Map<string, CondensedBubble>();

	for (const point of points) {
		const lat = Number(point.lat);
		const lon = Number(point.lon);
		if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

		const groupId = normalizeGroupId(point.clusterId);
		if (groupId === null) continue;

		const groupType = inferGroupType(groupId);
		if (excludeNoise && groupType === "noise") continue;

		const cellX = Math.floor(lon / cellSize);
		const cellY = Math.floor(lat / cellSize);

		const key = `${String(groupId)}__${cellX}__${cellY}`;

		const flags = getBusinessFlags(point.raw);

		if (!buckets.has(key)) {
			buckets.set(key, {
				groupId,
				lat: 0,
				lon: 0,
				count: 0,
				producerCount: 0,
				userCount: 0,
				presumedCount: 0,
				pointIds: [],
				groupType,
			});
		}

		const bucket = buckets.get(key)!;
		bucket.lat += lat;
		bucket.lon += lon;
		bucket.count += 1;
		bucket.producerCount += flags.producer ? 1 : 0;
		bucket.userCount += flags.user ? 1 : 0;
		bucket.presumedCount += flags.presumed ? 1 : 0;
		bucket.pointIds.push(point.pointId ?? `${lat},${lon}`);
	}

	const bubbles = Array.from(buckets.values()).map((bubble) => ({
		...bubble,
		lat: bubble.count > 0 ? bubble.lat / bubble.count : bubble.lat,
		lon: bubble.count > 0 ? bubble.lon / bubble.count : bubble.lon,
	}));

	return bubbles;
}


*/

import type { AnalysisResponse, CondensedBubble } from "$lib/shared/types/analysis-contract";

export function getCondensedBubblesFromAnalysis(
	result: AnalysisResponse | null | undefined,
): CondensedBubble[] {
	return result?.condensedBubbles ?? [];
}