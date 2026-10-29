import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
import { AreaSelectorMode } from "$lib/features/exploration/exploration.state.svelte";

type ResponseType = {
	min: number;
	max: number;
	count: number;
}[];

export async function fetchSubstanceHistogram({
	substance,
}: {
	substance: { substance: string; unit: string };
}): Promise<ResponseType> {
	const filters = { ...dataRune.filters };
	const areaMode = dataRune.areaSelectorMode;

	const targetSub = dataRune.filters.substances.find(
		(s) => s.name === substance.substance && s.unit === substance.unit,
	);

	let rangeLimit: [number, number] | null = null;

	if (targetSub?.rangeMode === "raw") {
		rangeLimit = targetSub?.filtered
			? [targetSub.raw.min, targetSub.raw.max]
			: null;
	} else {
		rangeLimit = targetSub?.filtered
			? [targetSub.filtered.min, targetSub.filtered.max]
			: null;
	}

	if (dataRune.areaSelectorMode !== AreaSelectorMode.nuts) {
		filters.nutsRegions = [];
	}

	filters.substances = filters.substances.filter(
		(s) => !(s.name === substance.substance && s.unit === substance.unit),
	);

	try {
		const res = await fetch("/api/substance-histogram", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({
				filters,
				substance: substance.substance,
				unit: substance.unit,
				rangeLimit,
				areaMode,
			}),
		});

		if (!res.ok) {
			console.error("[fetchSubstanceHistogram] Status non OK", res.status);
			return [];
		}

		const json: ResponseType = await res.json();
		return json;
	} catch (err) {
		console.error("[fetchSubstanceHistogram] Request failed", err);
		return [];
	}
}


/*import { dataRune } from "$lib/features/exploration/exploration.state.svelte";
import { AreaSelectorMode } from "$lib/features/exploration/exploration.state.svelte";

type ResponseType = {
    min: number;
    max: number;
    count: number;
}[];

export async function fetchSubstanceHistogram({
    substance
}: {
    substance: { substance: string; unit: string };
}): Promise<ResponseType> {
    const filters = { ...dataRune.filters };
    const areaMode = dataRune.areaSelectorMode;

    // Cherche la substance analysée pour récupérer min/max
    const targetSub = dataRune.filters.substances.find(
        (s) => s.name === substance.substance && s.unit === substance.unit
    );

    let rangeLimit: [number, number];

    if (targetSub?.rangeMode === "raw") {

        rangeLimit =
            targetSub?.filtered
                ? [targetSub.raw.min, targetSub.raw.max]
                : [-Infinity, Infinity];
    } else {
        rangeLimit =
            targetSub?.filtered
                ? [targetSub.filtered.min, targetSub.filtered.max]
                : [-Infinity, Infinity]; 
    }


    if (dataRune.areaSelectorMode !== AreaSelectorMode.nuts) {
        filters.nutsRegions = [];
    }

    // Supprimer le filtre actif pour cette substance
    filters.substances = filters.substances.filter(
        (s) => !(s.name === substance.substance && s.unit === substance.unit)
    );

    try {
        const res = await fetch("/api/substance-histogram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                filters,
                substance: substance.substance,
                unit: substance.unit,
                rangeLimit,
                areaMode
            })
        });

        if (!res.ok) {
            console.error("[fetchSubstanceHistogram] Status non OK", res.status);
            return [];
        }

        const json: ResponseType = await res.json();

        return json
    } catch (err) {
        console.error("[fetchSubstanceHistogram] Request failed", err);
        return [];
    }
}
*/