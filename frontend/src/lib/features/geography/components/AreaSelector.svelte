<script lang="ts">
    import * as d3 from "d3";
    import * as Select from "$lib/components/ui/select/index";
    import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
    import { Button } from "$lib/components/ui/button/index";
    import LassoSelect from "@lucide/svelte/icons/lasso-select";
    import RotateCcw from "@lucide/svelte/icons/rotate-ccw";
    import { AreaSelectorMode } from "$lib/features/exploration/exploration.state.svelte";

    let selectedYear = $state("2024");
    let selectedLevel = $state("0");
    let container: HTMLDivElement;
    let geojsonData: any = null;
    let worldGeojson: any = null;

    let selectedRegions: { id: string; name: string }[] = $state([]);

    async function loadAndRenderMap() {
        const nutsUrl = `/nuts/NUTS_${selectedYear}.geojson`;
        const worldUrl = `miniMap/world.geojson`;

        selectedRegions = [];
        dataRune.filters.nutsRegions = [];

        geojsonData = await d3.json(nutsUrl);
        worldGeojson = await d3.json(worldUrl);

        renderMap();
    }

    function renderMap() {
        d3.select(container).select("svg").remove();

        const svg = d3
            .select(container)
            .append("svg")
            .attr("viewBox", "0 0 1000 700")
            .attr("preserveAspectRatio", "xMidYMid meet")
            .style("width", "100%")
            .style("height", "100%");

        const projection = d3
            .geoConicConformal()
            .center([11, 50])
            .scale(1800)
            .translate([500, 350]);

        const path = d3.geoPath().projection(projection);

        // === 🌍 Monde en fond ===
        svg.append("g")
            .attr("class", "world-background")
            .selectAll("path")
            .data(worldGeojson.features)
            .join("path")
            .attr("d", (d: any) => path(d) as string)
            .attr("fill", "hsl(var(--color-land))")
            .attr("stroke", "#ccc")
            .attr("stroke-width", 0.3)
            .attr("opacity", 0.4);

        // === Couches interactives selon le niveau sélectionné ===
        const g = svg.append("g");

        const features = geojsonData.features.filter(
            (f: any) => f.properties.LEVL_CODE === +selectedLevel,
        );

        g.selectAll("path")
            .data(features)
            .join("path")
            .attr("d", (d: any) => path(d) as string)
            .attr("data-id", (d: any) => d.properties.NUTS_ID)
            .attr("fill", (d: any) =>
                selectedRegions.some((r) => r.id === d.properties.NUTS_ID)
                    ? "hsl(var(--primary))"
                    : "hsl(var(--color-countries))",
            )

            .attr("stroke", "#777")
            .attr("stroke-width", 0.4)
            .attr("opacity", 0.95)
            .style("cursor", "pointer")
            .on("mouseover", function (event, d: any) {
                const id = d.properties.NUTS_ID;
                d3.select(this).attr(
                    "fill",
                    selectedRegions.some((r) => r.id === id)
                        ? "var(--color-primary-hover)"
                        : "hsl(var(--color-land-hover))",
                );
            })
            .on("mouseout", function () {
                d3.select(this).attr("fill", (d: any) =>
                    selectedRegions.some((r) => r.id === d.properties.NUTS_ID)
                        ? "hsl(var(--primary))"
                        : "hsl(var(--color-countries))",
                );
            })
            .on("click", function (event, d: any) {
                const element = this as SVGPathElement;
                const id = d.properties.NUTS_ID;
                const name = d.properties.NUTS_NAME;

                const exists = selectedRegions.find((r) => r.id === id);

                if (exists) {
                    selectedRegions = selectedRegions.filter(
                        (r) => r.id !== id,
                    );
                } else {
                    selectedRegions = [...selectedRegions, { id, name }];
                }

                updateSelectedRegionsInRune();

                d3.select(element).attr(
                    "fill",
                    selectedRegions.some((r) => r.id === id)
                        ? "hsl(var(--primary))"
                        : "hsl(var(--color-countries))",
                );
            });

        // === NUTS 0 en fond (toujours visible) ===
        svg.append("g")
            .attr("class", "nuts0-background")
            .selectAll("path")
            .data(
                geojsonData.features.filter(
                    (f: any) => f.properties.LEVL_CODE === 0,
                ),
            )
            .join("path")
            .attr("d", (d: any) => path(d) as string)
            .attr("fill", "none")
            .attr("stroke", "#555")
            .attr("stroke-width", 0.8)
            .attr("pointer-events", "none")
            .attr("opacity", 1);

        svg.call(
            d3.zoom<SVGSVGElement, unknown>().on("zoom", (event) => {
                g.attr("transform", event.transform);
                svg.select(".world-background").attr(
                    "transform",
                    event.transform,
                );
                svg.select(".nuts0-background").attr(
                    "transform",
                    event.transform,
                );
            }),
        );
    }

    function updateSelectedRegionsInRune() {
        dataRune.filters.nutsRegions = selectedRegions.map(({ id }) => ({
            id,
            year: Number(selectedYear),
            level: Number(selectedLevel),
        }));
    }

    $effect(() => {
        if (selectedYear && selectedLevel) {
            loadAndRenderMap();
        }
    });
</script>

