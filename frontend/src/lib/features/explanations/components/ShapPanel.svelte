<script lang="ts">
	import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import { ChevronDown, Info } from "lucide-svelte";

	let { assignments = {} } = $props<{
		assignments?: Record<string, number>;
	}>();

	type ShapImportance = {
		feature?: string;
		featureKey?: string;
		featureLabel?: string;
		importance: number;
	};

	type ShapResult = {
		fidelity: number;
		message?: string;
		effectiveReduction?: string;
		shapInput?: string;
		globalImportances: ShapImportance[];
		localImportances: ShapImportance[] | null;
	};

	let loading = $state(false);
	let error = $state<string | null>(null);
	let result = $state<ShapResult | null>(null);
	let showGlobal = $state(true);
	let showLocal = $state(true);
	let explanationType = $state<"global" | "local">("global");
	let localClusterId = $state<string>("auto");

	const isClusterContext = $derived(dataRune.detailsContext === "cluster");

	const selectedClusterId = $derived(
		isClusterContext ? (dataRune.selectedClusterInfo?.clusterId ?? null) : null,
	);

	const availableClusterIds = $derived(
		analysisRune.clusterSummaries
			.filter((summary) => summary.clusterId !== -1)
			.map((summary) => summary.clusterId)
			.sort((a, b) => a - b),
	);

	const resolvedLocalClusterId = $derived(
		localClusterId === "auto"
			? (selectedClusterId ?? availableClusterIds[0] ?? null)
			: Number(localClusterId),
	);

	const canRun = $derived(
		analysisRune.clusterSummaries.length > 0 &&
			Object.keys(assignments ?? {}).length > 0 &&
			(explanationType === "global" || resolvedLocalClusterId != null),
	);

	function readSessionAssignments(): Record<string, number> {
		if (typeof sessionStorage === "undefined") return {};

		const raw = sessionStorage.getItem("last-analysis-assignments");
		if (!raw) return {};

		try {
			const parsed = JSON.parse(raw) as Record<string, unknown>;
			const normalized: Record<string, number> = {};

			for (const [pointId, cluster] of Object.entries(parsed ?? {})) {
				const numericCluster = Number(cluster);
				if (Number.isFinite(numericCluster)) {
					normalized[String(pointId)] = numericCluster;
				}
			}

			return normalized;
		} catch {
			return {};
		}
	}

	function getAssignmentsSnapshot(): Record<string, number> {
		const sessionAssignments = readSessionAssignments();
		return Object.keys(sessionAssignments).length > 0 ? sessionAssignments : assignments;
	}

	function resetPanelState() {
		error = null;
		result = null;
		showLocal = true;
		showGlobal = true;
		explanationType = dataRune.detailsContext === "cluster" ? "local" : "global";
		localClusterId = "auto";
	}

	function buildApiFilters() {
		const filtersSnapshot = $state.snapshot(dataRune.filters);
		const { nutsRegions: _nutsRegions, ...apiFilters } =
			filtersSnapshot as typeof filtersSnapshot & { nutsRegions?: unknown };

		return apiFilters;
	}

	async function parseErrorResponse(response: Response): Promise<string> {
		const text = await response.text().catch(() => "");
		if (!text) return `Erreur HTTP ${response.status}`;

		try {
			const parsed = JSON.parse(text);
			return (
				parsed?.detail ??
				parsed?.message ??
				parsed?.error ??
				`Erreur HTTP ${response.status}`
			);
		} catch {
			return text;
		}
	}

	async function runShap() {
		const assignmentsSnapshot = getAssignmentsSnapshot();
		if (Object.keys(assignmentsSnapshot).length === 0) {
			error = "Lancez d’abord une analyse de clustering.";
			return;
		}

		loading = true;
		error = null;
		result = null;

		try {
			const response = await fetch("/api/analysis/shap", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					algorithm: analysisRune.algorithm,
					filters: buildApiFilters(),
					selectedModelPfas: analysisRune.selectedModelPfas,
					assignments: assignmentsSnapshot,
						mode: "expert",
					params: {
						k: analysisRune.k,
						maxIterations: analysisRune.maxIterations,
						eps: analysisRune.eps,
						minPts: analysisRune.minPts,
						minClusterSize: analysisRune.minClusterSize,
						minSamples: analysisRune.minSamples,
						clusterSelectionMethod: analysisRune.clusterSelectionMethod,
						preprocessing: analysisRune.preprocessing,
						reduction: analysisRune.reduction,
					},
					clusterId:
						explanationType === "local" ? resolvedLocalClusterId : null,
				}),
			});

			if (!response.ok) {
				error = await parseErrorResponse(response);
				return;
			}

			result = (await response.json()) as ShapResult;

			if (explanationType === "local") {
				showLocal = true;
				showGlobal = Boolean(result.globalImportances?.length);
			} else {
				showLocal = false;
				showGlobal = true;
			}
		} catch (e: unknown) {
			if (e instanceof Error) {
				error = e.message;
			} else {
				error = "Erreur inconnue";
			}
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		dataRune.detailsContext;
		dataRune.selectedClusterInfo?.clusterId;
		analysisRune.algorithm;
		analysisRune.k;
		analysisRune.maxIterations;
		analysisRune.eps;
		analysisRune.minPts;
		analysisRune.minClusterSize;
		analysisRune.minSamples;
		analysisRune.clusterSelectionMethod;
		analysisRune.preprocessing;
		analysisRune.reduction;
		analysisRune.selectedModelPfas;
		analysisRune.expertMode;
		assignments;

		resetPanelState();
	});

	function formatImportancePercentage(
		value: number,
		allImportances: ShapImportance[],
	): string {
		const safeValue = Math.abs(Number(value) || 0);

		const total = allImportances.reduce((sum, item) => {
			return sum + Math.abs(Number(item.importance) || 0);
		}, 0);

		if (total <= 0) return "0.0%";

		return `${((safeValue / total) * 100).toFixed(1)}%`;
	}

	function stripCasSuffix(text: string): string {
		return String(text ?? "")
			.replace(/\s*\[[^\]]*\]\s*$/u, "")
			.trim();
	}

	function getRawFeatureDisplay(item: ShapImportance): string {
		const raw =
			item.featureLabel ??
			item.feature ??
			item.featureKey ??
			"PFAS inconnu";

		return String(raw).trim() || "PFAS inconnu";
	}

	function getFeatureDisplay(
		item: ShapImportance,
		allImportances: ShapImportance[],
	): string {
		const raw = getRawFeatureDisplay(item);
		const cleaned = stripCasSuffix(raw);
		if (!cleaned) return "PFAS inconnu";

		const duplicateCount = allImportances.reduce((count, currentItem) => {
			return count + (stripCasSuffix(getRawFeatureDisplay(currentItem)) === cleaned ? 1 : 0);
		}, 0);

		// Keep the short label when it is unique; otherwise preserve the full
		// SHAP label so genuinely distinct columns stay visually distinguishable.
		return duplicateCount > 1 ? raw : cleaned;
	}

	function getFeatureKey(
		item: ShapImportance,
		index: number,
		scope: "local" | "global",
	): string {
		return `${scope}-${item.featureKey ?? item.feature ?? item.featureLabel ?? "unknown"}-${index}`;
	}
