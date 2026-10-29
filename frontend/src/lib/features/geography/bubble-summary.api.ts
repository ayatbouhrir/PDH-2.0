export type BubbleSummaryResponse = {
	summary: {
		measurementCount: number;
		producerCount: number;
		userCount: number;
		presumedCount: number;
		maxDistanceKm: number;
	};
};

const cache = new Map<string, BubbleSummaryResponse>();

function makeKey(pointIds: Array<string | number>, maxDistanceKm: number) {
	return JSON.stringify({
		pointIds: [...pointIds].map(String).sort(),
		maxDistanceKm,
	});
}

export async function fetchBubbleSummary(
	pointIds: Array<string | number>,
	maxDistanceKm = 50,
): Promise<BubbleSummaryResponse> {
	const key = makeKey(pointIds, maxDistanceKm);

	if (cache.has(key)) {
		return cache.get(key)!;
	}

	const res = await fetch("/api/bubble-context", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			pointIds,
			maxDistanceKm,
			limitPerCategory: 1,
		}),
	});

	if (!res.ok) {
		const text = await res.text();
		throw new Error(text || `Erreur bubble-context: ${res.status}`);
	}

	const json = (await res.json()) as BubbleSummaryResponse;
	cache.set(key, json);
	return json;
}