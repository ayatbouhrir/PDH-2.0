<script lang="ts">
	import { onMount, onDestroy, untrack } from "svelte";
	import "leaflet/dist/leaflet.css";
	import { Category, dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import { getColor } from "$lib/shared/map/get-color";
	import { mapPointsForFsac } from "$lib/shared/map/map-points-for-fsac";
	import type { FetchResponse } from "$lib/features/exploration/filtered-points.resource.svelte";
	import * as htmlToImage from "html-to-image";
	import { Button } from "$lib/components/ui/button/index";
	import {
		Map as MapIcon,
		Plus,
		Minus,
		ImageDown,
		Crosshair,
	} from "lucide-svelte";
	import {
		Popover,
		PopoverContent,
		PopoverTrigger,
	} from "$lib/components/ui/popover/index";
	import type { Circle } from "$lib/vendor/fsac/src/circle";
	import "leaflet.heat";
	import type { PfasPoint } from "$lib/shared/types/pfas";
	import { thresholds, colors } from "$lib/shared/map/fsac-palette";
	import { tileLayers } from "$lib/shared/map/tile-layers";
	import fsac from "$lib/vendor/fsac/src/fsac";
	import { customMerge } from "$lib/shared/map/merge-map-clusters";

	const pointsIcon = "/assets/points.svg";
	const clustersIcon = "/assets/clusters.svg";
	const MAX_HEATMAP_POINTS = 250000;
	const MAX_RAW_POINTS_RENDER = 100000;
	const MOVE_DEBOUNCE_MS = 80;

	const { filteredPoints } = $props<{
		filteredPoints: FetchResponse;
		fsacEnabled?: boolean;
	}>();

	let mapContainer: HTMLDivElement;
	let map: import("leaflet").Map;
	let L: typeof import("leaflet");
	let lasso: any = null;
	let lassoFinishedHandler: ((event: any) => void) | null = null;
	let displayMode = $state<"cluster" | "points">("cluster");
	let heatLayer: any = null;
	let visibleClusters = $state<Circle[]>([]);
	let canvasRenderer: import("leaflet").Renderer;
	let renderLayerGroup: import("leaflet").LayerGroup | null = null;
	let currentTileLayer: import("leaflet").TileLayer | null = null;
	let tileLayerIndex = $state(4);
	let visible = $state<PfasPoint[]>([]);
	let legendMode = $state<"heatmap" | "cluster" | "none">("heatmap");
	let moveTimer: ReturnType<typeof setTimeout> | null = null;
	let isInternalMapUpdate = false;

	// ✅ FIX: $derived instead of writing to dataRune inside $effect.
	// This syncs nbFilteredPoints without creating a reactive write cycle.
	const _syncNbFilteredPoints = $derived.by(() => {
		const count = filteredPoints.data?.length ?? 0;
		// untrack the write so it doesn't register as a dependency
		untrack(() => {
			if (dataRune.nbFilteredPoints !== count) {
				dataRune.nbFilteredPoints = count;
			}
		});
		return count;
	});

	export function invalidateMapSize() {
		if (!map) return;

		isInternalMapUpdate = true;
		map.invalidateSize();

		requestAnimationFrame(() => {
			isInternalMapUpdate = false;
		});
	}

	function clearRenderLayers() {
		renderLayerGroup?.clearLayers();

		if (heatLayer && map) {
			map.removeLayer(heatLayer);
			heatLayer = null;
		}
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

	function fitToData() {
		if (!map || !filteredPoints.data?.length) return;

		const latLngs = filteredPoints.data
			.filter((p: PfasPoint) => p.lat != null && p.lon != null)
			.map((p: PfasPoint) => L.latLng(Number(p.lat), Number(p.lon)));

		if (latLngs.length > 0) {
			isInternalMapUpdate = true;
			map.fitBounds(L.latLngBounds(latLngs).pad(0.05));

			requestAnimationFrame(() => {
				isInternalMapUpdate = false;
			});
		}
	}

	function fitToCluster(cluster: Circle) {
		if (!map || !cluster || !L) return;

		const padding = -0.6;
		const radius = cluster.r * (1 + padding);

		const xMin = cluster.x - radius;
		const xMax = cluster.x + radius;
		const yMin = cluster.y - radius;
		const yMax = cluster.y + radius;

		const sw = L.Projection.SphericalMercator.unproject(L.point(xMin, yMin));
		const ne = L.Projection.SphericalMercator.unproject(L.point(xMax, yMax));

		isInternalMapUpdate = true;
		map.fitBounds(L.latLngBounds(sw, ne));

		requestAnimationFrame(() => {
			isInternalMapUpdate = false;
		});
	}

	function exportMapAsPng() {
		if (!mapContainer) return;

		htmlToImage
			.toPng(mapContainer, {
				pixelRatio: 3,
				style: {
					margin: "0",
					padding: "0",
					background: "transparent",
					boxShadow: "none",
					border: "none",
				},
				filter: (node) => {
					const id = (node as HTMLElement).id;
					return id !== "some-ui" && id !== "export-btn";
				},
			})
			.then((dataUrl) => {
				const link = document.createElement("a");
				link.download = "pfas-map.png";
				link.href = dataUrl;
				link.click();
			})
			.catch((error) => console.error("Export erreur :", error));
	}

	function getScaleFactorForLat(lat: number): number {
		return Math.cos((lat * Math.PI) / 180);
	}

	function computeVisiblePoints() {
		if (!map || !filteredPoints.data?.length) {
			visible = [];
			return;
		}

		const bounds = map.getBounds();

		visible = filteredPoints.data.filter((p: PfasPoint) => {
			const lat = Number(p.lat);
			const lon = Number(p.lon);

			return (
				Number.isFinite(lat) &&
				Number.isFinite(lon) &&
				bounds.contains([lat, lon])
			);
		});
	}

	function computeClusters() {
		if (
			displayMode !== "cluster" ||
			dataRune.filters.category !== Category.Sampling ||
			visible.length === 0 ||
			visible.length > MAX_HEATMAP_POINTS
		) {
			visibleClusters = [];
			return;
		}

		const zoom = map.getZoom();
		const fsacInput = mapPointsForFsac(visible, zoom);
		visibleClusters = fsac(fsacInput, zoom, { merge: customMerge });
	}

	function drawHeatmap() {
		const heatmapPoints = visible
			.filter((p) => p.lat != null && p.lon != null)
			.map((p) => [Number(p.lat), Number(p.lon)]);

		heatLayer = (L as any)
			.heatLayer(heatmapPoints, {
				radius: 20,
				blur: 25,
				maxZoom: 17,
			})
			.addTo(map);
	}

	function drawClusters() {
		if (!renderLayerGroup) return;

		for (const cluster of visibleClusters) {
			const { x, y, r, n, data } = cluster;

			const color = getColor(Category.Sampling, data);
			const latlng = L.Projection.SphericalMercator.unproject(L.point(x, y));
			const correction = getScaleFactorForLat(latlng.lat);

			L.circle(latlng, {
				radius: r * correction,
				fillColor: color,
				color: "grey",
				weight: 0.5,
				fillOpacity: 0.7,
				renderer: canvasRenderer,
			})
				.bindTooltip(
					`<strong>${new Intl.NumberFormat("fr-FR").format(n)} points</strong><br>` +
						`Average PFAS sum : ${new Intl.NumberFormat("fr-FR").format(Math.round(data))}`,
				)
				.addTo(renderLayerGroup)
				.on("click", () => {
					fitToCluster(cluster);
				});
		}
	}

	function drawPoints() {
		if (!renderLayerGroup) return;

		if (visible.length > MAX_RAW_POINTS_RENDER) {
			return;
		}

		const grouped = new Map<string, PfasPoint[]>();

		for (const point of visible) {
			if (point.lat == null || point.lon == null) continue;
			const key = `${point.lat},${point.lon}`;
			if (!grouped.has(key)) grouped.set(key, []);
			grouped.get(key)!.push(point);
		}

		for (const [key, group] of grouped) {
			const [lat, lon] = key.split(",").map(Number);
			const avgPfas =
				group.reduce((sum, p) => sum + Number(p.pfas_sum ?? 0), 0) / group.length;

			const color = getColor(Category.Sampling, avgPfas);

			const shape = L.circleMarker([lat, lon], {
				radius: group.length > 1 ? 4 + 0.2 * Math.sqrt(group.length) : 4,
				fillColor: color,
				color: "grey",
				weight: 1,
				fillOpacity: 0.8,
				renderer: canvasRenderer,
			});

			shape
				.bindTooltip(
					`<strong>${group.length} point${group.length > 1 ? "s" : ""}</strong><br>` +
						`Average PFAS sum : ${new Intl.NumberFormat("fr-FR").format(Math.round(avgPfas))}`,
				)
				.addTo(renderLayerGroup)
				.on("click", () => {
					dataRune.selectedPoints = group;
				});
		}
	}

	function updateMap() {
		if (!map || !L) return;

		clearRenderLayers();

		if (!visible.length) {
			legendMode = "none";
			return;
		}

		if (visible.length > MAX_HEATMAP_POINTS) {
			legendMode = "heatmap";
			drawHeatmap();
			return;
		}

		if (
			displayMode === "cluster" &&
			dataRune.filters.category === Category.Sampling
		) {
			legendMode = "cluster";
			drawClusters();
			return;
		}

		if (dataRune.filters.category !== Category.Sampling) {
			legendMode = "none";
		} else {
			legendMode = "cluster";
		}

		drawPoints();
	}

	function runRefresh() {
		if (!map || filteredPoints.loading || isInternalMapUpdate) return;

		computeVisiblePoints();
		computeClusters();
		updateMap();
	}

	function scheduleRefresh() {
		if (moveTimer) {
			clearTimeout(moveTimer);
		}

		moveTimer = setTimeout(() => {
			runRefresh();
		}, MOVE_DEBOUNCE_MS);
	}

	function toggleDisplayMode() {
		displayMode = displayMode === "cluster" ? "points" : "cluster";
		scheduleRefresh();
	}

	// Lasso effect — unchanged, reads only dataRune.lassoEnabled
	$effect(() => {
		if (!map || !L) return;

		if (dataRune.lassoEnabled) {
			if (!lasso) {
				lasso = new (L as any).Lasso(map, {
					intersect: true,
					polygon: { color: "var(--primary)" },
				});

				lassoFinishedHandler = (event: any) => {
					const rawPolygon = event?.latLngs;

					if (Array.isArray(rawPolygon)) {
						dataRune.filters.lassoRegion = rawPolygon.map(
							({ lat, lng }: { lat: number; lng: number }) => ({
								lat,
								lon: lng,
							}),
						);
					} else {
						dataRune.filters.lassoRegion = [];
					}
				};

				map.on("lasso.finished", lassoFinishedHandler);
				lasso.enable();
			}
		} else if (lasso) {
			lasso.disable();

			if (lassoFinishedHandler) {
				map.off("lasso.finished", lassoFinishedHandler);
				lassoFinishedHandler = null;
			}

			lasso = null;
		}
	});

	onMount(async () => {
		L = await import("leaflet");
		await import("leaflet-lasso");

		map = L.map(mapContainer, {
			preferCanvas: true,
			zoomControl: false,
		}).setView([48, 7], 5);

		canvasRenderer = L.canvas();
		renderLayerGroup = L.layerGroup().addTo(map);

		map.on("zoomend", scheduleRefresh);
		map.on("moveend", scheduleRefresh);

		const base = tileLayers[tileLayerIndex];
		currentTileLayer = L.tileLayer(base.url!, {
			attribution: base.attribution,
			crossOrigin: true,
		}).addTo(map);

		scheduleRefresh();
	});

	onDestroy(() => {
		if (moveTimer) {
			clearTimeout(moveTimer);
		}

		if (map && lassoFinishedHandler) {
			map.off("lasso.finished", lassoFinishedHandler);
		}

		map?.remove();
	});

	// ✅ FIX: $effect no longer writes to dataRune.
	// It only reads filteredPoints and displayMode to trigger map refresh.
	// nbFilteredPoints sync is handled separately via $derived above.
	$effect(() => {
		// Capture reactive dependencies as plain values
		const data = filteredPoints.data;
		const loading = filteredPoints.loading;
		const _mode = displayMode;
		const _category = dataRune.filters.category;

		if (!map) return;

		// All imperative map work runs outside Svelte's tracking context
		// so it cannot accidentally register new dependencies or trigger writes
		// that would re-run this effect.
		untrack(() => {
			scheduleRefresh();
		});
	});
</script>

<div class="map-wrapper">
	<div id="map" bind:this={mapContainer}></div>

	{#if filteredPoints.loading}
		<div class="loading-overlay">Loading...</div>
	{/if}

	{#if !filteredPoints.loading && displayMode === "points" && visible.length > MAX_RAW_POINTS_RENDER && visible.length <= MAX_HEATMAP_POINTS}
		<div class="overlay-warning">
			Trop de points visibles ({visible.length.toLocaleString("fr-FR")}). Passe en mode clusters ou zoome davantage.
		</div>
	{/if}

	<div class="buttons">
		<Button
			onclick={toggleDisplayMode}
			title={displayMode === "cluster"
				? "Afficher les points"
				: "Afficher les clusters"}
			class="absolute top-4 left-4 p-1"
			size="icon"
			disabled={visible.length > MAX_HEATMAP_POINTS}
		>
			<img
				src={displayMode === "cluster" ? pointsIcon : clustersIcon}
				alt={displayMode === "cluster" ? "Points" : "Clusters"}
				class="w-6 h-6"
			/>
		</Button>

		<Button
			onclick={() => map?.zoomIn()}
			size="icon"
			class="absolute top-16 left-4"
			title="Zoom avant"
		>
			<Plus class="w-4 h-4" />
		</Button>

		<Button
			onclick={() => map?.zoomOut()}
			size="icon"
			class="absolute top-28 left-4"
			title="Zoom arrière"
		>
			<Minus class="w-4 h-4" />
		</Button>

		{#if legendMode === "heatmap"}
			<div class="legend top-right">
				<div class="legend-title">Point density</div>
				<div class="legend-gradient heatmap"></div>
				<div class="legend-labels">
					<span>Low</span><span>High</span>
				</div>
			</div>
		{:else if legendMode === "cluster"}
			<div class="legend top-right">
				<div class="legend-title">PFAS Sum</div>
				{#each thresholds as t, i}
					<div class="legend-item">
						<span
							class="legend-color"
							style="background-color: {colors[i]}; opacity: 0.8;"
						></span>
						<span class="legend-value">
							{t.toLocaleString("fr-FR")}
						</span>
					</div>
				{/each}
			</div>
		{/if}

		<div class="absolute top-40 left-4">
			<Popover>
				<PopoverTrigger>
					<Button size="icon" title="Changer de fond de carte">
						<MapIcon class="w-4 h-4" />
					</Button>
				</PopoverTrigger>
				<PopoverContent class="w-64 p-2">
					<h4 class="text-sm font-semibold mb-2">
						Choix du fond de carte
					</h4>
					<ul class="grid gap-1">
						{#each tileLayers as layer, index}
							<li>
								<Button
									variant={index === tileLayerIndex
										? "default"
										: "ghost"}
									class="w-full justify-start"
									onclick={() => setTileLayer(index)}
								>
									{layer.name}
								</Button>
							</li>
						{/each}
					</ul>
				</PopoverContent>
			</Popover>
		</div>

		<Button
			onclick={exportMapAsPng}
			size="icon"
			class="absolute top-52 left-4"
			title="Exporter la carte"
		>
			<ImageDown class="w-4 h-4" />
		</Button>

		<Button
			onclick={fitToData}
			size="icon"
			class="absolute top-64 left-4"
			title="Recentrer la carte sur les données"
		>
			<Crosshair class="w-4 h-4" />
		</Button>
	</div>
</div>

<style>
	.map-wrapper {
		position: relative;
		width: 100%;
		height: 100%;
	}

	#map {
		height: 100%;
		width: 100%;
		z-index: 0;
	}

	.loading-overlay {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(255, 255, 255, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.2rem;
		font-weight: bold;
		z-index: 2;
		pointer-events: all;
	}

	.overlay-warning {
		position: absolute;
		top: 1rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 1000;
		padding: 0.7rem 1rem;
		border-radius: 0.75rem;
		background: rgba(255, 247, 237, 0.96);
		color: #9a3412;
		border: 1px solid #fdba74;
		font-weight: 600;
	}

	.buttons {
		z-index: 1;
	}

	.legend {
		position: absolute;
		top: 1rem;
		right: 1rem;
		background: white;
		padding: 0.75rem;
		border-radius: 0.5rem;
		box-shadow: 0 0 6px rgba(0, 0, 0, 0.1);
		font-size: 0.75rem;
		z-index: 1;
		width: max-content;
	}

	.legend-title {
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.25rem;
	}

	.legend-color {
		width: 18px;
		height: 10px;
		border-radius: 2px;
	}

	.legend-value {
		white-space: nowrap;
	}

	.legend-gradient.heatmap {
		height: 12px;
		background: linear-gradient(to right, #00f, #0ff, #0f0, #ff0, #f00);
		border-radius: 4px;
		margin-bottom: 0.25rem;
	}

	.legend-labels {
		display: flex;
		justify-content: space-between;
		font-size: 0.65rem;
	}
</style>
