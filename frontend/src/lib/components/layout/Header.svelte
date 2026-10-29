<script lang="ts">
    import ExportDialog from "$lib/features/export/components/ExportDialog.svelte";

    let { mode = "off" } = $props();
    const nextHref = mode === "off" ? "/analyse" : "/";

    interface Logo {
        src: string;
        url: string;
    }

    const logos: Logo[] = [
        { src: "/logos/LIRMM.png", url: "https://www.lirmm.fr" },
        { src: "/logos/UMd.png", url: "https://www.umontpellier.fr" },
        { src: "/logos/CNRSd.png", url: "https://www.cnrs.fr" },
        { src: "/logos/UMPVd.png", url: "https://www.univ-montp3.fr" },
        { src: "/logos/LIS.png", url: "https://www.lis-lab.fr" },
        { src: "/logos/AMU.png", url: "https://www.univ-amu.fr" },
    ];

    let open = $state(false);
</script>

<header>
	<div class="header-row">
		<div class="header-left">
			<div class="logos">
				{#each logos as logo}
					<a href={logo.url} target="_blank" rel="noopener noreferrer">
						<img src={logo.src} alt="Logo partenaire" />
					</a>
				{/each}
			</div>
		</div>

		<div class="header-center">
			<h1 class="header-title">LIS-LIRMM PFAS Data Hub</h1>
		</div>

		<div class="header-right">
			<a
				href={nextHref}
				class:active={mode === "on"}
				class="toggle-btn"
				aria-label={mode === "on" ? "Retour vers OFF" : "Aller vers ON"}
			>
				<span class="toggle-track">
					<span class="toggle-thumb"></span>
				</span>
				<span class="toggle-text">
					{mode === "on" ? "ON" : "OFF"}
				</span>
			</a>

			<ExportDialog {open} />
		</div>
	</div>
</header>


<style>
    .header-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 2rem;
    }

    .logo-title {
        display: flex;
        align-items: center;
        color: hsl(var(--primary-foreground));
        gap: 1.5rem;
    }
     header {
        background-color: hsl(var(--primary));
        padding: 1rem 1rem;
    }

   .logos {
	display: flex;
	align-items: center;
	gap: 0.9rem;
	flex-shrink: 0;
}

.logos a {
	display: flex;
	align-items: center;
	justify-content: center;
	padding: 0.22rem 0.4rem;
	border-radius: 6px;
	background: rgba(255, 255, 255, 0.05);
}

.logos img {
	height: 26px;
	max-width: 72px;
	width: auto;
	object-fit: contain;
	display: block;
	transition: opacity 0.2s ease, transform 0.2s ease;
}

.logos a:hover img {
	opacity: 0.9;
	transform: scale(1.04);
}
    .header-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
    }

    .toggle-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.75rem;
    text-decoration: none;
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.08);
    border-radius: 9999px;
    padding: 0.45rem 0.8rem;
    cursor: pointer;
    transition: all 0.2s ease;
    font-weight: 600;
    }

    .toggle-btn:hover {
    background: rgba(255, 255, 255, 0.14);
    }
    .header-right {
	display: flex;
	align-items: center;
	gap: 0.75rem;
}

    .toggle-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.65rem;
        height: 40px;
        padding: 0 0.9rem;
        box-sizing: border-box;
        position: relative;
        top: 1px;
    }

    .toggle-track {
    position: relative;
    width: 46px;
    height: 24px;
    border-radius: 9999px;
    background: rgba(255, 255, 255, 0.25);
    transition: background 0.2s ease;
    flex-shrink: 0;
    }

    .toggle-thumb {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 18px;
    height: 18px;
    border-radius: 9999px;
    background: white;
    transition: transform 0.2s ease;
    }

    .toggle-btn.active .toggle-track {
    background: #22c55e;
    }

    .toggle-btn.active .toggle-thumb {
    transform: translateX(22px);
    }

    .toggle-text {
    white-space: nowrap;
    font-size: 0.95rem;
    }

    .header-title {
        margin: 0;
        color: #ffffff;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        text-align: center;
        white-space: nowrap;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
}
</style>


