# Installation et lancement automatique

Depuis le dossier du projet, utilisez une commande :

**Windows — PowerShell ou CMD**

```powershell
.\run.cmd
```

**macOS et Linux — Terminal**

```sh
sh run.sh
```

Le programme principal est `run.py`. Les deux petits lanceurs installent aussi Python
s'il manque. **Docker n'est pas nécessaire**, même au premier lancement.

## Ce que la commande prépare

1. Python 3.12 avec uv, si nécessaire.
2. Node.js 22/24 existant compatible, ou une distribution Node.js 24 locale vérifiée par SHA256.
3. Un environnement Python isolé et les dépendances de l'application : FastAPI,
   PostgreSQL, pandas, scikit-learn, PyTorch CPU, SHAP, CLAMP, graphiques et tests.
4. Les dépendances du site avec `npm ci`, à partir du fichier verrouillé.
5. Des binaires PostgreSQL compatibles : réutilisation des programmes installés,
   téléchargement des binaires officiels sous Windows, ou compilation locale
   depuis une archive officielle vérifiée sous macOS/Linux.
6. Une **instance PostgreSQL propre au projet**, avec un mot de passe aléatoire.
7. Un extrait réel de données PFAS et les index NUTS 2016/2021/2024.
8. Le service Python, le site et leur connexion à la base. Le navigateur s'ouvre
   seulement une fois les contrôles de disponibilité réussis.

Les installations, les journaux et les données sont dans `.local` et `.venv`.
Le lanceur n'installe pas de service PostgreSQL global, ne remplace pas vos bases
existantes et ne change pas vos fichiers `.env` personnels. La configuration du
lanceur se trouve dans **`.local/project.env`** : ne la partagez pas.

Les programmes PostgreSQL déjà présents peuvent être utilisés pour créer la nouvelle
instance : cela ne signifie pas que leur serveur ou leurs données sont utilisés.
Les ports habituels sont **5434**, **8000** et **5173**. Un port libre est choisi pour
une nouvelle instance si nécessaire. Un service existant étranger n'est jamais arrêté.
La console affiche les adresses réellement retenues.

Le premier lancement peut prendre plusieurs minutes. Les suivants réutilisent les
installations et les données. Une même copie du projet ne peut pas être installée
simultanément par deux lanceurs.

## Commandes utiles

Ajoutez les mêmes options après `run.cmd` ou `sh run.sh` :

```text
--doctor       Diagnostic sans installation ni modification
--setup-only   Installer et préparer sans démarrer le site
--no-open      Démarrer sans ouvrir de navigateur
--check        Vérifier les types et compiler le site
--test         Lancer les 48 contrôles fonctionnels du jeu de référence
--repair       Revérifier les dépendances Python et réinstaller les modules du site
--stop         Arrêter uniquement les processus et la base privés de ce projet
--help         Afficher toutes les options
```

Exemples :

```powershell
.\run.cmd --no-open --check --test
.\run.cmd --doctor
.\run.cmd --repair
.\run.cmd --stop
```

```sh
sh run.sh --no-open --check --test
sh run.sh --doctor
sh run.sh --stop
```

Si Node.js est déjà installé, `npm run start:local`, `npm run test:local`,
`npm run stop:local` et `npm run doctor` sont également utilisables sur les trois systèmes.

## Données : extrait ou fichier complet

Par défaut, le lanceur télécharge un **extrait de 8 Mo du CSV public**, pas le fichier
complet ni vos données privées. Sa composition dépend de la version du fichier source.
L'origine, les nombres de points et le caractère partiel sont enregistrés dans
`.local/data-import.json`.

Pour importer le fichier complet dans une **installation neuve** :

```powershell
.\run.cmd --data full
```

```sh
sh run.sh --data full
```

Le fichier source fait environ **3,5 Go**. Prévoyez plusieurs gigaoctets supplémentaires
pour PostgreSQL, les index et les bibliothèques. L'import fait deux lectures et charge
les points par lots de 5 000 : il ne garde pas tout le CSV en mémoire.

Pour votre propre CSV **au format PDH** :

```powershell
.\run.cmd --csv "C:\mes donnees\full.csv"
```

```sh
sh run.sh --csv "/chemin/mes donnees/full.csv"
```

Un CSV arbitraire d'un autre format n'est pas automatiquement converti. Les colonnes
requises sont vérifiées et les enregistrements invalides sont signalés.

Une base déjà peuplée est conservée. Demander un nouveau CSV ou le fichier complet
sur une installation contenant un extrait provoque un message explicite, sans
remplacement des données. Pour garder les deux installations, utilisez une autre
copie du code, sans copier `.local`, `.venv` ou `node_modules`.

L'import initial est transactionnel : un échec annule les tables de ce nouvel import.
L'indexation NUTS peut être relancée sans dupliquer les associations. Les anciens
embeddings/caches fournis dans le dépôt ne sont pas réutilisés avec un nouveau jeu
de données ; les embeddings sont recalculés.

