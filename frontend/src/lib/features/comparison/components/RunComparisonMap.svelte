<script lang="ts">
	import { onDestroy, onMount } from "svelte";
	import "leaflet/dist/leaflet.css";
	import { Plus, Minus, Crosshair, Layers3, PanelBottom, PanelBottomClose } from "lucide-svelte";
	import type { CircleMarker } from "leaflet";
	import type { ClusteredPoint, DisplayMode, ViewportBounds } from "$lib/shared/types/analysis-contract";
	import type { ComparisonRunData } from "$lib/features/comparison/run-comparison.types";
	import { tileLayers } from "$lib/shared/map/tile-layers";
	import { getClusterColor } from "$lib/shared/map/cluster-colors";

	let {
		run,
		runIndex,
		syncViewport = false,
		syncedViewport = null,
		onViewportChange,
	}: {
		run: ComparisonRunData;
		runIndex: number;
		syncViewport?: boolean;
		syncedViewport?: ViewportBounds | null;
		onViewportChange?: ((viewport: ViewportBounds, sourceId: string) => void) | null;
	} = $props();

	let mapContainer: HTMLDivElement;
	let map: import("leaflet").Map;
	let L: typeof import("leaflet");
	let canvasRenderer: import("leaflet").Renderer;
	let rawPointsLayerGroup: import("leaflet").LayerGroup | null = null;
	let condensedLayerGroup: import("leaflet").LayerGroup | null = null;
	let currentTileLayer: import("leaflet").TileLayer | null = null;
	let tileLayerIndex = $state(run.entry.mapState?.tileLayerIndex ?? 4);
	let displayMode = $state<DisplayMode>(run.displayMode);
	let selectedClusterId = $state<number | null>(null);
	let clusterInfoOpen = $state(true);
	let isApplyingExternalViewport = false;

	const hasCondensed = $derived(run.condensedBubbles.length > 0);
	const clusterSummaries = $derived(run.result.clusterSummaries ?? []);
	const visibleClusterSummaries = $derived(
		[...clusterSummaries]
			.filter((summary) => summary.clusterId !== -1)
			.sort((a, b) => b.count - a.count),
	);
	const noiseSummary = $derived(
		clusterSummaries.find((summary) => summary.clusterId === -1) ?? null,
	);

	function getRunOrdinalLabel(index: number) {
		return ["Premier run", "Deuxième run", "Troisième run", "Quatrième run"][index] ?? `Run ${index + 1}`;
	}

	function formatRunLabel() {
		const baseLabel =
			run.entry.name ??
			`${run.entry.algorithm.toUpperCase()} · ${run.entry.clusterCount} clusters`;

		return `${baseLabel} · ${getRunOrdinalLabel(runIndex)} (${run.id.slice(0, 8)})`;
	}

	function buildViewportBounds() {
		if (!map) return null;
		const bounds = map.getBounds();
		return {
			south: bounds.getSouth(),
			west: bounds.getWest(),
			north: bounds.getNorth(),
			east: bounds.getEast(),
		} satisfies ViewportBounds;
	}

	function hasSameViewport(a: ViewportBounds | null, b: ViewportBounds | null) {
		if (!a || !b) return false;
		return (
			Math.abs(a.south - b.south) < 1e-6 &&
			Math.abs(a.west - b.west) < 1e-6 &&
			Math.abs(a.north - b.north) < 1e-6 &&
			Math.abs(a.east - b.east) < 1e-6
		);
	}

	function emitViewportChange() {
		if (!map || isApplyingExternalViewport) return;
		const viewport = buildViewportBounds();
		if (!viewport) return;
		onViewportChange?.(viewport, run.id);
	}

	function setTileLayer(index: number) {
		if (!map || !L) return;

		tileLayerIndex = index;

		if (currentTileLayer) {
			map.removeLayer(currentTileLayer);
			currentTileLayer = null;
		}

		const base = tileLayers[tileLayerIndex];

		currentTileLayer = L.tileLayer(base.url!, {
			attribution: base.attribution,
			crossOrigin: true,
		}).addTo(map);
	}

	function getPointStyle(clusterId: number) {
		const isNoise = clusterId === -1;
		const isActive = selectedClusterId == null || selectedClusterId === clusterId;

		if (isNoise) {
			return {
				radius: isActive ? 4.4 : 3.4,
				color: isActive ? "#111827" : "#9ca3af",
				weight: isActive ? 1.1 : 0.4,
				fillColor: getClusterColor(clusterId),
				fillOpacity: isActive ? 0.82 : 0.18,
				opacity: isActive ? 1 : 0.22,
				renderer: canvasRenderer,
			};
		}

		return {
			radius: isActive ? 4.6 : 3.2,
			color: isActive ? "#334155" : "#e2e8f0",
			weight: isActive ? 1 : 0.25,
			fillColor: getClusterColor(clusterId),
			fillOpacity: isActive ? 0.88 : 0.14,
			opacity: isActive ? 1 : 0.18,
			renderer: canvasRenderer,
		};
	}

	function getBubbleRadius(count: number) {
		if (count <= 1) return 4;
		return Math.min(16, 4 + Math.log2(count + 1) * 2);
	}

	function getBubbleStyle(parentClusterId: number, count: number) {
		const isNoise = parentClusterId === -1;
		const isActive =
			selectedClusterId == null || selectedClusterId === parentClusterId;

		return {
			radius: isActive
				? getBubbleRadius(count)
				: Math.max(4, getBubbleRadius(count) * 0.7),
			color: isActive ? "#111827" : "#cbd5e1",
			weight: isActive ? 1.2 : 0.45,
			fillColor: getClusterColor(parentClusterId),
			fillOpacity: isNoise
				? isActive
					? 0.52
					: 0.12
				: isActive
					? 0.74
					: 0.14,
			opacity: isActive ? 1 : 0.2,
			renderer: canvasRenderer,
		};
	}

	function offsetOverlappingPoints(points: ClusteredPoint[]): ClusteredPoint[] {
		const groups = new Map<string, ClusteredPoint[]>();

		for (const point of points) {
			const key = `${Number(point.lat).toFixed(6)},${Number(point.lon).toFixed(6)},${point.clusterId}`;
			if (!groups.has(key)) groups.set(key, []);
			groups.get(key)!.push(point);
		}

		const result: ClusteredPoint[] = [];

		for (const group of groups.values()) {
			if (group.length === 1) {
				result.push(group[0]);
				continue;
			}

			const radius = 0.00008;
			const step = (2 * Math.PI) / group.length;

			group.forEach((point, index) => {
				const angle = index * step;
				result.push({
					...point,
					lat: Number(point.lat) + radius * Math.sin(angle),
					lon: Number(point.lon) + radius * Math.cos(angle),
				});
			});
		}

		return result;
	}

	function clearLayers() {
		rawPointsLayerGroup?.clearLayers();
		condensedLayerGroup?.clearLayers();
	}

	function drawClusteredPoints() {
		if (!rawPointsLayerGroup) return;

		for (const point of offsetOverlappingPoints(run.clusteredPoints)) {
			const clusterId = Number(point.clusterId);
			const summary = clusterSummaries.find((item) => item.clusterId === clusterId);
			const tooltipLabel =
				clusterId === -1
					? "Noise"
					: `Cluster ${clusterId}${summary?.dominantPfas ? ` · ${summary.dominantPfas}` : ""}`;

			const marker = L.circleMarker(
				[Number(point.lat), Number(point.lon)],
				getPointStyle(clusterId),
			);

			marker
				.bindTooltip(
					`${tooltipLabel}<br>PFAS sum: ${Math.round(
						Number(point.pfasSum ?? 0),
					).toLocaleString("fr-FR")}`,
				)
				.addTo(rawPointsLayerGroup);
		}
	}

	function drawCondensedBubbles() {
		if (!condensedLayerGroup) return;

		for (const bubble of run.condensedBubbles) {
			const summary = clusterSummaries.find(
				(item) => item.clusterId === bubble.parentClusterId,
			);
			const style = getBubbleStyle(bubble.parentClusterId, bubble.count);

			const marker: CircleMarker = L.circleMarker([bubble.lat, bubble.lon], {
				radius: style.radius,
				color: style.color,
				weight: style.weight,
				fillColor: style.fillColor,
				fillOpacity: style.fillOpacity,
				opacity: style.opacity,
				renderer: canvasRenderer,
			});

			marker
				.bindTooltip(
					`${
						bubble.parentClusterId === -1
							? "Noise"
							: `Cluster ${bubble.parentClusterId}`
					}<br>${bubble.count.toLocaleString("fr-FR")} points${
						summary?.dominantPfas ? `<br>Dominant: ${summary.dominantPfas}` : ""
					}`,
				)
				.addTo(condensedLayerGroup);
		}
	}

	function drawMap() {
		if (!map) return;
		clearLayers();

		if (displayMode === "condensed" && hasCondensed) {
			drawCondensedBubbles();
			return;
		}

		drawClusteredPoints();
	}

	function fitToData() {
		if (!map || !L) return;

		const viewport = run.initialViewport;
		if (viewport) {
			isApplyingExternalViewport = true;
			map.fitBounds(
				[
					[viewport.south, viewport.west],
					[viewport.north, viewport.east],
				],
				{ padding: [20, 20], maxZoom: 10 },
			);
			requestAnimationFrame(() => {
				isApplyingExternalViewport = false;
			});
			return;
		}

		const coordinates =
			(displayMode === "condensed" && hasCondensed
				? run.condensedBubbles.map((bubble) => [bubble.lat, bubble.lon] as [number, number])
				: run.clusteredPoints.map((point) => [Number(point.lat), Number(point.lon)] as [number, number]))
				.filter(([lat, lon]) => Number.isFinite(lat) && Number.isFinite(lon));

		if (coordinates.length === 0) return;

		isApplyingExternalViewport = true;
		map.fitBounds(L.latLngBounds(coordinates).pad(0.08), {
			padding: [20, 20],
			maxZoom: 10,
		});

		requestAnimationFrame(() => {
			isApplyingExternalViewport = false;
		});
	}

	function toggleCluster(clusterId: number) {
		selectedClusterId = selectedClusterId === clusterId ? null : clusterId;
	}

	$effect(() => {
		displayMode;
		selectedClusterId;

		if (!map) return;
		drawMap();
	});

	$effect(() => {
		syncViewport;
		syncedViewport;

		if (!map || !syncViewport || !syncedViewport) return;

		const currentViewport = buildViewportBounds();
		if (hasSameViewport(currentViewport, syncedViewport)) {
			return;
		}

		isApplyingExternalViewport = true;
		map.fitBounds(
			[
				[syncedViewport.south, syncedViewport.west],
				[syncedViewport.north, syncedViewport.east],
			],
			{
				padding: [20, 20],
				maxZoom: 10,
				animate: false,
			},
		);

		requestAnimationFrame(() => {
			isApplyingExternalViewport = false;
		});
	});

	onMount(async () => {
		L = await import("leaflet");

		map = L.map(mapContainer, {
			preferCanvas: true,
			zoomControl: false,
			minZoom: 2,
			worldCopyJump: true,
		}).setView([48, 7], 5);

		canvasRenderer = L.canvas();
		rawPointsLayerGroup = L.layerGroup().addTo(map);
		condensedLayerGroup = L.layerGroup().addTo(map);

		setTileLayer(tileLayerIndex);
		map.on("moveend", emitViewportChange);

		fitToData();
		drawMap();
	});

	onDestroy(() => {
		map?.off("moveend", emitViewportChange);
		map?.remove();
	});
