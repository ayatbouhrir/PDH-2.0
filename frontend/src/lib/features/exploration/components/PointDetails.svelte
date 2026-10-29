<script lang="ts">
	import { X, ChevronDown } from "lucide-svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
	import { fetchPointDetails } from "$lib/features/exploration/point-details.resource.svelte";
	import { PFAS_THRESHOLDS } from "$lib/shared/pfas/pfas-concentration-quartiles";
	import VisualizationPanel from "$lib/features/visualization/components/VisualizationPanel.svelte";

	const { page = "home" } = $props<{ page?: "home" | "analyse" }>();

	let showClusterDetails = $state(false);
	let showPointInfo = $state(true);
	let showPfasValues = $state(false);

	let assignments = $state<Record<string, number>>({});

	const response = fetchPointDetails();

	// ── Tooltips for point detail view ──
	const POINT_TOOLTIPS: Record<string, string> = {
		typeDePoint: "Indique si ce point est une mesure, un site présumé, un producteur ou un utilisateur de PFAS.",
		milieuAnalyse: "Le type de milieu dans lequel l'échantillon a été prélevé (eau, sol, air, sédiment, etc.).",
		sourceDonnees: "Le jeu de données d'origine dont ce point est issu.",
		pfasSum: "Somme de toutes les concentrations PFAS détectées sur ce point.",
		pfasPrincipal: "Le PFAS ayant la concentration la plus élevée sur ce point.",
		membershipProbability:
			"Probability of membership : niveau de confiance d'appartenance du point à son cluster HDBSCAN.",
		outlierScore:
			"Outlier score : score d'atypicité du point dans HDBSCAN. Plus il est élevé, plus le point est atypique.",
	};

	const CLUSTER_TOOLTIPS: Record<string, string> = {
		centroide:
			"Point de référence du cluster. Ici, c'est le point réel le plus représentatif du cluster.",
		distanceAvg:
			"Distance moyenne entre les points du cluster et son point de référence. Plus elle est petite, plus les points se ressemblent.",
		distanceMin:
			"Point le plus proche du centre du cluster. Il ressemble le plus au profil typique du cluster.",
		distanceMax:
			"Point le plus éloigné du centre du cluster. Il est le plus atypique à l'intérieur du cluster.",
		dispersion:
			"Mesure à quel point les points du cluster sont regroupés ou étalés. Plus la dispersion est grande, plus le cluster est hétérogène.",
		clusterPersistence:
			"Cluster persistence : stabilité du cluster HDBSCAN à travers la hiérarchie. Plus elle est élevée, plus le cluster est robuste.",
		corePoints:
			"Points centraux du cluster détectés par DBSCAN. Ce sont les points qui forment le noyau du groupe.",
		borderPoints:
			"Points attachés au cluster mais moins centraux. Ils sont proches du noyau sans en faire partie pleinement.",
	};

	type PfasValueRow = {
		cas_id?: string;
		unit?: string;
		substance?: string;
		value?: number | string | null;
		[key: string]: unknown;
	};

	type PrimaryPfas = {
		substance: string;
		unit: string;
		value: number | null;
	};

	function toggleClusterDetails() {
		showClusterDetails = !showClusterDetails;
	}

	function togglePointInfo() {
		showPointInfo = !showPointInfo;
	}

	function togglePfasValues() {
		showPfasValues = !showPfasValues;
	}

	function close() {
		dataRune.selectedPoints = [];
		dataRune.selectedClusterInfo = null;
		dataRune.clusterGeometryRequest = null;
		dataRune.detailsContext = "none";
		analysisRune.selectedClusterId = null;
	}

	function isSelectedSubstance(substance: string, unit: string): boolean {
		return dataRune.filters.substances.some(
			(s) => s.name === substance && s.unit === unit,
		);
	}

	function toFiniteNumber(value: unknown): number | null {
		if (typeof value === "number") {
			return Number.isFinite(value) ? value : null;
		}

		if (typeof value === "string") {
			const parsed = Number(value);
			return Number.isFinite(parsed) ? parsed : null;
		}

		return null;
	}

	function formatCoordinate(value: unknown): string {
		const n = toFiniteNumber(value);
		return n == null ? "-" : n.toFixed(5);
	}

	function formatNumber(value: unknown, digits = 2): string {
		const n = toFiniteNumber(value);
		return n == null ? "-" : n.toFixed(digits);
	}

	function formatText(value: unknown): string {
		if (value == null) return "-";
		const text = String(value).trim();
		return text.length > 0 ? text : "-";
	}

	function parsePfasValues(value: unknown): PfasValueRow[] {
		try {
			const parsed =
				typeof value === "string"
					? JSON.parse(value)
					: value;

			return Array.isArray(parsed) ? (parsed as PfasValueRow[]) : [];
		} catch {
			return [];
		}
	}

	function getPrimaryPfas(rows: PfasValueRow[]): PrimaryPfas | null {
		if (!Array.isArray(rows) || rows.length === 0) return null;

		let best: PrimaryPfas | null = null;

		for (const row of rows) {
			const currentValue = toFiniteNumber(row.value);

			if (currentValue == null) continue;

			if (!best || currentValue > (best.value ?? -Infinity)) {
				best = {
					substance: formatText(row.substance),
					unit: formatText(row.unit),
					value: currentValue,
				};
			}
		}

		return best;
	}

	function getSelectedPointRecord(): Record<string, unknown> | null {
		if (!dataRune.selectedPoints || dataRune.selectedPoints.length !== 1) {
			return null;
		}

		return dataRune.selectedPoints[0] as unknown as Record<string, unknown>;
	}

	function getPointField(
		point: Record<string, unknown> | null,
		detail: Record<string, unknown> | null,
		keys: string[],
	): unknown {
		for (const key of keys) {
			if (point && point[key] != null && String(point[key]).trim?.() !== "") {
				return point[key];
			}
			if (detail && detail[key] != null && String(detail[key]).trim?.() !== "") {
				return detail[key];
			}
		}

		return null;
	}

	function getDatasetLabel(
		point: Record<string, unknown> | null,
		detail: Record<string, unknown> | null,
	): string {
		const datasetName = getPointField(point, detail, [
			"dataset_name",
			"datasetName",
			"dataset",
		]);

		const datasetId = getPointField(point, detail, [
			"dataset_id",
			"datasetId",
		]);

		const nameText = formatText(datasetName);
		const idText = formatText(datasetId);

		if (nameText !== "-" && idText !== "-" && nameText !== idText) {
			return `${nameText} (#${idText})`;
		}

		if (nameText !== "-") return nameText;
		if (idText !== "-") return idText;

		return "-";
	}

	function getThresholdClass(
		value: number | null | undefined,
		substance: string,
	): string {
		if (value == null) return "";

		const thresholds = PFAS_THRESHOLDS[substance];
		if (!thresholds) return "";

		if (value >= thresholds.bad) return "text-red-600 font-semibold";
		if (value >= thresholds.ok) return "text-orange-500 font-medium";
		return "text-green-600 font-medium";
	}

	function toggleClusterGeometry(
		clusterId: number,
		kind: "centroid" | "min" | "max",
	) {
		const current = dataRune.clusterGeometryRequest;
		const sameCluster = current?.clusterId === clusterId;

		const next = {
			clusterId,
			showCentroid: sameCluster ? current?.showCentroid ?? false : false,
			showMin: sameCluster ? current?.showMin ?? false : false,
			showMax: sameCluster ? current?.showMax ?? false : false,
		};

		if (kind === "centroid") next.showCentroid = !next.showCentroid;
		if (kind === "min") {
			next.showMin = !next.showMin;
			if (next.showMin) next.showCentroid = true;
		}
		if (kind === "max") {
			next.showMax = !next.showMax;
			if (next.showMax) next.showCentroid = true;
		}

		if (!next.showCentroid && !next.showMin && !next.showMax) {
			dataRune.clusterGeometryRequest = null;
			return;
		}

		dataRune.clusterGeometryRequest = next;
	}

	$effect(() => {
		const raw = sessionStorage.getItem("last-analysis-assignments");
		if (!raw) {
			assignments = {};
			return;
		}

		try {
			assignments = JSON.parse(raw);
		} catch {
			assignments = {};
		}
	});

	$effect(() => {
		const isPointContext = dataRune.detailsContext === "point";
		const isClusterContext = dataRune.detailsContext === "cluster";
		const hasCluster = !!dataRune.selectedClusterInfo;
		const hasPoint = dataRune.selectedPoints.length > 0;

		showClusterDetails = isClusterContext && hasCluster;
		showPointInfo = hasPoint;
		showPfasValues = hasPoint;
	});
