import type { PfasPoint } from "$lib/shared/types/pfas";
import { dataRune, AreaSelectorMode } from "$lib/features/exploration/exploration.state.svelte";

type ErrorMessage = string | null;

type FilterPointsApiResponse =
	| PfasPoint[]
	| {
			points?: PfasPoint[];
			data?: PfasPoint[];
			total?: number;
			error?: string;
	  };

const resolvedCache = new Map<string, { points: PfasPoint[]; total: number }>();
const inflightCache = new Map<string, Promise<{ points: PfasPoint[]; total: number }>>();

export class FetchResponse {
	data = $state<PfasPoint[]>([]);
	loading = $state<boolean>(true);
	error = $state<ErrorMessage>(null);
	total = $state<number>(0);
	reload = async () => {
		await Promise.resolve();
	};
}

function buildPayload() {
	const filtersSnapshot = $state.snapshot(dataRune.filters);
	const areaMode = dataRune.areaSelectorMode;

	const filters = {
		...filtersSnapshot,
		nutsRegions:
			areaMode === AreaSelectorMode.nuts
				? (filtersSnapshot.nutsRegions ?? [])
				: [],
	};

	return {
		filters,
		areaMode,
	};
}

function normalizeResponse(result: FilterPointsApiResponse): {
	points: PfasPoint[];
	total: number;
} {
	if (Array.isArray(result)) {
		return {
			points: result,
			total: result.length,
		};
	}

	const points = result.points ?? result.data ?? [];
	const total = result.total ?? points.length;

	return { points, total };
}

async function requestFilteredPoints(
	key: string,
	payload: unknown,
	signal: AbortSignal,
): Promise<{ points: PfasPoint[]; total: number }> {
	if (resolvedCache.has(key)) {
		return resolvedCache.get(key)!;
	}

	if (inflightCache.has(key)) {
		return inflightCache.get(key)!;
	}

	const promise = fetch("/api/filter-points", {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Accept: "application/json",
		},
		body: JSON.stringify(payload),
		signal,
	})
		.then(async (response) => {
			const result = (await response.json().catch(() => null)) as FilterPointsApiResponse | null;

			if (!response.ok) {
				throw new Error(result && !Array.isArray(result) && result.error
					? result.error
					: `Unexpected error occurred (status ${response.status})`);
			}

			const normalized = normalizeResponse(result ?? []);
			resolvedCache.set(key, normalized);
			return normalized;
		})
		.finally(() => {
			inflightCache.delete(key);
		});

	inflightCache.set(key, promise);
	return promise;
}

export function fetchFilteredPoints() {
	const resp = new FetchResponse();

	let abortController: AbortController | null = null;
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let lastAppliedKey = "";
	let requestSeq = 0;

	async function fetchData(force = false) {
		const payload = buildPayload();
		const requestKey = JSON.stringify(payload);

		if (!force && requestKey === lastAppliedKey) {
			return;
		}

		requestSeq += 1;
		const currentRequestSeq = requestSeq;

		abortController?.abort();
		abortController = new AbortController();

		resp.loading = true;

		try {
			const result = await requestFilteredPoints(
				requestKey,
				payload,
				abortController.signal,
			);

			if (currentRequestSeq !== requestSeq) {
				return;
			}

			lastAppliedKey = requestKey;
			resp.data = result.points;
			resp.total = result.total;
			dataRune.nbFilteredPoints = result.total;
			resp.error = null;
		} catch (err: any) {
			if (err?.name === "AbortError") {
				return;
			}

			if (currentRequestSeq !== requestSeq) {
				return;
			}

			console.error("[fetchFilteredPoints] Fetch error:", err);
			resp.error = err?.message ?? "Unexpected error";
			resp.data = [];
			resp.total = 0;
			dataRune.nbFilteredPoints = 0;
		} finally {
			if (currentRequestSeq === requestSeq) {
				resp.loading = false;
			}
		}
	}

	resp.reload = async () => {
		await fetchData(true);
	};

	$effect(() => {
		const payload = buildPayload();
		const requestKey = JSON.stringify(payload);

		requestKey;

		if (debounceTimer) {
			clearTimeout(debounceTimer);
		}

		debounceTimer = setTimeout(() => {
			void fetchData();
		}, 120);

		return () => {
			if (debounceTimer) {
				clearTimeout(debounceTimer);
			}
		};
	});

	return resp;
}