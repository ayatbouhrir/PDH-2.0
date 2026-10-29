import type { Circle } from "$lib/vendor/fsac/src/circle";

export function customMerge(a: Circle, b: Circle, zoom: number): Circle {
  if (
    !a || !b ||
    a.r === undefined || b.r === undefined ||
    a.x === undefined || b.x === undefined ||
    a.y === undefined || b.y === undefined
  ) {
    throw new Error("Les cercles fournis à la fonction merge ne sont pas valides : " + JSON.stringify({ a, b }));
  }

  const n = a.n + b.n;
  const data = (a.data * a.n + b.data * b.n) / n;

  // Coordonnées du centre
  let x: number, y: number;
  if (a.x === b.x && a.y === b.y) {
    x = a.x;
    y = a.y;
  } else {
    x = (a.x * a.n + b.x * b.n) / n;
    y = (a.y * a.n + b.y * b.n) / n;
  }

  // Calcul du rayon
  const r = (Math.log10(n + 1) * 0.97 + Math.sqrt(n) * 0.03) * 65000 / Math.pow(1.4, zoom);

  return { x, y, r, n, children: [a, b], data };
}
