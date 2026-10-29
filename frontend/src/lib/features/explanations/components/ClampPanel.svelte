<script lang="ts">
	import type { ClampResult, ClampRule } from "$lib/shared/types/analysis-contract";
	import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import { getClusterColor } from "$lib/shared/map/cluster-colors";

	const FIXED_CLAMP_PARAMS = {
		explainerType: "dtexp",
		boundingBoxSelection: "centroids",
		maxRulesPerCluster: 3,
		descriptionPointsRatio: 5,
		ignoreNoise: true,
	} as const;

	let {
		assignments = {},
		filters,
		selectedModelPfas = ["All"],
	} = $props<{
		assignments?: Record<string, number>;
		filters: Record<string, unknown>;
		selectedModelPfas?: string[];
	}>();

	let loading = $state(false);
	let error = $state<string | null>(null);
	let selectedClusterValue = $state<string>("all");
	let showRulesSummary = $state(true);

	const clampResult = $derived(analysisRune.clampResult);
	const activeRule = $derived(analysisRune.activeClampRule);
	const availableClusterIds = $derived(
		analysisRune.clusterSummaries
			.filter((summary) => summary.clusterId !== -1)
			.map((summary) => summary.clusterId)
			.sort((a, b) => a - b),
	);
	const requestedClusterId = $derived(
		selectedClusterValue === "all" ? null : Number(selectedClusterValue),
	);
	const selectedClusterRules = $derived(
		requestedClusterId == null
			? []
			: (clampResult?.rulesByCluster?.[String(requestedClusterId)] ?? []),
	);
	const clusterRuleEntries = $derived(
		clampResult
			? Object.entries(clampResult.rulesByCluster).sort(
					([a], [b]) => Number(a) - Number(b),
				)
			: [],
	);
	const reliableClusterRuleEntries = $derived(
		clusterRuleEntries.filter(([, rules]) => rules.length > 0),
	);
	const clustersWithoutReliableRuleCount = $derived(
		clusterRuleEntries.filter(([, rules]) => rules.length === 0).length,
	);
	const canRun = $derived(
		analysisRune.clusterSummaries.length > 0 &&
			Object.keys(getAssignmentsSnapshot()).length > 0,
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

	function buildClusterInfo(clusterId: number | null) {
		if (clusterId == null) return null;

		const summary =
			analysisRune.clusterSummaries.find((item) => item.clusterId === clusterId) ?? null;

		if (!summary) return null;

		return {
			...summary,
			color: getClusterColor(clusterId),
			algorithm: analysisRune.algorithm,
		};
	}

	function syncMapSelection(rule: ClampRule | null, displayMode: "points" | "heatmap" = "points") {
		if (!rule) {
			analysisRune.isClampMapMode = false;
			analysisRune.clampDisplayMode = "points";
			return;
		}

		analysisRune.selectClampRule(rule.cluster, rule.id);
		analysisRune.clampDisplayMode = displayMode;
		analysisRune.selectedClusterId = rule.cluster;
		dataRune.selectedClusterInfo = buildClusterInfo(rule.cluster);
	}

	function formatInt(value: number | null | undefined): string {
		if (value == null || Number.isNaN(value)) return "-";
		return Math.round(Number(value)).toLocaleString("fr-FR");
	}

	function formatPercent(value: number | null | undefined): string {
		if (value == null || Number.isNaN(value)) return "-";

		const numericValue = Number(value);
		if (numericValue > 0 && numericValue < 0.001) {
			return "< 0.1 %";
		}

		const percent = numericValue * 100;
		const digits = Math.abs(percent) >= 10 ? 1 : 2;
		return `${percent.toLocaleString("fr-FR", {
			minimumFractionDigits: digits,
			maximumFractionDigits: digits,
		})} %`;
	}

	function formatScore(value: number | null | undefined): string {
		if (value == null || Number.isNaN(value)) return "-";

		const numericValue = Number(value);
		if (numericValue > 0 && numericValue < 0.001) {
			return "< 0.001";
		}

		return numericValue.toLocaleString("fr-FR", {
			minimumFractionDigits: numericValue >= 1 ? 1 : 2,
			maximumFractionDigits: numericValue >= 1 ? 2 : 3,
		});
	}

	function formatScorePercent(value: number | null | undefined): string {
		if (value == null || Number.isNaN(value)) return "-";
		return formatPercent(Number(value));
	}

	function getRuleLabel(rule: ClampRule | null | undefined): string {
		if (!rule) return "-";
		return rule.rule || "Règle indisponible";
	}

	function parseErrorResponseText(text: string, status: number): string {
		if (!text) return `Erreur HTTP ${status}`;

		try {
			const parsed = JSON.parse(text);
			return (
				parsed?.detail ??
				parsed?.message ??
				parsed?.error ??
				`Erreur HTTP ${status}`
			);
		} catch {
			return text;
		}
	}

	async function runClamp() {
		const assignmentsSnapshot = getAssignmentsSnapshot();

		if (analysisRune.clusterSummaries.length === 0) {
			error = "Lancez d’abord une analyse de clustering.";
			return;
		}

		if (Object.keys(assignmentsSnapshot).length === 0) {
			error = "Aucun résultat de clustering disponible.";
			return;
		}

		loading = true;
		error = null;

		try {
			const response = await fetch("/api/analysis/clamp", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					filters,
					selectedModelPfas,
					assignments: assignmentsSnapshot,
					clusterId: requestedClusterId,
					params: FIXED_CLAMP_PARAMS,
				}),
			});

			const text = await response.text().catch(() => "");
			if (!response.ok) {
				error = parseErrorResponseText(text, response.status);
				analysisRune.resetClampState();
				return;
			}

			const result = JSON.parse(text) as ClampResult;
			analysisRune.activateClampResult(result, requestedClusterId);

			const defaultRule =
				(requestedClusterId != null
					? result.rulesByCluster?.[String(requestedClusterId)]?.[0]
					: null) ??
				(result.bestRuleId
					? result.rules.find((rule) => rule.id === result.bestRuleId) ?? null
					: null) ??
				result.rules[0] ??
				null;

			if (defaultRule) {
				syncMapSelection(defaultRule, "points");
			} else {
				analysisRune.isClampMapMode = false;
				analysisRune.clampDisplayMode = "points";
			}
		} catch (err: unknown) {
			error = err instanceof Error ? err.message : "Erreur inconnue";
			analysisRune.resetClampState();
		} finally {
			loading = false;
		}
	}

	function showRuleOnMap(rule: ClampRule, displayMode: "points" | "heatmap" = "points") {
		error = null;
		syncMapSelection(rule, displayMode);
	}

	function restoreClusterView(clusterId: number | null) {
		if (clusterId == null) {
			analysisRune.selectedClusterId = null;
			dataRune.selectedClusterInfo = null;
			dataRune.selectedCondensedGroup = null;
			dataRune.selectedPoints = [];
			dataRune.selectedBubblePointIds = [];
			dataRune.detailsContext = "all";
			dataRune.clusterGeometryRequest = null;
			return;
		}

		const pointIds = Object.entries(getAssignmentsSnapshot())
			.filter(([, assignedClusterId]) => Number(assignedClusterId) === clusterId)
			.map(([pointId]) => pointId);

		analysisRune.selectedClusterId = clusterId;
		dataRune.selectedClusterInfo = buildClusterInfo(clusterId);
		dataRune.selectedCondensedGroup = null;
		dataRune.selectedPoints = [];
		dataRune.selectedBubblePointIds = pointIds;
		dataRune.detailsContext = "cluster";
		dataRune.clusterGeometryRequest = null;
	}

	function resetClampMap() {
		const clusterId =
			analysisRune.selectedClampClusterId ?? activeRule?.cluster ?? null;

		analysisRune.isClampMapMode = false;
		analysisRune.clampDisplayMode = "points";
		restoreClusterView(clusterId);
	}

	function getStatusMessage(): string | null {
		if (error) return error;

		if (analysisRune.clusterSummaries.length === 0) {
			return "Lancez d’abord une analyse de clustering.";
		}

		if (Object.keys(getAssignmentsSnapshot()).length === 0) {
			return "Aucun résultat de clustering disponible.";
		}

		if (!clampResult) return null;

		if (requestedClusterId != null && selectedClusterRules.length === 0) {
			return "Aucune règle fiable trouvée pour ce cluster.";
		}

		if (clampResult.rules.length === 0) {
			return "Aucune règle fiable trouvée pour ce cluster.";
		}

		return null;
	}

	$effect(() => {
		analysisRune.clusterSummaries;
		dataRune.selectedClusterInfo?.clusterId;
		assignments;
		selectedModelPfas;

		if (
			selectedClusterValue !== "all" &&
			!availableClusterIds.includes(Number(selectedClusterValue))
		) {
			selectedClusterValue = "all";
		}
	});
