import RBush from 'rbush';

declare type Ref<T = any> = {
    v: T;
};
declare function ref<T>(v: T): Ref<T>;

declare type Circle = {
    x: number;
    y: number;
    r: number;
    n: number;
    children: any;
    data?: any;
};
declare function bbox(circle: Circle): {
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
};
declare function merge(a: Circle, b: Circle): Circle;
declare function overlap(a: Circle, b: Circle): number;
declare class CircleRbush<T extends Circle = Circle> extends RBush<Ref<T>> {
    toBBox(item: Ref<T>): {
        minX: number;
        minY: number;
        maxX: number;
        maxY: number;
    };
    compareMinX(a: Ref<T>, b: Ref<T>): number;
    compareMinY(a: Ref<T>, b: Ref<T>): number;
}

declare type FSACOptions<T> = {
    merge: (a: T, b: T) => T;
    overlap: (a: T, b: T) => number;
    bbox: (item: T) => {
        minX: number;
        minY: number;
        maxX: number;
        maxY: number;
    };
    Rbush: {
        new (): RBush<Ref<T>>;
    };
    brk?: boolean;
    reverse?: boolean;
    sort?: boolean;
};
declare function fsac<T = any>(clusters: T[], opts: FSACOptions<T>): T[];
declare function fsac<T extends Circle = Circle>(clusters: T[], opts?: Partial<FSACOptions<T>>): T[];

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
declare function offlinefsac<T = any, O = any>(clusters: T[], opts: OfflineFSACOptions<T, O>): T[];
declare function offlinefsac<T extends Circle = Circle, O extends OfflineCircle = OfflineCircle>(clusters: T[], opts?: Partial<OfflineFSACOptions<T, O>>): O[];
declare function powerTwoProjection(i: number): number;
declare function offlineCircleMerge(zoom: number, i: number): (a: OfflineCircle, b: OfflineCircle) => OfflineCircle;
declare function circleRescale(zoom: number): (c: OfflineCircle) => number;
declare function circlePrepare(maxZoom: number): (c: Circle) => OfflineCircle;

export { Circle, CircleRbush, Ref, bbox, circlePrepare, circleRescale, fsac, merge, offlineCircleMerge, offlinefsac, overlap, powerTwoProjection, ref };
