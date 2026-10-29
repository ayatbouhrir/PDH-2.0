<script lang="ts">
	import { X, ChevronDown } from "lucide-svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
	import { fetchPointDetails } from "$lib/features/exploration/point-details.resource.svelte";
	import { PFAS_THRESHOLDS } from "$lib/shared/pfas/pfas-concentration-quartiles";
	import VisualizationPanel from "$lib/features/visualization/components/VisualizationPanel.svelte";
	import ShapPanel from "$lib/features/explanations/components/ShapPanel.svelte";
	import ClampPanel from "$lib/features/explanations/components/ClampPanel.svelte";
	import { fetchBubbleContext } from "$lib/features/geography/bubble-context.resource.svelte";
	import { fetchLocalPopulation } from "$lib/features/geography/local-population.resource.svelte";
	import {
		PFAS_SITE_CATEGORY_META,
		normalizePfasSiteCategory,
	} from "$lib/shared/types/pfas";

	const localPopulation = fetchLocalPopulation();
	
	type AnyRecord = Record<string, unknown>;

	type PfasValueRow = {
		substance?: string;
		unit?: string;
		value?: number | string | null;
		cas_id?: string | number | null;
		[key: string]: unknown;
	};

	type AggregatePointStat = {
		substance?: string;
		unit?: string;
		detected?: number;
		count?: number;
		detected_mean?: number;
		min_value?: number;
		q1?: number;
		median?: number;
		q3?: number;
		max_value?: number;
		[key: string]: unknown;
	};

	let showDetails = $state(true);
	let showPfasValues = $state(true);
	let explanationMethod = $state<"shap" | "clamp">("shap");

	let assignments = $state<Record<string, number>>({});

	const response = fetchPointDetails();
	const bubbleContext = fetchBubbleContext();
	const MAX_VISIBLE_ENTITIES = 10;

	type BubbleEntity = {
		name?: string;
	};

	function getVisibleEntityNames(items: BubbleEntity[] | undefined): string[] {
		return (items ?? [])
			.map((item) => String(item?.name ?? "").trim())
			.filter(Boolean)
			.slice(0, MAX_VISIBLE_ENTITIES);
	}

	function getRemainingCount(total: number | undefined, shown: number): number {
		return Math.max(0, (total ?? 0) - shown);
	}	

	const CLUSTER_TOOLTIPS = {
	centroid: "Centroïde : centre moyen du cluster.",
	distanceAvg: "Distance moy. au centre : distance moyenne des points au centre.",
	distanceMin: "Distance min au centre : point le plus proche du centre.",
	distanceMax: "Distance max au centre : point le plus éloigné du centre.",
	dispersion: "Dispersion : niveau d’étalement du cluster.",
	clusterPersistence:
		"Cluster persistence : stabilité du cluster HDBSCAN à travers la hiérarchie. Plus elle est élevée, plus le cluster est robuste.",
	dominantPfas: "PFAS dominant : PFAS moyen le plus représentatif du cluster.",
	corePoints: "Core points : points au cœur dense du cluster.",
	borderPoints: "Border points : points à la frontière du cluster."
};

const GLOBAL_TOOLTIPS = {
	pointsBruit: "Points bruit : points non rattachés à un cluster dense.",
	ratioBruit: "Ratio bruit : part des points classés comme bruit.",
	silhouette: "Silhouette Score : qualité de séparation des clusters, plus grand = meilleur.",
	daviesBouldin: "Davies-Bouldin : chevauchement entre clusters, plus petit = meilleur.",
	calinskiHarabasz: "Calinski-Harabasz : qualité globale du clustering, plus grand = meilleur.",
	wcss: "WCSS / Inertia : compacité interne, plus petit = plus compact.",
	relativeValidity:
		"Relative validity : approximation du DBCV pour HDBSCAN. Plus grand = meilleure structure de densité.",
	clusterPersistence:
		"Cluster persistence moyenne : stabilité moyenne des clusters HDBSCAN. Plus grand = clusters plus robustes.",
	inertia: "Somme des distances internes au cluster, plus petit = plus compact."
};

const POINT_TOOLTIPS = {
	typeDePoint: "Type de point : nature du point observé.",
	milieuAnalyse: "Milieu analysé : support mesuré (eau, sol, air, etc.).",
	sourceDonnees: "Source des données : origine de l’information.",
	pfasSum: "PFAS sum : somme totale des concentrations PFAS.",
	pfasPrincipal: "PFAS principal du point : PFAS le plus concentré sur ce point."
};

let openTooltip = $state<string | null>(null);

