import { ANALYSIS_LIMITS } from "$lib/shared/types/analysis-contract";
import { dataRune } from "$lib/features/exploration/exploration.state.svelte";

type ErrorMessage = string | null;

const DEBOUNCE_MS = 300;

export type PointDetail = {
	id?: string | number;
	point_id?: string | number;
	pointId?: string | number;
	lat?: number;
	lon?: number;
	year?: number | string;
	category?: string;
	matrix?: string;
	dataset_id?: string | number;
	dataset_name?: string;
	pfas_sum?: number;
	pfas_values?: unknown[] | string;
	[key: string]: unknown;
};

class FetchPointDetailsResponse {
	details = $state<PointDetail[]>([]);
	loading = $state<boolean>(false);
	error = $state<ErrorMessage>(null);
}

export function fetchPointDetails() {
	const resp = new FetchPointDetailsResponse();
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;
	let requestId = 0;

	async function fetchData() {
		const ids = (dataRune.selectedPoints ?? [])
			.map((p: any) => p.id ?? p.point_id ?? p.pointId)
			.filter((v) => v !== null && v !== undefined && v !== "");

		if (!ids || ids.length === 0) {
			resp.details = [];
			resp.error = null;
			resp.loading = false;
			return;
		}

		if (ids.length > ANALYSIS_LIMITS.maxPointDetails) {
			resp.details = [];
			resp.error = `Trop de points sélectionnés (${ids.length}). Réduis la sélection pour afficher les détails PFAS.`;
			resp.loading = false;
			return;
		}

		abortController?.abort();
		abortController = new AbortController();
		const currentRequestId = ++requestId;

		resp.loading = true;
		resp.error = null;

		try {
			const res = await fetch("/api/fetch-point-details", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ pointIds: ids }),
				signal: abortController.signal,
			});

			if (currentRequestId !== requestId) return;

			if (!res.ok) {
				throw new Error(`Erreur serveur : ${res.status}`);
			}

			resp.details = (await res.json()) as PointDetail[];
			resp.error = null;
		} catch (err: unknown) {
			if (err instanceof DOMException && err.name === "AbortError") return;
			if (currentRequestId !== requestId) return;

			console.error("[fetchPointDetails] error:", err);

			if (err instanceof Error) {
				resp.error = err.message;
			} else {
				resp.error = "Erreur inconnue";
			}

			resp.details = [];
		} finally {
			if (currentRequestId === requestId) {
				resp.loading = false;
			}
		}
	}

	$effect(() => {
		const points = dataRune.selectedPoints;

		if (!points || points.length === 0) {
			resp.details = [];
			resp.error = null;
			resp.loading = false;
			return;
		}

		if (debounceTimer) clearTimeout(debounceTimer);

		debounceTimer = setTimeout(() => {
			void fetchData();
		}, DEBOUNCE_MS);
	});

	return resp;
}
/*
import { dataRune } from "$lib/features/exploration/exploration.state.svelte";

type ErrorMessage = string | null;

const DEBOUNCE_MS = 300;
const MAX_POINTS_FOR_DETAILS = 500;



class FetchPointDetailsResponse {
	details = $state<any[]>([]);
	loading = $state<boolean>(false);
	error = $state<ErrorMessage>(null);
}

export function fetchPointDetails() {
	const resp = new FetchPointDetailsResponse();
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;
	let requestId = 0;

	const MAX_POINTS_FOR_DETAILS = 500;

	async function fetchData() {
		const ids = dataRune.selectedPoints?.map((p) => p.id).filter(Boolean);

		if (!ids || ids.length === 0) {
			resp.details = [];
			resp.error = null;
			resp.loading = false;
			return;
		}

		if (ids.length > MAX_POINTS_FOR_DETAILS) {
			resp.details = [];
			resp.error = `Trop de points sélectionnés (${ids.length}). Réduis la sélection pour afficher les détails PFAS.`;
			resp.loading = false;
			return;
		}

		abortController?.abort();
		abortController = new AbortController();
		const currentRequestId = ++requestId;

		resp.loading = true;
		resp.error = null;

		try {
			const res = await fetch("/api/fetch-point-details", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ pointIds: ids }),
				signal: abortController.signal,
			});

			if (currentRequestId !== requestId) return;

			if (!res.ok) {
				throw new Error(`Erreur serveur : ${res.status}`);
			}

			resp.details = await res.json();
			resp.error = null;
		} catch (err: any) {
			if (err?.name === "AbortError") return;
			if (currentRequestId !== requestId) return;

			console.error("[fetchPointDetails] error:", err);
			resp.error = err?.message ?? "Erreur inconnue";
			resp.details = [];
		} finally {
			if (currentRequestId === requestId) {
				resp.loading = false;
			}
		}
	}

	$effect(() => {
		const points = dataRune.selectedPoints;

		if (!points || points.length === 0) {
			resp.details = [];
			resp.error = null;
			resp.loading = false;
			return;
		}

		if (debounceTimer) clearTimeout(debounceTimer);

		debounceTimer = setTimeout(() => {
			void fetchData();
		}, DEBOUNCE_MS);
	});

	return resp;
}
*/