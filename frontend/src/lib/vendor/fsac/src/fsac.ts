import Rbush from 'rbush';
import { ref, type Ref } from './ref';
import {
  type Circle,
  CircleRbush,
  bbox as circleBbox,
  merge as circleMerge,
  overlap as circleOverlap,
} from './circle';

export type FSACOptions<T> = {
  merge: (a: T, b: T, zoom: number) => T;
  overlap: (a: T, b: T) => number;
  bbox: (item: T) => {
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
  };
  Rbush: { new (): Rbush<Ref<T>> };
  brk?: boolean;
  reverse?: boolean;
  sort?: boolean;
};

export default function fsac<T = any>(clusters: T[], zoom: number, opts: FSACOptions<T>): T[];
export default function fsac<T extends Circle = Circle>(
  clusters: T[],
  zoom: number,
  opts?: Partial<FSACOptions<T>>
): T[];
export default function fsac(
  clusters: Circle[],
  zoom: number,
  {
    merge = circleMerge,
    overlap = circleOverlap,
    bbox = circleBbox,
    Rbush = CircleRbush,
    brk = false,
    reverse = false,
    sort = true,
  }: Partial<FSACOptions<Circle>> = {}
) {
  const refs = clusters.map(ref);
  const alives = new Set(refs);

  const collision = new Rbush();
  collision.load(refs);

  for (const refCl of alives) {
    let updated = false;
    let clustered = true;
    let cluster = refCl.v;

    while (clustered) {
      clustered = false;
      const candidates = collision.search(bbox(cluster));

      const indexes = new Uint32Array(candidates.length);
      {
        // unloads overlaps as soon as it's not used
        const overlaps = new Float64Array(candidates.length);
        candidates.forEach((c, i) => {
          indexes[i] = i;
          overlaps[i] = overlap(cluster, c.v);
        });
        if (sort) indexes.sort((a, b) => overlaps[b] - overlaps[a]);
      }

      const iterated = reverse ? indexes.reverse() : indexes;

      for (const i of iterated) {
        const refCandidate = candidates[i];
        if (refCl === refCandidate) continue;

        if (overlap(cluster, refCandidate.v) > 0) {
          if (!updated) updated = true;

          cluster = merge(cluster, refCandidate.v, zoom);
          alives.delete(refCandidate);
          collision.remove(refCandidate);
          if (!clustered) clustered = true;
          if (brk) break;
        }
      }
    }
    if (updated) {
      collision.remove(refCl);
      refCl.v = cluster;
      collision.insert(refCl);
    }
  }

  return Array.from(alives, ({ v }) => v);
}
