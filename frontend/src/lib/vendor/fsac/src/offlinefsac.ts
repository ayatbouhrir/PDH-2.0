import { type Circle, merge } from './circle';
import fsac, { type FSACOptions } from './fsac';

type OfflineFSACOptions<T, O> = Omit<FSACOptions<O>, 'merge'> & {
  step: number;
  maxZoom: number;
  projection: (i: number) => number;
  rescale: (zoom: number) => (c: O) => any;
  prepare: (maxZoom: number) => (c: T) => O;
  merge: (zoom: number, i: number) => (a: O, b: O) => O;
};
type OfflineCircle = Circle & { _r: number; at: number };

export default function offlinefsac<T = any, O = any>(
  clusters: T[],
  opts: OfflineFSACOptions<T, O>
): T[];
export default function offlinefsac<
  T extends Circle = Circle,
  O extends OfflineCircle = OfflineCircle
>(clusters: T[], opts?: Partial<OfflineFSACOptions<T, O>>): O[];
export default function offlinefsac(
  clusters: Circle[] /* Cluster[] list base clusters */,
  {
    step = 1 /*       number    integer, number of steps between each zoom must be >= 1 */,
    maxZoom = 18 /*   number    (included). At least 0. default: 18; compatible with most librairies*/,
    projection = customPowerProjection /* Function zoom factor*/,
    rescale = circleRescale,
    merge = offlineCircleMerge,
    prepare = circlePrepare,
    ...options /*     object    the rest is passed to default fsac algorithm */
  }: Partial<OfflineFSACOptions<Circle, OfflineCircle>> = {}
) {
  if (step <= 0)
    throw new Error(`step should be greater than 0, got "${step}"`);
  if (maxZoom < 0)
    throw new Error(`maxZoom should be at least equal to 0, got "${maxZoom}"`);


  // ajout de _r et at a chaque cluster
  let copy = Array.from(clusters, prepare(maxZoom));

  for (let i = maxZoom; i >= 0; i -= 1 / projection(step - 1)) {

    // console.log('[offlinefsac] for i = ', i);

    // on réduit leur rayon avant fsac car zoom augmente
    const zoom = projection(i);
    // console.log('[offlinefsac] zoom = ', zoom);

    // console.log("Before rescale | copy : ", copy);
    copy.forEach(rescale(zoom));
    // console.log("After rescale | copy : ", copy);
    // before et after sont = 
    // pas sur de comprendre la logique

    copy = fsac(copy, zoom, { ...options, merge: merge(zoom, i) });
    // console.log("After fsac | copy : ", copy);
  }

  return copy;
}

export function powerTwoProjection(i: number) {
  return Math.pow(2, i);
}

export function customPowerProjection(i: number) {
  return Math.pow(1.4, i);
}

export function offlineCircleMerge(zoom: number, i: number) {
  return function (a: OfflineCircle, b: OfflineCircle) {
    // console.log('[offlineCircleMerge]', a,b);
    const c = merge(a, b) as OfflineCircle;
    c._r = c.r; // backup original radius
    // setting radius to current zoom instead of moving the nodes apart
    // we emulate this behaviour by reducing the cluster radius
    c.r /= zoom; // pour affichage ??
    c.at = i;
    return c;
  };
}

export function circleRescale(zoom: number) {
  return function (c: OfflineCircle) {
    return (c.r = c._r / zoom);
  };
}

export function circlePrepare(maxZoom: number) {
  return function (c: Circle): OfflineCircle {
    return { ...c, _r: c.r, at: maxZoom };
  };
}
