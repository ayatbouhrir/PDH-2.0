import { error } from "@sveltejs/kit";

const PYTHON_API_URL =
	process.env.PYTHON_API_URL ??
	process.env.VITE_PYTHON_API_URL ??
	"http://127.0.0.1:8000";

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
			? `${fallback} - ${stripped.slice(0, 300)}`
			: fallback;
	} catch {
		return fallback;
	}
}

export async function proxyPythonJson(
	path: string,
	options: {
		method?: "GET" | "POST";
		body?: unknown;
		timeoutMs?: number;
	} = {},
) {
	const { method = "GET", body, timeoutMs = 30_000 } = options;
	const controller = new AbortController();
	const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

	let response: Response;

	try {
		response = await fetch(`${PYTHON_API_URL}${path}`, {
			method,
			headers: {
				Accept: "application/json",
				...(body !== undefined ? { "Content-Type": "application/json" } : {}),
			},
			body: body === undefined ? undefined : JSON.stringify(body),
			signal: controller.signal,
		});
	} catch (err: any) {
		clearTimeout(timeoutId);

		if (err?.name === "AbortError") {
			throw error(504, `Python service timed out after ${timeoutMs} ms`);
		}

		console.error(`[proxyPythonJson] Cannot reach Python service on ${path}:`, err?.message);
		throw error(
			502,
			`Cannot reach Python service at ${PYTHON_API_URL}. Make sure it is running.`,
		);
	} finally {
		clearTimeout(timeoutId);
	}

	if (!response.ok) {
		const detail = await readErrorBody(response);
		throw error(response.status >= 500 ? 502 : response.status, detail);
	}

	const contentType = response.headers.get("content-type") ?? "";
	if (!contentType.includes("application/json")) {
		const text = await response.text();
		throw error(502, `Python service returned non-JSON response: ${text.slice(0, 200)}`);
	}

	try {
		return await response.json();
	} catch (parseErr) {
		console.error(`[proxyPythonJson] JSON parse error on ${path}:`, parseErr);
		throw error(502, "Python service returned invalid JSON.");
	}
}
