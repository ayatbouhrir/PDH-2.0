import type { PageLoad } from "./$types";

export const ssr = false;

export const load: PageLoad = async ({ fetch }) => {
    const infoRes = await fetch("/api/info");
    const info = await infoRes.json();

    return {
        allMatrixes: info.allMatrixes,
        allDatasets: info.allDatasets,
        allSubstances: info.allSubstances,
    };
};