import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { proxyPythonJson } from "$lib/server/pythonAnalysisProxy";

export const GET: RequestHandler = async ({ url }) => {
	const limit = url.searchParams.get("limit") ?? "10";
	const payload = await proxyPythonJson(`/analysis/history/list?limit=${encodeURIComponent(limit)}`);
	return json(payload);
};
