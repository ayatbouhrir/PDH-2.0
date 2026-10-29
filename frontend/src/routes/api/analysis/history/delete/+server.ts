import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { proxyPythonJson } from "$lib/server/pythonAnalysisProxy";

export const POST: RequestHandler = async ({ request }) => {
	let body: unknown;

	try {
		body = await request.json();
	} catch {
		throw error(400, "Invalid JSON body");
	}

	const payload = await proxyPythonJson("/analysis/history/delete", {
		method: "POST",
		body,
		timeoutMs: 30_000,
	});
	return json(payload);
};
