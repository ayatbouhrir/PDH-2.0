import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { proxyPythonJson } from "$lib/server/pythonAnalysisProxy";

export const POST: RequestHandler = async () => {
	const payload = await proxyPythonJson("/analysis/history/clear", {
		method: "POST",
		timeoutMs: 30_000,
	});
	return json(payload);
};
