<script lang="ts">
	import * as Select from "$lib/components/ui/select/index";
	import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
	import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
	import {
		fetchTemporalVisualization,
		fetchRadarVisualization,
		type TemporalVisualizationResponse,
		type RadarVisualizationResponse,
	} from "$lib/features/visualization/visualization.api";
	import TemporalChart from "$lib/features/visualization/components/TemporalChart.svelte";
	import RadarChart from "$lib/features/visualization/components/RadarChart.svelte";
	import Check from "@lucide/svelte/icons/check";
	import ChevronsUpDown from "@lucide/svelte/icons/chevrons-up-down";
	import * as Command from "$lib/components/ui/command/index";
	import * as Popover from "$lib/components/ui/popover/index";
	import Button from "$lib/components/ui/button/button.svelte";
	import { cn } from "$lib/utils";

	const { assignments = {} } = $props<{
		assignments?: Record<string, number>;
	}>();

	let loading = $state(false);
	let error = $state<string | null>(null);
	let temporalData = $state<TemporalVisualizationResponse | null>(null);
	let radarData = $state<RadarVisualizationResponse | null>(null);
	let temporalAggregation = $state<"mean" | "median">("median");
	let pfasListOpen = $state(false);

	const currentContext = $derived(dataRune.detailsContext);
	const isClusterContext = $derived(currentContext === "cluster");
	const isAllContext = $derived(currentContext === "all");

	const currentClusterId = $derived(
		dataRune.selectedClusterInfo?.clusterId ?? analysisRune.selectedClusterId ?? null,
	);

	const currentClusterSummary = $derived(
		isClusterContext
			? (
					dataRune.selectedClusterInfo ??
					analysisRune.clusterSummaries.find((s) => s.clusterId === currentClusterId) ??
					null
				)
			: null,
	);

	const selectedVisualizationPfasCount = $derived(
		analysisRune.selectedVisualizationPfas.includes("All")
			? 0
			: analysisRune.selectedVisualizationPfas.length,
	);

	const allPfasNames = $derived(Object.keys(dataRune.allSubstances).sort());

	function getVisualizationLabel(value: string) {
		if (value === "none") return "None";
		if (value === "temporal") return "Temporal concentration";
		if (value === "radar-selected") return "Radar PFAS sélectionnés";
		if (value === "radar-detected") return "Radar Top 10 détectés";
		return "Radar Top 10 discriminants";
	}

	function getPfasListLabel() {
		const current = analysisRune.selectedVisualizationPfas;
		if (current.includes("All")) return "All";
		if (current.length === 0) return "All";
		if (current.length === 1) return current[0];
		return `${current.length} selected`;
	}

	function toggleVisualizationPfas(pfas: string) {
		const current = analysisRune.selectedVisualizationPfas;

		if (pfas === "All") {
			analysisRune.selectedVisualizationPfas = ["All"];
			return;
		}

		if (current.includes("All")) {
			analysisRune.selectedVisualizationPfas = [pfas];
			return;
		}

		if (current.includes(pfas)) {
			const next = current.filter((x) => x !== pfas);
			analysisRune.selectedVisualizationPfas = next.length ? next : ["All"];
		} else {
			if (current.length >= 10) return;
			analysisRune.selectedVisualizationPfas = [...current, pfas];
		}
	}

	function buildSelectionPayload() {
		if (dataRune.detailsContext === "all") {
			return {
				clusterId: null,
				pointIds: [] as number[],
			};
		}

		if (dataRune.detailsContext === "cluster") {
			return {
				clusterId:
					dataRune.selectedClusterInfo?.clusterId ??
					analysisRune.selectedClusterId ??
					null,
				pointIds: [] as number[],
			};
		}

		if (dataRune.detailsContext === "point") {
			const pointIds = (dataRune.selectedPoints ?? [])
				.map((p: any) => Number(p.id))
				.filter((v) => Number.isFinite(v));

			return {
				clusterId: null,
				pointIds,
			};
		}

		return {
			clusterId: null,
			pointIds: [] as number[],
		};
	}

	function getTemporalSelectedPfas(): string[] {
		if (isClusterContext) {
			const dominant = currentClusterSummary?.dominantPfas;
			if (dominant && dominant !== "All") return [dominant];
		}

		const current = analysisRune.selectedVisualizationPfas;
		if (!current || current.length === 0) return ["All"];
		if (current.includes("All")) return ["All"];
		return current;
	}

	async function loadVisualization() {
		error = null;
		temporalData = null;
		radarData = null;

		if (analysisRune.visualization === "none") return;

		if (
			analysisRune.visualization === "radar-discriminant" &&
			!isClusterContext
		) {
			error = "Le radar discriminant nécessite un cluster sélectionné.";
			return;
		}

		if (
			analysisRune.visualization === "radar-selected" &&
			(
				analysisRune.selectedVisualizationPfas.includes("All") ||
				analysisRune.selectedVisualizationPfas.length < 3
			)
		) {
			return;
		}

		loading = true;

		try {
			const { clusterId, pointIds } = buildSelectionPayload();

			if (analysisRune.visualization === "temporal") {
				temporalData = await fetchTemporalVisualization(
					assignments,
					clusterId,
					pointIds,
					"global",
					getTemporalSelectedPfas(),
					temporalAggregation,
				);
			} else if (analysisRune.visualization === "radar-selected") {
				radarData = await fetchRadarVisualization(
					assignments,
					clusterId,
					pointIds,
					"selected",
					analysisRune.selectedVisualizationPfas,
				);
			} else if (analysisRune.visualization === "radar-detected") {
				radarData = await fetchRadarVisualization(
					assignments,
					clusterId,
					pointIds,
					"detected",
					analysisRune.selectedVisualizationPfas,
				);
			} else if (analysisRune.visualization === "radar-discriminant") {
				radarData = await fetchRadarVisualization(
					assignments,
					clusterId,
					pointIds,
					"discriminant",
					analysisRune.selectedVisualizationPfas,
				);
			}
		} catch (err: unknown) {
			if (err instanceof Error) {
				error = err.message;
			} else {
				error = "Erreur visualisation";
			}
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (!isClusterContext && analysisRune.visualization === "radar-discriminant") {
			analysisRune.visualization = "radar-detected";
		}
	});

	$effect(() => {
		analysisRune.visualization;
		analysisRune.selectedVisualizationPfas;
		analysisRune.selectedClusterId;
		dataRune.selectedPoints;
		dataRune.selectedClusterInfo;
		dataRune.detailsContext;
		assignments;
		temporalAggregation;

		void loadVisualization();
	});
