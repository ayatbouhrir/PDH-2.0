import type {
	ClusteredPoint,
	CondensedBubble,
	DisplayMode,
	ViewportBounds,
} from "$lib/shared/types/analysis-contract";
import type { PfasPoint } from "$lib/shared/types/pfas";
import type { HistoryLoadResponse } from "$lib/features/history/history.api";
import type { RunHistoryEntry } from "$lib/features/history/run-history.state.svelte";

export type ComparisonRunData = {
	id: string;
	entry: RunHistoryEntry;
	result: HistoryLoadResponse;
	filteredPoints: PfasPoint[];
	clusteredPoints: ClusteredPoint[];
	condensedBubbles: CondensedBubble[];
	displayMode: DisplayMode;
	initialViewport: ViewportBounds | null;
};
