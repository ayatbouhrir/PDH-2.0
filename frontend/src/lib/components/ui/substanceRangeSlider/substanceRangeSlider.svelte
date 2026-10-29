<script lang="ts">
	import {
		Slider as SliderPrimitive,
		type WithoutChildrenOrChild,
	} from "bits-ui";
	import { cn } from "$lib/utils";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import { onMount } from "svelte";
	import { fetchSubstanceHistogram } from "$lib/features/exploration/substance-histogram.api";
	import * as d3 from "d3";

	let {
		filterKey,
		ref = $bindable(null),
		orientation = "horizontal",
		class: className,
		type: sliderType = "multiple",
		...restProps
	}: Omit<WithoutChildrenOrChild<Extract<SliderPrimitive.RootProps, { type: "multiple" }>>, "type" | "value" | "onValueCommit"> & {
		filterKey: { substance: string; unit: string };
		type?: "multiple";
	} = $props();

	let localValue = $state<number[]>([0, 1]);
	type HistogramBin = { min: number; max: number; count: number };
	let bins: HistogramBin[] = $state([]);

	let histogramContainer = $state<HTMLDivElement | null>(null);
	let bars: d3.Selection<
		SVGRectElement,
		HistogramBin,
		SVGGElement,
		unknown
	> | null = null;

	async function refreshHistogram() {
		console.log("refreshHistogram", filterKey);
		const result = await fetchSubstanceHistogram({ substance: filterKey });
		bins = result;
		drawHistogram();
	}

	function getSubstance() {
		return dataRune.filters.substances.find(
			(s) => s.name === filterKey.substance && s.unit === filterKey.unit,
		);
	}

	function updateSubstanceRange() {
		const sub = getSubstance();

		if (sub) {
			if (sub.rangeMode === "filtered") {
				sub.filteredRange = [...localValue];
			} else {
				sub.rawRange = [...localValue];
			}
		}
		recolorBars();
	}

	function drawHistogram() {
		if (!histogramContainer || bins.length === 0) return;

		const margin = { top: 4, right: 3, bottom: 4, left: 3 };
		const width =
			histogramContainer.clientWidth - margin.left - margin.right;
		const height =
			histogramContainer.clientHeight - margin.top - margin.bottom;

		d3.select(histogramContainer).selectAll("svg").remove();

		const svg = d3
			.select(histogramContainer)
			.append("svg")
			.attr(
				"viewBox",
				`0 0 ${width + margin.left + margin.right} ${height + margin.top + margin.bottom}`,
			)
			.attr("preserveAspectRatio", "xMidYMid meet")
			.style("width", "100%")
			.style("height", "100%")
			.append("g")
			.attr("transform", `translate(${margin.left},${margin.top})`);

		// 🔧 Recalculer les échelles sur toutes les bins visibles
		const visibleBins = bins.filter(
			(d) => d.min >= localValue[0] && d.max <= localValue[1],
		);

		if (visibleBins.length === 0) return;

		const x = d3
			.scaleLinear()
			.domain([bins[0].min, bins[bins.length - 1].max])
			.range([0, width]);

		const y = d3
			.scaleLinear()
			.domain([0, d3.max(visibleBins, (d) => d.count)!])
			.range([height, 0]);

		// Afficher toutes les bins mais avec height = 0 si hors range
		bars = svg
			.selectAll("rect")
			.data(bins)
			.enter()
			.append("rect")
			.attr("x", (d) => x(d.min))
			.attr("width", (d) => x(d.max) - x(d.min))
			.attr("y", (d) => {
				const inRange =
					d.min >= localValue[0] && d.max <= localValue[1];
				if (!inRange || d.count === 0) return height;
				const h = height - y(d.count);
				return height - Math.max(h, 1); // min 1px si count > 0
			})
			.attr("height", (d) => {
				const inRange =
					d.min >= localValue[0] && d.max <= localValue[1];
				if (!inRange || d.count === 0) return 0;
				const h = height - y(d.count);
				return Math.max(h, 1); // min 1px si count > 0
			})
			.attr("fill", "hsl(var(--primary))")
			.attr("opacity", 0.9);

		bars.append("title").text(
			(d) =>
				`${d.count} valeurs entre ${d.min.toFixed(2)} et ${d.max.toFixed(2)}`,
		);
	}

	function recolorBars() {
		if (!bars || !histogramContainer || bins.length === 0) return;

		const height = histogramContainer.clientHeight - 4 - 4; // margin.top + bottom

		// Calculer les bins visibles pour adapter l'échelle Y
		const visibleBins = bins.filter(
			(d) => d.min >= localValue[0] && d.max <= localValue[1],
		);

		if (visibleBins.length === 0) return;

		const maxVisibleCount = d3.max(visibleBins, (d) => d.count)!;

		const y = d3
			.scaleLinear()
			.domain([0, maxVisibleCount])
			.range([height, 0]);

		// Appliquer la transition conditionnellement
		bars.each(function (d) {
			const inRange = d.min >= localValue[0] && d.max <= localValue[1];
			const bar = d3.select(this);

			if (inRange && d.count > 0) {
				const h = height - y(d.count);
				bar.transition()
					.duration(400)
					.attr("y", height - Math.max(h, 1))
					.attr("height", Math.max(h, 1))
					.attr("fill", "hsl(var(--primary))");
			} else {
				bar.interrupt() // interrompt toute transition en cours
					.attr("y", height)
					.attr("height", 0)
					.attr("fill", "hsl(var(--border))");
			}
		});
	}

	$effect(() => {
		const _ = dataRune.filters;
		refreshHistogram();
	});

	onMount(() => {
		const sub = getSubstance();
		if (sub) {
			if (sub.rangeMode === "filtered") {
				localValue = [...sub.filteredRange];
			} else {
				localValue = [...sub.rawRange];
			}
		}
		refreshHistogram();

		// Redessiner si resize
		const observer = new ResizeObserver(() => drawHistogram());
		if (histogramContainer) observer.observe(histogramContainer);
		return () => observer.disconnect();
	});

	function countMeasuresInRange(): number {
		return bins.reduce((acc, bin) => {
			if (bin.min >= localValue[0] && bin.max <= localValue[1]) {
				return acc + bin.count;
			}
			return acc;
		}, 0);
	}
