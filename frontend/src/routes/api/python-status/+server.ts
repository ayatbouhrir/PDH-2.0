import { env } from "$env/dynamic/private";
import { json } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";

const DEFAULT_PY_API_URL = "http://127.0.0.1:8000";

function getPythonApiBaseUrl(): string {
    const baseUrl = env.PY_ANALYSIS_API_URL?.trim() || DEFAULT_PY_API_URL;
    return baseUrl.replace(/\/+$/, "");
}

export const GET: RequestHandler = async ({ fetch }) => {
    const baseUrl = getPythonApiBaseUrl();

    try {
        const response = await fetch(`${baseUrl}/gettest`, {
            method: "GET",
            headers: {
                Accept: "application/json",
            },
        });

        const data = await response.json().catch(() => null);

        if (!response.ok) {
            return json(
                {
                    ok: false,
                    message: "API Python non disponible.",
                    details: data,
                },
                { status: response.status },
            );
        }

        return json({
            ok: true,
            message: "Connexion établie avec l'API Python.",
            backendMessage: data?.message ?? null,
        });
    } catch (error) {
        return json(
            {
                ok: false,
                message: "Impossible de contacter l'API Python.",
                details: error instanceof Error ? error.message : "Erreur inconnue",
            },
            { status: 500 },
        );
    }
};