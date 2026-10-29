# Recherche scientifique

Les expériences et notebooks restent séparés du lancement de l'application.
Les notebooks retrouvent la racine du projet depuis le dossier courant ou un
de ses parents, et lisent `.local/project.env` pour la configuration locale.
Leurs sorties antérieures et métadonnées sont conservées.

Exemples depuis la racine, après installation avec le lanceur :

```powershell
.venv\Scripts\python.exe research\experiments\make_saint_tabpfn_plots.py
.venv\Scripts\python.exe research\experiments\compare_tabpfn_saint.py
```

Sous macOS/Linux, utiliser `.venv/bin/python`. Les expériences peuvent demander
des dépendances supplémentaires (Jupyter, TabPFN, extensions TabPFN, FP-growth,
Folium ou PyDeck selon le script), des accès externes et les données complètes.
Leur installation et les longs réentraînements ne font pas partie de la migration.

Pour les expériences utilisant le CSV complet, le chemin attendu est
`.local/full.csv`. Les exports relationnels facultatifs `point.csv`,
`metadonnee.csv` et `substance_ref.csv` peuvent être placés dans
`.local/research-data/`. Les résultats se trouvent dans `artifacts/experiments/`
et les embeddings SAINT dans `artifacts/embeddings/saint/`.

`init_db.ipynb` conserve l'ancienne procédure scientifique d'import et peut
modifier les tables. Pour installer le projet, utiliser le lanceur actuel.
La migration vérifie la conservation des modèles et résultats fournis ; elle
ne prétend pas avoir réexécuté chaque expérience scientifique.
