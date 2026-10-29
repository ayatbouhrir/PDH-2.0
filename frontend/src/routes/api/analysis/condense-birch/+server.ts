import type { RequestHandler } from "./$types";

const PYTHON_API_BASE = "http://127.0.0.1:8000";

export const POST: RequestHandler = async ({ request, fetch }) => {
	const body = await request.text();

	const upstream = await fetch(`${PYTHON_API_BASE}/analysis/condense-birch`, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
		},
		body,
	});

	const text = await upstream.text();

	return new Response(text, {
		status: upstream.status,
		headers: {
			"Content-Type": upstream.headers.get("content-type") ?? "application/json",
		},
	});
};