</script>

<div class="section">
	<div class="section-title visual-title">Visualization</div>

	<Select.Root type="single" bind:value={analysisRune.visualization}>
		<Select.Trigger>
			{getVisualizationLabel(analysisRune.visualization)}
		</Select.Trigger>

		<Select.Content>
			<Select.Group>
				<Select.Item value="none">None</Select.Item>
				<Select.Item value="temporal">Temporal concentration</Select.Item>
				<Select.Item value="radar-selected">Radar PFAS sélectionnés</Select.Item>
				<Select.Item value="radar-detected">Radar Top 10 détectés</Select.Item>
				{#if isClusterContext}
					<Select.Item value="radar-discriminant">
						Radar Top 10 discriminants
					</Select.Item>
				{/if}
			</Select.Group>
		</Select.Content>
	</Select.Root>

	{#if analysisRune.visualization === "temporal"}
		<div class="temporal-submode">
			<label for="temporal-aggregation" class="muted-label">Aggregation</label>
			<select id="temporal-aggregation" bind:value={temporalAggregation} class="simple-select">
				<option value="mean">Mean</option>
				<option value="median">Median</option>
			</select>
		</div>
	{/if}

	{#if analysisRune.visualization === "temporal" && !isClusterContext}
		<div class="pfas-picker">
			<Popover.Root bind:open={pfasListOpen}>
				<Popover.Trigger>
					{#snippet child({ props })}
						<Button
							variant="outline"
							class="w-full justify-between"
							{...props}
							role="combobox"
							aria-expanded={pfasListOpen}
						>
							{getPfasListLabel()}
							<ChevronsUpDown class="ml-2 opacity-50" />
						</Button>
					{/snippet}
				</Popover.Trigger>

				<Popover.Content class="w-[300px] p-0">
					<Command.Root>
						<Command.Input placeholder="Search PFAS..." />
						<Command.List>
							<Command.Empty>No PFAS found.</Command.Empty>
							<Command.Group>
								<Command.Item value="All" onSelect={() => toggleVisualizationPfas("All")}>
									<Check
										class={cn(
											!analysisRune.selectedVisualizationPfas.includes("All") &&
												"text-transparent",
										)}
									/>
									All
								</Command.Item>

								{#each allPfasNames as pfas (pfas)}
									<Command.Item value={pfas} onSelect={() => toggleVisualizationPfas(pfas)}>
										<Check
											class={cn(
												!analysisRune.selectedVisualizationPfas.includes(pfas) &&
													"text-transparent",
											)}
										/>
										{pfas}
									</Command.Item>
								{/each}
							</Command.Group>
						</Command.List>
					</Command.Root>
				</Popover.Content>
			</Popover.Root>
		</div>
	{/if}

	{#if analysisRune.visualization === "radar-selected"}
		<div class="pfas-picker">
			<Popover.Root bind:open={pfasListOpen}>
				<Popover.Trigger>
					{#snippet child({ props })}
						<Button
							variant="outline"
							class="w-full justify-between"
							{...props}
							role="combobox"
							aria-expanded={pfasListOpen}
						>
							{getPfasListLabel()}
							<ChevronsUpDown class="ml-2 opacity-50" />
						</Button>
					{/snippet}
				</Popover.Trigger>

				<Popover.Content class="w-[300px] p-0">
					<Command.Root>
						<Command.Input placeholder="Search PFAS..." />
						<Command.List>
							<Command.Empty>No PFAS found.</Command.Empty>
							<Command.Group>
								<Command.Item value="All" onSelect={() => toggleVisualizationPfas("All")}>
									<Check
										class={cn(
											!analysisRune.selectedVisualizationPfas.includes("All") &&
												"text-transparent",
										)}
									/>
									All
								</Command.Item>

								{#each allPfasNames as pfas (pfas)}
									<Command.Item value={pfas} onSelect={() => toggleVisualizationPfas(pfas)}>
										<Check
											class={cn(
												!analysisRune.selectedVisualizationPfas.includes(pfas) &&
													"text-transparent",
											)}
										/>
										{pfas}
									</Command.Item>
								{/each}
							</Command.Group>
						</Command.List>
					</Command.Root>
				</Popover.Content>
			</Popover.Root>
		</div>
	{/if}

	{#if analysisRune.visualization === "temporal" && isClusterContext}
		<div class="muted" style="margin-top: 10px;">
			La courbe temporelle utilise automatiquement le PFAS dominant du cluster du run courant :
			<strong>{currentClusterSummary?.dominantPfas ?? "-"}</strong>
		</div>
	{:else if analysisRune.visualization === "radar-detected"}
		<div class="muted" style="margin-top: 10px;">
			Les axes sont calculés automatiquement depuis les points du run courant.
		</div>
	{:else if analysisRune.visualization === "radar-discriminant"}
		<div class="muted" style="margin-top: 10px;">
			Les axes sont calculés automatiquement à partir des PFAS les plus discriminants du cluster du run courant.
		</div>
	{/if}

	<div class="visual-box">
		{#if loading}
			<div class="muted">Chargement de la visualisation...</div>

		{:else if error}
			<div class="error">{error}</div>

		{:else if analysisRune.visualization === "none"}
			<div class="muted">Aucune visualisation sélectionnée.</div>

		{:else if analysisRune.visualization === "temporal"}
			{#if temporalData?.meta?.error}
				<div class="muted">{temporalData.meta.error}</div>
			{:else}
				<TemporalChart series={temporalData?.series ?? []} />
			{/if}

		{:else if analysisRune.visualization === "radar-selected"}
			{#if selectedVisualizationPfasCount < 3}
				<div class="muted">
					Sélectionne au moins 3 PFAS pour afficher un radar exploitable.
				</div>
			{:else if radarData?.meta?.error}
				<div class="muted">{radarData.meta.error}</div>
			{:else}
				<RadarChart
					axes={radarData?.axes ?? []}
					values={radarData?.series?.[0]?.values ?? []}
				/>
			{/if}

		{:else if analysisRune.visualization === "radar-detected" || analysisRune.visualization === "radar-discriminant"}
			{#if radarData?.meta?.error}
				<div class="muted">{radarData.meta.error}</div>
			{:else}
				<RadarChart
					axes={radarData?.axes ?? []}
					values={radarData?.series?.[0]?.values ?? []}
				/>
			{/if}
		{/if}
	</div>
</div>

<style>
	.temporal-submode {
		margin-top: 10px;
	}

	.muted-label {
		display: block;
		font-size: 13px;
		color: #6b7280;
		margin-bottom: 6px;
		font-weight: 600;
	}

	.simple-select {
		width: 100%;
		border: 1px solid #d1d5db;
		border-radius: 10px;
		padding: 10px 12px;
		background: white;
		font-size: 14px;
	}

	.visual-title {
		margin-bottom: 10px;
	}

	.pfas-picker {
		margin-top: 10px;
		margin-bottom: 12px;
	}

	.visual-box {
		margin-top: 12px;
		max-height: 520px;
		overflow-y: auto;
	}

	.muted {
		font-size: 14px;
		color: #6b7280;
	}

	.error {
		font-size: 14px;
		color: #b91c1c;
	}
</style>
