import { Circle } from '../src/circle';
import { FSACOptions } from '../src/fsac';
declare type OfflineFSACOptions<T, O> = Omit<FSACOptions<O>, 'merge'> & {
    step: number;
    maxZoom: number;
    projection: (i: number) => number;
    rescale: (zoom: number) => (c: O) => any;
    prepare: (maxZoom: number) => (c: T) => O;
    merge: (zoom: number, i: number) => (a: O, b: O) => O;
};
declare type OfflineCircle = Circle & {
    _r: number;
    at: number;
};
export default function offlinefsac<T = any, O = any>(clusters: T[], opts: OfflineFSACOptions<T, O>): T[];
export default function offlinefsac<T extends Circle = Circle, O extends OfflineCircle = OfflineCircle>(clusters: T[], opts?: Partial<OfflineFSACOptions<T, O>>): O[];
export declare function powerTwoProjection(i: number): number;
export declare function offlineCircleMerge(zoom: number, i: number): (a: OfflineCircle, b: OfflineCircle) => OfflineCircle;
export declare function circleRescale(zoom: number): (c: OfflineCircle) => number;
export declare function circlePrepare(maxZoom: number): (c: Circle) => OfflineCircle;
export {};
//# sourceMappingURL=offlinefsac.d.ts.map