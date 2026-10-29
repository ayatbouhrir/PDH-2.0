<script lang="ts">
	import type {
		AnalysisResponse,
		ClusteredPoint,
		ClusterAssignments,
		CondensedBubble,
		DisplayMode,
	} from "$lib/shared/types/analysis-contract";
	import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
	import { onMount, onDestroy, untrack } from "svelte";
	import "leaflet/dist/leaflet.css";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import type { FetchResponse } from "$lib/features/exploration/filtered-points.resource.svelte";
	import * as htmlToImage from "html-to-image";
	import { Button } from "$lib/components/ui/button/index";
	import { fetchBubbleSummary } from "$lib/features/geography/bubble-summary.api";
	import PfasCondensation3DView from "$lib/features/analysis/components/PfasCondensation3DView.svelte";
	import type { CircleMarker } from "leaflet";
	import {
		runHistoryRune,
		type AnalysisHistoryMapState,
		type AnalysisHistoryPanelState,
		type RunHistoryEntry,
	} from "$lib/features/history/run-history.state.svelte";
	import {
		loadHistoryResult,
		type HistoryLoadResponse,
	} from "$lib/features/history/history.api";
	import { getClusterColor } from "$lib/shared/map/cluster-colors";

	import {
		Map as MapIcon,
		Plus,
		Minus,
		ImageDown,
		Crosshair,
		Factory,
	} from "lucide-svelte";
	import {
		Popover,
		PopoverContent,
		PopoverTrigger,
	} from "$lib/components/ui/popover/index";
	import {
		PFAS_SITE_CATEGORY_META,
		PFAS_SITE_CATEGORY_VALUES,
		normalizePfasSiteCategory,
		type PfasPoint,
		type PfasSiteCategory,
		type PfasSitePoint,
	} from "$lib/shared/types/pfas";
	import { tileLayers } from "$lib/shared/map/tile-layers";

	const pointsIcon = "/assets/points.svg";
	const condensedIcon = "/assets/clusters.svg";

	const MAX_RAW_RENDER_POINTS = 250000;
	const MOVE_DEBOUNCE_MS = 200;
	const PFAS_SITES_FETCH_DEBOUNCE_MS = 120;
	const PFAS_SITES_BUTTON_TOP_REM = 19;
	const PFAS_SITES_BUTTON_WITH_3D_TOP_REM = 25;
	const MAX_PFAS_SITE_RENDER_MARKERS = 1400;
	const MAX_PRESUMPTIVE_SITE_RENDER_MARKERS = 1100;

	type PfasSitesApiResponse = {
		data?: PfasSitePoint[];
		total?: number;
		error?: string;
	};

	const pfasSiteOptions = PFAS_SITE_CATEGORY_VALUES.map((category) => ({
		category,
		...PFAS_SITE_CATEGORY_META[category],
	}));

	let birchCondensationLoading = $state(false);
	let birchCondensationLoaded = $state(false);
	let showCondensation3D = $state(false);
	let lastRunAssignments = $state<ClusterAssignments>({});
	let lastPointAnnotations = $state<
		NonNullable<AnalysisResponse["pointAnnotations"]>
	>({});
	let activeHistoryCacheKey = $state<string | null>(null);
	let historyStateSyncSuspended = $state(false);
	let historyStateSaveTimer: ReturnType<typeof setTimeout> | null = null;

	let historyRestoreStep = $state<"idle" | "waiting-filters" | "loading-result">("idle");

	let clusterGeometryLayer: import("leaflet").LayerGroup | null = null;
	let pfasSitesLayerGroup: import("leaflet").LayerGroup | null = null;

	let condensedVisible = $state<CondensedBubble[]>([]);
	let viewportVisibleCount = $state(0);
	let renderedCount = $state(0);
	let pfasSitesVisible = $state<PfasSitePoint[]>([]);
	let pfasSitesViewportCount = $state(0);
	let pfasSitesRenderedCount = $state(0);
	let pfasSitesOpen = $state(false);
	let selectedPfasSiteCategories = $state<PfasSiteCategory[]>([]);
	let pfasSitesLoading = $state(false);
	let pfasSitesError = $state<string | null>(null);
	let pfasSitesAbortController: AbortController | null = null;
	let pfasSitesRequestId = 0;
	let pfasSitesFetchTimer: ReturnType<typeof setTimeout> | null = null;

	const { filteredPoints } = $props<{
		filteredPoints: FetchResponse;
	}>();

	let mapContainer: HTMLDivElement;
	let map: import("leaflet").Map;
	let L: typeof import("leaflet");
	let lasso: any = null;
	let lassoFinishedHandler: ((event: any) => void) | null = null;
	let canvasRenderer: import("leaflet").Renderer;
	let rawPointsLayerGroup: import("leaflet").LayerGroup | null = null;
	let condensedLayerGroup: import("leaflet").LayerGroup | null = null;
	let clampHeatLayer: import("leaflet").Layer | null = null;
	let abortController: AbortController | null = null;
	let moveTimer: ReturnType<typeof setTimeout> | null = null;
	let isInternalMapUpdate = false;

	let visible = $state<PfasPoint[]>([]);
	let clusteredVisible = $state<ClusteredPoint[]>([]);

	let analysisInfo = $state({
		analyzedPoints: 0,
		clusterCount: 0,
		noiseCount: 0,
		durationMs: 0,
		tooMany: false,
		message: "Clique sur Run analysis.",
		cached: false,
	});

	let tileLayerIndex = $state(4);
	let currentTileLayer: import("leaflet").TileLayer | null = null;

	let requestId = 0;
	let lastProcessedRunToken = 0;

	function toggle3DPanel() {
		showCondensation3D = !showCondensation3D;
	}

	function escapeHtml(value: unknown): string {
		return String(value ?? "")
			.replaceAll("&", "&amp;")
			.replaceAll("<", "&lt;")
			.replaceAll(">", "&gt;")
			.replaceAll('"', "&quot;")
			.replaceAll("'", "&#039;");
	}

	function buildCondensedTooltipHtml(
		groupId: string | number,
		total: number,
		producerCount: number,
		userCount: number,
		presumedCount: number,
		loading = false,
	): string {
		const label =
			groupId === -1 || String(groupId) === "-1"
				? "Noise"
				: `C${escapeHtml(groupId)}`;

		return `
			<div style="font-size: 14px; line-height: 1.45;">
				<div><strong>Groupe :</strong> ${label}</div>
				<div><strong>Total :</strong> ${escapeHtml(total)}</div>
				<div><strong>Producteur PFAS :</strong> ${
					loading ? "..." : escapeHtml(producerCount)
				}</div>
				<div><strong>User PFAS :</strong> ${
					loading ? "..." : escapeHtml(userCount)
				}</div>
				<div><strong>Présumés :</strong> ${
					loading ? "..." : escapeHtml(presumedCount)
				}</div>
				<div style="margin-top:6px; font-weight:600; color:#1d4ed8;">
					Cliquer pour plus de détails
				</div>
			</div>
		`;
	}

	async function enrichBubbleTooltip(
		layer: CircleMarker,
		bubble: {
			groupId: string | number;
			count: number;
			pointIds: Array<string | number>;
			producerCount?: number;
			userCount?: number;
			presumedCount?: number;
		},
	) {
		layer.bindTooltip(
			buildCondensedTooltipHtml(
				bubble.groupId,
				bubble.count,
				bubble.producerCount ?? 0,
				bubble.userCount ?? 0,
				bubble.presumedCount ?? 0,
				true,
			),
			{ sticky: true, direction: "top", opacity: 0.95 },
		);

		try {
			const res = await fetchBubbleSummary(bubble.pointIds, 50);

			bubble.producerCount = res.summary.producerCount;
			bubble.userCount = res.summary.userCount;
			bubble.presumedCount = res.summary.presumedCount;

			layer.setTooltipContent(
				buildCondensedTooltipHtml(
					bubble.groupId,
					bubble.count,
					bubble.producerCount,
					bubble.userCount,
					bubble.presumedCount,
					false,
				),
			);
		} catch (err) {
			console.error("[enrichBubbleTooltip]", err);

			layer.setTooltipContent(
				buildCondensedTooltipHtml(
					bubble.groupId,
					bubble.count,
					0,
					0,
					0,
					false,
				),
			);
		}
	}

	function resetClusterSelection() {
		analysisRune.selectedClusterId = null;
		dataRune.selectedClusterInfo = null;
		dataRune.selectedCondensedGroup = null;
		dataRune.selectedPoints = [];
		dataRune.selectedBubblePointIds = [];
		dataRune.detailsContext = "all";
		dataRune.clusterGeometryRequest = null;
		clearClusterGeometry();
		updateMap();
	}

	function showAllClusters() {
		resetClusterSelection();
	}

	function selectPoint(point: ClusteredPoint) {
		const clusterId = Number(point.clusterId);
		const raw = (point.raw ?? {}) as Record<string, unknown>;

		const summary = analysisRune.clusterSummaries.find(
			(s) => s.clusterId === clusterId,
		);

		analysisRune.selectedClusterId = Number.isFinite(clusterId)
			? clusterId
			: null;

		dataRune.selectedClusterInfo = summary
			? {
					...summary,
					color: getClusterColor(clusterId),
					algorithm: analysisRune.algorithm,
				}
			: null;

		dataRune.selectedCondensedGroup = null;
		dataRune.detailsContext = "point";
		dataRune.selectedBubblePointIds = [];
		dataRune.clusterGeometryRequest = null;

		dataRune.selectedPoints = [
			{
				...(raw as object),
				id: point.pointId ?? raw.id,
				lat: Number(point.lat),
				lon: Number(point.lon),
				pfas_sum: point.pfasSum ?? raw.pfas_sum ?? null,
				clusterId,
			} as unknown as PfasPoint,
		];

		clearClusterGeometry();
		updateMap();
	}

	function selectCluster(
		clusterId: number,
		summary: any,
		bubblePointIds: Array<string | number> = [],
	) {
		analysisRune.selectedClusterId = clusterId;
		analysisRune.resetClusterFocusIndex(clusterId);

		dataRune.selectedClusterInfo = summary
			? {
					...summary,
					color: getClusterColor(clusterId),
					algorithm: analysisRune.algorithm,
				}
			: null;

		const pointIds =
			bubblePointIds.length > 0
				? [...bubblePointIds]
				: clusteredVisible
						.filter((p) => Number(p.clusterId) === clusterId)
						.map((p) => p.pointId ?? `${p.lat},${p.lon}`);

		dataRune.selectedCondensedGroup = null;
		dataRune.selectedPoints = [];
		dataRune.selectedBubblePointIds = pointIds;
		dataRune.detailsContext = "cluster";
		dataRune.clusterGeometryRequest = null;

		clearClusterGeometry();
		updateMap();
	}

	function selectCondensedGroup(bubble: CondensedBubble, summary: any) {
		const parentClusterId = bubble.parentClusterId;

		analysisRune.selectedClusterId = Number.isFinite(parentClusterId)
			? parentClusterId
			: null;

		dataRune.selectedClusterInfo = summary
			? {
					...summary,
					color: getClusterColor(parentClusterId),
					algorithm: analysisRune.algorithm,
				}
			: null;

		dataRune.selectedCondensedGroup = {
			groupId: bubble.groupId,
			lat: bubble.lat,
			lon: bubble.lon,
			count: bubble.count,
			producerCount: bubble.producerCount ?? 0,
			userCount: bubble.userCount ?? 0,
			presumedCount: bubble.presumedCount ?? 0,
			groupType: bubble.groupType,
		};

		dataRune.selectedPoints = [];
		dataRune.selectedBubblePointIds = [...bubble.pointIds];
		dataRune.detailsContext = "condensed_group";
		dataRune.clusterGeometryRequest = null;

		clearClusterGeometry();
		updateMap();
	}

	function getClusterMarkerStyle(clusterId: number, groupSize: number) {
		const selected = analysisRune.selectedClusterId;
		const isActive = selected === null || clusterId === selected;
		const isNoise = clusterId === -1;

		if (isNoise) {
			return {
				radius: isActive ? 5 : 3.5,
				color: isActive ? "#111827" : "#9ca3af",
				weight: isActive ? 1.2 : 0.4,
				fillColor: "#6b7280",
				fillOpacity: isActive ? 0.9 : 0.18,
				opacity: isActive ? 1 : 0.18,
				renderer: canvasRenderer,
			};
		}

		return {
			radius: isActive
				? groupSize > 1
					? 5 + 0.25 * Math.sqrt(groupSize)
					: 5
				: groupSize > 1
					? 3.5
					: 3,
			color: isActive ? "#334155" : "#f3c4cf",
			weight: isActive ? 1.2 : 0.25,
			fillColor: getClusterColor(clusterId),
			fillOpacity: isActive ? 0.92 : 0.12,
			opacity: isActive ? 1 : 0.12,
			renderer: canvasRenderer,
		};
	}

	function getClampMarkerStyle(
		point: ClusteredPoint,
		coveredPointIds: Set<string>,
		activeRuleClusterId: number,
	) {
		const pointId = point.pointId != null ? String(point.pointId) : null;
		const clusterId = Number(point.clusterId);
		const isCovered = pointId != null && coveredPointIds.has(pointId);
		const isSameCluster = clusterId === activeRuleClusterId;
		const clusterColor = getClusterColor(activeRuleClusterId);

		if (isCovered) {
			return {
				radius: 7,
				color: "#111827",
				weight: 2,
				fillColor: clusterColor,
				fillOpacity: 1,
				opacity: 1,
				renderer: canvasRenderer,
			};
		}

		if (isSameCluster) {
			return {
				radius: 4,
				color: "#334155",
				weight: 1,
				fillColor: clusterColor,
				fillOpacity: 0.25,
				opacity: 0.45,
				renderer: canvasRenderer,
			};
		}

		return {
			radius: 3,
			color: "#9ca3af",
			weight: 0,
			fillColor: "#94a3b8",
			fillOpacity: 0.08,
			opacity: 0.14,
			renderer: canvasRenderer,
		};
	}

	function hexToRgb(hexColor: string): { r: number; g: number; b: number } | null {
		const sanitized = String(hexColor ?? "").trim().replace("#", "");
		if (!/^[0-9a-f]{6}$/iu.test(sanitized)) return null;

		return {
			r: Number.parseInt(sanitized.slice(0, 2), 16),
			g: Number.parseInt(sanitized.slice(2, 4), 16),
			b: Number.parseInt(sanitized.slice(4, 6), 16),
		};
	}

	function rgbaFromHex(hexColor: string, alpha: number): string {
		const rgb = hexToRgb(hexColor);
		if (!rgb) return `rgba(245, 158, 11, ${alpha})`;
		return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
	}

	function getClampHeatGradient(clusterId: number) {
		const clusterColor = getClusterColor(clusterId);
		return {
			0.2: rgbaFromHex(clusterColor, 0.18),
			0.45: rgbaFromHex(clusterColor, 0.38),
			0.7: rgbaFromHex(clusterColor, 0.66),
			1.0: rgbaFromHex(clusterColor, 0.92),
		};
	}

	function getDisplayMode(): DisplayMode {
		return analysisRune.displayMode ?? "points";
	}

	async function toggleDisplayMode() {
		if (analysisRune.displayMode === "condensed") {
			analysisRune.displayMode = "points";
			showCondensation3D = false;
			updateMap();
			return;
		}

		if (!birchCondensationLoaded && clusteredVisible.length > 0) {
			await loadBirchCondensation();
		}

		if (condensedVisible.length > 0) {
			analysisRune.displayMode = "condensed";
			updateMap();
			return;
		}

		analysisInfo = {
			...analysisInfo,
			message: "Aucune condensation disponible.",
		};
		updateMap();
	}

	function getToggleIcon() {
		return analysisRune.displayMode === "points" ? condensedIcon : pointsIcon;
	}

	function getToggleAlt() {
		return analysisRune.displayMode === "points" ? "Clusters" : "Points";
	}

	function getToggleTitle() {
		return analysisRune.displayMode === "points"
			? "Afficher les regroupements condensés"
			: "Afficher les points";
	}

	function shouldShow3DButton() {
		return (
			birchCondensationLoaded &&
			condensedVisible.length > 0 &&
			analysisRune.displayMode === "condensed"
		);
	}

	function getPfasSitesButtonTopRem() {
		return shouldShow3DButton()
			? PFAS_SITES_BUTTON_WITH_3D_TOP_REM
			: PFAS_SITES_BUTTON_TOP_REM;
	}

	function isAllPfasSiteCategoriesSelected() {
		return selectedPfasSiteCategories.length === PFAS_SITE_CATEGORY_VALUES.length;
	}

	function isPfasSiteCategorySelected(category: PfasSiteCategory) {
		return selectedPfasSiteCategories.includes(category);
	}

	function togglePfasSitesPanel() {
		pfasSitesOpen = !pfasSitesOpen;
	}

	function setSelectedPfasSiteCategories(categories: PfasSiteCategory[]) {
		selectedPfasSiteCategories = Array.from(new Set(categories));
	}

	function toggleAllPfasSiteCategories() {
		if (isAllPfasSiteCategoriesSelected()) {
			setSelectedPfasSiteCategories([]);
			return;
		}

		setSelectedPfasSiteCategories([...PFAS_SITE_CATEGORY_VALUES]);
	}

	function togglePfasSiteCategory(category: PfasSiteCategory) {
		if (isPfasSiteCategorySelected(category)) {
			setSelectedPfasSiteCategories(
				selectedPfasSiteCategories.filter((value) => value !== category),
			);
			return;
		}

		setSelectedPfasSiteCategories([...selectedPfasSiteCategories, category]);
	}

	function buildPfasSitesPayload() {
		const filtersSnapshot = $state.snapshot(dataRune.filters);
		const areaMode = dataRune.areaSelectorMode;

		return {
			categories: [...selectedPfasSiteCategories],
			areaMode,
			filters: {
				nutsRegions:
					areaMode === "NUTS" ? [...(filtersSnapshot.nutsRegions ?? [])] : [],
				lassoRegion:
					areaMode === "LASSO" ? [...(filtersSnapshot.lassoRegion ?? [])] : [],
			},
		};
	}

	async function fetchPfasSites() {
		if (selectedPfasSiteCategories.length === 0) {
			pfasSitesAbortController?.abort();
			pfasSitesAbortController = null;
			pfasSitesVisible = [];
			pfasSitesError = null;
			pfasSitesLoading = false;
			updateMap();
			return;
		}

		pfasSitesAbortController?.abort();
		pfasSitesAbortController = new AbortController();
		const currentRequestId = ++pfasSitesRequestId;

		pfasSitesLoading = true;
		pfasSitesError = null;

		try {
			const response = await fetch("/api/pfas-sites", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
				},
				body: JSON.stringify(buildPfasSitesPayload()),
				signal: pfasSitesAbortController.signal,
			});

			const result =
				(await response.json().catch(() => null)) as PfasSitesApiResponse | null;

			if (currentRequestId !== pfasSitesRequestId) return;

			if (!response.ok) {
				throw new Error(
					result?.error ??
						`Erreur pendant le chargement des sites PFAS (${response.status}).`,
				);
			}

			pfasSitesVisible = (result?.data ?? []).filter((site) => {
				const lat = Number(site.lat);
				const lon = Number(site.lon);
				const category = normalizePfasSiteCategory(site.category);
				return Number.isFinite(lat) && Number.isFinite(lon) && category !== null;
			});
			pfasSitesError = null;
		} catch (error: unknown) {
			if (error instanceof DOMException && error.name === "AbortError") {
				return;
			}

			if (currentRequestId !== pfasSitesRequestId) return;

			console.error("[fetchPfasSites]", error);
			pfasSitesVisible = [];
			pfasSitesError =
				error instanceof Error
					? error.message
					: "Impossible de charger les sites PFAS.";
		} finally {
			if (currentRequestId === pfasSitesRequestId) {
				pfasSitesLoading = false;
				updateMap();
			}
		}
	}

	function buildPfasSiteTooltipHtml(site: PfasSitePoint, category: PfasSiteCategory) {
		const name = escapeHtml(site.name || PFAS_SITE_CATEGORY_META[category].label);
		const label = escapeHtml(PFAS_SITE_CATEGORY_META[category].label);

		return `<div style="font-size: 13px; line-height: 1.4;"><strong>${name}</strong><br>${label}</div>`;
	}

	function buildPfasSiteMarkerHtml(category: PfasSiteCategory) {
		const meta = PFAS_SITE_CATEGORY_META[category];
		const borderShadow =
			meta.borderColor === "#000000"
				? "-1px -1px 0 #000000, 1px -1px 0 #000000, -1px 1px 0 #000000, 1px 1px 0 #000000"
				: "-1px -1px 0 #FFFFFF, 1px -1px 0 #FFFFFF, -1px 1px 0 #FFFFFF, 1px 1px 0 #FFFFFF";

		return `<span class="pfas-site-marker-symbol" style="color:${meta.color}; text-shadow:${borderShadow};">${meta.symbol}</span>`;
	}

	function selectPfasSite(site: PfasSitePoint) {
		analysisRune.selectedClusterId = null;
		dataRune.selectedClusterInfo = null;
		dataRune.selectedCondensedGroup = null;
		dataRune.selectedBubblePointIds = [];
		dataRune.clusterGeometryRequest = null;
		dataRune.selectedPoints = [site as PfasPoint];
		dataRune.detailsContext = "point";
		clearClusterGeometry();
		updateMap();
	}

	function getBubbleRadius(count: number): number {
		if (count <= 1) return 4;
		return Math.min(16, 4 + Math.log2(count + 1) * 2);
	}

	function getCondensedBubbleStyle(parentClusterId: number, count: number) {
		const selected = analysisRune.selectedClusterId;
		const isNoise = parentClusterId === -1;
		const isActive = selected === null || parentClusterId === selected;

		return {
			radius: isActive
				? getBubbleRadius(count)
				: Math.max(4, getBubbleRadius(count) * 0.7),
			color: isActive ? "#111827" : "#cbd5e1",
			weight: isActive ? 1.2 : 0.5,
			fillColor: getClusterColor(parentClusterId),
			fillOpacity: isNoise
				? isActive
					? 0.55
					: 0.12
				: isActive
					? 0.72
					: 0.16,
			opacity: isActive ? 1 : 0.2,
		};
	}

	export function invalidateMapSize() {
		if (!map) return;

		isInternalMapUpdate = true;
		map.invalidateSize();

		requestAnimationFrame(() => {
			isInternalMapUpdate = false;
		});
	}

	function invalidatePendingAnalysis() {
		requestId += 1;
		abortController?.abort();
		abortController = null;
		analysisRune.isRunning = false;
	}

	function clearMapShapes() {
		rawPointsLayerGroup?.clearLayers();
		condensedLayerGroup?.clearLayers();
		pfasSitesLayerGroup?.clearLayers();
		if (clampHeatLayer && map) {
			map.removeLayer(clampHeatLayer);
			clampHeatLayer = null;
		}
	}

	function clearClusterGeometry() {
		clusterGeometryLayer?.clearLayers();
	}

	function getCurrentViewport(map: import("leaflet").Map) {
		const bounds = map.getBounds();

		return {
			south: bounds.getSouth(),
			west: bounds.getWest(),
			north: bounds.getNorth(),
			east: bounds.getEast(),
		};
	}

	function getPointStableId(point: Record<string, unknown> | PfasPoint | null | undefined) {
		if (!point) return null;
		const rawPoint = point as Record<string, unknown>;
		return rawPoint["point_id"] ?? rawPoint["id"] ?? null;
	}

	function buildCurrentMapState(): AnalysisHistoryMapState {
		return {
			viewport: map ? getCurrentViewport(map) : null,
			displayMode: analysisRune.displayMode ?? "points",
			tileLayerIndex,
		};
	}

	function buildCurrentPanelState(): AnalysisHistoryPanelState {
		return {
			detailsContext: dataRune.detailsContext,
			selectedClusterId: analysisRune.selectedClusterId ?? null,
			selectedPointIds: dataRune.selectedPoints
				.map((point) => getPointStableId(point as unknown as Record<string, unknown>))
				.filter((value): value is string | number => value != null),
			selectedBubblePointIds: [...dataRune.selectedBubblePointIds],
			selectedCondensedGroup: dataRune.selectedCondensedGroup
				? { ...dataRune.selectedCondensedGroup }
				: null,
			clusterGeometryRequest: dataRune.clusterGeometryRequest
				? { ...dataRune.clusterGeometryRequest }
				: null,
			showCondensation3D,
		};
	}

	async function persistHistoryState(cacheKey: string) {
		const mapState = buildCurrentMapState();
		const panelState = buildCurrentPanelState();

		runHistoryRune.updateLocalState(cacheKey, {
			mapState,
			panelState,
		});

		try {
			const response = await fetch("/api/analysis/history/state", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					cacheKey,
					mapState,
					panelState,
				}),
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			const payload = await response.json();
			runHistoryRune.mergeServerEntry(payload?.entry ?? null);
		} catch (error) {
			console.error("[persistHistoryState]", error);
		}
	}

	function scheduleHistoryStatePersistence(delay = 300) {
		if (!activeHistoryCacheKey || historyStateSyncSuspended) return;

		if (historyStateSaveTimer) {
			clearTimeout(historyStateSaveTimer);
		}

		historyStateSaveTimer = setTimeout(() => {
			historyStateSaveTimer = null;

			if (!activeHistoryCacheKey || historyStateSyncSuspended) {
				return;
			}

			void persistHistoryState(activeHistoryCacheKey);
		}, delay);
	}

	function findClusterSummaryById(clusterId: number | null | undefined) {
		if (clusterId == null) return null;
		return (
			analysisRune.clusterSummaries.find((summary) => summary.clusterId === clusterId) ??
			null
		);
	}

	function buildSelectedClusterInfo(clusterId: number | null | undefined) {
		const summary = findClusterSummaryById(clusterId);
		if (!summary || clusterId == null) {
			return null;
		}

		return {
			...summary,
			color: getClusterColor(clusterId),
			algorithm: analysisRune.algorithm,
		};
	}

	function getPointAnnotation(pointId: string | number | null | undefined) {
		if (pointId == null) return null;
		return lastPointAnnotations[String(pointId)] ?? null;
	}

	function buildClusteredPointFromSource(
		point: PfasPoint,
		assignments: ClusterAssignments,
	): ClusteredPoint | null {
		const pointId = point.id;
		const stableId = String(pointId);
		const clusterId = assignments[stableId];

		if (clusterId == null) {
			return null;
		}

		const annotation = getPointAnnotation(pointId);

		return {
			pointId,
			lat: Number(point.lat),
			lon: Number(point.lon),
			pfasSum: point.pfas_sum ?? null,
			clusterId,
			raw: {
				...(point as unknown as Record<string, unknown>),
				membershipProbability: annotation?.membershipProbability ?? null,
				outlierScore: annotation?.outlierScore ?? null,
			},
		};
	}

	function buildClusteredVisibleFromAssignments(
		assignments: ClusterAssignments,
		sourcePoints: PfasPoint[] | undefined,
	): ClusteredPoint[] {
		if (!sourcePoints?.length) {
			return [];
		}

		return sourcePoints
			.map((point) => buildClusteredPointFromSource(point, assignments))
			.filter((point): point is ClusteredPoint => point !== null);
	}

	function restorePanelState(
		panelState: AnalysisHistoryPanelState | null | undefined,
	) {
		const restored = panelState ?? null;

		dataRune.selectedCondensedGroup = restored?.selectedCondensedGroup ?? null;
		dataRune.clusterGeometryRequest = restored?.clusterGeometryRequest ?? null;
		showCondensation3D = Boolean(restored?.showCondensation3D);

		const selectedClusterId =
			restored?.selectedClusterId != null ? restored.selectedClusterId : null;
		analysisRune.selectedClusterId = selectedClusterId;
		dataRune.selectedClusterInfo = buildSelectedClusterInfo(selectedClusterId);

		const selectedPointIds = new Set(
			(restored?.selectedPointIds ?? []).map((value) => String(value)),
		);

		dataRune.selectedPoints =
			selectedPointIds.size > 0
				? clusteredVisible
						.filter((point) => {
							const stableId = point.pointId ?? getPointStableId(point.raw);
							return stableId != null && selectedPointIds.has(String(stableId));
						})
						.map((point) => ({
							...(point.raw as object),
							id: point.pointId ?? point.raw.id,
							lat: Number(point.lat),
							lon: Number(point.lon),
							pfas_sum: point.pfasSum ?? point.raw.pfas_sum ?? null,
							clusterId: Number(point.clusterId),
						}) as unknown as PfasPoint)
				: [];

		if (Array.isArray(restored?.selectedBubblePointIds)) {
			dataRune.selectedBubblePointIds = [...restored.selectedBubblePointIds];
		} else if (selectedClusterId != null) {
			dataRune.selectedBubblePointIds = clusteredVisible
				.filter((point) => Number(point.clusterId) === selectedClusterId)
				.map((point) => point.pointId ?? `${point.lat},${point.lon}`);
		} else {
			dataRune.selectedBubblePointIds = [];
		}

		dataRune.detailsContext = restored?.detailsContext ?? "all";
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

		scheduleHistoryStatePersistence();
	}

	function computeVisiblePoints() {
		if (!filteredPoints.data?.length) {
			visible = [];
			viewportVisibleCount = 0;
			return;
		}

		const allPoints = filteredPoints.data.filter((p: PfasPoint) => {
			const lat = Number(p.lat);
			const lon = Number(p.lon);
			return Number.isFinite(lat) && Number.isFinite(lon);
		});

		visible = allPoints;

		if (!map) {
			viewportVisibleCount = allPoints.length;
			return;
		}

		const bounds = map.getBounds();
		viewportVisibleCount = allPoints.filter((p: PfasPoint) => {
			const lat = Number(p.lat);
			const lon = Number(p.lon);
			return bounds.contains([lat, lon]);
		}).length;
	}

	function drawRawVisiblePoints(pointsToDraw: PfasPoint[]) {
		if (!rawPointsLayerGroup) return;

		renderedCount = 0;

		const grouped = new Map<string, PfasPoint[]>();

		for (const point of pointsToDraw) {
			if (point.lat == null || point.lon == null) continue;

			const key = `${point.lat},${point.lon}`;
			if (!grouped.has(key)) grouped.set(key, []);
			grouped.get(key)!.push(point);
		}

		for (const [key, group] of grouped) {
			const [lat, lon] = key.split(",").map(Number);

			const marker = L.circleMarker([lat, lon], {
				radius: group.length > 1 ? 4 + 0.2 * Math.sqrt(group.length) : 4,
				color: "#475569",
				weight: 1,
				fillColor: "#94a3b8",
				fillOpacity: 0.85,
				renderer: canvasRenderer,
			});

			marker
				.bindTooltip(
					`<strong>${group.length} point${group.length > 1 ? "s" : ""}</strong>`,
				)
				.addTo(rawPointsLayerGroup)
				.on("click", () => {
					analysisRune.selectedClusterId = null;
					dataRune.selectedClusterInfo = null;
					dataRune.selectedCondensedGroup = null;
					dataRune.selectedBubblePointIds = [];
					dataRune.clusterGeometryRequest = null;
					dataRune.selectedPoints = group;
					dataRune.detailsContext = "point";
					clearClusterGeometry();
					updateMap();
				});

			renderedCount += group.length;
		}
	}

	function offsetOverlappingPoints(points: ClusteredPoint[]): ClusteredPoint[] {
		const groups = new Map<string, ClusteredPoint[]>();

		for (const p of points) {
			const key = `${Number(p.lat).toFixed(6)},${Number(p.lon).toFixed(6)},${p.clusterId}`;
			if (!groups.has(key)) groups.set(key, []);
			groups.get(key)!.push(p);
		}

		const result: ClusteredPoint[] = [];

		for (const group of groups.values()) {
			if (group.length === 1) {
				result.push(group[0]);
				continue;
			}

			const radius = 0.00008;
			const step = (2 * Math.PI) / group.length;

			group.forEach((p, i) => {
				const angle = i * step;
				result.push({
					...p,
					lat: Number(p.lat) + radius * Math.sin(angle),
					lon: Number(p.lon) + radius * Math.cos(angle),
				});
			});
		}

		return result;
	}

	function drawClusteredPoints() {
		if (!rawPointsLayerGroup) return;

		renderedCount = 0;

		const pointsToDraw = offsetOverlappingPoints(clusteredVisible);
		const activeClampRule =
			analysisRune.isClampMapMode ? analysisRune.activeClampRule : null;
		const coveredPointIds = new Set(
			(activeClampRule?.coveredPointIds ?? []).map((pointId) => String(pointId)),
		);

		for (const point of pointsToDraw) {
			const clusterId = Number(point.clusterId);
			const markerStyle = activeClampRule
				? getClampMarkerStyle(point, coveredPointIds, activeClampRule.cluster)
				: getClusterMarkerStyle(clusterId, 1);

			const marker = L.circleMarker(
				[Number(point.lat), Number(point.lon)],
				markerStyle,
			);

			marker
				.bindTooltip(
					`${
						clusterId === -1
							? "<strong>Noise / Outlier</strong>"
							: `<strong>Cluster ${clusterId}</strong>`
					}<br>PFAS sum: ${Math.round(Number(point.pfasSum ?? 0)).toLocaleString("fr-FR")}`,
				)
				.addTo(rawPointsLayerGroup)
				.on("click", (e: any) => {
					if (e?.originalEvent) {
						L.DomEvent.stopPropagation(e.originalEvent);
					}
					selectPoint(point);
				});

			renderedCount += 1;
		}
	}

	function drawClampHeatLayer() {
		if (!map || !L || !analysisRune.activeClampRule) return;

		const coveredPointIds = new Set(
			analysisRune.selectedClampCoveredPointIds.map((pointId) => String(pointId)),
		);
		if (coveredPointIds.size === 0) return;

		const heatPoints = clusteredVisible
			.filter((point) => {
				if (point.pointId == null) return false;
				return coveredPointIds.has(String(point.pointId));
			})
			.map((point) => [Number(point.lat), Number(point.lon), 1] as [number, number, number])
			.filter(
				(coords) => Number.isFinite(coords[0]) && Number.isFinite(coords[1]),
			);

		if (heatPoints.length === 0) return;

		const heatLayerFactory = (L as any).heatLayer;
		if (typeof heatLayerFactory !== "function") {
			console.warn("[Clamp heatmap] leaflet.heat n'est pas disponible.");
			return;
		}

		try {
			clampHeatLayer = heatLayerFactory(heatPoints, {
				radius: 24,
				blur: 16,
				maxZoom: 11,
				minOpacity: 0.34,
				gradient: getClampHeatGradient(analysisRune.activeClampRule.cluster),
			}).addTo(map);
		} catch (error) {
			console.error("[Clamp heatmap] Rendu impossible:", error);
			clampHeatLayer = null;
		}
	}

	function drawCondensedBubbles() {
		if (!condensedLayerGroup) return;

		renderedCount = 0;

		for (const bubble of condensedVisible) {
			const style = getCondensedBubbleStyle(bubble.parentClusterId, bubble.count);
			const parentClusterId = bubble.parentClusterId;

			const marker = L.circleMarker([bubble.lat, bubble.lon], {
				radius: style.radius,
				color: style.color,
				weight: style.weight,
				fillColor: style.fillColor,
				fillOpacity: style.fillOpacity,
				opacity: style.opacity,
				renderer: canvasRenderer,
			});

			marker.bindTooltip(
				buildCondensedTooltipHtml(
					bubble.groupId,
					bubble.count,
					bubble.producerCount ?? 0,
					bubble.userCount ?? 0,
					bubble.presumedCount ?? 0,
					true,
				),
				{
					sticky: true,
					direction: "top",
					opacity: 0.95,
				},
			);

			marker.on("mouseover", () => {
				void enrichBubbleTooltip(marker, bubble);
			});

			marker.on("click", (e: any) => {
				if (e?.originalEvent) {
					L.DomEvent.stopPropagation(e.originalEvent);
				}

				void enrichBubbleTooltip(marker, bubble);

				const summary = analysisRune.clusterSummaries.find(
					(s) => s.clusterId === parentClusterId,
				);
				selectCondensedGroup(bubble, summary);
				marker.openTooltip();
			});

			marker.addTo(condensedLayerGroup);
			renderedCount += 1;
		}
	}

	function getPfasSitesInViewport() {
		if (!map || pfasSitesVisible.length === 0) return [];

		const bounds = map.getBounds();

		return pfasSitesVisible.filter((site) => {
			const lat = Number(site.lat);
			const lon = Number(site.lon);

			return (
				Number.isFinite(lat) &&
				Number.isFinite(lon) &&
				bounds.contains([lat, lon])
			);
		});
	}

	function getPresumptiveSamplingGridSizePx(presumptiveCount: number) {
		const zoom = map?.getZoom() ?? 5;
		const baseGridSize =
			zoom <= 4
				? 48
				: zoom <= 5
					? 38
					: zoom <= 6
						? 30
						: zoom <= 7
							? 24
							: zoom <= 8
								? 20
								: 16;
		const densityRatio = presumptiveCount / MAX_PRESUMPTIVE_SITE_RENDER_MARKERS;

		return Math.min(84, Math.max(baseGridSize, Math.round(baseGridSize * Math.sqrt(densityRatio))));
	}

	function getRenderablePfasSites() {
		const viewportSites = getPfasSitesInViewport();
		if (!map || viewportSites.length === 0) {
			return {
				viewportSites,
				renderedSites: [] as PfasSitePoint[],
			};
		}

		const renderedSites: PfasSitePoint[] = [];
		const presumptiveSites: PfasSitePoint[] = [];

		for (const site of viewportSites) {
			const category = normalizePfasSiteCategory(site.category);
			if (!category) continue;

			if (category === "Presumptive") {
				presumptiveSites.push(site);
				continue;
			}

			renderedSites.push(site);
		}

		const remainingBudget = Math.max(
			0,
			MAX_PFAS_SITE_RENDER_MARKERS - renderedSites.length,
		);

		if (
			presumptiveSites.length === 0 ||
			presumptiveSites.length <= remainingBudget
		) {
			return {
				viewportSites,
				renderedSites: [...renderedSites, ...presumptiveSites].slice(
					0,
					MAX_PFAS_SITE_RENDER_MARKERS,
				),
			};
		}

		const gridSizePx = getPresumptiveSamplingGridSizePx(presumptiveSites.length);
		const sampledPresumptiveSites = new Map<string, PfasSitePoint>();

		for (const site of presumptiveSites) {
			const point = map.latLngToContainerPoint([Number(site.lat), Number(site.lon)]);
			const bucketKey = `${Math.floor(point.x / gridSizePx)}:${Math.floor(point.y / gridSizePx)}`;

			if (sampledPresumptiveSites.has(bucketKey)) continue;

			sampledPresumptiveSites.set(bucketKey, site);

			if (sampledPresumptiveSites.size >= remainingBudget) {
				break;
			}
		}

		return {
			viewportSites,
			renderedSites: [...renderedSites, ...sampledPresumptiveSites.values()],
		};
	}

	function drawPfasSites() {
		if (!pfasSitesLayerGroup || !map || pfasSitesVisible.length === 0) {
			pfasSitesViewportCount = 0;
			pfasSitesRenderedCount = 0;
			return;
		}

		const { viewportSites, renderedSites } = getRenderablePfasSites();
		pfasSitesViewportCount = viewportSites.length;
		pfasSitesRenderedCount = renderedSites.length;

		if (renderedSites.length === 0) return;

		for (const site of renderedSites) {
			const category = normalizePfasSiteCategory(site.category);
			if (!category) continue;

			const marker = L.marker([Number(site.lat), Number(site.lon)], {
				icon: L.divIcon({
					className: "pfas-site-div-icon",
					html: buildPfasSiteMarkerHtml(category),
					iconSize: [18, 18],
					iconAnchor: [9, 9],
				}),
			});

			marker
				.bindTooltip(buildPfasSiteTooltipHtml(site, category), {
					sticky: true,
					direction: "top",
					opacity: 0.95,
				})
				.addTo(pfasSitesLayerGroup)
				.on("click", (event: any) => {
					if (event?.originalEvent) {
						L.DomEvent.stopPropagation(event.originalEvent);
					}

					selectPfasSite(site);
				});
		}
	}

	function showClusterGeometry(clusterInfo: any, req: any) {
		if (!map || !L || !clusterGeometryLayer || !clusterInfo || !req) return;

		clearClusterGeometry();

		const {
			centroidLat,
			centroidLon,
			minPointLat,
			minPointLon,
			maxPointLat,
			maxPointLon,
		} = clusterInfo;

		const hasCenter = centroidLat != null && centroidLon != null;
		const hasMin = minPointLat != null && minPointLon != null;
		const hasMax = maxPointLat != null && maxPointLon != null;

		if (!hasCenter && !hasMin && !hasMax) return;

		const centerLatLng = hasCenter ? L.latLng(centroidLat, centroidLon) : null;
		const minLatLng = hasMin ? L.latLng(minPointLat, minPointLon) : null;
		const maxLatLng = hasMax ? L.latLng(maxPointLat, maxPointLon) : null;

		function sameLatLng(a: any, b: any) {
			if (!a || !b) return false;
			return (
				Math.abs(a.lat - b.lat) < 1e-10 &&
				Math.abs(a.lng - b.lng) < 1e-10
			);
		}

		const centerEqualsMin = sameLatLng(centerLatLng, minLatLng);
		const centerEqualsMax = sameLatLng(centerLatLng, maxLatLng);
		const minEqualsMax = sameLatLng(minLatLng, maxLatLng);

		const pointsForBounds: any[] = [];

		if (req.showCentroid && centerLatLng) pointsForBounds.push(centerLatLng);
		if (req.showMin && minLatLng) pointsForBounds.push(minLatLng);
		if (req.showMax && maxLatLng) pointsForBounds.push(maxLatLng);

		if (pointsForBounds.length === 0) return;

		const centroidIcon = L.divIcon({
			className: "cluster-centroid-star",
			html: "★",
			iconSize: [24, 24],
			iconAnchor: [12, 12],
		});

		if (req.showCentroid && centerLatLng) {
			L.marker(centerLatLng, {
				icon: centroidIcon,
			})
				.bindTooltip(
					`<strong>Centre représentatif</strong><br>Point réel le plus proche du centroïde de concentration`,
				)
				.addTo(clusterGeometryLayer);
		}

		if (req.showMin && minLatLng && !(req.showCentroid && centerEqualsMin)) {
			L.circleMarker(minLatLng, {
				radius: 7,
				color: "#111827",
				weight: 2,
				fillColor: "#22c55e",
				fillOpacity: 1,
				renderer: canvasRenderer,
			})
				.bindTooltip(
					`<strong>Point min</strong><br>Distance minimale au centroïde de concentration`,
				)
				.addTo(clusterGeometryLayer);
		}

		if (req.showMax && maxLatLng && !(req.showCentroid && centerEqualsMax)) {
			L.circleMarker(maxLatLng, {
				radius: 7,
				color: "#111827",
				weight: 2,
				fillColor: "#ef4444",
				fillOpacity: 1,
				renderer: canvasRenderer,
			})
				.bindTooltip(
					`<strong>Point max</strong><br>Distance maximale au centroïde de concentration`,
				)
				.addTo(clusterGeometryLayer);
		}

		if (req.showCentroid && req.showMin && centerLatLng && minLatLng && !centerEqualsMin) {
			L.polyline(
				[
					[centerLatLng.lat, centerLatLng.lng],
					[minLatLng.lat, minLatLng.lng],
				],
				{
					color: "#22c55e",
					weight: 4,
					opacity: 0.95,
				},
			).addTo(clusterGeometryLayer);
		}

		if (req.showCentroid && req.showMax && centerLatLng && maxLatLng && !centerEqualsMax) {
			L.polyline(
				[
					[centerLatLng.lat, centerLatLng.lng],
					[maxLatLng.lat, maxLatLng.lng],
				],
				{
					color: "#ef4444",
					weight: 4,
					opacity: 0.95,
				},
			).addTo(clusterGeometryLayer);
		}

		if (
			req.showMin &&
			req.showMax &&
			minLatLng &&
			maxLatLng &&
			minEqualsMax &&
			!(req.showCentroid && centerEqualsMin)
		) {
			L.circleMarker(minLatLng, {
				radius: 8,
				color: "#111827",
				weight: 2,
				fillColor: "#f59e0b",
				fillOpacity: 1,
				renderer: canvasRenderer,
			})
				.bindTooltip(
					`<strong>Point min = point max</strong><br>Même point sélectionné pour les deux extrêmes`,
				)
				.addTo(clusterGeometryLayer);
		}

		const bounds = L.latLngBounds(pointsForBounds.map((p) => [p.lat, p.lng]));
		map.flyToBounds(bounds.pad(0.25), {
			duration: 0.8,
			maxZoom: 12,
		});
	}

	const updateMap = () => {
		if (!map) return;

		clearMapShapes();
		renderedCount = 0;

		if (clusteredVisible.length > 0) {
			if (analysisRune.isClampMapMode && analysisRune.activeClampRule) {
				if (analysisRune.clampDisplayMode === "heatmap") {
					drawClampHeatLayer();
				}

				drawClusteredPoints();
				drawPfasSites();
				return;
			}

			if (getDisplayMode() === "condensed") {
				if (birchCondensationLoading || condensedVisible.length === 0) {
					drawClusteredPoints();
					drawPfasSites();
					return;
				}

				drawCondensedBubbles();
				drawPfasSites();
				renderedCount = condensedVisible.length;
				return;
			}

			drawClusteredPoints();
			drawPfasSites();
			return;
		}

		if (visible.length > 0) {
			const pointsToDraw =
				visible.length > MAX_RAW_RENDER_POINTS
					? visible.slice(0, MAX_RAW_RENDER_POINTS)
					: visible;

			drawRawVisiblePoints(pointsToDraw);
		}

		drawPfasSites();
	};

	function handleMove() {
		if (!map || filteredPoints.loading || isInternalMapUpdate) return;

		computeVisiblePoints();

		if (clusteredVisible.length > 0) {
			updateMap();
			scheduleHistoryStatePersistence();
			return;
		}

		analysisInfo = {
			...analysisInfo,
			analyzedPoints: visible.length,
			message:
				visible.length > MAX_RAW_RENDER_POINTS
					? `${visible.length.toLocaleString("fr-FR")} points filtrés, ${viewportVisibleCount.toLocaleString("fr-FR")} dans le viewport, rendu limité à ${MAX_RAW_RENDER_POINTS.toLocaleString("fr-FR")}.`
					: `${visible.length.toLocaleString("fr-FR")} points filtrés, ${viewportVisibleCount.toLocaleString("fr-FR")} dans le viewport.`,
		};

		updateMap();
		scheduleHistoryStatePersistence();
	}

	function scheduleHandleMove() {
		if (moveTimer) clearTimeout(moveTimer);

		moveTimer = setTimeout(() => {
			handleMove();
		}, MOVE_DEBOUNCE_MS);
	}

	async function runAnalysis() {
		if (!map) return;
		if (analysisRune.isRunning) return;

		activeHistoryCacheKey = null;
		historyStateSyncSuspended = true;
		if (historyStateSaveTimer) {
			clearTimeout(historyStateSaveTimer);
			historyStateSaveTimer = null;
		}

		computeVisiblePoints();

		if (!visible.length) {
			clusteredVisible = [];
			condensedVisible = [];
			lastRunAssignments = {};
			lastPointAnnotations = {};
			analysisRune.resetClampState();
			birchCondensationLoaded = false;
			birchCondensationLoading = false;
			showCondensation3D = false;
			analysisRune.clusterSummaries = [];
			dataRune.selectedCondensedGroup = null;

			analysisInfo = {
				analyzedPoints: 0,
				clusterCount: 0,
				noiseCount: 0,
				durationMs: 0,
				tooMany: false,
				message: "Aucun point filtré.",
				cached: false,
			};
			updateMap();
			historyStateSyncSuspended = false;
			return;
		}

		invalidatePendingAnalysis();
		const currentRequestId = ++requestId;
		abortController = new AbortController();
		clusteredVisible = [];
		condensedVisible = [];
		lastRunAssignments = {};
		lastPointAnnotations = {};
		analysisRune.resetClampState();
		birchCondensationLoaded = false;
		birchCondensationLoading = false;
		showCondensation3D = false;
		analysisRune.clusterSummaries = [];
		dataRune.selectedClusterInfo = null;
		dataRune.selectedCondensedGroup = null;
		dataRune.selectedPoints = [];
		dataRune.selectedBubblePointIds = [];
		dataRune.detailsContext = "none";
		dataRune.clusterGeometryRequest = null;
		analysisRune.selectedClusterId = null;

		clearMapShapes();
		clearClusterGeometry();

		try {
			analysisRune.isRunning = true;

			const filtersSnapshot = $state.snapshot(dataRune.filters);
			const { nutsRegions: _nutsRegions, ...apiFilters } = filtersSnapshot as any;

			let effectiveReduction: "none" | "pca" | "tsne" | "autoencoder" | "saint";

			try {
				effectiveReduction = resolveReductionForRequest();
			} catch (err) {
				analysisInfo = {
					analyzedPoints: visible.length,
					clusterCount: 0,
					noiseCount: 0,
					durationMs: 0,
					tooMany: false,
					message:
						err instanceof Error ? err.message : "Configuration SAINT invalide.",
					cached: false,
				};
				updateMap();
				return;
			}

			const response = await fetch("/api/analysis/run", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				signal: abortController.signal,
				body: JSON.stringify({
					algorithm: analysisRune.algorithm,
					filters: apiFilters,
					selectedModelPfas: analysisRune.selectedModelPfas,
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
						reduction: effectiveReduction,
					},
				}),
			});

			let result: AnalysisResponse & {
				error?: string;
				detail?: string;
				message?: string;
			};

			const rawText = await response.text();

			try {
				result = JSON.parse(rawText);
			} catch {
				throw new Error(
					rawText?.trim()
						? `Réponse non JSON (HTTP ${response.status}) : ${rawText.slice(0, 200)}`
						: `Le serveur a retourné une réponse invalide (HTTP ${response.status})`,
				);
			}

			if (currentRequestId !== requestId) return;

			if (!response.ok) {
				const detail =
					(result as any).detail ??
					(result as any).error ??
					(result as any).message ??
					`Erreur serveur (HTTP ${response.status})`;
				throw new Error(detail);
			}

			const finalReduction =
				result.effectiveParams?.reduction ?? effectiveReduction;

			if (result?.assignments) {
				sessionStorage.setItem(
					"last-analysis-assignments",
					JSON.stringify(result.assignments),
				);
			} else {
				sessionStorage.removeItem("last-analysis-assignments");
			}

			analysisRune.clusterSummaries = result.clusterSummaries ?? [];
			analysisRune.globalMetrics = result.globalMetrics ?? null;
			lastPointAnnotations = result.pointAnnotations ?? {};

			const assignments: ClusterAssignments = result.assignments ?? {};
			lastRunAssignments = assignments;

			const hasAssignments = Object.keys(assignments).length > 0;

			if (hasAssignments && filteredPoints.data?.length) {
				clusteredVisible = buildClusteredVisibleFromAssignments(
					assignments,
					filteredPoints.data,
				);
			} else if ((result as any).points?.length) {
				clusteredVisible = (result as any).points;
			} else {
				clusteredVisible = [];
			}

			analysisInfo = {
				analyzedPoints: result.summary.analyzedPoints,
				clusterCount: result.summary.clusterCount,
				noiseCount: result.summary.noiseCount,
				durationMs: result.summary.durationMs,
				tooMany: result.summary.tooMany,
				message: result.summary.message,
				cached: Boolean(result.cached),
			};

			analysisRune.noiseCount = result.summary?.noiseCount ?? 0;

			const serverCondensed = result.condensedBubbles ?? [];
			condensedVisible = serverCondensed;
			birchCondensationLoaded = serverCondensed.length > 0;
			birchCondensationLoading = false;
			activeHistoryCacheKey = result.cacheKey ?? result.analysisId ?? null;

			const savedEntry = runHistoryRune.addRun({
				algorithm: analysisRune.algorithm,
				params: {
					k: analysisRune.k,
					eps: analysisRune.eps,
					minPts: analysisRune.minPts,
					minClusterSize: analysisRune.minClusterSize,
					minSamples: analysisRune.minSamples,
					clusterSelectionMethod: analysisRune.clusterSelectionMethod,
					maxIterations: analysisRune.maxIterations,
					preprocessing: analysisRune.preprocessing,
					reduction: finalReduction,
					birchThreshold: analysisRune.birchThreshold,
					birchBranchingFactor: analysisRune.birchBranchingFactor,
				},
				pfasSelected: [...analysisRune.selectedModelPfas],
				pointCount: result.summary.analyzedPoints,
				clusterCount: result.summary.clusterCount,
				noiseCount: result.summary.noiseCount,
				durationMs: result.summary.durationMs,
				globalMetrics: result.globalMetrics ?? null,
				metricsSummary: result.metricsSummary ?? null,
				requestSnapshot: result.requestSnapshot ?? null,
				runMetadata: result.runMetadata ?? null,
				reductionMeta: result.reductionMeta ?? null,
				clusteringMeta: result.clusteringMeta ?? null,
				condensationMeta: result.condensationMeta ?? null,

				analysisId: result.analysisId ?? null,
				cacheKey: result.cacheKey ?? null,
				paramsHash: result.paramsHash ?? null,
				cached: Boolean(result.cached),
				status: (result as any).status ?? "ready",
				version: (result as any).version ?? null,
				hitCount: Number((result as any).hitCount ?? 0),
				mapState: buildCurrentMapState(),
				panelState: buildCurrentPanelState(),

				snapshot: {
					filters: JSON.parse(JSON.stringify(dataRune.filters)),
					viewport: map ? getCurrentViewport(map) : null,
					params: {
						k: analysisRune.k,
						maxIterations: analysisRune.maxIterations,
						eps: analysisRune.eps,
						minPts: analysisRune.minPts,
						minClusterSize: analysisRune.minClusterSize,
						minSamples: analysisRune.minSamples,
						clusterSelectionMethod: analysisRune.clusterSelectionMethod,
						preprocessing: analysisRune.preprocessing,
						reduction: finalReduction,
						birchThreshold: analysisRune.birchThreshold,
						birchBranchingFactor: analysisRune.birchBranchingFactor,
					},
					selectedModelPfas: [...analysisRune.selectedModelPfas],
						mode: "expert",
					algorithm: analysisRune.algorithm,
					displayMode: analysisRune.displayMode ?? "points",
					result:
						result.analysisId || result.cacheKey
							? null
							: JSON.parse(JSON.stringify(result)),
				},
			});

			runHistoryRune.updateServerRefs(savedEntry.id, {
				analysisId: result.analysisId ?? null,
				cacheKey: result.cacheKey ?? null,
				paramsHash: result.paramsHash ?? null,
				cached: Boolean(result.cached),
				status: (result as any).status ?? "ready",
				version: (result as any).version ?? null,
				hitCount: Number((result as any).hitCount ?? 0),
			});

			runHistoryRune.mergeServerEntry((result as any).historyEntry ?? null);
			updateMap();
			historyStateSyncSuspended = false;
			if (activeHistoryCacheKey) {
				void persistHistoryState(activeHistoryCacheKey);
			}
		} catch (err: any) {
			if (err?.name === "AbortError") return;
			if (currentRequestId !== requestId) return;

			console.error("[runAnalysis] error:", err);

			clusteredVisible = [];
			condensedVisible = [];
			analysisRune.clusterSummaries = [];
			dataRune.selectedClusterInfo = null;
			dataRune.selectedCondensedGroup = null;
			dataRune.selectedPoints = [];
			dataRune.selectedBubblePointIds = [];
			dataRune.detailsContext = "none";
			dataRune.clusterGeometryRequest = null;
			analysisRune.selectedClusterId = null;
			lastRunAssignments = {};
			lastPointAnnotations = {};
			analysisRune.resetClampState();
			birchCondensationLoaded = false;
			birchCondensationLoading = false;
			showCondensation3D = false;

			analysisInfo = {
				analyzedPoints: visible.length,
				clusterCount: 0,
				noiseCount: 0,
				durationMs: 0,
				tooMany: false,
				message: err?.message ?? "Erreur pendant le clustering.",
				cached: false,
			};

			updateMap();
		} finally {
			if (currentRequestId === requestId) {
				analysisRune.isRunning = false;
				abortController = null;
				historyStateSyncSuspended = false;
			}
		}
	}


	async function loadBirchCondensation() {
	if (birchCondensationLoading) return;
	if (!map) return;
	if (!Object.keys(lastRunAssignments).length) return;

	try {
		birchCondensationLoading = true;
		showCondensation3D = false;

		analysisInfo = {
			...analysisInfo,
			message: "Condensation BIRCH en cours...",
		};

		updateMap();

		const filtersSnapshot = $state.snapshot(dataRune.filters);
		const { nutsRegions: _nutsRegions, ...apiFilters } = filtersSnapshot as any;

		const birchPreprocessing =
			analysisRune.preprocessing === "none"
				? "standardize"
				: analysisRune.preprocessing;

		const birchThreshold =
			birchPreprocessing === "normalize"
				? 0.25
				: 0.9;

		const response = await fetch("/api/analysis/condense-birch", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				filters: apiFilters,
				viewport: null,
				selectedModelPfas: analysisRune.selectedModelPfas,
				preprocessing: birchPreprocessing,
				birchThreshold,
				birchBranchingFactor: 50,
				assignments: lastRunAssignments,
			}),
		});

		const rawText = await response.text();

		let result: any;
		try {
			result = JSON.parse(rawText);
		} catch {
			throw new Error(
				rawText?.trim()
					? `Réponse non JSON (HTTP ${response.status}) : ${rawText.slice(0, 200)}`
					: `Réponse invalide du serveur (HTTP ${response.status})`,
			);
		}

		if (!response.ok) {
			throw new Error(result?.detail ?? "Erreur condensation BIRCH.");
		}

		condensedVisible = result.condensedBubbles ?? [];
		birchCondensationLoaded = condensedVisible.length > 0;
		birchCondensationLoading = false;
		showCondensation3D = false;

		analysisInfo = {
			...analysisInfo,
			message: result?.summary?.message ?? "Condensation BIRCH terminée.",
		};
	} catch (err: any) {
		console.error("[loadBirchCondensation]", err);
		showCondensation3D = false;
		birchCondensationLoaded = false;

		analysisInfo = {
			...analysisInfo,
			message: err?.message ?? "Erreur pendant la condensation BIRCH.",
		};
	} finally {
		birchCondensationLoading = false;
		updateMap();
		scheduleHistoryStatePersistence();
	}
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

	function exportMapAsPng() {
		if (!mapContainer) return;

		htmlToImage
			.toPng(mapContainer, {
				pixelRatio: 2,
				style: {
					margin: "0",
					padding: "0",
					background: "transparent",
					boxShadow: "none",
					border: "none",
				},
			})
			.then((dataUrl) => {
				const link = document.createElement("a");
				link.download = "pfas-analysis-map.png";
				link.href = dataUrl;
				link.click();
			})
			.catch((error) => console.error("Erreur export :", error));
	}

	function isAllSelectedModelPfas(selected: string[]): boolean {
		return selected.length === 1 && selected[0] === "All";
	}

	function resolveReductionForRequest(): "none" | "pca" | "tsne" | "autoencoder" | "saint" {
		if (analysisRune.algorithm === "propos") {
			return "saint";
		}
			return analysisRune.reduction;
	}

	function applyRestoredAnalysis(
		entry: RunHistoryEntry,
		result: HistoryLoadResponse,
	) {
		analysisRune.resetClampState();
		analysisRune.clusterSummaries = result.clusterSummaries ?? [];
		analysisRune.globalMetrics = result.globalMetrics ?? null;
		analysisRune.noiseCount = result.summary?.noiseCount ?? 0;
		lastPointAnnotations = result.pointAnnotations ?? {};
		dataRune.selectedClusterInfo = null;
		dataRune.selectedCondensedGroup = null;
		dataRune.selectedPoints = [];
		dataRune.selectedBubblePointIds = [];
		dataRune.detailsContext = "all";
		dataRune.clusterGeometryRequest = null;

		const assignments = result.assignments ?? {};
		lastRunAssignments = assignments;
		showCondensation3D = false;

		if (Object.keys(assignments).length > 0 && filteredPoints.data?.length) {
			clusteredVisible = buildClusteredVisibleFromAssignments(
				assignments,
				filteredPoints.data,
			);

			sessionStorage.setItem(
				"last-analysis-assignments",
				JSON.stringify(assignments),
			);
		} else if ((result as any).points?.length) {
			clusteredVisible = (result as any).points;
			sessionStorage.removeItem("last-analysis-assignments");
		} else {
			clusteredVisible = [];
			sessionStorage.removeItem("last-analysis-assignments");
		}

		condensedVisible = result.condensedBubbles ?? [];
		birchCondensationLoaded = condensedVisible.length > 0;
		birchCondensationLoading = false;
		activeHistoryCacheKey = result.cacheKey ?? result.analysisId ?? entry.cacheKey ?? entry.analysisId ?? null;

		const restoredMapState =
			entry.mapState ??
			result.mapState ??
			(entry.snapshot?.viewport || entry.snapshot?.displayMode
				? {
						viewport: entry.snapshot?.viewport ?? null,
						displayMode: entry.snapshot?.displayMode ?? "points",
					}
				: null);
		const restoredPanelState = entry.panelState ?? result.panelState ?? null;

		analysisRune.displayMode =
			restoredMapState?.displayMode ??
			entry.snapshot?.displayMode ??
			(condensedVisible.length > 0 ? "condensed" : "points");
		if (
			restoredMapState?.tileLayerIndex != null &&
			restoredMapState.tileLayerIndex !== tileLayerIndex
		) {
			setTileLayer(restoredMapState.tileLayerIndex);
		}

		restorePanelState(restoredPanelState);

		analysisInfo = {
			analyzedPoints: result.summary.analyzedPoints,
			clusterCount: result.summary.clusterCount,
			noiseCount: result.summary.noiseCount,
			durationMs: result.summary.durationMs,
			tooMany: result.summary.tooMany,
			message: entry.cacheKey
				? "Analyse restaurée depuis le cache."
				: "Analyse restaurée depuis l'historique local.",
			cached: Boolean(result.cached),
		};

		historyStateSyncSuspended = false;
		if (activeHistoryCacheKey) {
			runHistoryRune.updateLocalState(activeHistoryCacheKey, {
				mapState: restoredMapState ?? buildCurrentMapState(),
				panelState: restoredPanelState ?? buildCurrentPanelState(),
			});
		}
		updateMap();
	}

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

	$effect(() => {
		const mode = analysisRune.displayMode;
		mode;

		if (!map) return;

		untrack(() => {
			updateMap();
			scheduleHistoryStatePersistence();
		});
	});

	$effect(() => {
		const requestKey = JSON.stringify({
			categories: selectedPfasSiteCategories,
			areaMode: dataRune.areaSelectorMode,
			nutsRegions: dataRune.filters.nutsRegions,
			lassoRegion: dataRune.filters.lassoRegion,
		});

		requestKey;

		if (pfasSitesFetchTimer) {
			clearTimeout(pfasSitesFetchTimer);
		}

		pfasSitesFetchTimer = setTimeout(() => {
			void fetchPfasSites();
		}, PFAS_SITES_FETCH_DEBOUNCE_MS);

		return () => {
			if (pfasSitesFetchTimer) {
				clearTimeout(pfasSitesFetchTimer);
				pfasSitesFetchTimer = null;
			}
		};
	});

	$effect(() => {
		const selectedPoint = dataRune.selectedPoints.length === 1
			? dataRune.selectedPoints[0]
			: null;
		const selectedCategory = normalizePfasSiteCategory(selectedPoint?.category);
		const isPointContext = dataRune.detailsContext === "point";
		selectedPfasSiteCategories;

		if (
			isPointContext &&
			selectedCategory &&
			!selectedPfasSiteCategories.includes(selectedCategory)
		) {
			untrack(() => {
				dataRune.selectedPoints = [];
				dataRune.detailsContext = "none";
			});
		}
	});

	$effect(() => {
		activeHistoryCacheKey;
		historyStateSyncSuspended;
		analysisRune.selectedClusterId;
		dataRune.detailsContext;
		dataRune.selectedPoints;
		dataRune.selectedBubblePointIds;
		dataRune.selectedCondensedGroup;
		dataRune.clusterGeometryRequest;
		showCondensation3D;

		if (!activeHistoryCacheKey || historyStateSyncSuspended) {
			return;
		}

		untrack(() => {
			scheduleHistoryStatePersistence();
		});
	});

	onMount(async () => {
		const leafletModule = await import("leaflet");
		L = ((leafletModule as any).default ?? leafletModule) as typeof import("leaflet");
		if (typeof window !== "undefined") {
			(window as Window & { L?: typeof import("leaflet") }).L = L;
		}
		await import("leaflet-lasso");
		await import("leaflet.heat");

		map = L.map(mapContainer, {
			preferCanvas: true,
			zoomControl: false,
			minZoom: 2,
			worldCopyJump: true,
		}).setView([48, 7], 5);

		canvasRenderer = L.canvas();

		rawPointsLayerGroup = L.layerGroup().addTo(map);
		condensedLayerGroup = L.layerGroup().addTo(map);
		clusterGeometryLayer = L.layerGroup().addTo(map);
		pfasSitesLayerGroup = L.layerGroup().addTo(map);

		map.on("zoomend", scheduleHandleMove);
		map.on("moveend", scheduleHandleMove);

		const base = tileLayers[tileLayerIndex];
		currentTileLayer = L.tileLayer(base.url!, {
			attribution: base.attribution,
			crossOrigin: true,
		}).addTo(map);

		scheduleHandleMove();
	});

	onDestroy(() => {
		if (moveTimer) clearTimeout(moveTimer);
		if (historyStateSaveTimer) clearTimeout(historyStateSaveTimer);
		if (pfasSitesFetchTimer) clearTimeout(pfasSitesFetchTimer);

		invalidatePendingAnalysis();
		pfasSitesAbortController?.abort();

		if (map && lassoFinishedHandler) {
			map.off("lasso.finished", lassoFinishedHandler);
		}

		map?.remove();
	});

	const _syncNbFilteredPoints = $derived.by(() => {
		const count = filteredPoints.data?.length ?? 0;
		untrack(() => {
			if (dataRune.nbFilteredPoints !== count) {
				dataRune.nbFilteredPoints = count;
			}
		});
		return count;
	});

	$effect(() => {
		const _data = filteredPoints.data;
		const _loading = filteredPoints.loading;

		if (!map) return;

		untrack(() => {
			scheduleHandleMove();
		});
	});

	$effect(() => {
		const token = analysisRune.runToken;

		if (!map) return;
		if (token === 0) return;
		if (token === lastProcessedRunToken) return;
		if (analysisRune.isRunning) return;

		lastProcessedRunToken = token;

		untrack(() => {
			invalidatePendingAnalysis();
		});

		void runAnalysis();
	});

	$effect(() => {
		const selected = analysisRune.selectedClusterId;
		selected;

		if (!map) return;
		if (clusteredVisible.length === 0) return;

		untrack(() => {
			updateMap();
		});
	});

	$effect(() => {
		const clampMode = analysisRune.isClampMapMode;
		const clampDisplayMode = analysisRune.clampDisplayMode;
		const activeClampRuleId = analysisRune.activeClampRule?.id ?? null;

		clampMode;
		clampDisplayMode;
		activeClampRuleId;

		if (!map) return;

		untrack(() => {
			updateMap();
		});
	});

	$effect(() => {
		const req = dataRune.clusterGeometryRequest;
		const clusterInfo = dataRune.selectedClusterInfo;

		if (!req || !clusterInfo || clusterInfo.clusterId !== req.clusterId) {
			clearClusterGeometry();
			return;
		}

		showClusterGeometry(clusterInfo, req);
	});

	$effect(() => {
		const pending = runHistoryRune.pendingLoadEntry;
		const loading = filteredPoints.loading;
		const step = historyRestoreStep;

		if (!pending?.snapshot || !map) return;

		const snap = pending.snapshot;

		if (step === "idle") {
			historyStateSyncSuspended = true;
			activeHistoryCacheKey = null;

			analysisRune.algorithm = snap.algorithm;
				analysisRune.expertMode = true;
			analysisRune.k = snap.params.k ?? analysisRune.k;
			analysisRune.maxIterations = snap.params.maxIterations ?? analysisRune.maxIterations;
			analysisRune.eps = snap.params.eps ?? analysisRune.eps;
			analysisRune.minPts = snap.params.minPts ?? analysisRune.minPts;
			analysisRune.minClusterSize =
				snap.params.minClusterSize ?? analysisRune.minClusterSize;
			analysisRune.minSamples = snap.params.minSamples ?? analysisRune.minSamples;
			analysisRune.clusterSelectionMethod =
				snap.params.clusterSelectionMethod === "leaf" ? "leaf" : "eom";
			analysisRune.preprocessing = snap.params.preprocessing as typeof analysisRune.preprocessing;
			analysisRune.reduction = snap.params.reduction as typeof analysisRune.reduction;
			analysisRune.birchThreshold =
				snap.params.birchThreshold ?? analysisRune.birchThreshold;
			analysisRune.birchBranchingFactor =
				snap.params.birchBranchingFactor ?? analysisRune.birchBranchingFactor;
			analysisRune.selectedModelPfas = [...snap.selectedModelPfas];

			dataRune.filters = JSON.parse(JSON.stringify(snap.filters));

			analysisRune.clusterSummaries = [];
			analysisRune.globalMetrics = null;
			analysisRune.noiseCount = 0;
			analysisRune.selectedClusterId = null;
			analysisRune.displayMode = "points";

			dataRune.selectedClusterInfo = null;
			dataRune.selectedCondensedGroup = null;
			dataRune.selectedPoints = [];
			dataRune.selectedBubblePointIds = [];
			dataRune.detailsContext = "none";
			dataRune.clusterGeometryRequest = null;

			clusteredVisible = [];
			condensedVisible = [];
			lastRunAssignments = {};
			lastPointAnnotations = {};
			analysisRune.resetClampState();
			birchCondensationLoaded = false;
			birchCondensationLoading = false;
			showCondensation3D = false;

			analysisInfo = {
				analyzedPoints: 0,
				clusterCount: 0,
				noiseCount: 0,
				durationMs: 0,
				tooMany: false,
				message: "Preparation du rechargement historique...",
				cached: Boolean(pending.cached),
			};

			historyRestoreStep = "waiting-filters";
			return;
		}

		if (step === "waiting-filters") {
			if (loading) return;
			historyRestoreStep = "loading-result";

			const pendingId = pending.id;

			untrack(async () => {
				try {
					const result = await loadHistoryResult(pending);

					if (runHistoryRune.pendingLoadEntry?.id !== pendingId) return;

					const restoredViewport =
						pending.mapState?.viewport ??
						result.mapState?.viewport ??
						snap.viewport ??
						null;

					if (restoredViewport) {
						map.fitBounds(
							[
								[restoredViewport.south, restoredViewport.west],
								[restoredViewport.north, restoredViewport.east],
							],
							{
								padding: [24, 24],
								maxZoom: 10,
							},
						);
					}

					applyRestoredAnalysis(pending, result);
				} catch (err: any) {
					console.error("[history load]", err);
					historyStateSyncSuspended = false;

					analysisInfo = {
						analyzedPoints: 0,
						clusterCount: 0,
						noiseCount: 0,
						durationMs: 0,
						tooMany: false,
						message: err?.message ?? "Erreur de restauration historique.",
						cached: false,
					};

					updateMap();
				} finally {
					if (runHistoryRune.pendingLoadEntry?.id === pendingId) {
						historyRestoreStep = "idle";
						runHistoryRune.clearPendingLoad();
					}
				}
			});
		}
	});

	function focusSelectedCluster(clusterId: number) {
		if (!map) return;

		const pts = clusteredVisible.filter((p) => p.clusterId === clusterId);
		if (pts.length === 0) return;

		const uniqueByCoord = new Map<string, ClusteredPoint>();

		for (const p of pts) {
			const key = `${Number(p.lat).toFixed(6)},${Number(p.lon).toFixed(6)}`;
			if (!uniqueByCoord.has(key)) {
				uniqueByCoord.set(key, p);
			}
		}

		const uniquePts = Array.from(uniqueByCoord.values()).sort((a, b) => {
			if (a.lat !== b.lat) return a.lat - b.lat;
			return a.lon - b.lon;
		});

		if (uniquePts.length === 0) return;

		if (clusterId === -1) {
			const bounds = L.latLngBounds(
				uniquePts.map((p) => [Number(p.lat), Number(p.lon)] as [number, number]),
			);

			map.flyToBounds(bounds, {
				padding: [40, 40],
				maxZoom: 10,
				duration: 0.8,
			});
			return;
		}

		if (uniquePts.length === 1) {
			const p = uniquePts[0];
			map.flyTo([Number(p.lat), Number(p.lon)], 13, {
				duration: 0.8,
			});
			return;
		}

		if (uniquePts.length <= 30) {
			const index = analysisRune.nextClusterFocusIndex(clusterId, uniquePts.length);
			const p = uniquePts[index];

			map.flyTo([Number(p.lat), Number(p.lon)], 11, {
				duration: 0.8,
			});
			return;
		}

		const bounds = L.latLngBounds(
			uniquePts.map((p) => [Number(p.lat), Number(p.lon)] as [number, number]),
		);

		map.flyToBounds(bounds, {
			padding: [40, 40],
			maxZoom: uniquePts.length <= 50 ? 10 : 8,
			duration: 0.8,
		});
	}

	function handleClusterLegendClick(clusterId: number) {
		const summary = analysisRune.clusterSummaries.find(
			(s) => s.clusterId === clusterId,
		);
		selectCluster(clusterId, summary, []);
		focusSelectedCluster(clusterId);
	}

	function handleNoiseLegendClick() {
		const summary = analysisRune.clusterSummaries.find(
			(s) => s.clusterId === -1,
		);
		selectCluster(-1, summary, []);
		focusSelectedCluster(-1);
	}
