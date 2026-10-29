import { json, type RequestHandler } from "@sveltejs/kit";

type PopulationRequest = {
	lat: number;
	lon: number;
	radiusKm?: number;
	year?: number;
};

function buildCirclePolygon(
	lat: number,
	lon: number,
	radiusKm: number,
	steps = 24,
): GeoJSON.FeatureCollection {
	const earthRadiusKm = 6371;
	const latRad = (lat * Math.PI) / 180;
	const lonRad = (lon * Math.PI) / 180;
	const angularDistance = radiusKm / earthRadiusKm;

	const coords: [number, number][] = [];

	for (let i = 0; i <= steps; i++) {
		const bearing = (2 * Math.PI * i) / steps;

		const newLat = Math.asin(
			Math.sin(latRad) * Math.cos(angularDistance) +
				Math.cos(latRad) * Math.sin(angularDistance) * Math.cos(bearing),
		);

		const newLon =
			lonRad +
			Math.atan2(
				Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latRad),
				Math.cos(angularDistance) - Math.sin(latRad) * Math.sin(newLat),
			);

		coords.push([
			(newLon * 180) / Math.PI,
			(newLat * 180) / Math.PI,
		]);
	}

	return {
		type: "FeatureCollection",
		features: [
			{
				type: "Feature",
				properties: {},
				geometry: {
					type: "Polygon",
					coordinates: [coords],
				},
			},
		],
	};
}

export const POST: RequestHandler = async ({ request, fetch }) => {
	try {
		const body = (await request.json()) as PopulationRequest;

		const lat = Number(body.lat);
		const lon = Number(body.lon);
		const radiusKm = Number(body.radiusKm ?? 5);
		const year = Number(body.year ?? 2020);

		if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
			return json({ error: "lat/lon invalides" }, { status: 400 });
		}

		const geojson = buildCirclePolygon(lat, lon, radiusKm, 24);
		const encodedGeojson = encodeURIComponent(JSON.stringify(geojson));

		const url =
			`https://api.worldpop.org/v1/services/stats` +
			`?dataset=wpgppop` +
			`&year=${year}` +
			`&geojson=${encodedGeojson}` +
			`&runasync=false`;

		console.log("[WorldPop request]", { lat, lon, radiusKm, year, url });

		const controller = new AbortController();
		const timeout = setTimeout(() => controller.abort(), 20000);

		let upstream: Response;
		try {
			upstream = await fetch(url, {
				method: "GET",
				headers: {
					Accept: "application/json",
					"User-Agent": "PDH-local-population/1.0",
				},
				signal: controller.signal,
			});
		} finally {
			clearTimeout(timeout);
		}

		const rawText = await upstream.text();

		if (!upstream.ok) {
			console.error("[api/local-population] upstream HTTP error:", upstream.status, rawText);
			return json(
				{
					error: `WorldPop HTTP ${upstream.status}`,
					detail: rawText,
				},
				{ status: 502 },
			);
		}

		let data: any;
		try {
			data = JSON.parse(rawText);
		} catch {
			console.error("[api/local-population] invalid JSON from WorldPop:", rawText);
			return json(
				{
					error: "Réponse JSON invalide de WorldPop",
					detail: rawText,
				},
				{ status: 502 },
			);
		}

		return json(data);
	} catch (error: any) {
		console.error("[api/local-population] error:", error);

		const isAbort = error?.name === "AbortError";

		return json(
			{
				error: isAbort
					? "Timeout lors de l'appel à WorldPop"
					: "Échec de l'appel à WorldPop",
				detail: error?.message ?? "Erreur inconnue",
			},
			{ status: 502 },
		);
	}
};