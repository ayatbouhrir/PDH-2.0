import RBush from 'rbush';
import type { Ref } from './ref';

export type Circle = {
  x: number;
  y: number;
  r: number;
  n: number;
  children: any;
  data?: any;
};

export function bbox(circle: Circle) {
  return {
    minX: circle.x - circle.r,
    minY: circle.y - circle.r,
    maxX: circle.x + circle.r,
    maxY: circle.y + circle.r,
  };
}

export function overlap(a: Circle, b: Circle) {
  return (a.r + b.r) ** 2 - ((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
}

// original merge

export function merge(a: Circle, b: Circle) {
  const xs = a.x * a.n + b.x * b.n,
    ys = a.y * a.n + b.y * b.n,
    n = a.n + b.n;

  return Cluster(xs / n, ys / n, n, [a, b]);
}

// original Cluster

function Cluster(x: number, y: number, n: number, children: any, data = null) {
  const obj: Circle = { x, y, r: Math.sqrt(n), n, children };
  if (data) obj.data = data;
  return obj;
}



// export function merge(a: Circle, b: Circle, zoom: number) {
//   // gère la maj de n, data et du nouveau centre

//   if (!a || !b || a.r === undefined || b.r === undefined || a.x === undefined || b.x === undefined || a.y === undefined || b.y === undefined) {
//     throw new Error("Les cercles fournis à la fonction merge ne sont pas valides : " + JSON.stringify({ a, b }));
//   }

//   const n = a.n + b.n;
//   const data = (a.data * a.n + b.data * b.n) / n;

//   // Si les deux cercles ont les mêmes coordonnées, on ne bouge pas le centre
//   if (a.x === b.x && a.y === b.y) {
//     return Cluster(a.x, a.y, n, [a, b], data, zoom);
//   }

//   // Barycentre pondéré
//   const centerX = (a.x * a.n + b.x * b.n) / n;
//   const centerY = (a.y * a.n + b.y * b.n) / n;

//   return Cluster(centerX, centerY, n, [a, b], data, zoom);
// }

// function Cluster(x: number, y: number, n: number, children: any, data: number, zoom: number): Circle {
//   // gère la maj du rayon

//   // ne dépend que de n
//   const r = (Math.log10(n + 1) * 0.97 + Math.sqrt(n) * 0.03) * 65000 / Math.pow(1.4, zoom);
//   const obj: Circle = { x, y, r, n, children, data };
//   return obj;
// }


export class CircleRbush<T extends Circle = Circle> extends RBush<Ref<T>> {
  toBBox(item: Ref<T>) {
    return bbox(item.v);
  }

  compareMinX(a: Ref<T>, b: Ref<T>) {
    return a.v.x - a.v.r - (b.v.x - b.v.r);
  }

  compareMinY(a: Ref<T>, b: Ref<T>) {
    return a.v.y - a.v.r - (b.v.y - b.v.r);
  }
}
