// https://github.com/stardisblue/fsac v1.0.1 Copyright (c) 2021 Fati CHEN
import RBush from 'rbush';

function ref(v) {
    return { v };
}

function bbox(circle) {
    return {
        minX: circle.x - circle.r,
        minY: circle.y - circle.r,
        maxX: circle.x + circle.r,
        maxY: circle.y + circle.r,
    };
}
function merge(a, b) {
    const xs = a.x * a.n + b.x * b.n, ys = a.y * a.n + b.y * b.n, n = a.n + b.n;
    return Cluster(xs / n, ys / n, n, [a, b]);
}
function overlap(a, b) {
    return (a.r + b.r) ** 2 - ((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
}
function Cluster(x, y, n, children, data = null) {
    const obj = { x, y, r: Math.sqrt(n), n, children };
    if (data)
        obj.data = data;
    return obj;
}
class CircleRbush extends RBush {
    toBBox(item) {
        return bbox(item.v);
    }
    compareMinX(a, b) {
        return a.v.x - a.v.r - (b.v.x - b.v.r);
    }
    compareMinY(a, b) {
        return a.v.y - a.v.r - (b.v.y - b.v.r);
    }
}

function fsac(clusters, { merge: merge$1 = merge, overlap: overlap$1 = overlap, bbox: bbox$1 = bbox, Rbush = CircleRbush, brk = false, reverse = false, sort = true, } = {}) {
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
            const candidates = collision.search(bbox$1(cluster));
            const indexes = new Uint32Array(candidates.length);
            {
                // unloads overlaps as soon as it's not used
                const overlaps = new Float64Array(candidates.length);
                candidates.forEach((c, i) => {
                    indexes[i] = i;
                    overlaps[i] = overlap$1(cluster, c.v);
                });
                if (sort)
                    indexes.sort((a, b) => overlaps[b] - overlaps[a]);
            }
            const iterated = reverse ? indexes.reverse() : indexes;
            for (const i of iterated) {
                const refCandidate = candidates[i];
                if (refCl === refCandidate)
                    continue;
                if (overlap$1(cluster, refCandidate.v) > 0) {
                    if (!updated)
                        updated = true;
                    cluster = merge$1(cluster, refCandidate.v);
                    alives.delete(refCandidate);
                    collision.remove(refCandidate);
                    if (!clustered)
                        clustered = true;
                    if (brk)
                        break;
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

function offlinefsac(clusters /* Cluster[] list base clusters */, { step = 1 /*       number    integer, number of steps between each zoom must be >= 1 */, maxZoom = 18 /*   number    (included). At least 0. default: 18; compatible with most librairies*/, projection = powerTwoProjection /* Function zoom factor*/, rescale = circleRescale, merge = offlineCircleMerge, prepare = circlePrepare, ...options /*     object    the rest is passed to default fsac algorithm */ } = {}) {
    if (step <= 0)
        throw new Error(`step should be greater than 0, got "${step}"`);
    if (maxZoom < 0)
        throw new Error(`maxZoom should be at least equal to 0, got "${maxZoom}"`);
    let copy = Array.from(clusters, prepare(maxZoom));
    for (let i = maxZoom; i >= 0; i -= 1 / projection(step - 1)) {
        const zoom = projection(i);
        copy.forEach(rescale(zoom));
        copy = fsac(copy, { ...options, merge: merge(zoom, i) });
    }
    return copy;
}
function powerTwoProjection(i) {
    return Math.pow(2, i);
}
function offlineCircleMerge(zoom, i) {
    return function (a, b) {
        const c = merge(a, b);
        c._r = c.r; // backup original radius
        // setting radius to current zoom instead of moving the nodes apart
        // we emulate this behaviour by reducing the cluster radius
        c.r /= zoom;
        c.at = i;
        return c;
    };
}
function circleRescale(zoom) {
    return function (c) {
        return (c.r = c._r / zoom);
    };
}
function circlePrepare(maxZoom) {
    return function (c) {
        return { ...c, _r: c.r, at: maxZoom };
    };
}

export { CircleRbush, bbox, circlePrepare, circleRescale, fsac, merge, offlineCircleMerge, offlinefsac, overlap, powerTwoProjection, ref };
