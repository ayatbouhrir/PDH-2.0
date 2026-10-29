<script lang="ts">
	import { onMount, onDestroy } from "svelte";
	import maplibregl from "maplibre-gl";
	import "maplibre-gl/dist/maplibre-gl.css";
	import { ColumnLayer } from "@deck.gl/layers";
	import { MapboxOverlay } from "@deck.gl/mapbox";

	import type { CondensedBubble } from "$lib/shared/types/analysis-contract";
	import { build3DCondensationData } from "$lib/features/analysis/condensation-3d";

	type Props = {
		bubbles: CondensedBubble[];
		selectedClusterId: number | null;
		getClusterColor: (clusterId: number) => string;
		onBubbleClick?: (bubble: CondensedBubble) => void;
	};

	let {
		bubbles = [],
		selectedClusterId = null,
		getClusterColor,
		onBubbleClick,
	}: Props = $props();

	let mapContainer: HTMLDivElement;
	let map: maplibregl.Map | null = null;
	let overlay: MapboxOverlay | null = null;
	let mapLoaded = false;
	let lastFitSignature = "";

	const MAP_STYLE: maplibregl.StyleSpecification = {
		version: 8,
		sources: {
			osm: {
				type: "raster",
				tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
				tileSize: 256,
				attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
			},
		},
		layers: [{ id: "osm", type: "raster", source: "osm" }],
	};

	type Condensation3DItem = {
		position: [number, number];
		elevation: number;
		radius: number;
		fillColor: [number, number, number, number];
		lineColor: [number, number, number, number];
		raw: CondensedBubble;
	};

	function buildFitSignature(items: Condensation3DItem[]): string {
		return items
			.map((item) => {
				const b = item.raw;
				return [
					String(b.groupId),
					String(b.parentClusterId),
					String(b.lat),
					String(b.lon),
					String(b.count),
				].join("|");
			})
			.join(";");
	}

	function fitToBubbles(items: Condensation3DItem[]) {
		if (!map || !items.length) return;

		const bounds = new maplibregl.LngLatBounds();

		for (const item of items) {
			bounds.extend(item.position);
		}

		map.fitBounds(bounds, {
			padding: 40,
			maxZoom: 7,
			duration: 600,
		});
	}

	function updateLayer() {
		if (!overlay || !mapLoaded) return;

		const items = build3DCondensationData(
			bubbles ?? [],
			getClusterColor,
			selectedClusterId,
		) as Condensation3DItem[];

		const layer = new ColumnLayer<Condensation3DItem>({
			id: "condensation-3d-columns",
			data: items,
			diskResolution: 20,
			extruded: true,
			wireframe: false,
			pickable: true,
			autoHighlight: true,
			highlightColor: [250, 204, 21, 220],

			getPosition: (d) => d.position,
			getElevation: (d) => d.elevation,
			radius: items.length ? items.reduce((sum, d) => sum + d.radius, 0) / items.length : 1000,
			getFillColor: (d) => d.fillColor,
			getLineColor: (d) => d.lineColor,
			lineWidthMinPixels: 1,

			onClick: (info) => {
				const bubble = info?.object?.raw;
				if (bubble && onBubbleClick) {
					onBubbleClick(bubble);
				}
			},
		});

		overlay.setProps({
			layers: [layer],
			getTooltip: ({ object }: { object?: Condensation3DItem }) => {
				if (!object?.raw) return null;

				const b = object.raw;

				return {
					className: "deck-tooltip",
					html: `
						<div style="font-size:13px; line-height:1.45;">
							<div><strong>Groupe :</strong> ${String(b.groupId)}</div>
							<div><strong>Cluster parent :</strong> C${b.parentClusterId}</div>
							<div><strong>Points :</strong> ${b.count}</div>
							<div><strong>${b.displayPfasName ?? "PFAS"} :</strong> ${Number(b.avgDisplayPfasValue ?? b.avgPfasSum ?? 0).toLocaleString("fr-FR")}</div>
							<div><strong>PFAS dominant :</strong> ${b.dominantPfas ?? "-"}</div>
						</div>
					`,
				};
			},
		});

		const nextSignature = buildFitSignature(items);
		if (nextSignature && nextSignature !== lastFitSignature) {
			lastFitSignature = nextSignature;
			fitToBubbles(items);
		}
	}

	onMount(() => {
		map = new maplibregl.Map({
			container: mapContainer,
			style: MAP_STYLE,
			center: [2, 46],
			zoom: 3,
			pitch: 55,
			bearing: -20,
			canvasContextAttributes: { antialias: true },
		});

		map.addControl(new maplibregl.NavigationControl(), "top-right");

		overlay = new MapboxOverlay({
			interleaved: false,
			layers: [],
		});

		map.addControl(overlay);

		map.on("load", () => {
			mapLoaded = true;
			updateLayer();
		});
	});

	onDestroy(() => {
		if (map && overlay) {
			map.removeControl(overlay);
		}
		map?.remove();
		map = null;
		overlay = null;
		mapLoaded = false;
	});

	$effect(() => {
		bubbles;
		selectedClusterId;
		getClusterColor;

		if (!map || !overlay || !mapLoaded) return;
		updateLayer();
	});
</script>

<div class="condensation-3d-wrapper">
	<div bind:this={mapContainer} class="condensation-3d-map"></div>
</div>

<style>
	.condensation-3d-wrapper {
		width: 100%;
		height: 100%;
		min-height: 420px;
		border-radius: 12px;
		overflow: hidden;
		border: 1px solid #e2e8f0;
		background: white;
	}

	.condensation-3d-map {
		width: 100%;
		height: 100%;
		min-height: 420px;
	}
</style>
