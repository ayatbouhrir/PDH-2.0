Sauvegarde des caches et artefacts associes aux parametres par defaut demandes.

Date de creation: 2026-06-29

Dossier:
- `analysis_cache/kmeans/`
- `analysis_cache/dbscan/`
- `analysis_cache/hdbscan/`
- `analysis_cache/propos/`
- `propos_cache/`
- `saint_outputs/`

Configurations cibles:

1. `kmeans`
- `k = 5`
- `maxIterations = 100`
- `reduction = saint`

Fichiers copies:
- `analysis_cache/kmeans/53cdb5c1bf08a8325d80879cb2090adbd9bed9aa47184ed23d09434d7361ecd1.json`
- `analysis_cache/kmeans/8bc105f76184639020d6044ad88823be96e0fc5ab0cb7f473d9412effb9efd9a.json`

2. `dbscan`
- `eps = 0.008`
- `minPts = 10`
- `reduction = saint`

Fichiers copies:
- `analysis_cache/dbscan/073752ae9f3f28caa65db7cd402fffaff00161a44c0197fd73b256101cd4aa08.json`
- `analysis_cache/dbscan/2b5c754bb0fd8301c03a8bbfb1dfe36c83cb1c9565cd3dde959f249e164da311.json`
- `analysis_cache/dbscan/a3ad97a6590c85310d356663db6681da54ecc81eb02cff30317dd99303c0fb8a.json`

3. `hdbscan`
- `minClusterSize = 30`
- `minSamples = 10`
- `clusterSelectionMethod = eom`
- `reduction = saint`

Fichier copie:
- `analysis_cache/hdbscan/6be9d2dcaa41c5ac0a619c4a2128d2f3818b10629f64bea9a201c8c43c6bb608.json`

4. `propos`
- `k = 5`
- `epochs = 100`
- `reduction = saint`

Fichier copie:
- `analysis_cache/propos/640467088adb3cec8460cf9925912dfdcb05e95c3516d562ab8e731c0513b829.json`

Artefacts relies copies:

SAINT:
- `saint_outputs/saint_pfas_latent_mean.parquet`
- `saint_outputs/saint_pfas_latent_mean.pt`
- `saint_outputs/saint_pfas_latent_mean.json`

ProPos:
- `propos_cache/propos_simple_reference.pt`

Notes:
- Tous ces caches correspondent au jeu global de `87281` points analyses, avec categorie `Measurement`, sans lasso, sans viewport local, et avec reduction `saint` quand elle est presente.
- Pour `dbscan`, plusieurs caches exacts existent avec les memes hyperparametres mais des resultats differents. Ils ont tous ete conserves.
- Pour `kmeans`, deux caches exacts existent. Ils ont tous les deux ete conserves.
