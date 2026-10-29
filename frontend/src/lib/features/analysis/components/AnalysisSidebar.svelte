<script lang="ts">
	import { analysisRune } from "$lib/features/analysis/analysis.state.svelte";
	import RunHistory from "$lib/features/history/components/RunHistory.svelte";
	import { dataRune, Category } from "$lib/features/exploration/exploration.state.svelte";
	import * as Select from "$lib/components/ui/select/index";
	import Button from "$lib/components/ui/button/button.svelte";
	import { YearSlider } from "$lib/components/ui/yearSlider/index";
	import AreaSelector from "$lib/features/geography/components/AreaSelector.svelte";
	import Check from "@lucide/svelte/icons/check";
	import ChevronsUpDown from "@lucide/svelte/icons/chevrons-up-down";
	import { tick } from "svelte";
	import * as Command from "$lib/components/ui/command/index";
	import * as Popover from "$lib/components/ui/popover/index";
	import { cn } from "$lib/utils";
	import { checkUnitAvailability } from "$lib/features/exploration/unit-availability.api";
	import { fetchSubstanceRange } from "$lib/features/exploration/substance-range.api";
	import { SubstanceRangeSlider } from "$lib/components/ui/substanceRangeSlider/index";

	let open = $state(false);
	let selectedSubstance = $state("");
	let selectedUnit = $state("");
	let triggerRef = $state<HTMLButtonElement>(null!);

	let datasetOpen = $state(false);
	let selectedDataset = $state("");
	let datasetTriggerRef = $state<HTMLButtonElement>(null!);

	let unavailableUnits = $state<string[]>([]);
	let isCheckingUnits = $state(false);
	let unitCheckRequestId = 0;

	let pfasListOpen = $state(false);
	let pfasTriggerRef = $state<HTMLButtonElement>(null!);
	let showAdvancedParameters = $state(false);

	let reductionValue = $state((analysisRune.reduction ?? "none") as
		| "none"
		| "pca"
		| "tsne"
		| "autoencoder"
		| "saint"
	);

	let preprocessingValue = $state((analysisRune.preprocessing ?? "standardize") as
		| "none"
		| "standardize"
		| "normalize");

	const isAllSelectedModelPfas = $derived(
	analysisRune.selectedModelPfas.length === 1 &&
	analysisRune.selectedModelPfas[0] === "All"
	);




	$effect(() => {
		const currentReduction = analysisRune.reduction ?? "none";
		if (reductionValue !== currentReduction) {
			reductionValue = currentReduction as
				| "none"
				| "pca"
				| "tsne"
				| "autoencoder"
				| "saint";
		}
	});

	$effect(() => {
		const currentPreprocessing = analysisRune.preprocessing ?? "standardize";
		if (preprocessingValue !== currentPreprocessing) {
			preprocessingValue = currentPreprocessing as
				| "none"
				| "standardize"
				| "normalize";
		}
	});

	$effect(() => {
		if (!selectedSubstance) {
			unavailableUnits = [];
			isCheckingUnits = false;
			selectedUnit = "";
			return;
		}

		const currentRequestId = ++unitCheckRequestId;
		isCheckingUnits = true;
		selectedUnit = "";

		checkUnitAvailability(selectedSubstance)
			.then((units) => {
				if (currentRequestId !== unitCheckRequestId) return;

				const allUnits =
					dataRune.allSubstances[selectedSubstance]?.units ?? [];

				unavailableUnits = allUnits.filter((u) => !units.includes(u));
			})
			.catch(() => {
				if (currentRequestId !== unitCheckRequestId) return;
				unavailableUnits = [];
			})
			.finally(() => {
				if (currentRequestId !== unitCheckRequestId) return;
				isCheckingUnits = false;
			});
	});

	const allPfasNames = $derived(Object.keys(dataRune.allSubstances).sort());

	const substancesOptions = $derived(
		Object.keys(dataRune.allSubstances).map((substance) => ({
			value: substance,
			label: substance,
		})),
	);

	const datasetsOptions = $derived(
		Object.entries(dataRune.allDatasets).map(([name, { id, count }]) => ({
			value: String(id),
			label: `[${id}] ${name}`,
			count,
		})),
	);

	function getModelPfasListLabel() {
		const current = analysisRune.selectedModelPfas;

		if (current.includes("All")) return "All";
		if (current.length === 0) return "All";
		if (current.length === 1) return current[0];

		return `${current.length} selected`;
	}
	function toggleModelPfas(pfas: string) {
		const current = analysisRune.selectedModelPfas;

		if (pfas === "All") {
			analysisRune.selectedModelPfas = ["All"];
			return;
		}

		if (current.includes("All")) {
			analysisRune.selectedModelPfas = [pfas];
			return;
		}

		if (current.includes(pfas)) {
			const next = current.filter((x) => x !== pfas);
			analysisRune.selectedModelPfas = next.length ? next : ["All"];
		} else {
			analysisRune.selectedModelPfas = [...current, pfas];
		}
	}

	function toggleVisualizationPfas(pfas: string) {
		const current = analysisRune.selectedVisualizationPfas;
		const isTemporal = analysisRune.visualization === "temporal";

		if (pfas === "All") {
			analysisRune.selectedVisualizationPfas = ["All"];
			return;
		}

		if (isTemporal) {
			analysisRune.selectedVisualizationPfas = [pfas];
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
			analysisRune.selectedVisualizationPfas = [...current, pfas];
		}
	}
	function handleReductionChange(event: Event) {
		const value = (event.currentTarget as HTMLSelectElement).value as
			| "none"
			| "pca"
			| "tsne"
			| "autoencoder"
			| "saint";

		reductionValue = value;
		analysisRune.reduction = value;
	}

	function handlePreprocessingChange(event: Event) {
		const value = (event.currentTarget as HTMLSelectElement).value as
			| "none"
			| "standardize"
			| "normalize";

		preprocessingValue = value;
		analysisRune.preprocessing = value;
	}

	function toggleSelectAll(field: "datasetId" | "matrix") {
		if (field === "datasetId") {
			const allDatasetIds = Object.values(dataRune.allDatasets).map(({ id }) =>
				String(id),
			);

			dataRune.filters.datasetId =
				dataRune.filters.datasetId.length === 0 ? allDatasetIds : [];
		} else {
			dataRune.filters.matrix =
				dataRune.filters.matrix.length === 0
					? Object.keys(dataRune.allMatrixes)
					: [];
		}
	}

	function isAllSelected(field: "datasetId" | "matrix") {
		return dataRune.filters[field].length === 0;
	}

	function closeAndFocusTrigger() {
		open = false;
		tick().then(() => {
			triggerRef?.focus();
		});
	}

	function closeAndFocusDatasetTrigger() {
		datasetOpen = false;
		tick().then(() => {
			datasetTriggerRef?.focus();
		});
	}

	function removeDataset(id: string) {
		dataRune.filters.datasetId = dataRune.filters.datasetId.filter(
			(d) => d !== id,
		);
	}
