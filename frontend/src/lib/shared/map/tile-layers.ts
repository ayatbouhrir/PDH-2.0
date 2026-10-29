// Fonds de cartes disponibles : utilisé dans ExplorationMap
export const tileLayers = [
    {
        name: "Carto no label",
        url: "https://basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png",
        attribution: "&copy; CARTO",
    },
    {
        name: "Carto",
        url: "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attribution: "&copy; CARTO",
    },
    {
        name: "Carto Light",
        url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attribution: "&copy; CARTO",
    },
    {
        name: "Carto Light no label",
        url: "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
        attribution: "&copy; CARTO",
    },
    {
        name: "OpenStreetMap",
        url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution:
            '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors',
    },
    {
        name: "OpenTopoMap",
        url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution:
            '&copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
    },
];
