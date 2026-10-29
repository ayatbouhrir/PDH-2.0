<script lang="ts">
	import { page } from "$app/state";
	import { onMount, untrack } from "svelte";
	import Header from "$lib/components/layout/Header.svelte";
	import RunComparisonMap from "$lib/features/comparison/components/RunComparisonMap.svelte";
	import RunComparisonMetrics from "$lib/features/comparison/components/RunComparisonMetrics.svelte";
	import {
		isComparableHistoryEntry,
		runHistoryRune,
		type RunHistoryEntry,
	} from "$lib/features/history/run-history.state.svelte";
	import type { ComparisonRunData } from "$lib/features/comparison/run-comparison.types";
	import type { ViewportBounds } from "$lib/shared/types/analysis-contract";
	import {
		buildClusteredPointsFromAssignments,
		loadHistoryFilteredPoints,
		loadHistoryResult,
	} from "$lib/features/history/history.api";

	type ComparisonFailure = {
		id: string;
		entry: RunHistoryEntry;
		error: string;
	};

	type ComparisonLoadTrace = {
		id: string;
		entry: RunHistoryEntry;
		status: "pending" | "loading" | "done" | "error";
		step: string;
		details: string;
	};

	const MAX_COMPARE_RUNS = 4;

	let runs = $state<ComparisonRunData[]>([]);
	let failures = $state<ComparisonFailure[]>([]);
	let loadTraces = $state<ComparisonLoadTrace[]>([]);
	let loading = $state(false);
	let loadError = $state<string | null>(null);
	let hasLoadedOnce = $state(false);
	let syncViewport = $state(true);
	let sharedViewport = $state<ViewportBounds | null>(null);
	let activeViewportSourceId = $state<string | null>(null);
	let currentLoadVersion = 0;
	let lastRequestedLoadSignature = $state<string | null>(null);

	const requestedIds = $derived.by(() => {
		const raw = page.url.searchParams.get("runs") ?? "";
		return Array.from(
			new Set(
				raw
					.split(",")
					.map((value) => value.trim())
					.filter(Boolean),
			),
		).slice(0, MAX_COMPARE_RUNS);
	});

	const selectedEntries = $derived.by(() =>
		requestedIds
			.map((id) => runHistoryRune.entries.find((entry) => entry.id === id) ?? null)
			.filter((entry): entry is RunHistoryEntry => Boolean(entry)),
	);

	const selectedLoadSignature = $derived.by(() =>
		selectedEntries
			.map(
				(entry) =>
					[
						entry.id,
						entry.cacheKey ?? entry.analysisId ?? "local",
						entry.params.reduction ?? "none",
						entry.algorithm,
						entry.pfasSelected.join("|"),
					].join(":"),
			)
			.join("||"),
	);

	function getRunLabel(entry: RunHistoryEntry) {
		return (
			entry.name ??
			`${entry.algorithm.toUpperCase()} · ${entry.clusterCount} clusters`
		);
	}

	function getComparisonRunOrdinal(index: number) {
		return ["Premier run", "Deuxième run", "Troisième run", "Quatrième run"][index] ?? `Run ${index + 1}`;
	}

	function getComparisonRunIdentity(entry: RunHistoryEntry, index: number) {
		return `${getComparisonRunOrdinal(index)} (${entry.id.slice(0, 8)})`;
	}

	function getComparisonRunHeading(entry: RunHistoryEntry, index: number) {
		return `${getRunLabel(entry)} · ${getComparisonRunIdentity(entry, index)}`;
	}

	function getRunModelLabel(entry: RunHistoryEntry) {
		const reduction = (entry.params.reduction ?? "none").toUpperCase();
		const algorithm = entry.algorithm.toUpperCase();
		return `${reduction} + ${algorithm}`;
	}

	function getRunSelectionLabel(entry: RunHistoryEntry) {
		return entry.pfasSelected.includes("All")
			? "PFAS: All"
			: `PFAS: ${entry.pfasSelected.length} sélectionnés`;
	}

	function formatDisplayMode(run: ComparisonRunData) {
		return run.displayMode === "condensed" ? "bulles condensées" : "points";
	}

	function getDominantPfas(run: ComparisonRunData) {
		const summaries =
			(run.result.clusterSummaries as Array<{
				clusterId?: number;
				dominantPfas?: string | null;
				count?: number;
			}>) ?? [];

		return summaries
			.filter((summary) => summary.clusterId !== -1 && summary.dominantPfas)
			.sort((a, b) => Number(b.count ?? 0) - Number(a.count ?? 0))
			.slice(0, 2)
			.map((summary) => summary.dominantPfas)
			.filter((value): value is string => Boolean(value));
	}

	function replaceLoadTrace(
		id: string,
		patch: Partial<ComparisonLoadTrace>,
	) {
		loadTraces = loadTraces.map((trace) =>
			trace.id === id ? { ...trace, ...patch } : trace,
		);
	}

	async function hydrateComparisonRun(entry: RunHistoryEntry): Promise<ComparisonRunData> {
		replaceLoadTrace(entry.id, {
			status: "loading",
			step: "Préparation du run",
			details: `${getRunModelLabel(entry)} · ${getRunSelectionLabel(entry)}`,
		});

		replaceLoadTrace(entry.id, {
			status: "loading",
			step: "Restauration du résultat sauvegardé",
			details: entry.cacheKey
				? "Lecture du run depuis le cache/historique persistant"
				: "Lecture du run depuis le snapshot local",
		});

		const result = await loadHistoryResult(entry, {
			syncHistoryEntry: false,
		});

		replaceLoadTrace(entry.id, {
			status: "loading",
			step: "Chargement des points du run",
			details: `${result.summary.analyzedPoints.toLocaleString("fr-FR")} points à restaurer`,
		});

		const filteredPoints = await loadHistoryFilteredPoints(entry);

		replaceLoadTrace(entry.id, {
			status: "loading",
			step: "Reconstruction de la carte",
			details:
				result.assignments && Object.keys(result.assignments).length > 0
					? "Reconstruction des assignments et des clusters visibles"
					: "Préparation directe des points restaurés",
		});

		const assignments = result.assignments ?? {};
		const clusteredPoints =
			Object.keys(assignments).length > 0
				? buildClusteredPointsFromAssignments(
						filteredPoints,
						assignments,
						result.pointAnnotations ?? null,
					)
				: ((result.points ?? []) as ComparisonRunData["clusteredPoints"]);
		const condensedBubbles = result.condensedBubbles ?? [];
		const displayMode =
			entry.mapState?.displayMode ??
			result.mapState?.displayMode ??
			entry.snapshot?.displayMode ??
			result.displayMode ??
			(condensedBubbles.length > 0 ? "condensed" : "points");
		const initialViewport =
			entry.mapState?.viewport ?? result.mapState?.viewport ?? entry.snapshot?.viewport ?? null;

		replaceLoadTrace(entry.id, {
			status: "done",
			step: "Run prêt",
			details: `${clusteredPoints.length.toLocaleString("fr-FR")} points de carte · ${condensedBubbles.length.toLocaleString("fr-FR")} bulles condensées`,
		});

		return {
			id: entry.id,
			entry,
			result,
			filteredPoints,
			clusteredPoints,
			condensedBubbles,
			displayMode,
			initialViewport,
		};
	}

	function handleViewportChange(viewport: ViewportBounds, sourceId: string) {
		if (!syncViewport) return;
		activeViewportSourceId = sourceId;
		sharedViewport = viewport;
	}

	function navigateBackToAnalysis() {
		if (typeof window === "undefined") {
			return;
		}

		window.location.assign("/analyse");
	}

	onMount(() => {
		void runHistoryRune.refreshFromServer();
	});

	$effect(() => {
		const ids = requestedIds;
		const selectedCount = selectedEntries.length;
		const historyLoading = runHistoryRune.isLoading;
		const loadSignature = selectedLoadSignature;

		if (ids.length === 0) {
			runs = [];
			failures = [];
			loadTraces = [];
			hasLoadedOnce = false;
			lastRequestedLoadSignature = null;
			loadError = "Sélectionne au moins deux runs depuis l’historique pour lancer la comparaison.";
			loading = false;
			return;
		}

		if (ids.length < 2) {
			runs = [];
			failures = [];
			loadTraces = [];
			hasLoadedOnce = false;
			lastRequestedLoadSignature = null;
			loadError = "La comparaison nécessite au moins deux runs.";
			loading = false;
			return;
		}

		if (selectedCount !== ids.length) {
			if (historyLoading) return;
			runs = [];
			failures = [];
			loadTraces = [];
			hasLoadedOnce = false;
			lastRequestedLoadSignature = null;
			loadError = "Impossible de retrouver un ou plusieurs runs dans l’historique local.";
			loading = false;
			return;
		}

		if (
			loading &&
			lastRequestedLoadSignature != null &&
			lastRequestedLoadSignature === loadSignature
		) {
			return;
		}

		if (
			!loading &&
			hasLoadedOnce &&
			lastRequestedLoadSignature != null &&
			lastRequestedLoadSignature === loadSignature
		) {
			return;
		}

		untrack(async () => {
			const entries = selectedEntries;
			const comparableEntries = entries.filter((entry) => isComparableHistoryEntry(entry));
			if (comparableEntries.length < 2) {
				runs = [];
				failures = [];
				loadTraces = [];
				hasLoadedOnce = false;
				lastRequestedLoadSignature = null;
				loadError =
					"Au moins deux runs restaurables sont nécessaires pour la comparaison.";
				loading = false;
				return;
			}

			const version = ++currentLoadVersion;
			loading = true;
			hasLoadedOnce = false;
			lastRequestedLoadSignature = loadSignature;
			loadError = null;
			loadTraces = comparableEntries.map((entry) => ({
				id: entry.id,
				entry,
				status: "pending",
				step: "En attente",
				details: `${getRunModelLabel(entry)} · ${getRunSelectionLabel(entry)}`,
			}));

			const results = await Promise.allSettled(
				comparableEntries.map((entry) => hydrateComparisonRun(entry)),
			);

			if (version !== currentLoadVersion) {
				return;
			}

			const nextRuns: ComparisonRunData[] = [];
			const nextFailures: ComparisonFailure[] = [];

			results.forEach((result, index) => {
				const entry = comparableEntries[index];
				if (result.status === "fulfilled") {
					nextRuns.push(result.value);
					return;
				}

				nextFailures.push({
					id: entry.id,
					entry,
					error:
						result.reason instanceof Error
							? result.reason.message
							: "Erreur de chargement du run.",
				});

				replaceLoadTrace(entry.id, {
					status: "error",
					step: "Échec du chargement",
					details:
						result.reason instanceof Error
							? result.reason.message
							: "Erreur de chargement du run.",
				});
			});

			runs = nextRuns;
			failures = nextFailures;
			sharedViewport = nextRuns[0]?.initialViewport ?? null;
			activeViewportSourceId = nextRuns[0]?.id ?? null;

			if (nextRuns.length < 2) {
				loadError =
					nextFailures.length > 0
						? "Impossible de charger suffisamment de runs pour afficher une comparaison utile."
						: "La comparaison nécessite au moins deux runs.";
			} else {
				loadError = null;
			}

			hasLoadedOnce = true;
			loading = false;
		});
	});