</script>

<div class="selection">
	<h3
		class="scroll-m-20 border-b pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
	>
		Model type
	</h3>

		<Select.Root type="single" bind:value={analysisRune.algorithm}>
		<Select.Trigger>
			{analysisRune.algorithm === "kmeans"
				? "KMeans"
				: analysisRune.algorithm === "dbscan"
					? "DBSCAN"
					: analysisRune.algorithm === "hdbscan"
						? "HDBSCAN"
						: "ProPos"}
		</Select.Trigger>
		<Select.Content>
			<Select.Group>
				<Select.GroupHeading>Algorithms</Select.GroupHeading>
				<Select.Item value="kmeans">KMeans</Select.Item>
				<Select.Item value="dbscan">DBSCAN</Select.Item>
				<Select.Item value="hdbscan">HDBSCAN</Select.Item>
				<Select.Item value="propos">ProPos</Select.Item>
			</Select.Group>
		</Select.Content>
	</Select.Root>
</div>

<div class="selection">
	<h3
		class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
	>
		PFAS list
	</h3>

	<Popover.Root bind:open={pfasListOpen}>
		<Popover.Trigger bind:ref={pfasTriggerRef}>
			{#snippet child({ props })}
				<Button
					variant="outline"
					class="w-full justify-between"
					{...props}
					role="combobox"
					aria-expanded={pfasListOpen}
				>
					{getModelPfasListLabel()}
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
						<Command.Item
							value="All"
							onSelect={() => {
								toggleModelPfas("All");
							}}
						>
							<Check
								class={cn(
									!analysisRune.selectedModelPfas.includes("All") &&
										"text-transparent",
								)}
							/>
							All
						</Command.Item>

						{#each allPfasNames as pfas (pfas)}
							<Command.Item
								value={pfas}
								onSelect={() => {
									toggleModelPfas(pfas);
								}}
							>
								<Check
									class={cn(
										!analysisRune.selectedModelPfas.includes(pfas) &&
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

<div class="advanced-toggle-block">
	<button
		type="button"
		class="advanced-toggle-btn"
		onclick={() => showAdvancedParameters = !showAdvancedParameters}
		aria-expanded={showAdvancedParameters}
	>
		{showAdvancedParameters ? "Masquer les paramètres avancés" : "Paramètres avancés"}
	</button>
</div>

{#if showAdvancedParameters}
	<div class="selection">
			<h3
				class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
			>
			Parameters
		</h3>

		{#if analysisRune.algorithm === "kmeans"}
			<div class="param-row">
				<label for="kmeans-k">K</label>
				<input
					id="kmeans-k"
					type="number"
					min="2"
					bind:value={analysisRune.k}
				/>
			</div>

			<div class="param-row">
				<label for="kmeans-iter">Max iterations</label>
				<input
					id="kmeans-iter"
					type="number"
					min="1"
					max="300"
					bind:value={analysisRune.maxIterations}
				/>
			</div>
		{:else if analysisRune.algorithm === "dbscan"}
			<div class="param-row">
				<label for="dbscan-eps">Eps</label>
				<input
					id="dbscan-eps"
					type="number"
					min="0.0001"
					step="0.05"
					bind:value={analysisRune.eps}
				/>
			</div>

			<div class="param-row">
				<label for="dbscan-minpts">MinPts</label>
				<input
					id="dbscan-minpts"
					type="number"
					min="2"
					bind:value={analysisRune.minPts}
				/>
			</div>
		{:else if analysisRune.algorithm === "hdbscan"}
			<div class="param-row">
				<label for="hdbscan-min-cluster-size">Min cluster size</label>
				<input
					id="hdbscan-min-cluster-size"
					type="number"
					min="2"
					bind:value={analysisRune.minClusterSize}
				/>
			</div>

			<div class="param-row">
				<label for="hdbscan-min-samples">Min samples</label>
				<input
					id="hdbscan-min-samples"
					type="number"
					min="1"
					bind:value={analysisRune.minSamples}
				/>
			</div>

			<div class="param-row">
				<label for="hdbscan-selection-method">Cluster selection</label>
				<select
					id="hdbscan-selection-method"
					class="native-select"
					bind:value={analysisRune.clusterSelectionMethod}
				>
					<option value="eom">eom</option>
					<option value="leaf">leaf</option>
				</select>
			</div>
		{:else}
			<div class="param-row">
				<label for="propos-k">K</label>
				<input
					id="propos-k"
					type="number"
					min="2"
					bind:value={analysisRune.k}
				/>
			</div>

			<div class="param-row">
				<label for="propos-epochs">Epochs</label>
				<input
					id="propos-epochs"
					type="number"
					min="1"
					max="400"
					bind:value={analysisRune.maxIterations}
				/>
			</div>
		{/if}
	</div>

	<div class="selection">
		<h3
			class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
		>
			Prétraitement
		</h3>

		<div class="param-column">
			<select
				id="preprocessing-method"
				value={preprocessingValue}
				onchange={handlePreprocessingChange}
				class="native-select"
			>
				<option value="none">Aucun</option>
				<option value="standardize">Standardisation (z-score)</option>
				<option value="normalize">Normalisation (min-max)</option>
			</select>
		</div>
	</div>

		{#if analysisRune.algorithm === "propos"}
			<div class="selection">
				<h3
					class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
				>
				Réduction de dimension
			</h3>

			<div class="param-column">
				<div class="static-hint">SAINT latent (obligatoire pour ProPos)</div>
			</div>
		</div>
		{:else}
			<div class="selection">
				<h3
					class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
				>
				Réduction de dimension
			</h3>

			<div class="param-column">
				<select
					id="reduction-method"
					value={reductionValue}
					onchange={handleReductionChange}
					class="native-select"
				>
					<option value="none">Aucune</option>
					<option value="pca">PCA</option>
					<option value="tsne">t-SNE</option>
					<option value="autoencoder">Autoencoder</option>
					<option value="saint">SAINT</option>
				</select>
			</div>
		</div>
		{/if}
{/if}

<div class="pt-4">
	<Button
		class="w-full"
		onclick={() => analysisRune.requestRun()}
		disabled={analysisRune.isRunning}
	>
		{analysisRune.isRunning ? "Calcul..." : "Run analysis"}
	</Button>
</div>

<h3
	class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
>
	Area selection
</h3>

<AreaSelector />

{#if dataRune.filters.category === Category.Sampling}
	<div class="selection">
		<h2
			class="scroll-m-20 border-b pt-8 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
		>
			Matrix
		</h2>

		<div class="matrix-buttons-grid">
			<Button
				variant={isAllSelected("matrix") ? "default" : "outline"}
				size="sm"
				onclick={() => toggleSelectAll("matrix")}
			>
				All
			</Button>

			{#each Object.keys(dataRune.allMatrixes) as matrix}
				<Button
					variant={dataRune.filters.matrix.includes(matrix)
						? "default"
						: "outline"}
					size="sm"
					onclick={() => {
						const idx = dataRune.filters.matrix.indexOf(matrix);
						if (idx === -1) {
							dataRune.filters.matrix = [
								...dataRune.filters.matrix,
								matrix,
							];
						} else {
							dataRune.filters.matrix = dataRune.filters.matrix.filter(
								(m) => m !== matrix,
							);
						}
					}}
				>
					{matrix}
				</Button>
			{/each}
		</div>
	</div>

	<div class="selection">
		<h2
			class="scroll-m-20 border-b pt-8 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
		>
			Datasets
		</h2>

		<Popover.Root bind:open={datasetOpen}>
			<Popover.Trigger bind:ref={datasetTriggerRef}>
				{#snippet child({ props })}
					<Button
						variant="outline"
						class="w-full justify-between"
						{...props}
						role="combobox"
						aria-expanded={datasetOpen}
					>
						{selectedDataset
							? datasetsOptions.find((d) => d.value === selectedDataset)?.label
							: "Select a dataset..."}
						<ChevronsUpDown class="ml-2 opacity-50" />
					</Button>
				{/snippet}
			</Popover.Trigger>

			<Popover.Content class="w-[300px] p-0">
				<Command.Root>
					<Command.Input placeholder="Search dataset..." />
					<Command.List>
						<Command.Empty>No dataset found.</Command.Empty>
						<Command.Group>
							{#each datasetsOptions as ds (ds.value)}
								<Command.Item
									value={ds.label}
									onSelect={() => {
										if (!dataRune.filters.datasetId.includes(ds.value)) {
											dataRune.filters.datasetId = [
												...dataRune.filters.datasetId,
												ds.value,
											];
										}
										selectedDataset = ds.value;
										closeAndFocusDatasetTrigger();
									}}
								>
									<Check
										class={cn(
											selectedDataset !== ds.value && "text-transparent",
										)}
									/>
									{ds.label}
								</Command.Item>
							{/each}
						</Command.Group>
					</Command.List>
				</Command.Root>
			</Popover.Content>
		</Popover.Root>

		{#each dataRune.filters.datasetId as datasetId}
			{#each Object.entries(dataRune.allDatasets) as [name, { id }]}
				{#if String(id) === datasetId}
					<Button
						size="sm"
						class="px-3 py-1 text-xs"
						onclick={() => removeDataset(datasetId)}
					>
						{name} ✕
					</Button>
				{/if}
			{/each}
		{/each}
	</div>

	<h2
		class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
	>
		Year range
	</h2>

	<div class="my-2 space-y-2">
		<YearSlider type="multiple" min={2003} max={2025} step={1} />
	</div>

	<div class="selection">
		<h2
			class="scroll-m-20 border-b pt-8 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
		>
			Substances
		</h2>

		{#each dataRune.filters.substances as sub (sub.name + sub.unit)}
			<div class="relative p-4 rounded-md border">
				<button
					class="absolute top-2 right-2 text-muted-foreground hover:text-destructive"
					onclick={() =>
						(dataRune.filters.substances =
							dataRune.filters.substances.filter(
								(s) => !(s.name === sub.name && s.unit === sub.unit),
							))}
				>
					✕
				</button>

				<div class="mb-4 text-sm font-medium">
					<strong>{sub.name}</strong> | {sub.unit}
				</div>

				{#if sub.rangeMode === "filtered"}
					<SubstanceRangeSlider
						type="multiple"
						min={sub.filtered.min}
						max={sub.filtered.max}
						step={Math.max((sub.filtered.max - sub.filtered.min) / 60, 0.0001)}
						filterKey={{ substance: sub.name, unit: sub.unit }}
						class="w-full"
					/>
				{:else}
					<SubstanceRangeSlider
						type="multiple"
						min={sub.raw.min}
						max={sub.raw.max}
						step={Math.max((sub.raw.max - sub.raw.min) / 60, 0.0001)}
						filterKey={{ substance: sub.name, unit: sub.unit }}
						class="w-full"
					/>
				{/if}
			</div>
		{/each}

		<Popover.Root>
			<Popover.Trigger>
				<Button class="w-full" variant="outline">Add substance</Button>
			</Popover.Trigger>

			<Popover.Content
				class="w-[300px] p-4 space-y-4 bg-background border rounded-md shadow"
			>
				<h3 class="text-base font-semibold">Add a substance</h3>

				<div>
					<label class="text-sm font-medium" for="substance-select">
						Substance
					</label>

					<Popover.Root bind:open>
						<Popover.Trigger bind:ref={triggerRef} id="substance-select">
							{#snippet child({ props })}
								<Button
									variant="outline"
									class="w-full justify-between"
									{...props}
									role="combobox"
									aria-expanded={open}
								>
									{selectedSubstance || "Select a substance..."}
									<ChevronsUpDown class="ml-2 opacity-50" />
								</Button>
							{/snippet}
						</Popover.Trigger>

						<Popover.Content class="w-[300px] p-0">
							<Command.Root>
								<Command.Input placeholder="Search substance..." />
								<Command.List>
									<Command.Empty>No substance found.</Command.Empty>
									<Command.Group>
										{#each substancesOptions as substance (substance.value)}
											<Command.Item
												value={substance.value}
												onSelect={() => {
													selectedSubstance = substance.value;
													closeAndFocusTrigger();
												}}
											>
												<Check
													class={cn(
														selectedSubstance !== substance.value &&
															"text-transparent",
													)}
												/>
												{substance.label}
											</Command.Item>
										{/each}
									</Command.Group>
								</Command.List>
							</Command.Root>
						</Popover.Content>
					</Popover.Root>
				</div>

				<div>
					<label class="text-sm font-medium" for="unit-select">Unit</label>
					<Select.Root
						type="single"
						bind:value={selectedUnit}
						disabled={!selectedSubstance}
					>
						<Select.Trigger class="w-full mt-1" id="unit-select">
							{selectedUnit || "Select unit..."}
						</Select.Trigger>

						<Select.Content>
							{#if isCheckingUnits}
								<div class="p-2 text-sm text-muted-foreground">
									Checking available units...
								</div>
							{:else}
								<Select.Group>
									{#each dataRune.allSubstances[selectedSubstance]?.units ?? [] as unit}
										<Select.Item value={unit}>
											{unit}
											{#if unavailableUnits.includes(unit)}
												<span class="ml-2 text-xs text-muted-foreground">
													(0 result with these filters)
												</span>
											{/if}
										</Select.Item>
									{/each}
								</Select.Group>
							{/if}
						</Select.Content>
					</Select.Root>
				</div>

				<Popover.Close>
					<Button
						class="w-full"
						onclick={async () => {
							const rangeResult = await fetchSubstanceRange(
								selectedSubstance,
								selectedUnit,
								dataRune.filters.category,
							);

							if (rangeResult) {
								const { raw, filtered } = rangeResult;

								dataRune.filters.substances = [
									...dataRune.filters.substances,
									{
										name: selectedSubstance,
										unit: selectedUnit,
										rangeMode: "filtered",
										raw,
										filtered,
										filteredRange: [filtered.min, filtered.max],
										rawRange: [raw.min, raw.max],
									},
								];

								selectedSubstance = "";
								selectedUnit = "";
							}
						}}
						disabled={!selectedSubstance ||
							!selectedUnit ||
							dataRune.filters.substances.some(
								(s) =>
									s.name === selectedSubstance &&
									s.unit === selectedUnit,
							)}
					>
						Add
					</Button>
				</Popover.Close>
			</Popover.Content>
		</Popover.Root>
	</div>
{/if}

<RunHistory />

<style>
	.selection {
		display: flex;
		flex-direction: column;
		gap: 0.8rem;
	}

	.matrix-buttons-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		gap: 0.5rem;
	}

	.param-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.param-row label {
		font-size: 0.95rem;
		font-weight: 500;
	}

	.param-row input[type="number"] {
		width: 120px;
		border: 1px solid #d4d4d8;
		border-radius: 0.5rem;
		padding: 0.45rem 0.65rem;
		background: white;
	}

	.param-column {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.native-select {
		width: 100%;
		border: 1px solid #d4d4d8;
		border-radius: 0.5rem;
		padding: 0.55rem 0.75rem;
		background: white;
	}

	.static-hint {
		border: 1px solid #d4d4d8;
		border-radius: 0.5rem;
		padding: 0.55rem 0.75rem;
		background: #f8fafc;
		color: #475569;
		font-size: 0.9rem;
	}

	.advanced-toggle-block {
		display: flex;
		flex-direction: column;
		margin-top: 1rem;
	}

	.advanced-toggle-btn {
		width: 100%;
		padding: 0.7rem 0.9rem;
		border: 1px solid #d4d4d8;
		border-radius: 0.5rem;
		background: white;
		font-size: 0.95rem;
		font-weight: 600;
		color: #0f172a;
		cursor: pointer;
		text-align: left;
		transition: all 0.15s ease;
	}

	.advanced-toggle-btn:hover {
		border-color: #94a3b8;
		background: #f8fafc;
	}
</style>
