import RBush from 'rbush';
import { Ref } from '../src/ref';
export declare type Circle = {
    x: number;
    y: number;
    r: number;
    n: number;
    children: any;
    data?: any;
};
export declare function bbox(circle: Circle): {
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
};
export declare function merge(a: Circle, b: Circle): Circle;
export declare function overlap(a: Circle, b: Circle): number;
export declare class CircleRbush<T extends Circle = Circle> extends RBush<Ref<T>> {
    toBBox(item: Ref<T>): {
        minX: number;
        minY: number;
        maxX: number;
        maxY: number;
    };
    compareMinX(a: Ref<T>, b: Ref<T>): number;
    compareMinY(a: Ref<T>, b: Ref<T>): number;
}
//# sourceMappingURL=circle.d.ts.map