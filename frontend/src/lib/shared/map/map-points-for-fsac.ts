import L from "leaflet";

export function mapPointsForFsac(points: any[], zoom: number) {

	// rayon variable en fonction du zoom actuel
	const projection = Math.pow(1.4, zoom);
	const radius = 20000 / projection;

	const result = [];

	for (const p of points) {
		const lat = parseFloat(p.lat);
		const lon = parseFloat(p.lon);
		if (isNaN(lat) || isNaN(lon)) continue;

		// on projete les coordonnées géographiques en coordonnées cartésiennes
		const projected = L.Projection.SphericalMercator.project(L.latLng(lat, lon));

		result.push({
			id: p.id,
			x: projected.x,
			y: projected.y,
			r: radius,
			n: 1,
			children: [],
			data: p.pfas_sum,
		});
	}

	return result;
}