function toggleTooltip(key: string) {
	openTooltip = openTooltip === key ? null : key;
}



	function close() {
		dataRune.detailsContext = "none";
		dataRune.selectedPoints = [];
		dataRune.selectedBubblePointIds = [];
		dataRune.selectedClusterInfo = null;
		dataRune.clusterGeometryRequest = null;
	}

	function isSelectedSubstance(substance: string, unit: string): boolean {
		return dataRune.filters.substances.some(
			(s) => s.name === substance && s.unit === unit,
		);
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

		if (kind === "centroid") {
			next.showCentroid = !next.showCentroid;
		}

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

	function fmtNumber(
		value: number | null | undefined,
		digits = 2,
	): string {
		if (value == null || Number.isNaN(value)) return "-";
		return Number(value).toLocaleString("fr-FR", {
			minimumFractionDigits: digits,
			maximumFractionDigits: digits,
		});
	}

	function fmtInt(value: number | null | undefined): string {
		if (value == null || Number.isNaN(value)) return "-";
		return Math.round(Number(value)).toLocaleString("fr-FR");
	}

	function fmtPct(value: number | null | undefined, digits = 2): string {
		if (value == null || Number.isNaN(value)) return "-";
		return `${(Number(value) * 100).toFixed(digits)}%`;
	}

	function formatText(value: unknown): string {
		if (value == null) return "-";
		const text = String(value).trim();
		return text.length > 0 ? text : "-";
	}

	function formatCoordinate(value: unknown, digits = 5): string {
		if (value == null || value === "") return "-";
		const numeric = Number(value);
		return Number.isFinite(numeric) ? fmtNumber(numeric, digits) : "-";
	}

	function toRecord(value: unknown): AnyRecord | null {
		if (!value || typeof value !== "object" || Array.isArray(value)) {
			return null;
		}

		return value as AnyRecord;
	}

	function parseDetailsRecord(value: unknown): AnyRecord | null {
		if (typeof value !== "string" || value.trim() === "") return null;

		try {
			return toRecord(JSON.parse(value));
		} catch {
			return null;
		}
	}

	function getFieldFromSources(
		sources: Array<AnyRecord | null | undefined>,
		keys: string[],
	): unknown {
		for (const source of sources) {
			if (!source) continue;

			for (const key of keys) {
				const value = source[key];
				if (value != null && String(value).trim() !== "") {
					return value;
				}
			}
		}

		return null;
	}

	function getSiteDatasetLabel(site: AnyRecord | null, detailsRecord: AnyRecord | null): string {
		const datasetName = getFieldFromSources([site, detailsRecord], [
			"dataset_name",
			"datasetName",
			"dataset",
		]);
		const datasetId = getFieldFromSources([site, detailsRecord], [
			"dataset_id",
			"datasetId",
		]);

		const nameText = formatText(datasetName);
		const idText = formatText(datasetId);

		if (nameText !== "-" && idText !== "-" && nameText !== idText) {
			return `${nameText} (#${idText})`;
		}

		return nameText !== "-" ? nameText : idText;
	}

	function normalizeExternalUrl(value: unknown): string | null {
		if (value == null) return null;

		const text = String(value).trim();
		if (text.length === 0) return null;

		if (/^https?:\/\//iu.test(text)) {
			return text;
		}

		if (/^www\./iu.test(text)) {
			return `https://${text}`;
		}

		return null;
	}

	function getSourceLinkLabel(url: string): string {
		try {
			const { hostname } = new URL(url);
			return hostname || "Ouvrir la source";
		} catch {
			return "Ouvrir la source";
		}
	}

	function getSiteSourceInfo(site: AnyRecord | null, detailsRecord: AnyRecord | null) {
		const rawSourceText = getFieldFromSources([site, detailsRecord], [
			"source_text",
			"sourceText",
			"source",
			"source_name",
			"sourceName",
		]);
		const rawSourceUrl = getFieldFromSources([site, detailsRecord], [
			"source_url",
			"sourceUrl",
			"url",
			"link",
			"url_fiche",
		]);
		const sourceType = formatText(
			getFieldFromSources([site, detailsRecord], [
				"source_type",
				"sourceType",
				"data_collection_method",
				"dataCollectionMethod",
			]),
		);

		const sourceUrl =
			normalizeExternalUrl(rawSourceUrl) ?? normalizeExternalUrl(rawSourceText);
		const sourceText = formatText(rawSourceText);
		const sourceParts = [sourceText, sourceType].filter(
			(value, index, all) =>
				value !== "-" &&
				!normalizeExternalUrl(value) &&
				all.indexOf(value) === index,
		);

		return {
			label: sourceParts.length > 0 ? sourceParts.join(" · ") : "-",
			url: sourceUrl,
			linkLabel: sourceUrl ? getSourceLinkLabel(sourceUrl) : null,
		};
	}

	function isSelectedSinglePfasSite() {
		if (dataRune.selectedPoints.length !== 1) return false;
		return normalizePfasSiteCategory(dataRune.selectedPoints[0]?.category) !== null;
	}

	function getClusterSummary(clusterId: number | null | undefined) {
		if (clusterId == null) return null;
		return (
			analysisRune.clusterSummaries.find((s) => s.clusterId === clusterId) ?? null
		);
	}

	function getPointClusterId(pointId: string | number | null | undefined) {
		if (pointId == null) return null;
		const raw = assignments[String(pointId)];
		return Number.isFinite(raw) ? Number(raw) : null;
	}

	function parsePfasValues(value: unknown): PfasValueRow[] {
		try {
			const parsed = typeof value === "string" ? JSON.parse(value) : value;
			return Array.isArray(parsed) ? (parsed as PfasValueRow[]) : [];
		} catch {
			return [];
		}
	}

	function getPrimaryPfasFromValues(
		pfasValues: PfasValueRow[],
	): { substance: string; value: number; unit: string } | null {
		if (!Array.isArray(pfasValues) || pfasValues.length === 0) return null;

		let best: { substance: string; value: number; unit: string } | null = null;

		for (const row of pfasValues) {
			const val =
				typeof row.value === "number" ? row.value : Number(row.value);

			if (!Number.isFinite(val)) continue;

			if (!best || val > best.value) {
				best = {
					substance: row.substance ?? "-",
					value: val,
					unit: row.unit ?? "",
				};
			}
		}

		return best;
	}

	function getPfasKeys(rows: PfasValueRow[]): string[] {
		return Array.from(
			new Set(
				rows.flatMap((row) =>
					row && typeof row === "object" ? Object.keys(row) : [],
				),
			),
		);
	}

	$effect(() => {
		if (typeof sessionStorage === "undefined") {
			assignments = {};
			return;
		}

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
		const cluster = dataRune.selectedClusterInfo;
		const pointsCount = dataRune.selectedPoints.length;
		const context = dataRune.detailsContext;

		if (cluster || pointsCount > 0 || context === "all") {
			showDetails = true;
			showPfasValues = true;
		}
	});


	function formatPopulationError(error: string | null | undefined): string {
	if (!error) return "Population locale indisponible.";

	try {
		const parsed = JSON.parse(error);

		if (typeof parsed?.message === "string" && parsed.message.trim()) {
			return parsed.message;
		}

		if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
			return parsed.detail;
		}
	} catch {
		// pas du JSON, on garde le texte brut
	}

	return error;
}

	function buildExplainableFilters() {
		const filtersSnapshot = $state.snapshot(dataRune.filters);
		const { nutsRegions: _nutsRegions, ...apiFilters } =
			filtersSnapshot as typeof filtersSnapshot & { nutsRegions?: unknown };

		return apiFilters;
	}



