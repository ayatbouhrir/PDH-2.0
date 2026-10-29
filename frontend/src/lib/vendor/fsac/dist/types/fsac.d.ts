import Rbush from 'rbush';
import { Ref } from '../src/ref';
import { Circle } from '../src/circle';
export declare type FSACOptions<T> = {
    merge: (a: T, b: T) => T;
    overlap: (a: T, b: T) => number;
    bbox: (item: T) => {
        minX: number;
        minY: number;
        maxX: number;
        maxY: number;
    };
    Rbush: {
        new (): Rbush<Ref<T>>;
    };
    brk?: boolean;
    reverse?: boolean;
    sort?: boolean;
};
export default function fsac<T = any>(clusters: T[], opts: FSACOptions<T>): T[];
export default function fsac<T extends Circle = Circle>(clusters: T[], opts?: Partial<FSACOptions<T>>): T[];
//# sourceMappingURL=fsac.d.ts.map