</script>

<div class="shap-panel">
	<div class="shap-header">
		<h4 class="shap-title">SHAP</h4>

		<button
			class="shap-run-btn"
			onclick={runShap}
			disabled={loading || !canRun}
		>
			{#if loading}
				Calcul...
			{:else if explanationType === "local"}
				Calculer SHAP local
			{:else}
				Calculer SHAP global
			{/if}
		</button>
	</div>

	<div class="shap-controls">
		<label class="shap-control">
			<span class="shap-control-label">Type d’explication</span>
			<select bind:value={explanationType} class="shap-select">
				<option value="global">Global</option>
				<option value="local">Local par cluster</option>
			</select>
		</label>

		{#if explanationType === "local"}
			<label class="shap-control">
				<span class="shap-control-label">Cluster cible</span>
				<select bind:value={localClusterId} class="shap-select">
					<option value="auto">Cluster courant</option>
					{#each availableClusterIds as clusterId}
						<option value={String(clusterId)}>C{clusterId}</option>
					{/each}
				</select>
			</label>
		{/if}
	</div>

	<p class="shap-disclaimer">
		<Info size={12} />
		SHAP explique un modèle surrogate RandomForest, pas directement le clustering.
	</p>

	{#if explanationType === "local"}
		<p class="shap-scope">
			Scope : cluster {resolvedLocalClusterId ?? "-"} = explication locale.
		</p>
	{:else}
		<p class="shap-scope">Scope : tous les clusters = explication globale.</p>
	{/if}

	{#if Object.keys(assignments ?? {}).length === 0}
		<p class="shap-error">Lancez d’abord une analyse de clustering.</p>
	{/if}

	{#if error}
		<p class="shap-error">{error}</p>
	{/if}

	{#if result}
		<p class="shap-fidelity">
			Fidélité du surrogate :
			<strong>{(result.fidelity * 100).toFixed(1)}%</strong>
		</p>

		{#if result.message}
			<p class="shap-note">{result.message}</p>
		{/if}

		{#if explanationType === "local"}
			<div class="shap-section">
				<button
					type="button"
					class="shap-section-header"
					onclick={() => (showLocal = !showLocal)}
				>
					<span>Importances locales du cluster</span>
					<ChevronDown
						class={`shap-chevron ${!showLocal ? "rotated" : ""}`}
						size={14}
					/>
				</button>

				{#if showLocal}
					{#if result.localImportances && result.localImportances.length > 0}
						{@const maxLocalImp = Math.max(
							...result.localImportances.map((i) => i.importance),
							0.001,
						)}
						<div class="shap-bars">
							{#each result.localImportances as item, index (getFeatureKey(item, index, "local"))}
								<div class="shap-bar-row">
									<span
										class="shap-feature"
										title={getFeatureDisplay(
											item,
											result.localImportances,
										)}
									>
										{getFeatureDisplay(
											item,
											result.localImportances,
										)}
									</span>

									<div class="shap-bar-container">
										<div
											class="shap-bar shap-bar-local"
											style={`width: ${(item.importance / maxLocalImp) * 100}%`}
										></div>
									</div>

									<span class="shap-value">
										{formatImportancePercentage(
											item.importance,
											result.localImportances,
										)}
									</span>
								</div>
							{/each}
						</div>
					{:else}
						<div class="muted">
							Aucune importance locale disponible pour ce cluster.
						</div>
					{/if}
				{/if}
			</div>
		{/if}

		{#if result.globalImportances.length > 0}
			<div class="shap-section">
				<button
					type="button"
					class="shap-section-header"
					onclick={() => (showGlobal = !showGlobal)}
				>
					<span>
						{#if explanationType === "local"}
							Importances globales de référence
						{:else}
							Importances globales
						{/if}
					</span>
					<ChevronDown
						class={`shap-chevron ${!showGlobal ? "rotated" : ""}`}
						size={14}
					/>
				</button>

				{#if showGlobal}
					{@const maxImp = Math.max(
						...result.globalImportances.map((i) => i.importance),
						0.001,
					)}
					<div class="shap-bars">
						{#each result.globalImportances as item, index (getFeatureKey(item, index, "global"))}
							<div class="shap-bar-row">
								<span
									class="shap-feature"
									title={getFeatureDisplay(
										item,
										result.globalImportances,
									)}
								>
									{getFeatureDisplay(
										item,
										result.globalImportances,
									)}
								</span>

								<div class="shap-bar-container">
									<div
										class="shap-bar"
										style={`width: ${(item.importance / maxImp) * 100}%`}
									></div>
								</div>

								<span class="shap-value">
									{formatImportancePercentage(
										item.importance,
										result.globalImportances,
									)}
								</span>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{:else if result && !result.message}
			<div class="muted">Aucune importance globale disponible.</div>
		{/if}
	{/if}
</div>

<style>
	.shap-panel {
		margin-top: 1rem;
		padding-top: 0.75rem;
		border-top: 1px solid #e2e8f0;
	}

	.shap-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
		gap: 0.75rem;
	}

	.shap-controls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-bottom: 0.6rem;
	}

	.shap-control {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.shap-control-label {
		font-size: 0.76rem;
		font-weight: 600;
		color: #334155;
	}

	.shap-select {
		border: 1px solid #cbd5e1;
		border-radius: 0.45rem;
		padding: 0.42rem 0.6rem;
		font-size: 0.78rem;
		background: white;
		color: #0f172a;
	}

	.shap-title {
		font-size: 0.95rem;
		font-weight: 700;
		color: #111827;
	}

	.shap-run-btn {
		all: unset;
		cursor: pointer;
		padding: 0.3rem 0.7rem;
		border-radius: 0.4rem;
		font-size: 0.78rem;
		font-weight: 600;
		background: hsl(var(--primary));
		color: white;
		white-space: nowrap;
	}

	.shap-run-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.shap-disclaimer {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.72rem;
		color: #94a3b8;
		font-style: italic;
		margin-bottom: 0.35rem;
	}

	.shap-scope {
		font-size: 0.76rem;
		color: #64748b;
		margin-bottom: 0.5rem;
	}

	.shap-error {
		font-size: 0.8rem;
		color: #dc2626;
		margin-bottom: 0.5rem;
	}

	.shap-note {
		font-size: 0.78rem;
		color: #92400e;
		background: #fff7ed;
		border: 1px solid #fdba74;
		border-radius: 0.45rem;
		padding: 0.45rem 0.6rem;
		margin-bottom: 0.5rem;
	}

	.shap-fidelity {
		font-size: 0.82rem;
		color: #475569;
		margin-bottom: 0.5rem;
	}

	.shap-section {
		margin-bottom: 0.6rem;
	}

	.shap-section-header {
		all: unset;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
		font-size: 0.85rem;
		font-weight: 600;
		color: #334155;
		margin-bottom: 0.4rem;
	}

	:global(.shap-chevron) {
		transition: transform 0.2s ease;
		color: #94a3b8;
	}

	:global(.shap-chevron.rotated) {
		transform: rotate(-90deg);
	}

	.shap-bars {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.shap-bar-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
	}

	.shap-feature {
		flex: 0 0 170px;
		max-width: 170px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: #475569;
		font-weight: 500;
		display: inline-block;
	}

	.shap-bar-container {
		flex: 1;
		height: 12px;
		background: #f1f5f9;
		border-radius: 3px;
		overflow: hidden;
		min-width: 80px;
	}

	.shap-bar {
		height: 100%;
		background: #3b82f6;
		border-radius: 3px;
		transition: width 0.3s ease;
	}

	.shap-bar-local {
		background: #8b5cf6;
	}

	.shap-value {
		flex: 0 0 52px;
		text-align: right;
		color: #64748b;
		font-size: 0.7rem;
	}

	.muted {
		font-size: 0.8rem;
		color: #6b7280;
	}
</style>