</script>

<!-- Slider avec valeurs -->
{#if (getSubstance()?.rangeMode === "filtered" && (getSubstance()?.filtered?.count ?? 0) < 3) || (getSubstance()?.rangeMode === "raw" && (getSubstance()?.raw?.count ?? 0) < 3)}
	<p class="text-muted-foreground text-sm mt-8">
		Too few measures ({getSubstance()?.raw.count}) to show histogram
	</p>
{:else}
	<!-- Histogramme en D3 -->
	<div class="h-20 w-full relative mb-2">
		<div bind:this={histogramContainer} class="absolute inset-0"></div>
	</div>
	<SliderPrimitive.Root
		type="multiple"
		bind:ref
		bind:value={localValue}
		onValueCommit={updateSubstanceRange}
		{orientation}
		class={cn(
			"relative flex touch-none select-none items-center data-[orientation='vertical']:h-full data-[orientation='vertical']:min-h-44 data-[orientation='horizontal']:w-full data-[orientation='vertical']:w-auto data-[orientation='vertical']:flex-col",
			className,
		)}
		{...restProps}
	>
		{#snippet children({ thumbs })}
			<span
				data-orientation={orientation}
				style="background-color: hsl(var(--border));"
				class="relative grow overflow-hidden rounded-full data-[orientation='horizontal']:h-1 data-[orientation='vertical']:h-full data-[orientation='horizontal']:w-full data-[orientation='vertical']:w-2"
			>
				<SliderPrimitive.Range
					class="bg-primary absolute data-[orientation='horizontal']:h-full data-[orientation='vertical']:w-full"
				/>
			</span>

			{#each thumbs as thumb (thumb)}
				<SliderPrimitive.Thumb
					index={thumb}
					class="relative border-primary bg-background ring-offset-background focus-visible:ring-ring block size-4 rounded-full border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
				>
					{#if Array.isArray(localValue)}
						<div
							class="absolute top-5 left-1/2 -translate-x-1/2 text-xs text-muted-foreground pointer-events-none select-none"
						>
							{localValue[thumb].toFixed(2)}
						</div>
					{/if}
				</SliderPrimitive.Thumb>
			{/each}
		{/snippet}
	</SliderPrimitive.Root>
	<p class="text-muted-foreground text-sm mt-8">
		{new Intl.NumberFormat("fr-FR").format(countMeasuresInRange())} measures
		in this range
	</p>
{/if}

<!-- Toggle pour le mode de sélection -->
<label class="flex items-center gap-2 mt-2 text-sm text-muted-foreground">
	<input
		type="checkbox"
		checked={getSubstance()?.rangeMode === "filtered"}
		onchange={(e) => {
			const sub = getSubstance();
			if (!sub) return;
			sub.rangeMode = e.currentTarget.checked ? "filtered" : "raw";
			localValue = [
				...(sub.rangeMode === "filtered"
					? sub.filteredRange
					: sub.rawRange),
			];
		}}
	/>
	Remove outliers ({(
		100 -
		((getSubstance()?.filtered.count ?? 0) /
			(getSubstance()?.raw.count ?? 0)) *
			100
	).toFixed(0)}%)
</label>
