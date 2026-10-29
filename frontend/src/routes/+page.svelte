<script lang="ts">
	import type { PageProps } from "./$types";
	import { onMount, onDestroy } from "svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import Header from "$lib/components/layout/Header.svelte";
	import ExplorationFilters from "$lib/features/exploration/components/ExplorationFilters.svelte";
	import ExplorationMap  from "$lib/features/exploration/components/ExplorationMap.svelte";
	import PointDetails from "$lib/features/exploration/components/PointDetails.svelte";
	import { fetchFilteredPoints } from "$lib/features/exploration/filtered-points.resource.svelte";

	let { data }: PageProps = $props();
	let fsacEnabled = $state(true);

	let mapRef: any;

	let leftWidth = $state(20);
	let detailsWidth = $state(50);
	
	let isResizing = false;
	let isResizingDetails = false;

	// filteredPoints est mis à jour automatiquement 
	const filteredPoints = fetchFilteredPoints();

	onMount(() => {
		dataRune.initialize({
			allMatrixes: data.allMatrixes,
			allDatasets: data.allDatasets,
			allSubstances: data.allSubstances,
		});

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
		const _ = dataRune.selectedPoints;
		mapRef?.invalidateMapSize?.();
	});
</script>

<Header mode="off" />

<div class="main">
	<div class="left" style={`width: ${leftWidth}%`}>
		<ExplorationFilters />
	</div>

	<button
		class="resizer"
		aria-label="Resize panel"
		onmousedown={startResize}
	></button>

	<div
		class="right"
		style={`width: ${100 - leftWidth - (dataRune.selectedPoints.length > 0 ? detailsWidth : 0)}%`}
	>
		<ExplorationMap {filteredPoints} bind:this={mapRef} {fsacEnabled} />
	</div>

	{#if dataRune.selectedPoints.length > 0}
		<button
			class="resizer"
			aria-label="Resize point details"
			onmousedown={startResizeDetails}
		></button>

		<div class="details" style={`width: ${detailsWidth}%`}>
			<PointDetails page="home" />
		</div>
	{/if}
</div>

<style>
	.main {
		display: flex;
		height: calc(100vh - 72px);
		overflow: hidden;
	}
	.left,.right {
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
</style>