</script>

<div class="comparison-map-card">
	<div class="map-card-header">
		<div>
			<div class="map-card-title">{formatRunLabel()}</div>
			<div class="map-card-subtitle">
				{run.entry.algorithm.toUpperCase()} · {displayMode === "condensed" ? "bulles condensées" : "points"}
			</div>
		</div>

		<div class="map-card-actions">
			{#if hasCondensed}
				<button
					type="button"
					class="icon-btn"
					title="Basculer entre points et bulles condensées"
					onclick={() =>
						(displayMode =
							displayMode === "condensed" ? "points" : "condensed")}
				>
					<Layers3 size={16} />
				</button>
			{/if}

			<button type="button" class="icon-btn" title="Zoom avant" onclick={() => map?.zoomIn()}>
				<Plus size={16} />
			</button>

			<button type="button" class="icon-btn" title="Zoom arrière" onclick={() => map?.zoomOut()}>
				<Minus size={16} />
			</button>

			<button type="button" class="icon-btn" title="Recentrer" onclick={fitToData}>
				<Crosshair size={16} />
			</button>

			<button
				type="button"
				class="icon-btn"
				title={clusterInfoOpen
					? "Masquer la carte d'information des clusters"
					: "Afficher la carte d'information des clusters"}
				onclick={() => (clusterInfoOpen = !clusterInfoOpen)}
			>
				{#if clusterInfoOpen}
					<PanelBottomClose size={16} />
				{:else}
					<PanelBottom size={16} />
				{/if}
			</button>
		</div>
	</div>

	<div class="map-shell">
		<div class="map-canvas" bind:this={mapContainer}></div>
	</div>

	{#if clusterInfoOpen}
		<div class="map-legend map-legend-below">
			<div class="legend-stat-grid">
				<div class="legend-stat">
					<span>Points</span>
					<strong>{run.result.summary.analyzedPoints.toLocaleString("fr-FR")}</strong>
				</div>

				<div class="legend-stat">
					<span>Clusters</span>
					<strong>{run.result.summary.clusterCount}</strong>
				</div>

				<div class="legend-stat">
					<span>Durée</span>
					<strong>
						{run.entry.durationMs < 1000
							? `${run.entry.durationMs} ms`
							: `${(run.entry.durationMs / 1000).toFixed(1)} s`}
					</strong>
				</div>
			</div>

			{#if visibleClusterSummaries.length > 0}
				<div class="legend-chip-list">
					{#each visibleClusterSummaries as summary}
						<button
							type="button"
							class="legend-chip"
							class:legend-chip-active={selectedClusterId === summary.clusterId}
							onclick={() => toggleCluster(summary.clusterId)}
						>
							<span class="legend-chip-content">
								<span
									class="legend-dot"
									style={`background:${getClusterColor(summary.clusterId)}`}
								></span>
								<span class="legend-chip-id">C{summary.clusterId}</span>
								<span class="legend-chip-note">Local au run</span>
								{#if summary.dominantPfas}
									<span class="legend-chip-meta">{summary.dominantPfas}</span>
								{/if}
							</span>
						</button>
					{/each}

					{#if noiseSummary}
						<button
							type="button"
							class="legend-chip"
							class:legend-chip-active={selectedClusterId === -1}
							onclick={() => toggleCluster(-1)}
						>
							<span class="legend-chip-content">
								<span
									class="legend-dot"
									style={`background:${getClusterColor(-1)}`}
								></span>
								<span class="legend-chip-id">Noise</span>
								<span class="legend-chip-note">Local au run</span>
							</span>
						</button>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.comparison-map-card {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
		padding: 0.85rem;
		border-radius: 1rem;
		border: 1px solid #dbe4ee;
		background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
		box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
	}

	.map-card-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
	}

	.map-card-title {
		font-size: 0.98rem;
		font-weight: 700;
		color: #0f172a;
	}

	.map-card-subtitle {
		margin-top: 0.15rem;
		font-size: 0.8rem;
		color: #64748b;
	}

	.map-card-actions {
		display: flex;
		gap: 0.35rem;
		flex-wrap: wrap;
	}

	.icon-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border: 1px solid #d6dde8;
		border-radius: 0.65rem;
		background: rgba(255, 255, 255, 0.92);
		color: #0f172a;
		cursor: pointer;
	}

	.icon-btn:hover {
		background: #eff6ff;
		border-color: #93c5fd;
	}

	.map-shell {
		position: relative;
		border-radius: 0.9rem;
		overflow: hidden;
		border: 1px solid #dbe4ee;
		background: #d7e8ef;
		min-height: clamp(22rem, 52vh, 34rem);
	}

	.map-canvas {
		height: 100%;
		min-height: clamp(22rem, 52vh, 34rem);
		width: 100%;
	}

	.map-legend {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		padding: 0.65rem;
		border-radius: 0.9rem;
		background: rgba(255, 255, 255, 0.92);
		backdrop-filter: blur(8px);
		box-shadow: 0 10px 22px rgba(15, 23, 42, 0.1);
	}

	.map-legend-below {
		position: static;
		width: auto;
	}

	.legend-stat-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.45rem 0.75rem;
	}

	.legend-stat {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		font-size: 0.74rem;
		color: #475569;
	}

	.legend-stat strong {
		color: #0f172a;
		font-weight: 700;
	}

	.legend-chip-list {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
		gap: 0.3rem;
		margin-top: 0.25rem;
	}

	.legend-chip {
		display: inline-flex;
		align-items: center;
		padding: 0.4rem 0.55rem;
		border-radius: 0.8rem;
		border: 1px solid #dbe4ee;
		background: #ffffff;
		color: #334155;
		font-size: 0.74rem;
		cursor: pointer;
		text-align: left;
	}

	.legend-chip-content {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.28rem 0.42rem;
		min-width: 0;
	}

	.legend-chip-active {
		border-color: #1d4ed8;
		background: #eff6ff;
		color: #0f172a;
	}

	.legend-dot {
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 999px;
		flex-shrink: 0;
	}

	.legend-chip-id {
		font-weight: 700;
		color: #0f172a;
	}

	.legend-chip-note {
		font-size: 0.66rem;
		font-weight: 600;
		color: #64748b;
	}

	.legend-chip-meta {
		min-width: 0;
		font-size: 0.7rem;
		color: #475569;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	@media (max-width: 900px) {
		.map-shell,
		.map-canvas {
			min-height: clamp(20rem, 46vh, 28rem);
		}

		.legend-stat-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
