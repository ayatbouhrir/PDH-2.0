<script lang="ts">
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
    const { panelTitle = "Data type" } = $props<{
     panelTitle?: string;
    }>();
    let selectedSubstance = $state("");
    let selectedUnit = $state("");
    let triggerRef = $state<HTMLButtonElement>(null!);
    let datasetOpen = $state(false);
    let selectedDataset = $state("");
    let datasetTriggerRef = $state<HTMLButtonElement>(null!);
    let unavailableUnits = $state<string[]>([]);
    let isCheckingUnits = $state(false);

    $effect(() => {
        if (selectedSubstance) {
            isCheckingUnits = true;
            checkUnitAvailability(selectedSubstance).then((units) => {
                unavailableUnits = dataRune.allSubstances[
                    selectedSubstance
                ].units.filter((u) => !units.includes(u));
                isCheckingUnits = false;
            });
        } else {
            unavailableUnits = [];
            isCheckingUnits = false;
        }
    });

    function toggleSelectAll(field: "datasetId" | "matrix") {
        if (field === "datasetId") {
            dataRune.filters.datasetId =
                dataRune.filters.datasetId.length === 0
                    ? Object.keys(dataRune.allDatasets)
                    : [];
        } else if (field === "matrix") {
            dataRune.filters.matrix =
                dataRune.filters.matrix.length === 0
                    ? Object.keys(dataRune.allMatrixes)
                    : [];
        }
    }

    function isAllSelected(field: "datasetId" | "matrix") {
        return dataRune.filters[field].length === 0;
    }

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

    function closeAndFocusTrigger() {
        open = false;
        tick().then(() => {
            triggerRef.focus();
        });
    }

    function closeAndFocusDatasetTrigger() {
        datasetOpen = false;
        tick().then(() => {
            datasetTriggerRef.focus();
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
        Data type
    </h3>

    <Select.Root
        type="single"
        bind:value={dataRune.filters.category}
        onValueChange={() => {
            // dataRune.filters.datasetId = [];
            // dataRune.filters.matrix = [];
            // dataRune.filters.yearRange = [2003, 2025],
            // // dataRune.filters.nutsRegions = [],
            // // dataRune.filters.lassoRegion = [],
            // dataRune.filters.substances = []
        }}
    >
        <Select.Trigger>
            {dataRune.filters.category || "Choose a category"}
        </Select.Trigger>
        <Select.Content>
            <Select.Group>
                <Select.GroupHeading>Categories</Select.GroupHeading>

                {#each [...Object.values(Category)] as cat (cat)}
                    <Select.Item value={cat}>{cat}</Select.Item>
                {/each}
            </Select.Group>
        </Select.Content>
    </Select.Root>
</div>

<h3
    class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
>
    Area selection
</h3>

<AreaSelector />

{#if dataRune.filters.category === Category.Sampling}
    <!-- Matrices -->
    <div class="selection">
        <h2
            class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
        >
            Matrix
        </h2>
        <div class="matrix-buttons-grid">
            <Button
                variant={isAllSelected("matrix") ? "default" : "outline"}
                onclick={() => toggleSelectAll("matrix")}
            >
                All
            </Button>

            {#each Object.entries(dataRune.allMatrixes) as [m, count]}
                <Button
                    variant={dataRune.filters.matrix.includes(m)
                        ? "default"
                        : "outline"}
                    onclick={() => {
                        if (dataRune.filters.matrix.includes(m)) {
                            dataRune.filters.matrix =
                                dataRune.filters.matrix.filter((i) => i !== m);
                        } else {
                            dataRune.filters.matrix = [
                                ...dataRune.filters.matrix,
                                m,
                            ];
                        }
                    }}
                >
                    <span class="truncate">{m}</span>
                </Button>
            {/each}
        </div>
    </div>

    <!-- Datasets -->
    <div class="selection">
        <h2
            class="scroll-m-20 border-b pt-8 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
        >
            Datasets
        </h2>

        <!-- ComboBox datasets -->
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
                            ? datasetsOptions.find(
                                  (d) => d.value === selectedDataset,
                              )?.label
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
                                        if (
                                            !dataRune.filters.datasetId.includes(
                                                ds.value,
                                            )
                                        ) {
                                            dataRune.filters.datasetId = [
                                                ...dataRune.filters.datasetId,
                                                ds.value,
                                            ];
                                        }
                                        selectedDataset = "";
                                        closeAndFocusDatasetTrigger();
                                    }}
                                >
                                    <Check
                                        class={cn(
                                            selectedDataset !== ds.value &&
                                                "text-transparent",
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

        <!-- Datasets sélectionnés -->
        {#each dataRune.filters.datasetId as datasetId}
            {#each Object.entries(dataRune.allDatasets) as [name, { id, count }]}
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

    <!-- Year range -->
    <h2
        class="scroll-m-20 border-b pt-5 pb-2 text-xl font-semibold tracking-tight transition-colors first:mt-0"
    >
        Year range
    </h2>

    <div class="my-2 space-y-2">
        <YearSlider type="multiple" min={2003} max={2025} step={1}/>
    </div>

    <!-- Substances existantes -->
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
                                (s) =>
                                    !(
                                        s.name === sub.name &&
                                        s.unit === sub.unit
                                    ),
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
                        step={(sub.filtered.max - sub.filtered.min) / 60}
                        filterKey={{ substance: sub.name, unit: sub.unit }}
                        class="w-full"
                    />
                {:else}


                    <SubstanceRangeSlider
                        type="multiple"
                        min={sub.raw.min}
                        max={sub.raw.max}
                        step={(sub.raw.max - sub.raw.min) / 60}
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

                <!-- Select substance -->
                <div>
                    <label class="text-sm font-medium" for="substance-select">Substance</label>
                    <!-- ComboBox substances -->
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
                                    {selectedSubstance ||
                                        "Select a substance..."}
                                    <ChevronsUpDown class="ml-2 opacity-50" />
                                </Button>
                            {/snippet}
                        </Popover.Trigger>
                        <Popover.Content class="w-[300px] p-0">
                            <Command.Root>
                                <Command.Input
                                    placeholder="Search substance..."
                                />
                                <Command.List>
                                    <Command.Empty
                                        >No substance found.</Command.Empty
                                    >
                                    <Command.Group>
                                        {#each substancesOptions as substance (substance.value)}
                                            <Command.Item
                                                value={substance.value}
                                                onSelect={() => {
                                                    selectedSubstance =
                                                        substance.value;
                                                    closeAndFocusTrigger();
                                                }}
                                            >
                                                <Check
                                                    class={cn(
                                                        selectedSubstance !==
                                                            substance.value &&
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

                <!-- Select unit -->
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
                                                <span
                                                    class="ml-2 text-xs text-muted-foreground"
                                                    >(0 result with these
                                                    filters)</span
                                                >
                                            {/if}
                                        </Select.Item>
                                    {/each}
                                </Select.Group>
                            {/if}
                        </Select.Content>
                    </Select.Root>
                </div>

                <!-- Add button -->
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
                                        filteredRange: [
                                            filtered.min,
                                            filtered.max,
                                        ],
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
</style>
