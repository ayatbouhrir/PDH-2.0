# PFAS Data Hub Analytics

Application locale d'exploration et d'analyse de données PFAS : cartes, filtres,
clustering, explications, export et comparaison des analyses.

Depuis ce dossier :

```powershell
# Windows
.\run.cmd
```

```sh
# macOS / Linux
sh run.sh
```

Le lanceur prépare les dépendances et une instance PostgreSQL privée au projet.
Docker n'est pas nécessaire. Les adresses effectives s'affichent au démarrage.
Le premier lancement utilise un extrait réel ; l'import complet est optionnel.

- [Installation, options et dépannage](docs/installation.md)
- [Organisation et conventions](docs/project-structure.md)
- [Migration, sauvegarde et restauration](docs/migration/README.md)
- [Validation de la réorganisation](docs/migration/validation.md)

`frontend/` contient SvelteKit, `backend/` le serveur Python, `research/` les
expériences, `artifacts/` les modèles et résultats, `vendor/` les dépendances
scientifiques externes. Les données et journaux privés restent dans `.local/`.

Pour vérifier : `run.cmd --no-open --check --test` sous Windows, ou
`sh run.sh --no-open --check --test` sous macOS/Linux. Pour arrêter : ajouter `--stop`.
