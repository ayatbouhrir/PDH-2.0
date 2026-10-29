import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

import { proxyPythonJson } from "$lib/server/pythonAnalysisProxy";

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const result = await proxyPythonJson("/analysis/clamp", {
		method: "POST",
		body,
		timeoutMs: 300_000,
	});

	return json(result);
};
