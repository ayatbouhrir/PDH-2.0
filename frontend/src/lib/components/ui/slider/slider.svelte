<script lang="ts">
	import {
		Slider as SliderPrimitive,
		type WithoutChildrenOrChild,
	} from "bits-ui";
	import { cn } from "$lib/utils";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import { scaleLinear, extent, bin, max as d3Max } from "d3";

	let {
		filteredPoints,
		ref = $bindable(null),
		value = $bindable<number[]>([]),
		type: sliderType = "multiple",
		orientation = "horizontal",
		class: className,
		filterKey = null,
		mode,
		min,
		max,
		...restProps
	}: Omit<WithoutChildrenOrChild<Extract<SliderPrimitive.RootProps, { type: "multiple" }>>, "type"> & {
		type?: "multiple";
		filteredPoints?: unknown;
		filterKey?: { substance: string; unit: string } | null;
		mode?: string;
	} = $props();

	let substance = $derived(() =>
		dataRune.filters.substances.find(
			(s) =>
				s.name === filterKey?.substance && s.unit === filterKey?.unit,
		),
	);

	let sub: any;

	// function getValues(): number[] {
	// 	if (!filterKey || !filteredPoints.data) return [];
	// 	return filteredPoints.data
	// 		.flatMap((p) => p.substances ?? [])
	// 		.filter(
	// 			(s) =>
	// 				s.substance === filterKey.substance &&
	// 				s.unit === filterKey.unit &&
	// 				typeof s.value === "number",
	// 		)
	// 		.map((s) => s.value);
	// }

	// function removeOutliers(values: number[]): number[] {
	// 	if (values.length < 4) return values;
	// 	const sorted = [...values].sort((a, b) => a - b);
	// 	const q1 = sorted[Math.floor(values.length * 0.25)];
	// 	const q3 = sorted[Math.floor(values.length * 0.75)];
	// 	const iqr = q3 - q1;
	// 	const lower = q1 - 1.5 * iqr;
	// 	const upper = q3 + 1.5 * iqr;
	// 	return values.filter((v) => v >= lower && v <= upper);
	// }

	// let bins = $derived(() => {
	// 	const values = getValues();
	// 	const clean = mode === "filtered" ? removeOutliers(values) : values;
	// 	if (clean.length === 0) return [];

	// 	const binGenerator = bin().thresholds(30);
	// 	return binGenerator(clean);
	// });

	// let xScale = $derived(() => {
	// 	const values = getValues();
	// 	const clean = mode === "filtered" ? removeOutliers(values) : values;
	// 	const [minVal, maxVal] = extent(clean) as [number, number];
	// 	return scaleLinear().domain([minVal, maxVal]).range([0, 300]);
	// });

	// let yScale = $derived(() => {
	// 	const maxCount = d3Max(bins(), (d) => d.length) || 1;
	// 	return scaleLinear().domain([0, maxCount]).range([40, 0]);
	// });

	// let count = $derived(() => {
	// 	if (!filterKey || !filteredPoints.data) return 0;
	// 	return filteredPoints.data.filter((point) =>
	// 		point.substances?.some(
	// 			(s) =>
	// 				s.substance === filterKey.substance &&
	// 				s.unit === filterKey.unit &&
	// 				s.value >= value[0] &&
	// 				s.value <= value[1],
	// 		),
	// 	).length;
	// });

	// let nbOutliers = $derived(() => {
	// 	if (!filterKey) return 0;
	// 	sub = dataRune.filters.substances.find(
	// 		(s) => s.name === filterKey.substance && s.unit === filterKey.unit,
	// 	);
	// 	if (!sub) return 0;
	// 	return (sub.raw.count ?? 0) - (sub.filtered.count ?? 0);
	// });

	function toggleRangeMode() {
		console.log("toggleRangeMode triggered");
		const index = dataRune.filters.substances.findIndex(
			(s) =>
				s.name === filterKey?.substance && s.unit === filterKey?.unit,
		);

		if (index !== -1) {
			const current = dataRune.filters.substances[index].rangeMode;
			dataRune.filters.substances[index].rangeMode =
				current === "raw" ? "filtered" : "raw";
		}
	}
</script>

<!-- <svg viewBox="0 0 300 40" class="w-full h-10 mb-3">
	{#each bins().filter((b) => b.x0 != null && b.x1 != null && b.x0 >= value[0] && b.x1 <= value[1]) as b (b.x0)}
		<rect
			x={xScale()(b.x0)}
			width={Math.max(xScale()(b.x1) - xScale()(b.x0), 0.5)}
			y={yScale()(b.length)}
			height={40 - yScale()(b.length)}
			fill="hsl(var(--primary))"
			opacity="1"
		>
			<title>
				{b.length} valeur{b.length > 1 ? "s" : ""} entre {b.x0?.toFixed(
					2,
				)} et {b.x1?.toFixed(2)}
			</title>
		</rect>
	{/each}
</svg> -->

<!-- Slider -->
<SliderPrimitive.Root
	type="multiple"
	bind:ref
	bind:value
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
				class="border-primary bg-background ring-offset-background focus-visible:ring-ring block size-4 rounded-full border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
			/>
		{/each}
	{/snippet}
</SliderPrimitive.Root>

<!-- Labels -->
<div class="flex justify-between text-xs text-muted-foreground mt-2">
	<span>{min}</span>
	<span>{max}</span>
</div>
<!-- 
<p class="mt-2 text-xs text-muted-foreground">
	{count()} points in this range
</p> -->

<!-- <span class="text-xs text-destructive">
	{nbOutliers()} outliers in range [{sub.raw.min} ; {sub.raw.max}]
</span> -->

<label class="flex items-center space-x-2 mt-2">
	<input
		type="checkbox"
		checked={substance()?.rangeMode === "raw"}
		onchange={toggleRangeMode}
	/>
	<span class="text-xs">Include outliers</span>
</label>