</script>

<div class="analysis-container">
	<div class="map-wrapper-full">
		<div class="map-wrapper">
			<div id="map" bind:this={mapContainer}></div>

			{#if filteredPoints.loading}
				<div class="loading-overlay">Loading...</div>
			{/if}

			<div class="buttons">
				<Button
					onclick={toggleDisplayMode}
					size="icon"
					title={getToggleTitle()}
					class="absolute top-4 left-4 z-[100] h-10 w-10 rounded-md border-2 border-white bg-primary text-primary-foreground shadow-md hover:bg-primary/90"
					type="button"
				>
					<img
						src={getToggleIcon()}
						alt={getToggleAlt()}
						class="w-6 h-6 pointer-events-none"
					/>
				</Button>

				<Button
					onclick={() => map?.zoomIn()}
					size="icon"
					class="absolute top-16 left-4 z-[100] h-10 w-10"
					title="Zoom avant"
					type="button"
				>
					<Plus class="w-4 h-4" />
				</Button>

				<Button
					onclick={() => map?.zoomOut()}
					size="icon"
					class="absolute top-28 left-4 z-[100] h-10 w-10"
					title="Zoom arrière"
					type="button"
				>
					<Minus class="w-4 h-4" />
				</Button>

				<div class="absolute top-40 left-4 z-[100]">
					<Popover>
						<PopoverTrigger>
							<Button size="icon" title="Changer de fond de carte" type="button">
								<MapIcon class="w-4 h-4" />
							</Button>
						</PopoverTrigger>

						<PopoverContent side="right" align="start" sideOffset={12} class="z-[130] w-64 p-2">
							<h4 class="mb-2 text-sm font-semibold">Choix du fond de carte</h4>
							<ul class="grid gap-1">
								{#each tileLayers as layer, index}
									<li>
										<Button
											variant={index === tileLayerIndex ? "default" : "ghost"}
											class="w-full justify-start"
											onclick={() => setTileLayer(index)}
											type="button"
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
					class="absolute top-52 left-4 z-[100] h-10 w-10"
					title="Exporter la carte"
					type="button"
				>
					<ImageDown class="w-4 h-4" />
				</Button>

				<Button
					onclick={fitToData}
					size="icon"
					class="absolute top-64 left-4 z-[100] h-10 w-10"
					title="Recentrer la carte sur les données"
					type="button"
				>
					<Crosshair class="w-4 h-4" />
				</Button>

				{#if shouldShow3DButton()}
					<Button
						onclick={toggle3DPanel}
						size="icon"
						class="absolute top-[19rem] left-4 z-[100] h-10 w-10"
						title="Vue 3D de la condensation"
						type="button"
					>
						3D
					</Button>
				{/if}

				<Button
					onclick={togglePfasSitesPanel}
					size="icon"
					class="absolute left-4 z-[100] h-10 w-10"
					style={`top: ${getPfasSitesButtonTopRem()}rem;`}
					title="Sites PFAS"
					type="button"
					variant="default"
				>
					<Factory class="w-4 h-4" />
				</Button>

				{#if pfasSitesOpen}
					<div
						class="pfas-sites-panel"
						style={`top: ${getPfasSitesButtonTopRem()}rem;`}
					>
						<div class="pfas-sites-panel-title">Sites PFAS</div>

						<button
							type="button"
							class="pfas-sites-option"
							class:pfas-sites-option-active={isAllPfasSiteCategoriesSelected()}
							onclick={toggleAllPfasSiteCategories}
						>
							<span class="pfas-sites-option-all">Tous</span>
							<span>Tout sélectionner</span>
						</button>

						{#each pfasSiteOptions as option}
							<button
								type="button"
								class="pfas-sites-option"
								class:pfas-sites-option-active={isPfasSiteCategorySelected(option.category)}
								onclick={() => togglePfasSiteCategory(option.category)}
							>
								<span
									class="pfas-sites-option-symbol"
									style={`color:${option.color}; text-shadow:${option.borderColor === "#000000"
										? "-1px -1px 0 #000000, 1px -1px 0 #000000, -1px 1px 0 #000000, 1px 1px 0 #000000"
										: "-1px -1px 0 #FFFFFF, 1px -1px 0 #FFFFFF, -1px 1px 0 #FFFFFF, 1px 1px 0 #FFFFFF"};`}
								>
									{option.symbol}
								</span>
								<span>{option.label}</span>
							</button>
						{/each}

						{#if pfasSitesLoading}
							<div class="pfas-sites-panel-info">Chargement des sites...</div>
						{:else if pfasSitesError}
							<div class="pfas-sites-panel-error">{pfasSitesError}</div>
						{:else if selectedPfasSiteCategories.length > 0}
							<div class="pfas-sites-panel-info">
								{pfasSitesVisible.length.toLocaleString("fr-FR")} site(s) chargé(s)
								{#if pfasSitesVisible.length > 0}
									, {pfasSitesViewportCount.toLocaleString("fr-FR")} dans la vue,
									{pfasSitesRenderedCount.toLocaleString("fr-FR")} rendu(s)
								{/if}
							</div>
						{/if}
					</div>
				{/if}
			</div>

			<div class="legend top-right">
				<div class="legend-title">Analysis</div>

				<div class="legend-item">
					<span class="legend-label">Algorithm</span>
					<span class="legend-value">{analysisRune.algorithm.toUpperCase()}</span>
				</div>

				<div class="legend-item">
					<span class="legend-label">Visible points</span>
					<span class="legend-value">{visible.length.toLocaleString("fr-FR")}</span>
				</div>

				<div class="legend-item">
					<span class="legend-label">Analyzed points</span>
					<span class="legend-value">{analysisInfo.analyzedPoints.toLocaleString("fr-FR")}</span>
				</div>

				<div class="legend-item">
					<span class="legend-label">Clusters</span>
					<span class="legend-value">{analysisInfo.clusterCount}</span>
				</div>

				<div class="legend-item">
					<span class="legend-label">Duration</span>
					<span class="legend-value">{analysisInfo.durationMs} ms</span>
				</div>

				<div class="legend-item">
					<span class="legend-label">Cache</span>
					<span class="legend-value">{analysisInfo.cached ? "oui" : "non"}</span>
				</div>

				{#if analysisRune.isRunning}
					<div class="legend-warning">
						Calcul en cours...
					</div>
				{/if}

				{#if analysisInfo.message}
					<div class="legend-warning">
						{analysisInfo.message}
					</div>
				{/if}

				{#if analysisInfo.clusterCount > 0}
					<div class="legend-clusters">
						<div class="legend-subtitle">Clusters</div>

						<button
							type="button"
							class="cluster-chip"
							class:cluster-chip-active={dataRune.detailsContext === "all"}
							onclick={(e) => {
								e.stopPropagation();
								showAllClusters();
							}}
						>
							<span class="cluster-dot cluster-dot-all"></span>
							<span class="cluster-label">Tous</span>
						</button>

						{#each analysisRune.clusterSummaries.filter((s) => s.clusterId !== -1) as cs}
							<button
								type="button"
								class="cluster-chip"
								class:cluster-chip-active={analysisRune.selectedClusterId === cs.clusterId}
								onclick={(e) => {
									e.stopPropagation();
									handleClusterLegendClick(cs.clusterId);
								}}
							>
								<span
									class="cluster-dot"
									style={`background:${getClusterColor(cs.clusterId)}`}
								></span>
								<span class="cluster-label">C{cs.clusterId}</span>
								<span class="cluster-count">{cs.count}</span>
							</button>
						{/each}

						{#if analysisRune.algorithm === "dbscan" && analysisRune.noiseCount > 0}
							<button
								type="button"
								class="cluster-chip"
								class:cluster-chip-active={analysisRune.selectedClusterId === -1}
								onclick={(e) => {
									e.stopPropagation();
									handleNoiseLegendClick();
								}}
							>
								<span
									class="cluster-dot"
									style={`background:${getClusterColor(-1)}`}
								></span>
								<span class="cluster-label">Noise</span>
								<span class="cluster-count">{analysisRune.noiseCount}</span>
							</button>
						{/if}
					</div>
				{/if}

				{#if analysisRune.isClampMapMode && analysisRune.activeClampRule}
					<div class="clamp-legend">
						<div class="legend-subtitle">Légende de l’explication</div>
						<div class="clamp-legend-active-rule">
							C{analysisRune.activeClampRule.cluster} · {analysisRune.activeClampRule.rule}
						</div>
						<div class="clamp-legend-item">
							<span
								class="clamp-legend-dot clamp-legend-dot-covered"
								style={`background:${getClusterColor(analysisRune.activeClampRule.cluster)}`}
							></span>
							<span>Points couverts par la règle active</span>
						</div>
						<div class="clamp-legend-item">
							<span
								class="clamp-legend-dot clamp-legend-dot-cluster"
								style={`background:${getClusterColor(analysisRune.activeClampRule.cluster)}`}
							></span>
							<span>Autres points du cluster sélectionné</span>
						</div>
						<div class="clamp-legend-item">
							<span class="clamp-legend-dot clamp-legend-dot-other"></span>
							<span>Points des autres clusters</span>
						</div>
					</div>
				{/if}
			</div>

			{#if showCondensation3D && birchCondensationLoaded && condensedVisible.length > 0}
				<div class="condensation-3d-overlay">
					<div class="condensation-3d-toolbar">
						<button type="button" class="close-3d-btn" onclick={toggle3DPanel}>
							Fermer
						</button>
					</div>

					<PfasCondensation3DView
						bubbles={condensedVisible}
						selectedClusterId={analysisRune.selectedClusterId}
						getClusterColor={getClusterColor}
						onBubbleClick={(bubble) => {
							const summary = analysisRune.clusterSummaries.find(
								(s) => s.clusterId === bubble.parentClusterId,
							);

							// on mémorise la sélection
							selectCondensedGroup(bubble, summary);

							// IMPORTANT :
							// on reste en vue 3D
							// showCondensation3D reste true
						}}
					/>
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	#map {
		height: 100%;
		width: 100%;
		z-index: 0;
		background: #c7dce2;
	}

	.loading-overlay {
		position: absolute;
		inset: 0;
		background: rgba(255, 255, 255, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.2rem;
		font-weight: bold;
		z-index: 2;
		pointer-events: all;
	}

	.buttons {
		z-index: 1;
	}

	.pfas-sites-panel {
		position: absolute;
		left: 4.75rem;
		z-index: 120;
		width: 220px;
		padding: 0.75rem;
		border-radius: 0.75rem;
		border: 1px solid #e2e8f0;
		background: rgba(255, 255, 255, 0.98);
		box-shadow: 0 12px 26px rgba(15, 23, 42, 0.16);
		backdrop-filter: blur(8px);
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}

	.pfas-sites-panel-title {
		font-size: 0.82rem;
		font-weight: 700;
		color: #0f172a;
	}

	.pfas-sites-option {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		width: 100%;
		padding: 0.5rem 0.6rem;
		border-radius: 0.65rem;
		border: 1px solid #e2e8f0;
		background: white;
		color: #0f172a;
		font-size: 0.82rem;
		font-weight: 600;
		text-align: left;
		cursor: pointer;
	}

	.pfas-sites-option:hover {
		background: #f8fafc;
	}

	.pfas-sites-option-active {
		border-color: #0f172a;
		background: #eff6ff;
	}

	.pfas-sites-option-symbol,
	.pfas-sites-option-all,
	:global(.pfas-site-marker-symbol) {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 1rem;
		font-size: 1rem;
		line-height: 1;
		flex-shrink: 0;
	}

	.pfas-sites-option-all {
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		color: #475569;
	}

	.pfas-sites-panel-info,
	.pfas-sites-panel-error {
		font-size: 0.76rem;
		line-height: 1.4;
		padding-top: 0.15rem;
	}

	.pfas-sites-panel-info {
		color: #475569;
	}

	.pfas-sites-panel-error {
		color: #b91c1c;
	}

	:global(.pfas-site-div-icon) {
		background: transparent;
		border: none;
	}

	:global(.pfas-site-marker-symbol) {
		font-size: 1rem;
		font-weight: 700;
	}

	.legend {
		position: absolute;
		top: 1rem;
		right: 1rem;
		background: white;
		padding: 0.75rem;
		border-radius: 0.5rem;
		box-shadow: 0 0 6px rgba(0, 0, 0, 0.1);
		font-size: 0.8rem;
		z-index: 10;
		width: 320px;
		max-height: calc(100% - 2rem);
		overflow-y: auto;
	}

	.legend-title {
		font-weight: 700;
		margin-bottom: 0.75rem;
	}

	.legend-subtitle {
		font-weight: 600;
		font-size: 0.75rem;
		margin-bottom: 0.35rem;
		color: #475569;
		width: 100%;
	}

	.legend-item {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 0.35rem;
	}

	.legend-label {
		color: #475569;
	}

	.legend-value {
		font-weight: 600;
		white-space: nowrap;
	}

	.legend-warning {
		margin-top: 0.5rem;
		padding: 0.6rem;
		border-radius: 0.4rem;
		background: #fff7ed;
		color: #9a3412;
		line-height: 1.4;
	}

	.legend-clusters {
		margin-top: 0.6rem;
		padding-top: 0.5rem;
		border-top: 1px solid #e2e8f0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		position: relative;
		z-index: 20;
		pointer-events: auto;
	}

	.cluster-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.2rem 0.5rem;
		border-radius: 9999px;
		background: #f1f5f9;
		border: 1px solid transparent;
		cursor: pointer;
		pointer-events: auto;
		position: relative;
		z-index: 20;
	}

	.cluster-chip:hover {
		background: #e2e8f0;
	}

	.cluster-chip-active {
		background: #dbeafe;
		border-color: #93c5fd;
	}

	.cluster-dot {
		width: 10px;
		height: 10px;
		border-radius: 999px;
		display: inline-block;
		flex-shrink: 0;
		pointer-events: none;
	}

	.cluster-label,
	.cluster-count {
		pointer-events: none;
	}

	.cluster-label {
		font-weight: 600;
	}

	.cluster-count {
		font-weight: 700;
		color: #334155;
	}

	.clamp-legend {
		margin-top: 0.7rem;
		padding-top: 0.7rem;
		border-top: 1px solid #e2e8f0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.clamp-legend-active-rule {
		font-size: 0.78rem;
		line-height: 1.45;
		font-weight: 600;
		color: #0f172a;
		background: #f8fafc;
		border-radius: 10px;
		padding: 0.55rem 0.65rem;
	}

	.clamp-legend-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: #334155;
	}

	.clamp-legend-dot {
		width: 12px;
		height: 12px;
		border-radius: 999px;
		flex-shrink: 0;
	}

	.clamp-legend-dot-covered {
		border: 2px solid #111827;
	}

	.clamp-legend-dot-cluster {
		opacity: 0.45;
		border: 1px solid #334155;
	}

	.clamp-legend-dot-other {
		background: #94a3b8;
		opacity: 0.45;
	}

	.analysis-container {
			display: flex;
			width: 100%;
			height: 100%;
			min-height: 0;
			overflow-y: auto;
		}

	:global(.cluster-centroid-star) {
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 22px;
		font-weight: 700;
		color: #facc15;
		text-shadow:
			-1px -1px 0 #111827,
			1px -1px 0 #111827,
			-1px 1px 0 #111827,
			1px 1px 0 #111827;
		background: transparent;
		border: none;
	}

	.map-wrapper-full {
		width: 100%;
		height: 100%;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.map-wrapper {
		position: relative;
		width: 100%;
		flex: 1;
		min-height: 0;
	}

	.condensation-3d-overlay {
		position: absolute;
		inset: 1rem;
		z-index: 300;
		background: white;
		border-radius: 12px;
		border: 1px solid #e2e8f0;
		box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
		overflow: hidden;
	}

	.condensation-3d-toolbar {
		position: absolute;
		top: 0.75rem;
		right: 0.75rem;
		z-index: 301;
	}

	.close-3d-btn {
		background: #0f172a;
		color: white;
		border: none;
		border-radius: 8px;
		padding: 0.55rem 0.85rem;
		cursor: pointer;
		font-size: 0.9rem;
		font-weight: 600;
	}

	:global(.deck-tooltip) {
		background: rgba(255, 255, 255, 0.96);
		color: #111827;
		padding: 8px 10px;
		border-radius: 8px;
		border: 1px solid #e2e8f0;
		font-size: 13px;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
	}
</style>
