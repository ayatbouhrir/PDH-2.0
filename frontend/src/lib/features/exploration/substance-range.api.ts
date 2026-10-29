export async function fetchSubstanceRange(
	substance: string,
	unit: string,
	category: string
): Promise<{
	raw: { min: number; max: number; count: number };
	filtered: { min: number; max: number, count: number };
} | null> {
	try {
		const res = await fetch('/api/fetch-substance-range', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ substance, unit, category })
		});

		if (!res.ok) throw new Error(`Server error: ${res.status}`);
		return await res.json();
	} catch (err) {
		console.error('[fetchSubstanceRange] Error:', err);
		return null;
	}
}
