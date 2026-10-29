# Organisation du projet

## Responsabilités

- `frontend/` : application SvelteKit, routes publiques et dépendances JavaScript.
- `backend/` : API FastAPI, visualisations, SAINT à la demande, chargement des modèles et CLAMP.
- `research/notebooks/` : notebooks scientifiques, séparés de l'installation applicative.
- `research/experiments/` : comparaisons, règles d'association et cartes scientifiques.
- `research/saint/` : sources SAINT utilisées par les notebooks.
- `artifacts/embeddings/saint/` : embeddings, métadonnées et modèle SAINT conservés.
- `artifacts/experiments/` : résultats FP-growth, TabPFN et comparaisons SAINT/TabPFN.
- `artifacts/reference-runs/` : copie datée du 29 juin 2026 et caches scientifiques antérieurs ; doublons conservés volontairement.
- `vendor/propos/` : copie complète de ProPos et de son adaptateur tabulaire.
- `scripts/` : installation, import, gestion des services et contrôles fonctionnels.
- `tests/` : tests du lanceur et installation isolée de PostgreSQL.
- `docs/` : documentation actuelle ; les instructions antérieures sont dans `docs/archive/`.
- `archives/` : références algorithmiques, ancien panneau inutilisé, fichiers `.save`, fichiers système et anciennes sorties générées.
- `.local/` : base PostgreSQL privée, configuration, caches actifs et journaux.
- `.venv/` : environnement Python local, conservé à son emplacement.

`run.cmd`, `run.sh` et `run.py` restent les entrées publiques à la racine.
Le manifeste npm racine contient uniquement l'orchestration. Les versions des
dépendances applicatives restent dans `frontend/package.json` et son verrou.

## Frontend

`frontend/src/lib/features/` regroupe les fonctionnalités `exploration`, `analysis`,
`geography`, `history`, `comparison`, `visualization`, `explanations` et `export`.
Les composants métier se trouvent dans le sous-dossier `components/` de chaque
fonctionnalité. `components/ui/` conserve la bibliothèque générique et ses conventions.
L'en-tête commun est dans `components/layout/`.

`shared/map/`, `shared/pfas/` et `shared/types/` contiennent les éléments transversaux.
`shared/types/analysis-contract.ts` conserve les types et constantes du contrat
existant sans changer leurs identifiants exportés.

Conventions : composants en PascalCase ; modules TypeScript en kebab-case ; appels
HTTP suffixés `.api.ts` ; ressources réactives suffixées `.resource.svelte.ts` ;
états suffixés `.state.svelte.ts`. Les extensions réactives et les fichiers imposés
par SvelteKit (`+page`, `+server`, etc.) sont conservés. Les exports `dataRune`,
`analysisRune` et `runHistoryRune` conservent leur nom pour éviter une modification
du contrat interne.

`pfas-concentration-quartiles.ts` représente les quartiles empiriques existants ;
le renommage ne transforme pas ces valeurs en seuils réglementaires.

La copie FSAC complète est dans `frontend/src/lib/vendor/fsac/`, avec sa licence,
ses sources, distributions, verrous et configuration d'origine.

## Python et recherche

Les modules maintenus utilisent `snake_case`. Les noms internes des dépendances
externes restent inchangés. Les exigences Python sont dans `backend/requirements.txt`
et `backend/requirements-dev.txt`.

Les scripts de recherche sont facultatifs : leurs dépendances scientifiques,
jeux de données et éventuels accès TabPFN ne sont pas tous fournis par l'installation
applicative. Ils ne sont pas exécutés automatiquement au démarrage.

Les notebooks conservent leurs sorties scientifiques historiques. L'initialisation
de base historique n'est pas une procédure d'installation : utiliser le lanceur et
`scripts/import_local_data.py`. Ne pas exécuter le notebook d'import sur une autre base.
Les modèles fournis peuvent décrire un jeu différent de l'extrait local ; leur
présence ne constitue pas une validation scientifique sur cet extrait.

Le découpage de `backend/main.py` et des grands composants reste une étape distincte.
