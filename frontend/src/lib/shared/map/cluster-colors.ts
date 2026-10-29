const CLUSTER_COLORS = [
	"#e11d48",
	"#2563eb",
	"#16a34a",
	"#f59e0b",
	"#7c3aed",
	"#0891b2",
	"#ea580c",
	"#4f46e5",
	"#0f766e",
	"#9333ea",
	"#dc2626",
	"#65a30d",
	"#0284c7",
	"#c026d3",
	"#059669",
	"#d97706",
	"#6d28d9",
	"#be123c",
	"#15803d",
	"#1d4ed8",
	"#b91c1c",
	"#a16207",
	"#4338ca",
	"#9f1239",
	"#047857",
	"#1e40af",
	"#92400e",
	"#5b21b6",
	"#166534",
	"#c2410c",
];

export function getClusterColor(clusterId: number): string {
	if (clusterId === -1) return "#6b7280";
	return CLUSTER_COLORS[Math.abs(clusterId) % CLUSTER_COLORS.length];
}