## Systèmes et prérequis de l'ordinateur

- **Windows 10/11 x64** : PowerShell est inclus. PostgreSQL installé est détecté même
  s'il n'est pas dans le PATH. Sans PostgreSQL, les binaires EDB sont téléchargés
  localement. Sur Windows ARM64, fournissez des binaires compatibles via `PFAS_PG_BIN`.
  Si le runtime Microsoft Visual C++ manque, son installateur officiel est téléchargé,
  sa signature Microsoft est vérifiée et son installation est lancée. Windows peut
  demander une autorisation administrateur ; aucun redémarrage n'est imposé.
- **macOS Intel ou Apple Silicon** : si aucun PostgreSQL n'est installé, la compilation
  demande les outils de développement Apple (`xcode-select --install`). Si des outils
  supplémentaires manquent, Homebrew doit être disponible ; le lanceur installe alors
  bison, flex et make. Les autorisations ou l'installation initiale des outils Apple
  peuvent demander une intervention du système.
  Le Mac Intel utilise un profil séparé (PyTorch 2.2.2, NumPy 1.26 et versions compatibles) :
  [PyTorch ne publie plus de binaires Intel récents](https://dev-discuss.pytorch.org/t/pytorch-macos-x86-builds-deprecation-starting-january-2024/1690).
  Ce profil ancien ne bénéficie pas du support des versions PyTorch actuelles.
- **Linux glibc x86_64/ARM64** : Ubuntu/Debian, Fedora/RHEL avec dnf, et Arch avec pacman.
  En l'absence de PostgreSQL et des outils de compilation, ceux-ci sont installés via
  le gestionnaire du système. `sudo` peut demander votre mot de passe. Le lanceur
  lui-même doit fonctionner avec un utilisateur normal, car PostgreSQL refuse root.
  Sur Linux ARM64, HDBSCAN utilise l'implémentation fournie par scikit-learn pour éviter
  une compilation supplémentaire du paquet hdbscan, sans binaire officiel pour cette cible.
- **Alpine/musl et les systèmes 32 bits ne sont pas pris en charge** par cette installation
  des bibliothèques scientifiques. Utilisez une distribution Linux glibc.
- Une connexion Internet et assez d'espace disque sont nécessaires au premier lancement.
  Sous macOS/Linux, `curl` ou `wget` est nécessaire si uv manque.

Vous pouvez indiquer un répertoire de programmes PostgreSQL existants, sans changer
leur serveur :

```powershell
$env:PFAS_PG_BIN = 'C:\Program Files\PostgreSQL\18\bin'
.\run.cmd
```

```sh
PFAS_PG_BIN=/chemin/postgresql/bin sh run.sh
```

Si une base existe déjà, les binaires doivent correspondre à sa version majeure.
Le lanceur ne tente pas de migration automatique d'une base incompatible.

## Diagnostic et limites

Les erreurs de réseau, de permissions, d'espace disque ou de téléchargement produisent
un message avec l'étape concernée. Les archives Node.js et uv, ainsi que les sources
PostgreSQL, sont vérifiées avec les SHA256 publiés par leurs distributeurs.
Les binaires PostgreSQL Windows sont obtenus directement du serveur HTTPS officiel EDB.

Journaux des services :

```text
.local/backend.log
.local/backend-error.log
.local/frontend.log
.local/frontend-error.log
.local/postgres.log
.local/setup.log
.local/test-results.json
```

Le lanceur corrige les problèmes d'installation qu'il sait traiter. Il ne peut pas
garantir de résoudre toute panne possible : restrictions administrateur, matériel
incompatible, réseau bloqué, évolution du CSV source et services externes restent
des causes possibles d'échec.

`--doctor` exécuté directement avec Python n'effectue aucune installation. Si vous
passez par `run.cmd` ou `run.sh` sans uv/Python installé, le petit environnement
du lanceur doit d'abord être téléchargé, même pour afficher ce diagnostic.

WorldPop a expiré pendant les tests précédents, et les fonds CARTO demandent une clé
dans cet environnement. OpenStreetMap est utilisé par défaut. Des alertes de sécurité
dans les dépendances restent à traiter : le lanceur ne lance pas `npm audit fix --force`
et n'affirme pas les avoir corrigées.

Les tests fonctionnels utilisent les 94 points du jeu Danube et PFOA/PFOS. Ils ne
remplacent pas une validation scientifique ou un test de chaque jeu de données.
La CI `.github/workflows/launcher.yml` prévoit l'installation et les tests sur Windows,
macOS et Ubuntu. Ajouter cette CI ne signifie pas qu'elle a déjà été exécutée sur GitHub.

Sources des programmes téléchargés : [uv](https://docs.astral.sh/uv/getting-started/installation/),
[Node.js](https://nodejs.org/dist/), [PostgreSQL](https://www.postgresql.org/ftp/source/),
[binaires Windows EDB](https://www.enterprisedb.com/download-postgresql-binaries).