</script>

<div class="clamp-panel">
	<div class="clamp-controls">
		<label class="field-label" for="clamp-cluster-target">Cluster cible</label>
		<select id="clamp-cluster-target" bind:value={selectedClusterValue} class="field-select">
			<option value="all">Tous les clusters</option>
			{#each availableClusterIds as clusterId}
				<option value={String(clusterId)}>C{clusterId}</option>
			{/each}
		</select>

		<button
			type="button"
			class="clamp-run-btn"
			onclick={runClamp}
			disabled={loading || !canRun}
		>
			{#if loading}
				Calcul...
			{:else}
				Calculer ClAMP
			{/if}
		</button>
	</div>

	{#if getStatusMessage()}
		<div class="clamp-message clamp-message-error">
			{getStatusMessage()}
		</div>
	{/if}

	{#if clampResult}
		<div class="clamp-section">
			<div class="section-header">
				<h4 class="section-title">Carte explicative</h4>
				<div class="mode-switch">
					<button
						type="button"
						class:mode-btn-active={analysisRune.isClampMapMode && analysisRune.clampDisplayMode === "points"}
						class="mode-btn"
						disabled={!activeRule}
						onclick={() => activeRule && showRuleOnMap(activeRule, "points")}
					>
						Points expliqués
					</button>
					<button
						type="button"
						class:mode-btn-active={analysisRune.isClampMapMode && analysisRune.clampDisplayMode === "heatmap"}
						class="mode-btn"
						disabled={!activeRule}
						onclick={() => activeRule && showRuleOnMap(activeRule, "heatmap")}
					>
						Heatmap des points couverts
					</button>
				</div>
			</div>

			{#if activeRule}
				<div class="rule-card">
					<div class="rule-card-title">Explication ClAMP</div>

					<div class="rule-row">
						<span class="rule-label">Cluster expliqué</span>
						<span class="rule-value">C{activeRule.cluster}</span>
					</div>

					<div class="rule-row rule-row-stack">
						<span class="rule-label">Règle active</span>
						<span class="rule-value rule-text">{getRuleLabel(activeRule)}</span>
					</div>

					<div class="rule-grid">
						<div class="metric-card">
							<div class="metric-label">Points expliqués</div>
							<div class="metric-value">{formatInt(activeRule.support)}</div>
						</div>
						<div class="metric-card">
							<div class="metric-label">Fiabilité</div>
							<div class="metric-value">{formatPercent(activeRule.precision)}</div>
						</div>
						<div class="metric-card">
							<div class="metric-label">Couverture du cluster</div>
							<div class="metric-value">{formatPercent(activeRule.coverageCluster)}</div>
						</div>
						<div class="metric-card">
							<div class="metric-label">Score</div>
							<div class="metric-value">{formatScorePercent(activeRule.score)}</div>
						</div>
					</div>

					<div class="rule-row rule-row-stack">
						<span class="rule-label">PFAS impliqués</span>
						<span class="rule-value">
							{activeRule.features.length > 0 ? activeRule.features.join(", ") : "-"}
						</span>
					</div>

					<div class="rule-actions">
						<button
							type="button"
							class="secondary-btn"
							onclick={() => (showRulesSummary = !showRulesSummary)}
						>
							{showRulesSummary ? "Masquer autres règles" : "Voir autres règles"}
						</button>
						<button type="button" class="secondary-btn" onclick={resetClampMap}>
							Réinitialiser la carte
						</button>
					</div>
				</div>
			{:else}
				<div class="clamp-message">
					Aucune règle fiable trouvée pour ce cluster.
				</div>
			{/if}
		</div>

		{#if showRulesSummary}
			<div class="clamp-section">
				<div class="section-header">
					<h4 class="section-title">Résumé des règles par cluster</h4>
				</div>

				<div class="cluster-rule-list">
					{#each reliableClusterRuleEntries as [clusterKey, rules]}
						<div class="cluster-rule-card">
							<div class="cluster-rule-header">
								<div class="cluster-badge" style={`background:${getClusterColor(Number(clusterKey))}`}>
									C{clusterKey}
								</div>
								<div class="cluster-rule-subtitle">
									{Math.min(rules.length, 3)} règle{Math.min(rules.length, 3) > 1 ? "s" : ""} fiable{Math.min(rules.length, 3) > 1 ? "s" : ""}
								</div>
							</div>

							{#each rules.slice(0, 3) as rule}
								<div class="summary-rule">
									<div class="summary-rule-cluster">Cluster C{rule.cluster}</div>
									<div class="summary-rule-title">Règle principale : {getRuleLabel(rule)}</div>
									<div class="summary-rule-metrics">
										<span>Fiabilité : {formatPercent(rule.precision)}</span>
										<span>Couverture du cluster : {formatPercent(rule.coverageCluster)}</span>
										<span>Score : {formatScorePercent(rule.score)}</span>
										<span>Points expliqués : {formatInt(rule.support)}</span>
									</div>
									<button
										type="button"
										class="summary-map-btn"
										onclick={() => showRuleOnMap(rule, "points")}
									>
										Voir sur la carte
									</button>
								</div>
							{/each}
						</div>
					{/each}

					{#if clustersWithoutReliableRuleCount > 0}
						<div class="cluster-rule-empty-summary">
							{clustersWithoutReliableRuleCount} cluster{clustersWithoutReliableRuleCount > 1 ? "s" : ""} sans règle fiable selon les seuils actuels.
						</div>
					{/if}
				</div>
			</div>
		{/if}
	{/if}
</div>

<style>
	.clamp-panel {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.clamp-controls {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.field-label {
		font-size: 0.95rem;
		font-weight: 600;
		color: #334155;
	}

	.field-select {
		width: 100%;
		min-height: 44px;
		border-radius: 12px;
		border: 1px solid #cbd5e1;
		padding: 0.75rem 0.9rem;
		background: white;
		color: #0f172a;
	}

	.clamp-run-btn {
		min-height: 46px;
		border: none;
		border-radius: 12px;
		background: #0f172a;
		color: white;
		font-weight: 700;
		cursor: pointer;
	}

	.clamp-run-btn:disabled {
		cursor: not-allowed;
		opacity: 0.6;
	}

	.clamp-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding-top: 0.25rem;
	}

	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.section-title {
		font-size: 1rem;
		font-weight: 700;
		color: #0f172a;
		margin: 0;
	}

	.mode-switch {
		display: inline-flex;
		gap: 0.4rem;
		flex-wrap: wrap;
	}

	.mode-btn,
	.secondary-btn,
	.summary-map-btn {
		border-radius: 999px;
		border: 1px solid #cbd5e1;
		background: white;
		color: #0f172a;
		padding: 0.55rem 0.85rem;
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
	}

	.mode-btn-active {
		background: #dbeafe;
		border-color: #93c5fd;
		color: #1d4ed8;
	}

	.mode-btn:disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}

	.rule-card,
	.cluster-rule-card {
		border: 1px solid #e2e8f0;
		border-radius: 16px;
		background: #fff;
		padding: 1rem;
	}

	.rule-card-title {
		font-size: 1rem;
		font-weight: 700;
		color: #0f172a;
		margin-bottom: 0.9rem;
	}

	.rule-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.8rem;
	}

	.rule-row-stack {
		align-items: flex-start;
		flex-direction: column;
	}

	.rule-label {
		font-size: 0.85rem;
		font-weight: 600;
		color: #64748b;
	}

	.rule-value {
		font-size: 0.95rem;
		font-weight: 600;
		color: #0f172a;
	}

	.rule-text {
		line-height: 1.5;
	}

	.rule-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.7rem;
		margin-bottom: 0.9rem;
	}

	.metric-card {
		border-radius: 14px;
		background: #f8fafc;
		padding: 0.8rem;
	}

	.metric-label {
		font-size: 0.8rem;
		font-weight: 600;
		color: #64748b;
		margin-bottom: 0.3rem;
	}

	.metric-value {
		font-size: 1rem;
		font-weight: 700;
		color: #0f172a;
	}

	.rule-actions {
		display: flex;
		gap: 0.6rem;
		flex-wrap: wrap;
		margin-top: 0.3rem;
	}

	.clamp-message {
		border-radius: 12px;
		padding: 0.8rem 0.9rem;
		background: #f8fafc;
		color: #334155;
		line-height: 1.5;
	}

	.clamp-message-error {
		background: #fff7ed;
		color: #9a3412;
	}

	.cluster-rule-list {
		display: flex;
		flex-direction: column;
		gap: 0.8rem;
	}

	.cluster-rule-header {
		display: flex;
		align-items: center;
		gap: 0.65rem;
		margin-bottom: 0.8rem;
		flex-wrap: wrap;
	}

	.cluster-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 44px;
		height: 28px;
		padding: 0 0.6rem;
		border-radius: 999px;
		color: white;
		font-size: 0.85rem;
		font-weight: 700;
	}

	.cluster-rule-subtitle {
		font-size: 0.85rem;
		color: #64748b;
		font-weight: 600;
	}

	.cluster-rule-empty {
		font-size: 0.92rem;
		color: #64748b;
	}

	.summary-rule {
		padding-top: 0.8rem;
		margin-top: 0.8rem;
		border-top: 1px solid #e2e8f0;
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
	}

	.summary-rule:first-of-type {
		border-top: none;
		padding-top: 0;
		margin-top: 0;
	}

	.summary-rule-title {
		font-size: 0.95rem;
		font-weight: 700;
		color: #0f172a;
		line-height: 1.45;
	}

	.summary-rule-cluster {
		font-size: 0.85rem;
		font-weight: 700;
		color: #475569;
	}

	.summary-rule-metrics {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem 0.9rem;
		font-size: 0.85rem;
		color: #475569;
	}

	.summary-map-btn {
		align-self: flex-start;
	}

	.cluster-rule-empty-summary {
		border: 1px dashed #cbd5e1;
		border-radius: 14px;
		background: #f8fafc;
		padding: 0.9rem 1rem;
		font-size: 0.92rem;
		font-weight: 600;
		color: #475569;
	}

	@media (max-width: 640px) {
		.rule-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
