<script lang="ts">
	export let axes: string[] = [];
	export let values: number[] = [];

	const size = 360;
	const cx = size / 2;
	const cy = size / 2;
	const radius = 120;

	function polarToCartesian(angle: number, r: number) {
		const x = cx + Math.cos(angle) * r;
		const y = cy + Math.sin(angle) * r;
		return { x, y };
	}

	$: count = axes.length;
	$: angles = axes.map((_, i) => -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(count, 1));

	$: polygonPoints = values
		.map((v, i) => {
			const r = radius * Math.max(0, Math.min(1, v ?? 0));
			const p = polarToCartesian(angles[i], r);
			return `${p.x},${p.y}`;
		})
		.join(" ");
	function shortLabel(label: string) {
		if (!label) return "";
		return label.length > 4 ? label.slice(0, 4) : label;
	}
</script>

<div class="chart-card">
	<div class="chart-title">Radar PFAS</div>

	{#if axes.length === 0 || values.length === 0}
		<div class="empty">Aucune donnée radar à afficher.</div>
		{:else}
			<svg width={size} height={size} class="chart">
				{#each [0.25, 0.5, 0.75, 1] as level}
					<polygon
						points={axes
						.map((_, i) => {
							const p = polarToCartesian(angles[i], radius * level);
							return `${p.x},${p.y}`;
						})
						.join(" ")}
						class="grid"
					/>
				{/each}

				{#each [
					{ level: 0, label: "0 %" },
					{ level: 0.25, label: "25 %" },
					{ level: 0.5, label: "50 %" },
					{ level: 0.75, label: "75 %" },
					{ level: 1, label: "100 %" },
				] as tick}
					<text
						x={cx + 12}
						y={cy - radius * tick.level}
						class="level-label"
					>
						{tick.label}
					</text>
				{/each}

				{#each axes as axis, i}
					{@const end = polarToCartesian(angles[i], radius)}
					<line x1={cx} y1={cy} x2={end.x} y2={end.y} class="axis" />
					<text x={end.x} y={end.y} class="axis-label">{shortLabel(axis)}</text>
			{/each}

			<polygon points={polygonPoints} class="shape" />

			{#each values as v, i}
				{@const p = polarToCartesian(angles[i], radius * Math.max(0, Math.min(1, v ?? 0)))}
				<circle cx={p.x} cy={p.y} r="4" class="point" />
			{/each}
		</svg>
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
	}
	.chart {
		display: block;
		margin: 0 auto;
	}
	.grid {
		fill: none;
		stroke: #d1d5db;
		stroke-width: 1;
	}
	.axis {
		stroke: #9ca3af;
		stroke-width: 1;
	}
	.axis-label {
		font-size: 11px;
		fill: #374151;
		text-anchor: middle;
		dominant-baseline: middle;
	}
	.level-label {
		font-size: 10px;
		fill: #6b7280;
		text-anchor: start;
		dominant-baseline: middle;
	}
	.shape {
		fill: rgba(37, 99, 235, 0.2);
		stroke: #2563eb;
		stroke-width: 2;
	}
	.point {
		fill: #dc2626;
	}
	.empty {
		font-size: 14px;
		color: #6b7280;
	}
</style>
