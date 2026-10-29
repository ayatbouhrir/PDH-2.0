import { dataRune } from "$lib/features/exploration/exploration.state.svelte";

export async function checkUnitAvailability(substanceName: string): Promise<string[]> {
	const filters = {
		...dataRune.filters,
		substances: [
			...dataRune.filters.substances,
			{ name: substanceName, unit: "" }
		]
	};

	const areaMode = dataRune.areaSelectorMode;

	const res = await fetch("/api/check-units", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ filters, areaMode })
	});

	if (!res.ok) {
		console.error("Error checking unit availability:", res.statusText);
		return [];
	}

	const units = await res.json();
	return units as string[];
}
