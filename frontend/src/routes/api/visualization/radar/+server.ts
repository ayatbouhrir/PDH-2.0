import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const PYTHON_API_URL =
	process.env.PYTHON_API_URL ??
	process.env.VITE_PYTHON_API_URL ??
	"http://127.0.0.1:8000";

const TIMEOUT_MS = 60_000;

export const POST: RequestHandler = async ({ request }) => {
	let body: unknown;

	try {
		body = await request.json();
	} catch {
		throw error(400, "Invalid JSON body");
	}

	const controller = new AbortController();
	const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

	let response: Response;

	try {
		response = await fetch(`${PYTHON_API_URL}/visualization/radar`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
			},
			body: JSON.stringify(body),
			signal: controller.signal,
		});
	} catch (err: any) {
		clearTimeout(timeoutId);
		if (err?.name === "AbortError") {
			throw error(504, "Radar visualization timed out");
		}
		throw error(502, `Cannot reach Python service at ${PYTHON_API_URL}`);
	} finally {
		clearTimeout(timeoutId);
	}

	if (!response.ok) {
		const contentType = response.headers.get("content-type") ?? "";
		let detail = `Python service returned HTTP ${response.status}`;
		try {
			if (contentType.includes("application/json")) {
				const errBody = await response.json();
				detail = errBody?.detail ?? detail;
			}
		} catch {}
		throw error(response.status >= 500 ? 502 : response.status, detail);
	}

	const result = await response.json();
	return json(result);
};
