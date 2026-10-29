<script lang="ts">
	export let series: { label: string; points: { x: number; y: number }[] }[] = [];

	const width = 760;
	const height = 340;
	const paddingLeft = 60;
	const paddingRight = 18;
	const paddingTop = 24;
	const paddingBottom = 74;

	const colors = [
		"#84cc16",
		"#38bdf8",
		"#9ca3af",
		"#f97316",
		"#a855f7",
		"#ef4444",
		"#14b8a6",
		"#eab308",
	];

	$: allPoints = series.flatMap((s) => s.points);
	$: xs = allPoints.map((p) => p.x);
	$: ys = allPoints.map((p) => p.y);

	$: minX = xs.length ? Math.min(...xs) : 0;
	$: maxX = xs.length ? Math.max(...xs) : 1;
	$: minY = ys.length ? Math.min(...ys) : 0;
	$: maxY = ys.length ? Math.max(...ys) : 1;

	$: uniqueYears = [...new Set(xs)].sort((a, b) => a - b);
	$: yearStep = uniqueYears.length > 12 ? Math.ceil(uniqueYears.length / 12) : 1;
	$: displayedYears = uniqueYears.filter(
		(year, index) => index % yearStep === 0 || index === uniqueYears.length - 1,
	);

	function scaleX(x: number) {
		if (maxX === minX) return paddingLeft;
		return (
			paddingLeft +
			((x - minX) / (maxX - minX)) * (width - paddingLeft - paddingRight)
		);
	}

	function scaleY(y: number) {
		if (maxY === minY) return height - paddingBottom;
		return (
			height -
			paddingBottom -
			((y - minY) / (maxY - minY)) * (height - paddingTop - paddingBottom)
		);
	}

	function linePath(points: { x: number; y: number }[]) {
		if (!points.length) return "";
		return points
			.map((p, i) => `${i === 0 ? "M" : "L"} ${scaleX(p.x)} ${scaleY(p.y)}`)
			.join(" ");
	}

	function shortLabel(label: string, max = 18) {
		if (!label) return "";
		return label.length > max ? `${label.slice(0, max)}…` : label;
	}

	function yTicks(count = 4) {
		if (maxY === minY) return [minY];
		const step = (maxY - minY) / count;
		return Array.from({ length: count + 1 }, (_, i) => minY + step * i);
	}

	function formatAxisValue(value: number) {
		if (!Number.isFinite(value)) return "-";
		if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
		if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
		return value.toFixed(0);
	}
</script>

<div class="chart-card">
	<div class="chart-title">Temporal concentration</div>

	{#if series.length === 0}
		<div class="empty">Aucune donnée à afficher.</div>
	{:else}
		<svg viewBox={`0 0 ${width} ${height}`} class="chart" preserveAspectRatio="xMidYMid meet">
			{#each yTicks(4) as tick}
				<line
					x1={paddingLeft}
					y1={scaleY(tick)}
					x2={width - paddingRight}
					y2={scaleY(tick)}
					class="grid"
				/>
				<text
					x={paddingLeft - 8}
					y={scaleY(tick) + 4}
					text-anchor="end"
					class="y-tick-label"
				>
					{formatAxisValue(tick)}
				</text>
			{/each}

			<line
				x1={paddingLeft}
				y1={height - paddingBottom}
				x2={width - paddingRight}
				y2={height - paddingBottom}
				class="axis"
			/>
			<line
				x1={paddingLeft}
				y1={paddingTop}
				x2={paddingLeft}
				y2={height - paddingBottom}
				class="axis"
			/>

			<text
				x={(paddingLeft + width - paddingRight) / 2}
				y={height - 12}
				text-anchor="middle"
				class="axis-label"
			>
				Time
			</text>

			<text
				x={18}
				y={height / 2}
				text-anchor="middle"
				class="axis-label"
				transform={`rotate(-90 18 ${height / 2})`}
			>
				Concentration
			</text>

			{#each displayedYears as year}
				<line
					x1={scaleX(year)}
					y1={height - paddingBottom}
					x2={scaleX(year)}
					y2={height - paddingBottom + 6}
					class="tick"
				/>
				<text
					x={scaleX(year)}
					y={height - paddingBottom + 20}
					text-anchor="end"
					class="tick-label"
					transform={`rotate(-35 ${scaleX(year)} ${height - paddingBottom + 20})`}
				>
					{year}
				</text>
			{/each}

			{#each series as s, i}
				<path
					d={linePath(s.points)}
					class="line"
					stroke={colors[i % colors.length]}
				/>
				{#each s.points as p}
					<circle
						cx={scaleX(p.x)}
						cy={scaleY(p.y)}
						r="3.5"
						fill={colors[i % colors.length]}
					/>
				{/each}
			{/each}
		</svg>

		<div class="legend">
			{#each series as s, i}
				<div class="legend-item">
					<span
						class="legend-dot"
						style={`background:${colors[i % colors.length]}`}
					></span>
					<span>{shortLabel(s.label)}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.chart-card {
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 12px;
		background: white;
	}

	.chart-title {
		font-weight: 700;
		margin-bottom: 10px;
		font-size: 15px;
	}

	.chart {
		width: 100%;
		height: auto;
		display: block;
	}

	.axis {
		stroke: #9ca3af;
		stroke-width: 1;
	}

	.grid {
		stroke: #e5e7eb;
		stroke-width: 1;
	}

	.axis-label {
		font-size: 12px;
		fill: #374151;
		font-weight: 600;
	}

	.tick {
		stroke: #9ca3af;
		stroke-width: 1;
	}

	.tick-label {
		font-size: 10px;
		fill: #6b7280;
	}

	.y-tick-label {
		font-size: 10px;
		fill: #6b7280;
	}

	.line {
		fill: none;
		stroke-width: 3;
		stroke-linecap: round;
		stroke-linejoin: round;
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-top: 10px;
	}

	.legend-item {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 12px;
		padding: 4px 8px;
		border-radius: 999px;
		background: #f3f4f6;
	}

	.legend-dot {
		width: 10px;
		height: 10px;
		border-radius: 999px;
		display: inline-block;
		flex-shrink: 0;
	}

	.empty {
		font-size: 14px;
		color: #6b7280;
	}
</style>