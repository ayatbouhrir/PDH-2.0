<script lang="ts">
    import * as Dialog from "$lib/components/ui/dialog/index";
    import { Label } from "$lib/components/ui/label/index";
    import { Checkbox } from "$lib/components/ui/checkbox/index";
    import { Button } from "$lib/components/ui/button/index";
    import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
    import { exportableFields } from '$lib/features/export/exportable-fields';

    const props = $props();

    let availableFields: string[] = $state([]);
    let selectedFields = $state(new Set<string>());
    let estimatedSize = $state(0);

    // Initialise les champs exportables
    $effect(() => {
        if (
            availableFields.length === 0 &&
            exportableFields.length > 0
        ) {
            availableFields = exportableFields;
            selectedFields = new Set(availableFields);
            // updateEstimatedSize();
        }
    });

    // $effect(() => {
    //     updateEstimatedSize();
    // });

    function toggleField(field: string) {
        if (selectedFields.has(field)) {
            selectedFields.delete(field);
        } else {
            selectedFields.add(field);
        }
        selectedFields = new Set(selectedFields); // trigger reactivity
        // updateEstimatedSize();
    }

    // async function updateEstimatedSize() {
    //     const ids = dataRune.filteredPoints.map((p) => p.id);
    //     if (ids.length === 0) {
    //         estimatedSize = 0;
    //         return;
    //     }

    //     const body = {
    //         idList: ids,
    //         fieldList: Array.from(selectedFields),
    //     };

    //     const res = await fetch("/api/export-preview", {
    //         method: "POST",
    //         headers: { "Content-Type": "application/json" },
    //         body: JSON.stringify(body),
    //     });

    //     const preview = await res.text();
    //     estimatedSize = Math.round(preview.length / 1024); // en KB
    // }

    async function exportCSV() {
        const filters = { ...dataRune.filters };
        if (dataRune.areaSelectorMode !== "NUTS") {
            filters.nutsRegions = [];
        }

        const areaMode = dataRune.areaSelectorMode;

        const res = await fetch("/api/filter-points", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                filters,
                areaMode,
                exportMode: true,
                fields: Array.from(selectedFields),
            }),
        });

        if (!res.ok) {
            const errorText = await res.text();
            console.error("Erreur export CSV :", errorText);
            return;
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "export.csv";
        link.click();
        URL.revokeObjectURL(url);
    }
    function selectAllFields() {
        selectedFields = new Set(availableFields);
    }

    function unselectAllFields() {
        selectedFields = new Set();
    }
</script>

<Dialog.Root open={props.open}>
    <Dialog.Trigger>
        <Button variant="outline">
            Export {new Intl.NumberFormat("fr-FR").format(
                dataRune.nbFilteredPoints,
            )} points
        </Button>
    </Dialog.Trigger>
    <Dialog.Content class="sm:max-w-[500px] max-h-[100vh] overflow-y-auto">
        <Dialog.Header>
            <Dialog.Title>Export data</Dialog.Title>
            <Dialog.Description>
                Choose the fields to include in the CSV export.
            </Dialog.Description>
        </Dialog.Header>

        <div class="grid gap-3 py-2">
            <div class="flex gap-2 mb-4">
                <Button
                    variant="outline"
                    class="w-full flex-1"
                    onclick={selectAllFields}
                >
                    Select all
                </Button>
                <Button
                    variant="outline"
                    class="w-full flex-1"
                    onclick={unselectAllFields}
                >
                    Unselect all
                </Button>
            </div>

            <hr class="my-2 border-muted-foreground opacity-30" />

            {#each availableFields as field (field)}
                <div class="flex items-center gap-3">
                    <Checkbox
                        id={`field-${field}`}
                        checked={selectedFields.has(field)}
                        onCheckedChange={() => toggleField(field)}
                    />
                    <Label for={`field-${field}`}>{field}</Label>
                </div>
            {/each}
        </div>

        <Dialog.Footer>
            <Button onclick={exportCSV} class="w-full">Export</Button>
        </Dialog.Footer>
    </Dialog.Content>
</Dialog.Root>
