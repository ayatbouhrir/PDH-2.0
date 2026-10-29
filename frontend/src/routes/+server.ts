import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const PYTHON_API_URL =
	process.env.PYTHON_API_URL ??
	process.env.VITE_PYTHON_API_URL ??
	"http://127.0.0.1:8000";

// Abort after 300 s (DBSCAN sampling + autoencoder on large datasets can be slow)
const TIMEOUT_MS = 300_000;
async function readErrorBody(response: Response): Promise<string> {
	const contentType = response.headers.get("content-type") ?? "";
	const fallback = `Python service returned HTTP ${response.status}`;

	try {
		if (contentType.includes("application/json")) {
			const errBody = await response.json();
			return errBody?.detail ?? errBody?.error ?? errBody?.message ?? fallback;
		}

		// HTML crash page or plain text — strip tags and truncate
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
		response = await fetch(`${PYTHON_API_URL}/analysis/run`, {
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
			throw error(504, "Python clustering service timed out after 300 s");
		}

		console.error("[api/analysis/run] Cannot reach Python service:", err?.message);
		throw error(
			502,
			`Cannot reach Python clustering service at ${PYTHON_API_URL}. ` +
				`Make sure the service is running (uvicorn main:app --port 8000).`,
		);
	} finally {
		clearTimeout(timeoutId);
	}

	//  (handles HTML crash pages)
	if (!response.ok) {
		const detail = await readErrorBody(response);
		console.error("[api/analysis/run] Python error:", detail);
		throw error(response.status >= 500 ? 502 : response.status, detail);
	}

	// Parse the success response — if Python returns non-JSON on 2xx, report it clearly
	const contentType = response.headers.get("content-type") ?? "";
	if (!contentType.includes("application/json")) {
		const text = await response.text();
		console.error("[api/analysis/run] Python returned non-JSON 2xx:", text.slice(0, 200));
		throw error(502, `Python service returned non-JSON response: ${text.slice(0, 200)}`);
	}

	let result: unknown;
	try {
		result = await response.json();
	} catch (parseErr) {
		console.error("[api/analysis/run] JSON parse error:", parseErr);
		throw error(502, "Python service returned invalid JSON — check uvicorn logs for details");
	}

	return json(result);
};

