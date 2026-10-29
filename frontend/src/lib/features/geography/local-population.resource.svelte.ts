import { dataRune } from "$lib/features/exploration/exploration.state.svelte";

type ErrorMessage = string | null;

export type LocalPopulationResponse = {
	population1km: number;
	population5km: number;
	year: number;
	source: string;
	cachedAt: number;
};

class FetchLocalPopulationState {
	data = $state<LocalPopulationResponse | null>(null);
	loading = $state<boolean>(false);
	error = $state<ErrorMessage>(null);
}

export function fetchLocalPopulation() {
	const resp = new FetchLocalPopulationState();

	let abortController: AbortController | null = null;
	let requestId = 0;
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	async function fetchData() {
		const group = dataRune.selectedCondensedGroup;
		const context = dataRune.detailsContext;

		if (
			context !== "condensed_group" ||
			!group ||
			!Number.isFinite(group.lat) ||
			!Number.isFinite(group.lon)
		) {
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
			const res = await fetch("/api/local-population", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					lat: group.lat,
					lon: group.lon,
					year: 2020,
				}),
				signal: abortController.signal,
			});

			if (currentRequestId !== requestId) return;

			if (!res.ok) {
				const text = await res.text();
				throw new Error(text || `Erreur serveur : ${res.status}`);
			}

			resp.data = (await res.json()) as LocalPopulationResponse;
			resp.error = null;
		} catch (err: unknown) {
			if (err instanceof DOMException && err.name === "AbortError") return;
			if (currentRequestId !== requestId) return;

			resp.data = null;
			resp.error = err instanceof Error ? err.message : "Erreur inconnue";
		} finally {
			if (currentRequestId === requestId) {
				resp.loading = false;
			}
		}
	}

	$effect(() => {
		const context = dataRune.detailsContext;
		const lat = dataRune.selectedCondensedGroup?.lat;
		const lon = dataRune.selectedCondensedGroup?.lon;
		const groupId = dataRune.selectedCondensedGroup?.groupId;

		context;
		lat;
		lon;
		groupId;

		if (debounceTimer) clearTimeout(debounceTimer);

		debounceTimer = setTimeout(() => {
			void fetchData();
		}, 200);

		return () => {
			if (debounceTimer) clearTimeout(debounceTimer);
		};
	});

	return resp;
}