<script lang="ts">
	import type { PageProps } from "./$types";
	import { onMount, onDestroy, tick } from "svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import Header from "$lib/components/layout/Header.svelte";
	import AnalysisSidebar from "$lib/features/analysis/components/AnalysisSidebar.svelte";
	import AnalysisMap from "$lib/features/analysis/components/AnalysisMap.svelte";
	
	import { fetchFilteredPoints } from "$lib/features/exploration/filtered-points.resource.svelte";
	import AnalysisResultsPanel from "$lib/features/analysis/components/AnalysisResultsPanel.svelte";

	type ApiStatus = "checking" | "connected" | "error";

	type MapRef = {
		invalidateMapSize?: () => void;
	};

	let { data }: PageProps = $props();

	let mapRef = $state<MapRef | undefined>(undefined);

	let leftWidth = $state(20);
	let detailsWidth = $state(25);

	let isResizing = false;
	let isResizingDetails = false;

	let apiStatus = $state<ApiStatus>("checking");
	let apiMessage = $state("Vérification de la connexion à l'API Python...");

	const filteredPoints = fetchFilteredPoints();

	let hadDetails = false;

	async function checkPythonApiConnection() {
		apiStatus = "checking";
		apiMessage = "Vérification de la connexion à l'API Python...";

		try {
			const response = await fetch("/api/python-status", {
				method: "GET",
				headers: {
					Accept: "application/json",
				},
			});

			const result = await response.json().catch(() => null);

			if (response.ok && result?.ok) {
				apiStatus = "connected";
				apiMessage = "Connexion établie avec l'API Python.";
				return;
			}

			apiStatus = "error";
			apiMessage = result?.message ?? "API Python non disponible.";
		} catch {
			apiStatus = "error";
			apiMessage = "Impossible de contacter l'API Python.";
		}
	}

	onMount(() => {
		dataRune.initialize({
			allMatrixes: data.allMatrixes,
			allDatasets: data.allDatasets,
			allSubstances: data.allSubstances,
		});

		void checkPythonApiConnection();

		window.addEventListener("mousemove", doResize);
		window.addEventListener("mouseup", stopResize);
	});

	onDestroy(() => {
		window.removeEventListener("mousemove", doResize);
		window.removeEventListener("mouseup", stopResize);
	});

	function startResize(event: MouseEvent) {
		isResizing = true;
		event.preventDefault();
	}

	function startResizeDetails(event: MouseEvent) {
		isResizingDetails = true;
		event.preventDefault();
	}

	function doResize(event: MouseEvent) {
		if (isResizing) {
			const newLeftWidth = (event.clientX / window.innerWidth) * 100;
			if (newLeftWidth > 15 && newLeftWidth < 66) {
				leftWidth = newLeftWidth;
			}
		} else if (isResizingDetails) {
			const fromRight = window.innerWidth - event.clientX;
			const newDetailsWidth = (fromRight / window.innerWidth) * 100;
			if (newDetailsWidth > 15 && newDetailsWidth < 66) {
				detailsWidth = newDetailsWidth;
			}
		}
	}

	function stopResize() {
		isResizing = false;
		isResizingDetails = false;
		mapRef?.invalidateMapSize?.();
	}

	$effect(() => {
		const hasDetails = dataRune.detailsContext !== "none";

		if (hasDetails !== hadDetails) {
			hadDetails = hasDetails;

			void tick().then(() => {
				mapRef?.invalidateMapSize?.();
			});
		}
	});
</script>

<Header mode="on" />

<div class="main">
	<div
		class="api-status-banner"
		class:checking={apiStatus === "checking"}
		class:connected={apiStatus === "connected"}
		class:error={apiStatus === "error"}
	>
		<span
			class="status-dot"
			class:checking={apiStatus === "checking"}
			class:connected={apiStatus === "connected"}
			class:error={apiStatus === "error"}
		></span>

		<span>{apiMessage}</span>

		{#if apiStatus === "error"}
			<button class="retry-button" onclick={() => void checkPythonApiConnection()}>
				Réessayer
			</button>
		{/if}
	</div>

	<div class="left" style={`width: ${leftWidth}%`}>
		<AnalysisSidebar />
	</div>

	<button
		class="resizer"
		aria-label="Resize panel"
		onmousedown={startResize}
	></button>

	<div
		class="right"
		style="flex: 1; min-width: 0;"
	>
		<AnalysisMap {filteredPoints} bind:this={mapRef} />
	</div>
	{#if dataRune.detailsContext !== "none"}
		<button
			class="resizer"
			aria-label="Resize point details"
			onmousedown={startResizeDetails}
		></button>

		<div class="details" style={`width: ${detailsWidth}%`}>
			<AnalysisResultsPanel />
		</div>
	{/if}
</div>

<style>
	.main {
		position: relative;
		display: flex;
		height: calc(100vh - 72px);
		overflow: hidden;
	}

	.left,
	.right {
		height: 100%;
		overflow: auto;
	}

	.left {
		background-color: var(--color-background);
		padding: 1rem;
	}

	.resizer {
		all: unset;
		width: 4px;
		cursor: col-resize;
		background-color: hsl(var(--color-resizer));
	}

	.resizer:hover {
		background-color: hsl(var(--primary));
	}

	.details {
		height: 100%;
		overflow: auto;
		background-color: var(--color-background);
		padding: 1rem;
	}

	.api-status-banner {
		position: absolute;
		top: 1rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 1000;
		display: flex;
		align-items: center;
		gap: 0.65rem;
		padding: 0.8rem 1rem;
		border-radius: 0.75rem;
		font-size: 0.95rem;
		font-weight: 600;
		box-shadow: 0 8px 22px rgba(0, 0, 0, 0.12);
		border: 1px solid transparent;
		backdrop-filter: blur(6px);
	}

	.api-status-banner.checking {
		background: rgba(255, 247, 237, 0.96);
		color: #9a3412;
		border-color: #fdba74;
	}

	.api-status-banner.connected {
		background: rgba(236, 253, 245, 0.96);
		color: #166534;
		border-color: #86efac;
	}

	.api-status-banner.error {
		background: rgba(254, 242, 242, 0.96);
		color: #991b1b;
		border-color: #fca5a5;
	}

	.status-dot {
		width: 10px;
		height: 10px;
		border-radius: 9999px;
		display: inline-block;
		flex-shrink: 0;
	}

	.status-dot.checking {
		background: #f59e0b;
	}

	.status-dot.connected {
		background: #22c55e;
	}

	.status-dot.error {
		background: #ef4444;
	}

	.retry-button {
		all: unset;
		cursor: pointer;
		padding: 0.25rem 0.55rem;
		border-radius: 0.45rem;
		font-size: 0.85rem;
		font-weight: 700;
		background: rgba(255, 255, 255, 0.7);
		border: 1px solid currentColor;
	}

	.retry-button:hover {
		background: rgba(255, 255, 255, 0.95);
	}
</style>