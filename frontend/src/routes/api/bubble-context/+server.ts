import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const PYTHON_API_URL =
	process.env.PYTHON_API_URL ??
	process.env.VITE_PYTHON_API_URL ??
	"http://127.0.0.1:8000";

const TIMEOUT_MS = 120_000;

async function readErrorBody(response: Response): Promise<string> {
	const contentType = response.headers.get("content-type") ?? "";
	const fallback = `Python service returned HTTP ${response.status}`;

	try {
		if (contentType.includes("application/json")) {
			const errBody = await response.json();
			return errBody?.detail ?? errBody?.error ?? errBody?.message ?? fallback;
		}

		const text = await response.text();
		const stripped = text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
		return stripped.length > 0
			? `${fallback} — ${stripped.slice(0, 300)}`
			: fallback;
	} catch {
		return fallback;
	}
}

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
		response = await fetch(`${PYTHON_API_URL}/bubble-context`, {
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
			throw error(504, "Python bubble-context service timed out");
		}

		console.error("[api/bubble-context] Cannot reach Python service:", err?.message);
		throw error(
			502,
			`Cannot reach Python service at ${PYTHON_API_URL}.`,
		);
	} finally {
		clearTimeout(timeoutId);
	}

	if (!response.ok) {
		const detail = await readErrorBody(response);
		console.error("[api/bubble-context] Python error:", detail);
		throw error(response.status >= 500 ? 502 : response.status, detail);
	}

	const contentType = response.headers.get("content-type") ?? "";
	if (!contentType.includes("application/json")) {
		const text = await response.text();
		throw error(502, `Python service returned non-JSON response: ${text.slice(0, 200)}`);
	}

	let result: unknown;
	try {
		result = await response.json();
	} catch {
		throw error(502, "Python service returned invalid JSON");
	}

	return json(result);
};