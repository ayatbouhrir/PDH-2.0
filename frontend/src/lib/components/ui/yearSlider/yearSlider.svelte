<script lang="ts">
	import {
		Slider as SliderPrimitive,
		type WithoutChildrenOrChild,
	} from "bits-ui";
	import { cn } from "$lib/utils";
	import * as d3 from "d3";
	import { onMount } from "svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";

	let {
		ref = $bindable(null),
		orientation = "horizontal",
		class: className,
		type: sliderType = "multiple",
		...restProps
	}: Omit<WithoutChildrenOrChild<Extract<SliderPrimitive.RootProps, { type: "multiple" }>>, "type" | "value" | "onValueCommit"> & { type?: "multiple" } = $props();

	// Valeur locale pour le slider
	let localValue = $state([...dataRune.filters.yearRange]);

	let histogramContainer: HTMLDivElement;
	let previousFilters = { ...dataRune.filters };
	let bars: d3.Selection<
		SVGRectElement,
		number,
		SVGGElement,
		unknown
	> | null = null;

	interface PointWithYear {
		year: number | null;
	}

	let histogramLoading = $state(false);
	let yearCounts: Map<number, number> = new Map();

	async function fetchHistogramData() {
		let rawYearCounts: Map<number, number> = new Map();
		histogramLoading = true;

		const filtersWithoutYear = {
			...dataRune.filters,
			yearRange: [2003, 2025],
		};

		try {
			const areaMode = dataRune.areaSelectorMode;
			const res = await fetch("/api/filter-points", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ filters: filtersWithoutYear, areaMode }),
			});

			const allPoints = await res.json();
			const typedPoints = allPoints as PointWithYear[];

			rawYearCounts = d3.rollup(
				typedPoints.filter((d) => d.year != null && !isNaN(+d.year)),
				(v) => v.length,
				(d) => (d.year !== null ? +d.year : 0),
			);
		} catch (err) {
			console.error("Erreur chargement histogramme :", err);
			rawYearCounts = new Map();
		}

		histogramLoading = false;
		return rawYearCounts;
	}

	async function drawHistogram() {
		if (!histogramContainer) return;

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

		const years = Array.from(
			{ length: 2025 - 2003 + 1 },
			(_, i) => 2003 + i,
		);

		const x = d3
			.scaleBand()
			.domain(years.map(String))
			.range([0, width])
			.padding(0.1);

		const y = d3
			.scaleLinear()
			.domain([0, d3.max(years.map((y) => yearCounts.get(y) ?? 0)) ?? 1])
			.range([height, 0]);

		bars = svg
			.selectAll("rect")
			.data(years)
			.enter()
			.append("rect")
			.attr("x", (d) => x(String(d)) ?? 0)
			.attr("y", (d) => {
				const count = yearCounts.get(d) ?? 0;
				const barHeight = height - y(count);
				const adjustedHeight = count > 0 ? Math.max(barHeight, 1) : 0;
				return height - adjustedHeight;
			})
			.attr("width", x.bandwidth())
			.attr("height", (d) => {
				const count = yearCounts.get(d) ?? 0;
				const h = height - y(count);
				return count > 0 ? Math.max(h, 1) : 0;
			})
			.attr("fill", (d) => {
				const [minYear, maxYear] = dataRune.filters.yearRange;
				return d >= minYear && d <= maxYear
					? "hsl(var(--primary))"
					: "hsl(var(--border))";
			})
			.attr("fill-opacity", 1);

		bars.append("title").text(
			(d) => `${d} : ${yearCounts.get(d) ?? 0} points`,
		);
	}

	onMount(() => {
		const observer = new ResizeObserver(() => {
			drawHistogram();
		});
		if (histogramContainer) {
			observer.observe(histogramContainer);
		}

		(async () => {
			yearCounts = await fetchHistogramData();
			drawHistogram();
		})();

		return () => observer.disconnect();
	});

	$effect(() => {
		const currentFilters = dataRune.filters;

		const onlyYearRangeChanged =
			JSON.stringify({ ...previousFilters, yearRange: undefined }) ===
				JSON.stringify({ ...currentFilters, yearRange: undefined }) &&
			JSON.stringify(previousFilters.yearRange) !==
				JSON.stringify(currentFilters.yearRange);

		if (onlyYearRangeChanged) {
			drawHistogram();
		} else {
			histogramLoading = true;
			fetchHistogramData().then((result) => {
				yearCounts = result;
				histogramLoading = false;
				drawHistogram();
			});
		}

		previousFilters = { ...currentFilters };
	});
</script>

<div class="h-20 w-full relative">
	<div bind:this={histogramContainer} class="absolute inset-0"></div>

	{#if histogramLoading}
		<div
			class="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground bg-white/70 z-10"
		>
			Loading histogram...
		</div>
	{/if}
</div>

<SliderPrimitive.Root
	type="multiple"
	bind:ref
	bind:value={localValue}
	onValueCommit={() => {
		dataRune.filters.yearRange = [...localValue];
	}}
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
						{localValue[thumb]}
					</div>
				{/if}
			</SliderPrimitive.Thumb>
		{/each}
	{/snippet}
</SliderPrimitive.Root>
