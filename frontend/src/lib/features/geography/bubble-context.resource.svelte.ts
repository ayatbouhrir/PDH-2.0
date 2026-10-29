import type { BubbleContextResponse } from "$lib/shared/types/analysis-contract";
import { dataRune } from "$lib/features/exploration/exploration.state.svelte";

type ErrorMessage = string | null;

const DEBOUNCE_MS = 250;
const DEFAULT_MAX_DISTANCE_KM = 50;
const DEFAULT_LIMIT_PER_CATEGORY = 10;

class FetchBubbleContextState {
	data = $state<BubbleContextResponse | null>(null);
	loading = $state<boolean>(false);
	error = $state<ErrorMessage>(null);
}

function shouldFetchBubbleContext(
	context: string,
	pointIds: Array<string | number>,
): boolean {
	return ["cluster", "condensed_group"].includes(context) && pointIds.length > 0;
}

export function fetchBubbleContext() {
	const resp = new FetchBubbleContextState();

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;
	let requestId = 0;

	async function fetchData() {
		const pointIds = (dataRune.selectedBubblePointIds ?? []).filter(Boolean);

		if (!shouldFetchBubbleContext(dataRune.detailsContext, pointIds)) {
			resp.data = null;
			resp.error = null;
			resp.loading = false;
			return;
		}

		abortController?.abort();
		abortController = new AbortController();
		const currentRequestId = ++requestId;

		resp.loading = true;
		resp.error = null;

		try {
			const res = await fetch("/api/bubble-context", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
				},
				body: JSON.stringify({
					pointIds,
					maxDistanceKm: DEFAULT_MAX_DISTANCE_KM,
					limitPerCategory: DEFAULT_LIMIT_PER_CATEGORY,
				}),
				signal: abortController.signal,
			});

			if (currentRequestId !== requestId) return;

			if (!res.ok) {
				const text = await res.text();
				throw new Error(text || `Erreur serveur : ${res.status}`);
			}

			resp.data = (await res.json()) as BubbleContextResponse;
			resp.error = null;
		} catch (err: unknown) {
			if (err instanceof DOMException && err.name === "AbortError") return;
			if (currentRequestId !== requestId) return;

			console.error("[fetchBubbleContext] error:", err);

			resp.data = null;
			resp.error =
				err instanceof Error ? err.message : "Erreur inconnue";
		} finally {
			if (currentRequestId === requestId) {
				resp.loading = false;
			}
		}
	}


	$effect(() => {
		const context = dataRune.detailsContext;
		const pointIds = dataRune.selectedBubblePointIds ?? [];

		context;
		pointIds.length;
		

		if (!shouldFetchBubbleContext(context, pointIds)) {
			if (debounceTimer) {
				clearTimeout(debounceTimer);
				debounceTimer = null;
			}

			abortController?.abort();
			resp.data = null;
			resp.error = null;
			resp.loading = false;
			return;
		}

		if (debounceTimer) {
			clearTimeout(debounceTimer);
		}

		debounceTimer = setTimeout(() => {
			void fetchData();
		}, DEBOUNCE_MS);

		return () => {
			if (debounceTimer) {
				clearTimeout(debounceTimer);
				debounceTimer = null;
			}
		};
	});

	return resp;
}


