import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const PYTHON_API_URL =
	process.env.PYTHON_API_URL ??
	process.env.VITE_PYTHON_API_URL ??
	"http://127.0.0.1:8000";

export const POST: RequestHandler = async ({ request }) => {
	let body: unknown;

	try {
		body = await request.json();
	} catch {
		throw error(400, "Invalid JSON body");
	}

	const response = await fetch(`${PYTHON_API_URL}/pfas-time-series`, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Accept: "application/json",
		},
		body: JSON.stringify(body),
	});

	if (!response.ok) {
		const text = await response.text();
		throw error(response.status, text || "Python error");
	}

	const result = await response.json();
	return json(result);
};