</script>

{#snippet ExplainableAnalysisSection()}
	<div class="xai-panel">
		<div class="xai-header">
			<h4 class="xai-title">Analyse explicable</h4>
			<p class="xai-subtitle">
				Choisissez une méthode pour interpréter les clusters obtenus.
			</p>
		</div>

		<div class="xai-methods">
			<span class="xai-label">Méthode d’explication :</span>
			<div class="xai-toggle">
				<button
					type="button"
					class:xai-toggle-active={explanationMethod === "shap"}
					class="xai-toggle-button"
					onclick={() => {
						explanationMethod = "shap";
						analysisRune.isClampMapMode = false;
						analysisRune.clampDisplayMode = "points";
					}}
				>
					SHAP — importance des PFAS
				</button>
				<button
					type="button"
					class:xai-toggle-active={explanationMethod === "clamp"}
					class="xai-toggle-button"
					onclick={() => (explanationMethod = "clamp")}
				>
					ClAMP — règles explicables
				</button>
			</div>
		</div>

		{#if explanationMethod === "shap"}
			<ShapPanel {assignments} />
		{:else}
			<ClampPanel
				{assignments}
				filters={buildExplainableFilters()}
				selectedModelPfas={analysisRune.selectedModelPfas}
			/>
		{/if}
	</div>
{/snippet}

<div class="details-panel">
	<div class="header">
		<h3 class="panel-title">
			{#if dataRune.detailsContext === "point"}
				{isSelectedSinglePfasSite() ? "Détails du site PFAS" : "Détails du point"}
			{:else if dataRune.detailsContext === "cluster"}
				Détails du cluster
			{:else if dataRune.detailsContext === "all"}
				Vue globale
			{/if}
		</h3>

		<button onclick={close} class="close-btn" title="Fermer">
			<X class="w-5 h-5" />
		</button>
	</div>

	{#if dataRune.detailsContext === "point"}
	{#if dataRune.selectedPoints.length === 1}
		{@const selectedSiteCategory = normalizePfasSiteCategory(
			dataRune.selectedPoints[0]?.category,
		)}

		{#if selectedSiteCategory}
			{@const rawSite = (response.details[0] as AnyRecord) ?? (dataRune.selectedPoints[0] as unknown as AnyRecord)}
			{@const detailsRecord = parseDetailsRecord(rawSite?.details)}
			{@const siteName = formatText(
				getFieldFromSources([rawSite, detailsRecord], ["name", "site_name", "siteName"]),
			)}
			{@const siteCategoryLabel = PFAS_SITE_CATEGORY_META[selectedSiteCategory].label}
			{@const siteType = formatText(
				getFieldFromSources([rawSite, detailsRecord], ["type", "site_type", "siteType"]),
			)}
			{@const siteCity = formatText(
				getFieldFromSources([rawSite, detailsRecord], ["city", "town", "municipality"]),
			)}
			{@const siteCountry = formatText(
				getFieldFromSources([rawSite, detailsRecord], ["country", "country_name", "countryName"]),
			)}
			{@const siteSector = formatText(
				getFieldFromSources([rawSite, detailsRecord], [
					"sector",
					"activity",
					"activite",
					"industry",
				]),
			)}
			{@const siteStatus = formatText(
				getFieldFromSources([rawSite, detailsRecord], ["status", "statut"]),
			)}
			{@const siteDataset = getSiteDatasetLabel(rawSite, detailsRecord)}
			{@const siteSource = getSiteSourceInfo(rawSite, detailsRecord)}

			<div class="section">
				<div class="section-title">Informations du site PFAS</div>

				<div class="section-content">
					<div class="cluster-info-card">
						<div class="stat-row">
							<span class="stat-label">Nom</span>
							<span class="stat-value">{siteName}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Catégorie</span>
							<span class="stat-value">{siteCategoryLabel}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Type</span>
							<span class="stat-value">{siteType}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Ville</span>
							<span class="stat-value">{siteCity}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Pays</span>
							<span class="stat-value">{siteCountry}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Coordonnées</span>
							<span class="stat-value">
								{formatCoordinate(
									getFieldFromSources([rawSite, detailsRecord], ["lat"]),
								)},
								{formatCoordinate(
									getFieldFromSources([rawSite, detailsRecord], ["lon"]),
								)}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Secteur</span>
							<span class="stat-value">{siteSector}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Statut</span>
							<span class="stat-value">{siteStatus}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Jeu de données</span>
							<span class="stat-value">{siteDataset}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Source</span>
							<span class="stat-value stat-value-stack">
								{#if siteSource.url}
									{#if siteSource.label !== "-"}
										<span>{siteSource.label}</span>
									{/if}
									<a
										class="stat-value-link"
										href={siteSource.url}
										target="_blank"
										rel="noreferrer noopener"
										title={siteSource.url}
									>
										{siteSource.linkLabel}
									</a>
								{:else}
									{siteSource.label}
								{/if}
							</span>
						</div>
					</div>
				</div>
			</div>

			{#if response.loading}
				<p class="text-sm text-muted-foreground">Chargement du détail complet...</p>
			{:else if response.error && response.details.length === 0}
				<p class="text-sm text-destructive">{response.error}</p>
			{/if}
		{:else if response.loading}
			<p class="text-sm text-muted-foreground">Chargement...</p>
		{:else if response.error}
			<p class="text-sm text-destructive">{response.error}</p>
		{:else if response.details.length === 0}
			<p class="text-sm text-muted-foreground">Aucune donnée disponible.</p>
		{:else}
			{@const d = response.details[0] as AnyRecord}
			{@const pointId = d.point_id ?? d.id ?? dataRune.selectedPoints[0]?.id}
			{@const pointClusterId = getPointClusterId(pointId as string | number | null)}
			{@const pointCluster = getClusterSummary(pointClusterId)}
			{@const pfasValues = parsePfasValues(d.pfas_values)}
			{@const primaryPfas = getPrimaryPfasFromValues(pfasValues)}
			{@const allKeys = getPfasKeys(pfasValues)}

			<div class="section">
				<button
					type="button"
					class="section-header"
					onclick={() => (showDetails = !showDetails)}
				>
					<div class="section-title">Informations du point</div>
					<ChevronDown
						class={`chevron ${!showDetails ? "rotated" : ""}`}
						size={18}
					/>
				</button>

				{#if showDetails}
					<div class="section-content">
						<div class="cluster-info-card">
							<div class="stat-row">
								<span class="stat-label">Point ID</span>
								<span class="stat-value">{pointId ?? "-"}</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">Algorithme</span>
								<span class="stat-value">{analysisRune.algorithm.toUpperCase()}</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">Cluster</span>
								<span class="stat-value">
									{#if pointClusterId == null}
										-
									{:else if pointClusterId === -1}
										Bruit / Noise
									{:else}
										C{pointClusterId}
									{/if}
								</span>
							</div>

							{#if pointCluster}
								<div class="stat-row">
									<span class="stat-label">Taille du cluster</span>
									<span class="stat-value">{fmtInt(pointCluster.count)}</span>
								</div>

								<div class="stat-row">
									<div class="stat-label-with-tooltip">
										<span class="stat-label">PFAS dominant du cluster</span>

										<div class="tooltip-wrap">
											<button
												type="button"
												class="tooltip-icon"
												onclick={() => toggleTooltip("clusterDominantPfas")}
												aria-label="Informations PFAS dominant du cluster"
											>
												?
											</button>

											{#if openTooltip === "clusterDominantPfas"}
												<div class="tooltip-card">
													{CLUSTER_TOOLTIPS.dominantPfas}
												</div>
											{/if}
										</div>
									</div>

									<span class="stat-value">{pointCluster.dominantPfas ?? "-"}</span>
								</div>
							{/if}

							<div class="stat-row">
								<span class="stat-label">Latitude</span>
								<span class="stat-value">
									{d.lat != null ? fmtNumber(Number(d.lat), 4) : "-"}
								</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">Longitude</span>
								<span class="stat-value">
									{d.lon != null ? fmtNumber(Number(d.lon), 4) : "-"}
								</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">Année</span>
								<span class="stat-value">{formatText(d.year)}</span>
							</div>

							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">Type de point</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("pointType")}
											aria-label="Informations type de point"
										>
											?
										</button>

										{#if openTooltip === "pointType"}
											<div class="tooltip-card">
												{POINT_TOOLTIPS.typeDePoint}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">{formatText(d.category)}</span>
							</div>

							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">Milieu analysé</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("matrix")}
											aria-label="Informations milieu analysé"
										>
											?
										</button>

										{#if openTooltip === "matrix"}
											<div class="tooltip-card">
												{POINT_TOOLTIPS.milieuAnalyse}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">{formatText(d.matrix)}</span>
							</div>

							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">Source des données</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("dataset")}
											aria-label="Informations source des données"
										>
											?
										</button>

										{#if openTooltip === "dataset"}
											<div class="tooltip-card">
												{POINT_TOOLTIPS.sourceDonnees}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">
									{d.dataset_name ?? d.dataset_id ?? "-"}
								</span>
							</div>

							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">PFAS sum</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("pfasSum")}
											aria-label="Informations PFAS sum"
										>
											?
										</button>

										{#if openTooltip === "pfasSum"}
											<div class="tooltip-card">
												{POINT_TOOLTIPS.pfasSum}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">
									{d.pfas_sum != null ? fmtNumber(Number(d.pfas_sum), 2) : "-"}
								</span>
							</div>

							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">PFAS principal du point</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("pointDominantPfas")}
											aria-label="Informations PFAS principal du point"
										>
											?
										</button>

										{#if openTooltip === "pointDominantPfas"}
											<div class="tooltip-card">
												{POINT_TOOLTIPS.pfasPrincipal}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">
									{#if primaryPfas}
										{primaryPfas.substance} ({fmtNumber(primaryPfas.value, 3)} {primaryPfas.unit})
									{:else}
										-
									{/if}
								</span>
							</div>
						</div>
					</div>
				{/if}
			</div>

			{#if pfasValues.length > 0}
				<div class="section">
					<button
						type="button"
						class="section-header"
						onclick={() => (showPfasValues = !showPfasValues)}
					>
						<div class="section-title">Valeurs PFAS</div>
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
											<tr class={`border-t border-border ${isSelectedSubstance(String(item.substance ?? ""), String(item.unit ?? "")) ? "bg-muted/80" : ""}`}>
												{#each allKeys as k}
													<td class="p-2">
														{#if k === "value"}
															{@const val = Number(item[k])}
															{@const substanceName = String(item.substance ?? "")}
															<span class={getThresholdClass(Number.isFinite(val) ? val : null, substanceName)}>
																{Number.isFinite(val) ? fmtNumber(val, 3) : "-"}
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
			{/if}
		{/if}

	{:else if dataRune.selectedPoints.length > 1}
		{#if response.loading}
			<p class="text-sm text-muted-foreground">Chargement...</p>
		{:else if response.error}
			<p class="text-sm text-destructive">{response.error}</p>
		{:else if response.details.length === 0}
			<p class="text-sm text-muted-foreground">Aucune donnée disponible.</p>
		{:else}
			<div class="section">
				<button
					type="button"
					class="section-header"
					onclick={() => (showPfasValues = !showPfasValues)}
				>
					<div class="section-title">Valeurs PFAS</div>
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
										<th class="p-2 text-left">Unité</th>
										<th class="p-2 text-right">Détections</th>
										<th class="p-2 text-right">Moyenne</th>
										<th class="p-2 text-right">Min</th>
										<th class="p-2 text-right">Q1</th>
										<th class="p-2 text-right">Médiane</th>
										<th class="p-2 text-right">Q3</th>
										<th class="p-2 text-right">Max</th>
									</tr>
								</thead>

								<tbody>
									{#each response.details as rawStat}
										{@const stat = rawStat as AggregatePointStat}
										<tr class={`border-t border-border ${isSelectedSubstance(String(stat.substance ?? ""), String(stat.unit ?? "")) ? "bg-muted/80" : ""}`}>
											<td class="p-2 max-w-[150px] break-words">{stat.substance ?? "-"}</td>
											<td class="p-2">{stat.unit ?? "-"}</td>
											<td class="p-2 text-right">{stat.detected ?? "-"} / {stat.count ?? "-"}</td>
											<td class="p-2 text-right">
												<span class={getThresholdClass(stat.detected_mean ?? null, String(stat.substance ?? ""))}>
													{stat.detected_mean != null ? stat.detected_mean.toFixed(2) : "-"}
												</span>
											</td>
											<td class="p-2 text-right">
												<span class={getThresholdClass(stat.min_value ?? null, String(stat.substance ?? ""))}>
													{stat.min_value != null ? stat.min_value.toFixed(2) : "-"}
												</span>
											</td>
											<td class="p-2 text-right">
												<span class={getThresholdClass(stat.q1 ?? null, String(stat.substance ?? ""))}>
													{stat.q1 != null ? stat.q1.toFixed(2) : "-"}
												</span>
											</td>
											<td class="p-2 text-right">
												<span class={getThresholdClass(stat.median ?? null, String(stat.substance ?? ""))}>
													{stat.median != null ? stat.median.toFixed(2) : "-"}
												</span>
											</td>
											<td class="p-2 text-right">
												<span class={getThresholdClass(stat.q3 ?? null, String(stat.substance ?? ""))}>
													{stat.q3 != null ? stat.q3.toFixed(2) : "-"}
												</span>
											</td>
											<td class="p-2 text-right">
												<span class={getThresholdClass(stat.max_value ?? null, String(stat.substance ?? ""))}>
													{stat.max_value != null ? stat.max_value.toFixed(2) : "-"}
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
	{:else}
		<p class="text-sm text-muted-foreground">Aucun point sélectionné.</p>
	{/if}

{:else if dataRune.detailsContext === "cluster"}
	{#if dataRune.selectedClusterInfo}
		{@const ci = dataRune.selectedClusterInfo}

		<div class="section">
			<button
				type="button"
				class="section-header"
				onclick={() => (showDetails = !showDetails)}
			>
				<div class="section-title">Cluster Info</div>
				<ChevronDown
					class={`chevron ${!showDetails ? "rotated" : ""}`}
					size={18}
				/>
			</button>

			{#if showDetails}
				<div class="section-content">
					<div class="cluster-info-card">
						<div class="cluster-header">
							<span class="cluster-color-dot" style={`background: ${ci.color}`}></span>
							<span class="cluster-title">
								{ci.clusterId === -1 ? "Noise / Outliers" : `Cluster ${ci.clusterId}`}
							</span>
							<span class="cluster-algo">{ci.algorithm.toUpperCase()}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Algorithme</span>
							<span class="stat-value">{ci.algorithm.toUpperCase()}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Taille</span>
							<span class="stat-value">{fmtInt(ci.count)}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Taille relative</span>
							<span class="stat-value">{fmtPct(ci.relativeSize, 2)}</span>
						</div>

						<div class="stat-row">
							<div class="stat-label-with-tooltip">
								<span class="stat-label">PFAS dominant</span>

								<div class="tooltip-wrap">
									<button
										type="button"
										class="tooltip-icon"
										onclick={() => toggleTooltip("clusterDominantPfas")}
										aria-label="Informations PFAS dominant du cluster"
									>
										?
									</button>

									{#if openTooltip === "clusterDominantPfas"}
										<div class="tooltip-card">
											{CLUSTER_TOOLTIPS.dominantPfas}
										</div>
									{/if}
								</div>
							</div>

							<span class="stat-value">{ci.dominantPfas ?? "-"}</span>
						</div>

						{#if ci.centroidLat != null && ci.centroidLon != null}
							<div
								class="stat-row stat-row-clickable"
								role="button"
								tabindex="0"
								onclick={() => toggleClusterGeometry(ci.clusterId, "centroid")}
								onkeydown={(e) => {
									if (e.key === "Enter" || e.key === " ") {
										e.preventDefault();
										toggleClusterGeometry(ci.clusterId, "centroid");
									}
								}}
							>
								<div class="stat-label-with-tooltip">
									<span class="stat-label">Centroïde</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={(e) => {
												e.stopPropagation();
												toggleTooltip("centroid");
											}}
											aria-label="Informations centroïde"
										>
											?
										</button>

										{#if openTooltip === "centroid"}
											<div class="tooltip-card">
												{CLUSTER_TOOLTIPS.centroid}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value text-xs">
									{fmtNumber(ci.centroidLat, 4)}, {fmtNumber(ci.centroidLon, 4)}
								</span>
							</div>
						{/if}

						<div
							class="stat-row stat-row-clickable"
							role="button"
							tabindex="0"
							onclick={() => toggleClusterGeometry(ci.clusterId, "centroid")}
							onkeydown={(e) => {
								if (e.key === "Enter" || e.key === " ") {
									e.preventDefault();
									toggleClusterGeometry(ci.clusterId, "centroid");
								}
							}}
						>
							<div class="stat-label-with-tooltip">
								<span class="stat-label">Distance moy. au centre</span>

								<div class="tooltip-wrap">
									<button
										type="button"
										class="tooltip-icon"
										onclick={(e) => {
											e.stopPropagation();
											toggleTooltip("distanceAvg");
										}}
										aria-label="Informations distance moyenne au centre"
									>
										?
									</button>

									{#if openTooltip === "distanceAvg"}
										<div class="tooltip-card">
											{CLUSTER_TOOLTIPS.distanceAvg}
										</div>
									{/if}
								</div>
							</div>

							<span class="stat-value">{fmtNumber(ci.distanceAvg, 3)}</span>
						</div>

						<div
							class="stat-row stat-row-clickable"
							role="button"
							tabindex="0"
							onclick={() => toggleClusterGeometry(ci.clusterId, "min")}
							onkeydown={(e) => {
								if (e.key === "Enter" || e.key === " ") {
									e.preventDefault();
									toggleClusterGeometry(ci.clusterId, "min");
								}
							}}
						>
							<div class="stat-label-with-tooltip">
								<span class="stat-label">Distance min au centre</span>

								<div class="tooltip-wrap">
									<button
										type="button"
										class="tooltip-icon"
										onclick={(e) => {
											e.stopPropagation();
											toggleTooltip("distanceMin");
										}}
										aria-label="Informations distance minimale au centre"
									>
										?
									</button>

									{#if openTooltip === "distanceMin"}
										<div class="tooltip-card">
											{CLUSTER_TOOLTIPS.distanceMin}
										</div>
									{/if}
								</div>
							</div>

							<span class="stat-value">{fmtNumber(ci.distanceMin, 3)}</span>
						</div>

						<div
							class="stat-row stat-row-clickable"
							role="button"
							tabindex="0"
							onclick={() => toggleClusterGeometry(ci.clusterId, "max")}
							onkeydown={(e) => {
								if (e.key === "Enter" || e.key === " ") {
									e.preventDefault();
									toggleClusterGeometry(ci.clusterId, "max");
								}
							}}
						>
							<div class="stat-label-with-tooltip">
								<span class="stat-label">Distance max au centre</span>

								<div class="tooltip-wrap">
									<button
										type="button"
										class="tooltip-icon"
										onclick={(e) => {
											e.stopPropagation();
											toggleTooltip("distanceMax");
										}}
										aria-label="Informations distance maximale au centre"
									>
										?
									</button>

									{#if openTooltip === "distanceMax"}
										<div class="tooltip-card">
											{CLUSTER_TOOLTIPS.distanceMax}
										</div>
									{/if}
								</div>
							</div>

							<span class="stat-value">{fmtNumber(ci.distanceMax, 3)}</span>
						</div>

						<div class="stat-row">
							<div class="stat-label-with-tooltip">
								<span class="stat-label">Dispersion</span>

								<div class="tooltip-wrap">
									<button
										type="button"
										class="tooltip-icon"
										onclick={() => toggleTooltip("dispersion")}
										aria-label="Informations dispersion"
									>
										?
									</button>

									{#if openTooltip === "dispersion"}
										<div class="tooltip-card">
											{CLUSTER_TOOLTIPS.dispersion}
										</div>
									{/if}
								</div>
							</div>

							<span class="stat-value">{fmtNumber(ci.dispersion, 3)}</span>
						</div>

						{#if ci.algorithm?.toLowerCase() === "hdbscan"}
							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">Cluster persistence</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("clusterPersistence")}
											aria-label="Informations cluster persistence"
										>
											?
										</button>

										{#if openTooltip === "clusterPersistence"}
											<div class="tooltip-card">
												{CLUSTER_TOOLTIPS.clusterPersistence}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">
									{ci.clusterPersistence != null ? ci.clusterPersistence.toFixed(4) : "-"}
								</span>
							</div>
						{/if}

						{#if ci.algorithm?.toLowerCase() === "dbscan"}
							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">Core points</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("corePoints")}
											aria-label="Informations core points"
										>
											?
										</button>

										{#if openTooltip === "corePoints"}
											<div class="tooltip-card">
												{CLUSTER_TOOLTIPS.corePoints}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">{ci.corePoints ?? "-"}</span>
							</div>

							<div class="stat-row">
								<div class="stat-label-with-tooltip">
									<span class="stat-label">Border points</span>

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("borderPoints")}
											aria-label="Informations border points"
										>
											?
										</button>

										{#if openTooltip === "borderPoints"}
											<div class="tooltip-card">
												{CLUSTER_TOOLTIPS.borderPoints}
											</div>
										{/if}
									</div>
								</div>

								<span class="stat-value">{ci.borderPoints ?? "-"}</span>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>

		<VisualizationPanel {assignments} />
		{@render ExplainableAnalysisSection()}
	{:else}
		<p class="text-sm text-muted-foreground">Aucun cluster sélectionné.</p>
	{/if}

		{:else if dataRune.detailsContext === "condensed_group"}


	{#if dataRune.selectedCondensedGroup}
	{@const ctx = bubbleContext.data}

	{@const producerNames = getVisibleEntityNames(ctx?.producers)}
	{@const userNames = getVisibleEntityNames(ctx?.users)}
	{@const presumptiveNames = getVisibleEntityNames(ctx?.presumptives)}

	{@const producerRemaining = getRemainingCount(
		ctx?.summary?.producerCount ?? dataRune.selectedCondensedGroup.producerCount,
		producerNames.length,
	)}
	{@const userRemaining = getRemainingCount(
		ctx?.summary?.userCount ?? dataRune.selectedCondensedGroup.userCount,
		userNames.length,
	)}
	{@const presumptiveRemaining = getRemainingCount(
		ctx?.summary?.presumedCount ?? dataRune.selectedCondensedGroup.presumedCount,
		presumptiveNames.length,
	)}

	<div class="section">
		<div class="section-title">Détails du groupe condensé</div>

		<div class="cluster-info-card">
			<div class="stat-row">
				<span class="stat-label">Groupe</span>
				<span class="stat-value">
					{dataRune.selectedCondensedGroup.groupId === -1
						? "Noise"
						: `C${dataRune.selectedCondensedGroup.groupId}`}
				</span>
			</div>

			<div class="stat-row">
				<span class="stat-label">Total</span>
				<span class="stat-value">{dataRune.selectedCondensedGroup.count}</span>
			</div>

			<div class="entity-block">
	<div class="entity-title">Population locale</div>

	{#if localPopulation.loading}
		<div class="entity-empty">Chargement de la population locale...</div>
	{:else if localPopulation.error}
	<div class="entity-empty">
		{formatPopulationError(localPopulation.error)}
	</div>
	{:else if localPopulation.data}
		<div class="stat-row">
			<span class="stat-label">Population estimée à 1 km</span>
			<span class="stat-value">
				{Math.round(localPopulation.data.population1km).toLocaleString()}
			</span>
		</div>

		<div class="stat-row">
			<span class="stat-label">Population estimée à 5 km</span>
			<span class="stat-value">
				{Math.round(localPopulation.data.population5km).toLocaleString()}
			</span>
		</div>

		<div class="entity-more">
					Source : {localPopulation.data.source} — année {localPopulation.data.year}
		</div>
			{:else}
		<div class="entity-empty">Aucune estimation disponible.</div>
			{/if}
		</div>




			<div class="stat-row">
				<span class="stat-label">Producteurs PFAS</span>
				<span class="stat-value">{dataRune.selectedCondensedGroup.producerCount}</span>
			</div>

			{#if bubbleContext.loading}
				<p class="text-sm text-muted-foreground">Chargement du contexte...</p>
			{:else if bubbleContext.error}
				<p class="text-sm text-destructive">{bubbleContext.error}</p>
			{:else}
				<div class="entity-block">
					<div class="entity-title">Producteurs PFAS</div>
					{#if producerNames.length > 0}
						<ul class="entity-list">
							{#each producerNames as name}
								<li>{name}</li>
							{/each}
						</ul>

						{#if producerRemaining > 0}
							<div class="entity-more">+ {producerRemaining} autres</div>
						{/if}
					{:else}
						<div class="entity-empty">Aucun producteur trouvé.</div>
					{/if}
				</div>

				<div class="entity-block">
					<div class="entity-title">Utilisateurs PFAS</div>
					{#if userNames.length > 0}
						<ul class="entity-list">
							{#each userNames as name}
								<li>{name}</li>
							{/each}
						</ul>

						{#if userRemaining > 0}
							<div class="entity-more">+ {userRemaining} autres</div>
						{/if}
					{:else}
						<div class="entity-empty">Aucun utilisateur trouvé.</div>
					{/if}
				</div>

				<div class="entity-block">
					<div class="entity-title">Sites présumés</div>
					{#if presumptiveNames.length > 0}
						<ul class="entity-list">
							{#each presumptiveNames as name}
								<li>{name}</li>
							{/each}
						</ul>

						{#if presumptiveRemaining > 0}
							<div class="entity-more">+ {presumptiveRemaining} autres</div>
						{/if}
					{:else}
						<div class="entity-empty">Aucun site présumé trouvé.</div>
					{/if}
				</div>
			{/if}
		</div>

	</div>
{:else}
	<p class="text-sm text-muted-foreground">Aucun groupe condensé sélectionné.</p>
{/if}

	
		{:else if dataRune.detailsContext === "all"}
		{@const summaries = analysisRune.clusterSummaries}
		{@const algo = analysisRune.algorithm}
		{@const gm = analysisRune.globalMetrics}
		{@const realClusters = summaries.filter((s) => s.clusterId !== -1)}
		{@const totalPoints = summaries.reduce((sum, s) => sum + s.count, 0)}
		{@const noiseCount = gm?.noiseCount ?? summaries.find((s) => s.clusterId === -1)?.count ?? 0}

		<div class="section">
			<button
				type="button"
				class="section-header"
				onclick={() => (showDetails = !showDetails)}
			>
				<div class="section-title">Run Summary</div>
				<ChevronDown
					class={`chevron ${!showDetails ? "rotated" : ""}`}
					size={18}
				/>
			</button>

			{#if showDetails}
				<div class="section-content">
					<div class="cluster-info-card">
						<div class="stat-row">
							<span class="stat-label">Algorithme</span>
							<span class="stat-value">{algo.toUpperCase()}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Nombre de clusters</span>
							<span class="stat-value">{realClusters.length}</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">Points analysés</span>
							<span class="stat-value">{fmtInt(totalPoints)}</span>
						</div>

						{#if algo === "dbscan" || algo === "hdbscan"}
							<div class="stat-row">
								<span class="stat-label">
									Points bruit
									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("pointsBruit")}
											aria-label="Informations points bruit"
										>
											?
										</button>

										{#if openTooltip === "pointsBruit"}
											<div class="tooltip-card">
												{GLOBAL_TOOLTIPS.pointsBruit}
											</div>
										{/if}
									</div>
								</span>
								<span class="stat-value">{fmtInt(noiseCount)}</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">
									Ratio bruit

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("ratioBruit")}
											aria-label="Informations ratio bruit"
										>
											?
										</button>

										{#if openTooltip === "ratioBruit"}
											<div class="tooltip-card">
												{GLOBAL_TOOLTIPS.ratioBruit}
											</div>
										{/if}
									</div>
								</span>
								<span class="stat-value">
									{gm?.noiseRatio != null
										? `${(gm.noiseRatio * 100).toFixed(1)}%`
										: totalPoints > 0
											? `${((noiseCount / totalPoints) * 100).toFixed(1)}%`
											: "-"}
								</span>
							</div>
						{/if}

						<div class="stat-row">
							<span class="stat-label">
								Silhouette Score

								<div class="tooltip-wrap">
									<button
										type="button"
										class="tooltip-icon"
										onclick={() => toggleTooltip("silhouette")}
										aria-label="Informations silhouette score"
									>
										?
									</button>

									{#if openTooltip === "silhouette"}
										<div class="tooltip-card">
											{GLOBAL_TOOLTIPS.silhouette}
										</div>
									{/if}
								</div>

							</span>
							<span class="stat-value">
								{gm?.silhouetteScore != null ? gm.silhouetteScore.toFixed(4) : "-"}
							</span>
						</div>

						<div class="stat-row">
							<span class="stat-label">
								Davies-Bouldin

								<div class="tooltip-wrap">
									<button
										type="button"
										class="tooltip-icon"
										onclick={() => toggleTooltip("daviesBouldin")}
										aria-label="Informations Davies-Bouldin"
									>
										?
									</button>

									{#if openTooltip === "daviesBouldin"}
										<div class="tooltip-card">
											{GLOBAL_TOOLTIPS.daviesBouldin}
										</div>
									{/if}
								</div>
							</span>
							<span class="stat-value">
								{gm?.daviesBouldinIndex != null ? gm.daviesBouldinIndex.toFixed(4) : "-"}
							</span>
						</div>

						{#if algo === "hdbscan"}
							<div class="stat-row">
								<span class="stat-label">
									Relative validity

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("relativeValidity")}
											aria-label="Informations relative validity"
										>
											?
										</button>

										{#if openTooltip === "relativeValidity"}
											<div class="tooltip-card">
												{GLOBAL_TOOLTIPS.relativeValidity}
											</div>
										{/if}
									</div>
								</span>
								<span class="stat-value">
									{gm?.relativeValidity != null ? gm.relativeValidity.toFixed(4) : "-"}
								</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">
									Cluster persistence

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("globalClusterPersistence")}
											aria-label="Informations cluster persistence moyenne"
										>
											?
										</button>

										{#if openTooltip === "globalClusterPersistence"}
											<div class="tooltip-card">
												{GLOBAL_TOOLTIPS.clusterPersistence}
											</div>
										{/if}
									</div>
								</span>
								<span class="stat-value">
									{gm?.clusterPersistenceMean != null ? gm.clusterPersistenceMean.toFixed(4) : "-"}
								</span>
							</div>
						{/if}

						{#if algo === "kmeans" || algo === "propos"}
							<div class="stat-row">
								<span class="stat-label">
									Calinski-Harabasz

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("calinskiHarabasz")}
											aria-label="Informations Calinski-Harabasz"
										>
											?
										</button>

										{#if openTooltip === "calinskiHarabasz"}
											<div class="tooltip-card">
												{GLOBAL_TOOLTIPS.calinskiHarabasz}
											</div>
										{/if}
									</div>
								</span>
								<span class="stat-value">
									{gm?.calinskiHarabaszScore != null ? gm.calinskiHarabaszScore.toFixed(2) : "-"}
								</span>
							</div>

							<div class="stat-row">
								<span class="stat-label">
									WCSS / Inertia

									<div class="tooltip-wrap">
										<button
											type="button"
											class="tooltip-icon"
											onclick={() => toggleTooltip("wcss")}
											aria-label="Informations WCSS ou Inertia"
										>
											?
										</button>

										{#if openTooltip === "wcss"}
											<div class="tooltip-card">
												{GLOBAL_TOOLTIPS.wcss}
											</div>
										{/if}
									</div>

								</span>
								<span class="stat-value">
									{gm?.wcss != null ? gm.wcss.toFixed(2) : "-"}
								</span>
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>

		<VisualizationPanel {assignments} />
		{@render ExplainableAnalysisSection()}
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

	.xai-panel {
		margin-top: 1rem;
		padding-top: 0.9rem;
		border-top: 1px solid #e2e8f0;
	}

	.xai-header {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.xai-title {
		font-size: 1rem;
		font-weight: 700;
		color: #0f172a;
	}

	.xai-subtitle {
		font-size: 0.8rem;
		color: #64748b;
	}

	.xai-methods {
		margin-top: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}

	.xai-label {
		font-size: 0.8rem;
		font-weight: 600;
		color: #334155;
	}

	.xai-toggle {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
	}

	.xai-toggle-button {
		all: unset;
		cursor: pointer;
		padding: 0.45rem 0.75rem;
		border-radius: 999px;
		border: 1px solid #cbd5e1;
		font-size: 0.78rem;
		font-weight: 600;
		color: #475569;
		background: white;
	}

	.xai-toggle-button.xai-toggle-active {
		background: #0f172a;
		color: white;
		border-color: #0f172a;
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

	:global(.chevron) {
		transition: transform 0.2s ease;
		color: #6b7280;
		flex-shrink: 0;
	}

	:global(.chevron.rotated) {
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
	}

	.stat-value-stack {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.15rem;
		max-width: 65%;
	}

	.stat-value-link {
		color: #2563eb;
		text-decoration: underline;
		text-underline-offset: 2px;
		word-break: break-word;
	}

	.stat-value-link:hover {
		color: #1d4ed8;
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

	.table-wrapper {
		border-radius: 0.5rem;
		overflow: auto;
		border: 1px solid var(--color-border, #e5e7eb);
		background: white;
	}

	.tooltip-icon {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	width: 18px;
	height: 18px;
	border-radius: 50%;
	border: none;
	background: #e2e8f0;
	color: #64748b;
	font-size: 0.7rem;
	font-weight: 700;
	cursor: pointer;
	flex-shrink: 0;
}
.stat-label-with-tooltip {
	display: inline-flex;
	align-items: center;
	gap: 6px;
}

.tooltip-wrap {
	position: relative;
	display: inline-flex;
	align-items: center;
}

.tooltip-card {
	position: absolute;
	top: calc(100% + 8px);
	left: 50%;
	transform: translateX(-50%);
	z-index: 999;
	width: min(240px, 80vw);
	padding: 10px 12px;
	border-radius: 10px;
	background: white;
	border: 1px solid #d1d5db;
	box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
	font-size: 12px;
	line-height: 1.45;
	color: #374151;
	white-space: normal;
	word-break: break-word;
}

.tooltip-wrap {
	position: relative;
	display: inline-flex;
	align-items: center;
	overflow: visible;
}

.cluster-info-card,
.section-content,
.details-panel {
	overflow: visible;
}

	.entity-block {
	margin-top: 14px;
	padding-top: 12px;
	border-top: 1px solid rgba(0, 0, 0, 0.08);
}

.entity-title {
	font-size: 0.95rem;
	font-weight: 700;
	margin-bottom: 8px;
	color: #1f2937;
}

.entity-list {
	margin: 0;
	padding-left: 18px;
}

.entity-list li {
	margin: 4px 0;
	font-size: 0.9rem;
	color: #374151;
}

.entity-more {
	margin-top: 6px;
	font-size: 0.85rem;
	color: #6b7280;
	font-style: italic;
}

.entity-empty {
	font-size: 0.85rem;
	color: #9ca3af;
}





</style>
