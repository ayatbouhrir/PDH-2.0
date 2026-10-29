<script lang="ts">
	import type { ComparisonRunData } from "$lib/features/comparison/run-comparison.types";

	let { runs }: { runs: ComparisonRunData[] } = $props();

	const RUN_COLORS = ["#1d4ed8", "#ea580c", "#0f766e", "#be123c"];

	type MetricDefinition = {
		key: string;
		label: string;
		hint: string;
		direction: "higher" | "lower";
		getValue: (run: ComparisonRunData) => number | null;
		formatValue: (value: number) => string;
	};

	const metricDefinitions: MetricDefinition[] = [
		{
			key: "silhouette",
			label: "Silhouette",
			hint: "Plus élevé = mieux",
			direction: "higher",
			getValue: (run) => run.result.globalMetrics?.silhouetteScore ?? null,
			formatValue: (value) => value.toFixed(4),
		},
		{
			key: "davies-bouldin",
			label: "Davies-Bouldin",
			hint: "Plus faible = mieux",
			direction: "lower",
			getValue: (run) => run.result.globalMetrics?.daviesBouldinIndex ?? null,
			formatValue: (value) => value.toFixed(4),
		},
		{
			key: "calinski-harabasz",
			label: "Calinski-Harabasz",
			hint: "Plus élevé = mieux",
			direction: "higher",
			getValue: (run) => run.result.globalMetrics?.calinskiHarabaszScore ?? null,
			formatValue: (value) => value.toLocaleString("fr-FR", { maximumFractionDigits: 2 }),
		},
		{
			key: "wcss",
			label: "WCSS / Inertia",
			hint: "Plus faible = mieux",
			direction: "lower",
			getValue: (run) => run.result.globalMetrics?.wcss ?? null,
			formatValue: (value) => value.toLocaleString("fr-FR", { maximumFractionDigits: 2 }),
		},
		{
			key: "cluster-count",
			label: "Nombre de clusters",
			hint: "Lecture structurelle du run",
			direction: "higher",
			getValue: (run) => run.result.summary.clusterCount ?? null,
			formatValue: (value) => value.toLocaleString("fr-FR"),
		},
		{
			key: "noise-count",
			label: "Points bruit",
			hint: "Plus faible = mieux",
			direction: "lower",
			getValue: (run) => run.result.globalMetrics?.noiseCount ?? run.result.summary.noiseCount ?? null,
			formatValue: (value) => value.toLocaleString("fr-FR"),
		},
		{
			key: "noise-ratio",
			label: "Ratio bruit",
			hint: "Plus faible = mieux",
			direction: "lower",
			getValue: (run) => run.result.globalMetrics?.noiseRatio ?? null,
			formatValue: (value) => `${(value * 100).toFixed(1)}%`,
		},
		{
			key: "duration",
			label: "Durée",
			hint: "Plus faible = mieux",
			direction: "lower",
			getValue: (run) => run.result.summary.durationMs ?? run.entry.durationMs ?? null,
			formatValue: (value) =>
				value < 1000 ? `${value.toLocaleString("fr-FR")} ms` : `${(value / 1000).toFixed(1)} s`,
		},
		{
			key: "condensed-bubbles",
			label: "Bulles condensées",
			hint: "Taille de la vue condensée",
			direction: "higher",
			getValue: (run) => run.condensedBubbles.length,
			formatValue: (value) => value.toLocaleString("fr-FR"),
		},
	];

	function getRunOrdinalLabel(index: number) {
		return ["Premier run", "Deuxième run", "Troisième run", "Quatrième run"][index] ?? `Run ${index + 1}`;
	}

	function getRunLabel(run: ComparisonRunData, index: number) {
		return `${getRunOrdinalLabel(index)} (${run.id.slice(0, 8)})`;
	}

	function getRunColor(index: number) {
		return RUN_COLORS[index % RUN_COLORS.length];
	}

	function normalizeBarWidth(value: number, values: number[]) {
		const maxValue = Math.max(...values, 0);
		if (maxValue <= 0) return 0;
		return Math.max(8, (value / maxValue) * 100);
	}

	function availableMetricRows(metric: MetricDefinition) {
		return runs
			.map((run, index) => ({
				run,
				index,
				value: metric.getValue(run),
			}))
			.filter(
				(row): row is { run: ComparisonRunData; index: number; value: number } =>
					row.value != null && Number.isFinite(row.value),
			);
	}

	function metricValues(
		rows: Array<{ run: ComparisonRunData; index: number; value: number }>,
	) {
		return rows.map((row) => row.value);
	}
</script>

<div class="metrics-section">
	<div class="section-header">
		<div>
			<h2>Métriques comparées</h2>
			<p>Les valeurs uniques sont comparées en barres, avec un repère de lecture pour aider à interpréter chaque métrique.</p>
		</div>
	</div>

	<div class="metric-grid">
		{#each metricDefinitions as metric}
			{@const rows = availableMetricRows(metric)}
			{#if rows.length > 0}
				<div class="metric-card">
					<div class="metric-head">
						<div>
							<div class="metric-title">{metric.label}</div>
							<div class="metric-hint">{metric.hint}</div>
						</div>
					</div>

					<div class="metric-bars">
						{#each rows as row}
							<div class="metric-row">
								<div class="metric-row-top">
									<span class="metric-run-label">{getRunLabel(row.run, row.index)}</span>
									<span class="metric-run-value">{metric.formatValue(row.value)}</span>
								</div>
								<div class="metric-bar-track">
									<div
										class="metric-bar-fill"
										style={`width:${normalizeBarWidth(row.value, metricValues(rows))}%; background:${getRunColor(row.index)};`}
									></div>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		{/each}
	</div>
</div>

<style>
	.metrics-section {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.section-header h2 {
		margin: 0;
		font-size: 1.15rem;
		color: #0f172a;
	}

	.section-header p {
		margin: 0.25rem 0 0;
		color: #64748b;
		font-size: 0.9rem;
	}

	.metric-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
		gap: 0.9rem;
	}

	.metric-card {
		padding: 1rem;
		border-radius: 1rem;
		border: 1px solid #dbe4ee;
		background: #ffffff;
		box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
	}

	.metric-head {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 0.85rem;
	}

	.metric-title {
		font-size: 0.95rem;
		font-weight: 700;
		color: #0f172a;
	}

	.metric-hint {
		margin-top: 0.2rem;
		font-size: 0.78rem;
		color: #64748b;
	}

	.metric-bars {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.metric-row {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}

	.metric-row-top {
		display: flex;
		justify-content: space-between;
		gap: 0.75rem;
		font-size: 0.82rem;
	}

	.metric-run-label {
		color: #334155;
		font-weight: 600;
	}

	.metric-run-value {
		color: #0f172a;
		font-weight: 700;
	}

	.metric-bar-track {
		width: 100%;
		height: 0.7rem;
		border-radius: 999px;
		background: #e2e8f0;
		overflow: hidden;
	}

	.metric-bar-fill {
		height: 100%;
		border-radius: 999px;
	}

</style>