</script>

<div class="details-panel">
	<div class="header">
		<h3 class="panel-title">Details</h3>
		<button onclick={close} class="close-btn" title="Fermer">
			<X class="w-5 h-5" />
		</button>
	</div>
	{#if dataRune.detailsContext === "cluster" && dataRune.selectedClusterInfo}
		{@const ci = dataRune.selectedClusterInfo}

		<div class="section">
			<button type="button" class="section-header" onclick={toggleClusterDetails}>
				<div class="section-title">Cluster Info</div>
				<ChevronDown
					class={`chevron ${!showClusterDetails ? "rotated" : ""}`}
					size={18}
				/>
			</button>

			{#if showClusterDetails}
				<div class="section-content">
					<div class="cluster-info-card">
						<div class="cluster-header">
							<span
								class="cluster-color-dot"
								style={`background: ${ci.color}`}
							></span>

							<span class="cluster-title">
								{ci.clusterId === -1
									? "Noise / Outliers"
									: `Cluster ${ci.clusterId}`}
							</span>

							<span class="cluster-algo">
								{ci.algorithm.toUpperCase()}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Algorithme</span>
							<span class="stat-value">{ci.algorithm.toUpperCase()}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Taille</span>
							<span class="stat-value">{ci.count ?? "-"}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Taille relative</span>
							<span class="stat-value">
								{ci.relativeSize != null
									? `${(ci.relativeSize * 100).toFixed(2)}%`
									: "-"}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">PFAS dominant</span>
							<span class="stat-value">{ci.dominantPfas ?? "-"}</span>
						</div>

						{#if ci.centroidLat != null && ci.centroidLon != null}
							<button
								type="button"
								class="stat-row stat-row-clickable"
								onclick={() => toggleClusterGeometry(ci.clusterId, "centroid")}
							>
								<span class="stat-label">
									Centroïde
									<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.centroide}>?</span>
								</span>
								<span class="stat-value text-xs">
									{Number(ci.centroidLat).toFixed(4)}, {Number(ci.centroidLon).toFixed(4)}
								</span>
							</button>
						{/if}

						<button
							type="button"
							class="stat-row stat-row-clickable"
							onclick={() => toggleClusterGeometry(ci.clusterId, "centroid")}
						>
							<span class="stat-label">
								Distance moy. au centre
								<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.distanceAvg}>?</span>
							</span>
							<span class="stat-value">
								{ci.distanceAvg != null ? ci.distanceAvg.toFixed(3) : "-"}
							</span>
						</button>

						<button
							type="button"
							class="stat-row stat-row-clickable"
							onclick={() => toggleClusterGeometry(ci.clusterId, "min")}
						>
							<span class="stat-label">
								Distance min au centre
								<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.distanceMin}>?</span>
							</span>
							<span class="stat-value">
								{ci.distanceMin != null ? ci.distanceMin.toFixed(3) : "-"}
							</span>
						</button>

						<button
							type="button"
							class="stat-row stat-row-clickable"
							onclick={() => toggleClusterGeometry(ci.clusterId, "max")}
						>
							<span class="stat-label">
								Distance max au centre
								<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.distanceMax}>?</span>
							</span>
							<span class="stat-value">
								{ci.distanceMax != null ? ci.distanceMax.toFixed(3) : "-"}
							</span>
						</button>

						<div class="stat-row">
							<span class="stat-label">
								Dispersion
								<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.dispersion}>?</span>
							</span>
							<span class="stat-value">
								{ci.dispersion != null ? ci.dispersion.toFixed(3) : "-"}
							</span>
						</div>

						{#if ci.algorithm?.toLowerCase() === "hdbscan"}
							<div class="stat-row">
								<span class="stat-label">
									Cluster persistence
									<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.clusterPersistence}>?</span>
								</span>
								<span class="stat-value">
									{ci.clusterPersistence != null
										? ci.clusterPersistence.toFixed(4)
										: "-"}
								</span>
							</div>
						{/if}

						{#if ci.algorithm?.toLowerCase() === "dbscan"}
							<div class="stat-row">
								<span class="stat-label">
									Core points
									<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.corePoints}>?</span>
								</span>
								<span class="stat-value">{ci.corePoints ?? "-"}</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">
									Border points
									<span class="tooltip-icon" title={CLUSTER_TOOLTIPS.borderPoints}>?</span>
								</span>
								<span class="stat-value">{ci.borderPoints ?? "-"}</span>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	{/if}

	{#if dataRune.selectedPoints.length === 1}
		{@const point = getSelectedPointRecord()}
		{@const d =
			response.details.length > 0
				? (response.details[0] as unknown as Record<string, unknown>)
				: null}
		{@const pointPfasSource =
			d?.pfas_values ?? point?.pfas_values ?? []}
		{@const pfasValues = parsePfasValues(pointPfasSource)}
		{@const primaryPfas = getPrimaryPfas(pfasValues)}
		{@const datasetLabel = getDatasetLabel(point, d)}
		{@const allKeys = Array.from(
			new Set(pfasValues.flatMap((obj) => Object.keys(obj))),
		)}

		<div class="section">
			<button type="button" class="section-header" onclick={togglePointInfo}>
				<div class="section-title">Point</div>
				<ChevronDown
					class={`chevron ${!showPointInfo ? "rotated" : ""}`}
					size={18}
				/>
			</button>

			{#if showPointInfo}
				<div class="section-content">
					<div class="cluster-info-card">
						<div class="stat-row">
							<span class="stat-label">Coordonnées</span>
							<span class="stat-value">
								{formatCoordinate(getPointField(point, d, ["lat"]))},
								{formatCoordinate(getPointField(point, d, ["lon"]))}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Année</span>
							<span class="stat-value">
								{formatText(getPointField(point, d, ["year"]))}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">
								Type de point
								<span class="tooltip-icon" title={POINT_TOOLTIPS.typeDePoint}>?</span>
							</span>
							<span class="stat-value">
								{formatText(getPointField(point, d, ["category"]))}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">
								Milieu analysé
								<span class="tooltip-icon" title={POINT_TOOLTIPS.milieuAnalyse}>?</span>
							</span>
							<span class="stat-value">
								{formatText(getPointField(point, d, ["matrix"]))}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">
								Source des données
								<span class="tooltip-icon" title={POINT_TOOLTIPS.sourceDonnees}>?</span>
							</span>
							<span class="stat-value">{datasetLabel}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">
								Somme PFAS
								<span class="tooltip-icon" title={POINT_TOOLTIPS.pfasSum}>?</span>
							</span>
							<span class="stat-value">
								{formatNumber(getPointField(point, d, ["pfas_sum"]), 3)}
							</span>
						</div>

						{#if getPointField(point, d, ["membershipProbability"]) != null}
							<div class="stat-row">
								<span class="stat-label">
									Probability of membership
									<span class="tooltip-icon" title={POINT_TOOLTIPS.membershipProbability}>?</span>
								</span>
								<span class="stat-value">
									{formatNumber(getPointField(point, d, ["membershipProbability"]), 4)}
								</span>
							</div>
						{/if}

						{#if getPointField(point, d, ["outlierScore"]) != null}
							<div class="stat-row">
								<span class="stat-label">
									Outlier score
									<span class="tooltip-icon" title={POINT_TOOLTIPS.outlierScore}>?</span>
								</span>
								<span class="stat-value">
									{formatNumber(getPointField(point, d, ["outlierScore"]), 4)}
								</span>
							</div>
						{/if}

						<div class="stat-row">
							<span class="stat-label">
								PFAS principal
								<span class="tooltip-icon" title={POINT_TOOLTIPS.pfasPrincipal}>?</span>
							</span>
							<span class="stat-value">
								{primaryPfas ? primaryPfas.substance : "-"}
							</span>
						</div>

						{#if primaryPfas && primaryPfas.value != null}
							<div class="stat-row">
								<span class="stat-label">Valeur principale</span>
								<span class="stat-value">
									{primaryPfas.value.toFixed(3)} {primaryPfas.unit !== "-" ? primaryPfas.unit : ""}
								</span>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>

		{#if response.loading}
			<p class="text-sm text-muted-foreground">Loading...</p>
		{:else if response.error}
			<p class="text-sm text-destructive">{response.error}</p>
		{:else if pfasValues.length > 0}
			<div class="section">
				<button
					type="button"
					class="section-header"
					onclick={togglePfasValues}
				>
					<div class="section-title">PFAS values</div>
					<ChevronDown
						class={`chevron ${!showPfasValues ? "rotated" : ""}`}
						size={18}
					/>
				</button>

				{#if showPfasValues}
					<div class="section-content info">
						<div class="table-wrapper">
							<table class="w-full text-sm border border-border rounded-md">
								<thead class="bg-muted">
									<tr class="border-b border-border">
										{#each allKeys as k}
											<th class="text-left p-2 font-semibold">{k}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each pfasValues as item, i (`${item.cas_id ?? "null"}-${i}`)}
										<tr
											class={`border-t border-border ${
												isSelectedSubstance(
													String(item.substance ?? ""),
													String(item.unit ?? ""),
												)
													? "bg-muted/80"
													: ""
											}`}
										>
											{#each allKeys as k}
												<td class="p-2">
													{#if k === "value"}
														{@const val = toFiniteNumber(item[k])}
														{@const substanceName = String(item.substance ?? "")}
														{@const s = PFAS_THRESHOLDS[substanceName]}
														<span
															class={
																!s || val == null
																	? ""
																	: val >= s.bad
																		? "text-red-600 font-semibold"
																		: val >= s.ok
																			? "text-orange-500 font-medium"
																			: "text-green-600 font-medium"
															}
														>
															{val == null ? "-" : val}
														</span>
													{:else}
														{item[k] ?? "null"}
													{/if}
												</td>
											{/each}
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</div>
				{/if}
			</div>
		{:else}
			<p class="text-sm text-muted-foreground">No data available.</p>
		{/if}
	{:else if dataRune.selectedPoints.length > 1}
		{#if response.loading}
			<p class="text-sm text-muted-foreground">Loading...</p>
		{:else if response.error}
			<p class="text-sm text-destructive">{response.error}</p>
		{:else if response.details.length === 0}
			<p class="text-sm text-muted-foreground">No data available.</p>
		{:else}
			<div class="section">
				<button
					type="button"
					class="section-header"
					onclick={togglePfasValues}
				>
					<div class="section-title">PFAS values</div>
					<ChevronDown
						class={`chevron ${!showPfasValues ? "rotated" : ""}`}
						size={18}
					/>
				</button>

				{#if showPfasValues}
					<div class="section-content info">
						<p class="text-sm text-muted-foreground mb-3">
							{dataRune.selectedPoints.length} points
						</p>

						<div class="table-wrapper">
							<table class="w-full text-sm border border-border rounded-md">
								<thead class="bg-muted">
									<tr class="border-b border-border">
										<th class="p-2 text-left">Substance</th>
										<th class="p-2 text-left">Unit</th>
										<th class="p-2 text-right">Detections</th>
										<th class="p-2 text-right">Mean</th>
										<th class="p-2 text-right">Min</th>
										<th class="p-2 text-right">Q1</th>
										<th class="p-2 text-right">Median</th>
										<th class="p-2 text-right">Q3</th>
										<th class="p-2 text-right">Max</th>
									</tr>
								</thead>
								<tbody>
									{#each response.details as stat}
										<tr
											class={`border-t border-border ${
												isSelectedSubstance(
													String(stat.substance ?? ""),
													String(stat.unit ?? ""),
												)
													? "bg-muted/80"
													: ""
											}`}
										>
											<td class="p-2 max-w-[150px] break-words">
												{stat.substance}
											</td>

											<td class="p-2">{stat.unit}</td>

											<td class="p-2 text-right">
												{stat.detected}/{stat.count}
											</td>

											<td class="p-2 text-right">
												<span
													class={getThresholdClass(
														toFiniteNumber(stat.detected_mean),
														String(stat.substance ?? ""),
													)}
												>
													{toFiniteNumber(stat.detected_mean)?.toFixed(2) ?? "-"}
												</span>
											</td>

											<td class="p-2 text-right">
												<span
													class={getThresholdClass(
														toFiniteNumber(stat.min_value),
														String(stat.substance ?? ""),
													)}
												>
													{toFiniteNumber(stat.min_value)?.toFixed(2) ?? "-"}
												</span>
											</td>

											<td class="p-2 text-right">
												<span
													class={getThresholdClass(
														toFiniteNumber(stat.q1),
														String(stat.substance ?? ""),
													)}
												>
													{toFiniteNumber(stat.q1)?.toFixed(2) ?? "-"}
												</span>
											</td>

											<td class="p-2 text-right">
												<span
													class={getThresholdClass(
														toFiniteNumber(stat.median),
														String(stat.substance ?? ""),
													)}
												>
													{toFiniteNumber(stat.median)?.toFixed(2) ?? "-"}
												</span>
											</td>

											<td class="p-2 text-right">
												<span
													class={getThresholdClass(
														toFiniteNumber(stat.q3),
														String(stat.substance ?? ""),
													)}
												>
													{toFiniteNumber(stat.q3)?.toFixed(2) ?? "-"}
												</span>
											</td>

											<td class="p-2 text-right">
												<span
													class={getThresholdClass(
														toFiniteNumber(stat.max_value),
														String(stat.substance ?? ""),
													)}
												>
													{toFiniteNumber(stat.max_value)?.toFixed(2) ?? "-"}
												</span>
											</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</div>
				{/if}
			</div>
		{/if}
	{/if}

	{#if page === "analyse" && dataRune.detailsContext === "cluster" && dataRune.selectedClusterInfo}
		<VisualizationPanel {assignments} />
	{/if}
</div>

<style>
	.details-panel {
		padding: 1rem;
		height: 100%;
		background: var(--color-background);
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		overflow-x: hidden;
		min-height: 0;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
		flex-shrink: 0;
	}

	.panel-title {
		font-size: 1.125rem;
		font-weight: 700;
	}

	.close-btn {
		all: unset;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.section {
		margin-bottom: 1rem;
		flex-shrink: 0;
		min-height: 0;
	}

	.section-header {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		background: transparent;
		border: none;
		padding: 0;
		margin-bottom: 0.75rem;
		cursor: pointer;
		text-align: left;
	}

	.section-title {
		font-size: 1rem;
		font-weight: 700;
		color: #111827;
	}

	.chevron {
		transition: transform 0.2s ease;
		color: #6b7280;
		flex-shrink: 0;
	}

	.chevron.rotated {
		transform: rotate(-90deg);
	}

	.section-content {
		overflow: hidden;
	}

	.info {
		overflow-y: visible;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.cluster-info-card {
		background: #f8fafc;
		border: 1px solid #e2e8f0;
		border-radius: 0.75rem;
		padding: 0.9rem;
	}

	.cluster-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.cluster-color-dot {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.cluster-title {
		font-weight: 700;
		font-size: 0.95rem;
	}

	.cluster-algo {
		margin-left: auto;
		font-size: 0.7rem;
		font-weight: 600;
		padding: 0.15rem 0.45rem;
		border-radius: 0.35rem;
		background: #e2e8f0;
		color: #475569;
	}

	.cluster-stats {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.stat-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.85rem;
		padding: 0.2rem 0;
		border-bottom: 1px solid #e5e7eb;
	}

	.stat-row:last-child {
		border-bottom: none;
	}

	.stat-label {
		color: #64748b;
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}

	.stat-value {
		font-weight: 600;
		text-align: right;
		word-break: break-word;
		max-width: 55%;
	}

	.table-wrapper {
		border-radius: 0.5rem;
		overflow: auto;
		border: 1px solid var(--color-border, #e5e7eb);
		background: white;
	}

	.stat-row-clickable {
		width: 100%;
		border: none;
		background: transparent;
		cursor: pointer;
		padding: 0.2rem 0;
		border-bottom: 1px solid #e5e7eb;
	}

	.stat-row-clickable:hover {
		background: #f1f5f9;
		border-radius: 0.35rem;
	}

	.tooltip-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 15px;
		height: 15px;
		border-radius: 50%;
		background: #e2e8f0;
		color: #64748b;
		font-size: 0.65rem;
		font-weight: 700;
		cursor: help;
		flex-shrink: 0;
	}
</style>