</script>

<Header mode="on" />

<div class="comparison-page">
	<div class="comparison-toolbar">
		<div>
			<h1>Comparaison de runs</h1>
			<p>Vue dédiée, en lecture seule, construite à partir des runs déjà présents dans l’historique et restaurés depuis leur cache/résultat existant.</p>
		</div>

		<div class="toolbar-actions">
			<label class="sync-toggle">
				<input type="checkbox" bind:checked={syncViewport} />
				<span>Synchroniser les cartes</span>
			</label>

			<button type="button" class="secondary-btn" onclick={navigateBackToAnalysis}>
				Retour à l’analyse
			</button>
		</div>
	</div>

	{#if loading || hasLoadedOnce}
		<div class="state-card loading-card" class:loading-card-complete={!loading && hasLoadedOnce}>
			<div class="loading-head">
				<h2>
					{#if loading}
						Traçabilité du chargement
					{:else}
						Traçabilité du chargement finalisée
					{/if}
				</h2>
				<p>
					Chaque run affiche son modèle chargé, son étape de restauration et son statut final.
				</p>
			</div>

			<div class="loading-trace-list">
				{#each loadTraces as trace (trace.id)}
					<div class="loading-trace-item">
						<div class="loading-trace-top">
							<div>
								<div class="loading-trace-title">{getRunLabel(trace.entry)}</div>
								<div class="loading-trace-model">{getRunModelLabel(trace.entry)}</div>
							</div>

							<span class={`loading-status ${trace.status}`}>
								{#if trace.status === "pending"}
									En attente
								{:else if trace.status === "loading"}
									Chargement
								{:else if trace.status === "done"}
									Prêt
								{:else}
									Erreur
								{/if}
							</span>
						</div>

						<div class="loading-step">{trace.step}</div>
						<div class="loading-details">{trace.details}</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	{#if loadError}
		<div class="state-card error">
			<p>{loadError}</p>
			<button type="button" class="secondary-btn" onclick={navigateBackToAnalysis}>
				Revenir à l’historique
			</button>
		</div>
	{:else if !loading}
		<div class="summary-grid">
			{#each runs as run, index (run.id)}
				<div class="summary-card">
					<div class="summary-title-row">
						<h2>{getComparisonRunHeading(run.entry, index)}</h2>
						<span class="summary-badge">{run.entry.algorithm.toUpperCase()}</span>
					</div>

					<div class="summary-stats">
						<div class="summary-stat">
							<span>Réduction</span>
							<strong>{run.entry.params.reduction}</strong>
						</div>
						<div class="summary-stat">
							<span>Affichage</span>
							<strong>{formatDisplayMode(run)}</strong>
						</div>
						<div class="summary-stat">
							<span>Points analysés</span>
							<strong>{run.result.summary.analyzedPoints.toLocaleString("fr-FR")}</strong>
						</div>
						<div class="summary-stat">
							<span>Clusters</span>
							<strong>{run.result.summary.clusterCount}</strong>
						</div>
						<div class="summary-stat">
							<span>Bruit</span>
							<strong>{run.result.summary.noiseCount.toLocaleString("fr-FR")}</strong>
						</div>
						<div class="summary-stat">
							<span>PFAS modèle</span>
							<strong>
								{run.entry.pfasSelected.includes("All")
									? "All"
									: `${run.entry.pfasSelected.length} sélectionnés`}
							</strong>
						</div>
					</div>

					{#if getDominantPfas(run).length > 0}
						<div class="summary-tags">
							{#each getDominantPfas(run) as pfas}
								<span class="summary-tag">{pfas}</span>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<div class="section-card">
			<div class="section-head">
				<div>
					<h2>Comparaison cartographique</h2>
					<p>Chaque carte conserve sa propre légende locale. Les identifiants de clusters ne sont jamais alignés entre runs.</p>
				</div>
			</div>

			<div class="map-grid">
				{#each runs as run, index (run.id)}
					<RunComparisonMap
						{run}
						runIndex={index}
						syncViewport={syncViewport}
						syncedViewport={
							syncViewport && activeViewportSourceId !== run.id ? sharedViewport : null
						}
						onViewportChange={handleViewportChange}
					/>
				{/each}
			</div>
		</div>

		<div class="section-card">
			<RunComparisonMetrics {runs} />
		</div>

		{#if failures.length > 0}
			<div class="state-card warning">
				<h3>Runs non chargés</h3>
				<div class="failure-list">
					{#each failures as failure}
						<div class="failure-item">
							<strong>{getRunLabel(failure.entry)}</strong>
							<span>{failure.error}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}
</div>

<style>
	.comparison-page {
		min-height: calc(100vh - 72px);
		padding: 1.25rem;
		background:
			radial-gradient(circle at top left, rgba(191, 219, 254, 0.45), transparent 32%),
			radial-gradient(circle at top right, rgba(253, 230, 138, 0.3), transparent 22%),
			linear-gradient(180deg, #f8fbff 0%, #eef5fb 100%);
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.comparison-toolbar,
	.section-card,
	.state-card {
		border-radius: 1.2rem;
		border: 1px solid #dbe4ee;
		background: rgba(255, 255, 255, 0.9);
		box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
	}

	.comparison-toolbar,
	.section-card,
	.state-card {
		padding: 1.1rem 1.2rem;
	}

	.comparison-toolbar {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
	}

	.comparison-toolbar h1,
	.section-head h2 {
		margin: 0;
		color: #0f172a;
	}

	.comparison-toolbar p,
	.section-head p {
		margin: 0.35rem 0 0;
		color: #64748b;
		max-width: 68ch;
	}

	.toolbar-actions {
		display: flex;
		align-items: center;
		gap: 0.85rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}

	.sync-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.9rem;
		color: #334155;
	}

	.secondary-btn {
		border: 1px solid #cbd5e1;
		background: #ffffff;
		color: #0f172a;
		border-radius: 0.8rem;
		padding: 0.65rem 0.9rem;
		font-weight: 600;
		cursor: pointer;
	}

	.secondary-btn:hover {
		background: #eff6ff;
		border-color: #93c5fd;
	}

	.summary-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
		gap: 0.9rem;
	}

	.summary-card {
		padding: 1rem;
		border-radius: 1rem;
		border: 1px solid #dbe4ee;
		background: rgba(255, 255, 255, 0.9);
		box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
	}

	.summary-title-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.8rem;
	}

	.summary-title-row h2 {
		margin: 0;
		font-size: 1rem;
		color: #0f172a;
	}

	.summary-badge {
		padding: 0.28rem 0.55rem;
		border-radius: 999px;
		background: #dbeafe;
		color: #1d4ed8;
		font-size: 0.75rem;
		font-weight: 700;
	}

	.summary-stats {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.7rem;
	}

	.summary-stat {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.summary-stat span {
		font-size: 0.78rem;
		color: #64748b;
	}

	.summary-stat strong {
		font-size: 0.9rem;
		color: #0f172a;
	}

	.summary-tags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
		margin-top: 0.8rem;
	}

	.summary-tag {
		padding: 0.3rem 0.55rem;
		border-radius: 999px;
		background: #f1f5f9;
		color: #334155;
		font-size: 0.76rem;
		font-weight: 600;
	}

	.section-head {
		margin-bottom: 0.95rem;
	}

	.map-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
		gap: 1rem;
	}

	.state-card {
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
		color: #0f172a;
	}

	.loading-card {
		gap: 1rem;
	}

	.loading-card-complete {
		background: rgba(248, 250, 252, 0.92);
	}

	.loading-head h2 {
		margin: 0;
		font-size: 1.05rem;
		color: #0f172a;
	}

	.loading-head p {
		margin: 0.3rem 0 0;
		font-size: 0.9rem;
		color: #64748b;
	}

	.loading-trace-list {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
		gap: 0.85rem;
	}

	.loading-trace-item {
		padding: 0.95rem;
		border-radius: 1rem;
		border: 1px solid #dbe4ee;
		background: #f8fbff;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}

	.loading-trace-top {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		align-items: flex-start;
	}

	.loading-trace-title {
		font-size: 0.95rem;
		font-weight: 700;
		color: #0f172a;
	}

	.loading-trace-model {
		margin-top: 0.15rem;
		font-size: 0.78rem;
		color: #475569;
		font-weight: 600;
	}

	.loading-status {
		padding: 0.24rem 0.55rem;
		border-radius: 999px;
		font-size: 0.72rem;
		font-weight: 700;
		white-space: nowrap;
	}

	.loading-status.pending {
		background: #e2e8f0;
		color: #475569;
	}

	.loading-status.loading {
		background: #dbeafe;
		color: #1d4ed8;
	}

	.loading-status.done {
		background: #dcfce7;
		color: #166534;
	}

	.loading-status.error {
		background: #fee2e2;
		color: #b91c1c;
	}

	.loading-step {
		font-size: 0.86rem;
		font-weight: 700;
		color: #0f172a;
	}

	.loading-details {
		font-size: 0.82rem;
		color: #64748b;
		line-height: 1.4;
	}

	.state-card.error {
		border-color: #fecaca;
		background: rgba(254, 242, 242, 0.92);
	}

	.state-card.warning {
		border-color: #fde68a;
		background: rgba(255, 251, 235, 0.92);
	}

	.state-card h3 {
		margin: 0;
	}

	.failure-list {
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}

	.failure-item {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.failure-item strong {
		color: #7c2d12;
	}

	.failure-item span {
		color: #92400e;
	}

	@media (max-width: 960px) {
		.comparison-toolbar {
			flex-direction: column;
		}

		.toolbar-actions {
			width: 100%;
			justify-content: space-between;
		}
	}

	@media (max-width: 720px) {
		.comparison-page {
			padding: 0.85rem;
		}

		.summary-stats {
			grid-template-columns: 1fr;
		}
	}
</style>
