<script lang="ts">
	import { runHistoryRune } from "$lib/runes/runHistoryRune.svelte";
	import { ChevronDown, Trash2, Clock, Download, Pencil } from "lucide-svelte";

	let expanded = $state<string | null>(null);

	function toggle(id: string) {
		expanded = expanded === id ? null : id;
	}

	function formatDateTime(ts: number): string {
		return new Date(ts).toLocaleString("fr-FR", {
			year: "2-digit",
			month: "2-digit",
			day: "2-digit",
			hour: "2-digit",
			minute: "2-digit",
		});
	}

	function getEntryDisplayTime(entry: (typeof runHistoryRune.entries)[number]): number {
		return entry.lastOpenedAt ?? entry.timestamp;
	}

	function formatDuration(ms: number): string {
		if (ms < 1000) return `${ms} ms`;
		return `${(ms / 1000).toFixed(1)} s`;
	}

	function renameEntry(id: string, current?: string) {
		const next = window.prompt("Nom de l'analyse enregistrée", current ?? "");
		if (next == null) return;
		runHistoryRune.rename(id, next);
	}
</script>

<div class="history-panel">
	<div class="history-header">
		<div class="history-title">
			<Clock size={16} />
			Historique des analyses ({runHistoryRune.entries.length}/10)
		</div>

		{#if runHistoryRune.entries.length > 0}
			<button
				class="clear-btn"
				onclick={() => runHistoryRune.clear()}
				title="Effacer l'historique"
				type="button"
			>
				<Trash2 size={14} />
			</button>
		{/if}
	</div>

	{#if runHistoryRune.entries.length === 0}
		<p class="empty-msg">Aucune analyse enregistrée.</p>
	{:else}
		<div class="entries">
			{#each runHistoryRune.entries as entry (entry.id)}
				<div class="entry">
					<button
						type="button"
						class="entry-summary"
						onclick={() => toggle(entry.id)}
					>
						<span class="entry-algo">{entry.algorithm.toUpperCase()}</span>

						<span class="entry-info">
							{entry.name ?? `${entry.clusterCount} clusters · ${entry.pointCount.toLocaleString("fr-FR")} pts`}
						</span>

						<span class="entry-time">{formatDateTime(getEntryDisplayTime(entry))}</span>

						<ChevronDown
							class={`entry-chevron ${expanded === entry.id ? "" : "rotated"}`}
							size={14}
						/>
					</button>

					{#if expanded === entry.id}
						<div class="entry-details">
							<div class="detail-row">
								<span>Durée</span>
								<span>{formatDuration(entry.durationMs)}</span>
							</div>

							<div class="detail-row">
								<span>Dernière ouverture</span>
								<span>{formatDateTime(getEntryDisplayTime(entry))}</span>
							</div>

							<div class="detail-row">
								<span>Paramètres</span>
								<span>
									{#if entry.algorithm === "kmeans"}
										k={entry.params.k}
									{:else if entry.algorithm === "propos"}
										k={entry.params.k ?? "-"} · epochs={entry.params.maxIterations ?? "-"}
									{:else if entry.algorithm === "hdbscan"}
										minClusterSize={entry.params.minClusterSize ?? "-"} · minSamples={entry.params.minSamples ?? "-"} · {entry.params.clusterSelectionMethod ?? "eom"}
									{:else}
										eps={entry.params.eps} · minPts={entry.params.minPts}
									{/if}
								</span>
							</div>

							<div class="detail-row">
								<span>Préprocessing</span>
								<span>{entry.params.preprocessing}</span>
							</div>

							<div class="detail-row">
								<span>Réduction</span>
								<span>{entry.params.reduction}</span>
							</div>
							<div class="detail-row">
								<span>Cache backend</span>
								<span>{entry.cacheKey ? "oui" : "non"}</span>
							</div>

							<div class="detail-row">
								<span>Dernière exécution servie du cache</span>
								<span>{entry.cached ? "oui" : "non"}</span>
							</div>

							<div class="detail-row">
								<span>Source</span>
								<span>{entry.hitCount && entry.hitCount > 0 ? "Cache persistant" : "Calcul initial"}</span>
							</div>

							<div class="detail-row">
								<span>Ouvertures cache</span>
								<span>{entry.hitCount ?? 0}</span>
							</div>

							<div class="detail-row">
								<span>Bruit</span>
								<span>{entry.noiseCount}</span>
							</div>

							{#if entry.globalMetrics?.silhouetteScore != null}
								<div class="detail-row">
									<span>Silhouette</span>
									<span>{entry.globalMetrics.silhouetteScore.toFixed(4)}</span>
								</div>
							{/if}

							{#if entry.globalMetrics?.daviesBouldinIndex != null}
								<div class="detail-row">
									<span>Davies-Bouldin</span>
									<span>{entry.globalMetrics.daviesBouldinIndex.toFixed(4)}</span>
								</div>
							{/if}

							{#if entry.algorithm === "hdbscan" && entry.globalMetrics?.relativeValidity != null}
								<div class="detail-row">
									<span>Relative validity</span>
									<span>{entry.globalMetrics.relativeValidity.toFixed(4)}</span>
								</div>
							{/if}

							{#if entry.algorithm === "hdbscan" && entry.globalMetrics?.clusterPersistenceMean != null}
								<div class="detail-row">
									<span>Cluster persistence</span>
									<span>{entry.globalMetrics.clusterPersistenceMean.toFixed(4)}</span>
								</div>
							{/if}

							{#if (entry.algorithm === "kmeans" || entry.algorithm === "propos") && entry.globalMetrics?.calinskiHarabaszScore != null}
								<div class="detail-row">
									<span>Calinski-Harabasz</span>
									<span>{entry.globalMetrics.calinskiHarabaszScore.toFixed(2)}</span>
								</div>
							{/if}

							{#if (entry.algorithm === "kmeans" || entry.algorithm === "propos") && entry.globalMetrics?.wcss != null}
								<div class="detail-row">
									<span>WCSS / Inertia</span>
									<span>{entry.globalMetrics.wcss.toFixed(2)}</span>
								</div>
							{/if}

							<div class="history-actions">
								<button
									class="action-btn"
									type="button"
									onclick={() => runHistoryRune.requestLoad(entry.id)}
								>
									<Download size={14} />
									{entry.cacheKey ? "Afficher" : "Charger local"}
								</button>

								<button
									class="action-btn"
									type="button"
									onclick={() => renameEntry(entry.id, entry.name)}
								>
									<Pencil size={14} />
									Renommer
								</button>

								<button
									class="action-btn danger"
									type="button"
									onclick={() => runHistoryRune.remove(entry.id)}
								>
									<Trash2 size={14} />
									Supprimer
								</button>
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.history-panel {
		margin-top: 0.75rem;
	}

	.history-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.history-title {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.9rem;
		font-weight: 700;
		color: #111827;
	}

	.clear-btn {
		all: unset;
		cursor: pointer;
		display: flex;
		align-items: center;
		padding: 0.25rem;
		border-radius: 0.35rem;
		color: #94a3b8;
	}

	.clear-btn:hover {
		color: #ef4444;
		background: #fef2f2;
	}

	.empty-msg {
		font-size: 0.82rem;
		color: #94a3b8;
		text-align: center;
		padding: 0.75rem 0;
	}

	.entries {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		max-height: 320px;
		overflow-y: auto;
	}

	.entry {
		background: #f8fafc;
		border: 1px solid #e2e8f0;
		border-radius: 0.5rem;
		padding: 0.5rem 0.65rem;
	}

	.entry-summary {
		all: unset;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		width: 100%;
		text-align: left;
	}

	.entry-algo {
		font-weight: 700;
		font-size: 0.7rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.25rem;
		background: #e2e8f0;
		color: #475569;
	}

	.entry-info {
		flex: 1;
		color: #334155;
		font-weight: 500;
	}

	.entry-time {
		color: #94a3b8;
		font-size: 0.72rem;
		white-space: nowrap;
	}

	:global(.entry-chevron) {
		transition: transform 0.2s ease;
		color: #94a3b8;
		flex-shrink: 0;
	}

	:global(.entry-chevron.rotated) {
		transform: rotate(-90deg);
	}

	.entry-details {
		margin-top: 0.5rem;
		padding-top: 0.4rem;
		border-top: 1px solid #e2e8f0;
	}

	.detail-row {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		font-size: 0.78rem;
		padding: 0.15rem 0;
		color: #475569;
	}

	.detail-row span:last-child {
		font-weight: 600;
		color: #1e293b;
		text-align: right;
	}

	.history-actions {
		display: flex;
		gap: 0.35rem;
		margin-top: 0.65rem;
		flex-wrap: wrap;
	}

	.action-btn {
		all: unset;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.35rem 0.5rem;
		border-radius: 0.4rem;
		color: #475569;
		background: #f1f5f9;
		font-size: 0.78rem;
		font-weight: 600;
	}

	.action-btn:hover {
		background: #e2e8f0;
	}

	.action-btn.danger {
		color: #991b1b;
		background: #fee2e2;
	}

	.action-btn.danger:hover {
		background: #fecaca;
	}
</style>