<div class="flex items-center gap-3 pt-3 pb-2 w-full border-b">
    <!-- <span class="text-sm font-medium text-muted-foreground flex-1">Mode</span> -->
    <Button
        class="flex-1"
        variant={dataRune.areaSelectorMode === "NUTS" ? "default" : "outline"}
        onclick={() => (dataRune.areaSelectorMode = AreaSelectorMode.nuts)}
    >
        Mini map
    </Button>
    <Button
        class="flex-1"
        variant={dataRune.areaSelectorMode === "LASSO" ? "default" : "outline"}
        onclick={() => {
            dataRune.areaSelectorMode = AreaSelectorMode.lasso;
        }}
    >
        Lasso
    </Button>
</div>

<div class="map-filter-layout pt-3">
    <!-- Filtres NUTS -->
    {#if dataRune.areaSelectorMode === AreaSelectorMode.nuts}
        <div class="nuts-controls">
            <Select.Root bind:value={selectedYear} type="single">
                <Select.Trigger>NUTS {selectedYear}</Select.Trigger>
                <Select.Content>
                    <Select.Group>
                        <Select.GroupHeading>Dataset year</Select.GroupHeading>
                        {#each ["2016", "2021", "2024"] as y}
                            <Select.Item value={y}>{y}</Select.Item>
                        {/each}
                    </Select.Group>
                </Select.Content>
            </Select.Root>

            <Select.Root bind:value={selectedLevel} type="single">
                <Select.Trigger>Level {selectedLevel}</Select.Trigger>
                <Select.Content>
                    <Select.Group>
                        <Select.GroupHeading>NUTS Level</Select.GroupHeading>
                        {#each ["0", "1", "2", "3"] as l}
                            <Select.Item value={l}>Level {l}</Select.Item>
                        {/each}
                    </Select.Group>
                </Select.Content>
            </Select.Root>
        </div>
    {/if}

    <!-- Carte -->
    <div
        class:hidden={dataRune.areaSelectorMode !== AreaSelectorMode.nuts}
        class="map-stack"
    >
        <div bind:this={container} class="map-layer"></div>
    </div>

    <!-- Liste des régions sélectionnées -->
    <div
        class:hidden={dataRune.areaSelectorMode !== AreaSelectorMode.nuts}
        class="region-list"
    >
        <div class="flex flex-wrap gap-2">
            {#each selectedRegions as region (region.id)}
                <Button
                    size="sm"
                    class="px-3 py-1 text-xs"
                    onclick={() => {
                        selectedRegions = selectedRegions.filter(
                            (r) => r.id !== region.id,
                        );
                        updateSelectedRegionsInRune();
                        d3.select(`path[data-id="${region.id}"]`).attr(
                            "fill",
                            "hsl(var(--color-countries))",
                        );
                    }}
                >
                    {region.name} ✕
                </Button>
            {/each}
        </div>

        {#if selectedRegions.length === 0}
            <p
                class:hidden={dataRune.areaSelectorMode !==
                    AreaSelectorMode.nuts}
                class="text-muted-foreground text-sm"
            >
                Select an area to start geographical selection.
            </p>
        {:else}
            <Button
                size="sm"
                variant="outline"
                class="px-3 py-1 text-xs mt-2"
                onclick={() => {
                    // Réinitialise la liste
                    selectedRegions = [];
                    updateSelectedRegionsInRune();

                    // Restaure la couleur de tous les pays visibles à leur couleur par défaut
                    d3.selectAll("path[data-id]").attr(
                        "fill",
                        "hsl(var(--color-countries))",
                    );
                }}
            >
                Reset filter
            </Button>
        {/if}
    </div>

    <!-- UI Lasso -->
    {#if dataRune.areaSelectorMode === AreaSelectorMode.lasso}
        <div class="mt-1 flex gap-2">
            {#if dataRune.filters.lassoRegion.length === 0}
                {#if !dataRune.lassoEnabled}
                    <Button
                        onclick={() => {
                            dataRune.lassoEnabled = true;
                            // selectedRegions.forEach((region) => {
                            //     d3.select(`path[data-id="${region.id}"]`).attr(
                            //         "fill",
                            //         "var(--color-countries)",
                            //     );
                            // });
                            // selectedRegions = [];
                        }}
                        class="w-full"
                        variant="outline"
                    >
                        <LassoSelect class="mr-0.5 size-4" />
                        Start lasso selection
                    </Button>
                {:else}
                    <Button
                        onclick={() => {
                            dataRune.lassoEnabled = false;
                        }}
                        class="w-full"
                        variant="outline"
                    >
                        <LassoSelect class="mr-0.5 size-4" />
                        Cancel lasso selection
                    </Button>
                {/if}
            {/if}

            {#if dataRune.filters.lassoRegion.length > 0}
                <Button
                    variant="outline"
                    onclick={() => {
                        dataRune.filters.lassoRegion = [];
                        dataRune.lassoEnabled = false;
                    }}
                    class="w-full"
                >
                    <RotateCcw class="mr-0.5 size-4" />

                    Reset lasso selection
                </Button>
            {/if}
        </div>
    {/if}
</div>

<style>
    .map-filter-layout {
        display: flex;
        flex-direction: column;
        gap: 0.8rem;
        width: 100%;
    }

    .nuts-controls {
        display: flex;
        flex-wrap: nowrap; /* empêche le retour à la ligne */
        gap: 0.8rem;
        justify-content: flex-start;
        align-items: center;
    }

    .map-stack {
        position: relative;
        width: 100%;
        aspect-ratio: 9 / 7;
        border: 1px solid #e3e3e3;
        border-radius: 0.5rem;
        overflow: hidden;
        min-height: 300px;
        cursor: grab; /* main ouverte par défaut */
    }

    .map-layer {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        z-index: 1;
    }

    .region-list {
        width: 100%;
    }
</style>
