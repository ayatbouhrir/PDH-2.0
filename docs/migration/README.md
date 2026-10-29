# Réorganisation 

La migration est réalisée sur place, après une sauvegarde complète vérifiée.
Elle porte sur les dossiers, noms, imports, chemins et commandes. Les calculs,
contrats API, URL des pages et identifiants exportés restent conservés.

## Sauvegarde privée

Emplacement : `D:\pfas-backups\pfas-data-hub-analytics-main-20261029-174830`.

La copie contient 63 254 fichiers, soit 2 369 230 591 octets : sources, fichiers
cachés, configurations privées, dépendances, modèles, résultats et données PostgreSQL.
Chaque fichier copié a été comparé à l'original par taille et SHA256, et les listes
de fichiers ont été comparées intégralement avant le premier déplacement.

La base privée du projet a été arrêtée pendant la copie physique. Le service
PostgreSQL indépendant sur le port 5433 est resté actif. L'accès à la sauvegarde
est limité au compte Windows courant et à SYSTEM.

La sauvegarde contient `BACKUP_VERIFIED.json`, `file-inventory.json`,
`database-before.json`, `migration-manifest.json`, `migration-journal.jsonl` et
`RESTORE.md`. Elle doit rester privée : elle contient des mots de passe.

## Traçabilité et conservation

[files.csv](files.csv) attribue à chacun des 63 254 fichiers initiaux un ancien
chemin, un nouveau chemin et un motif, y compris les fichiers restant en place.
Le manifeste a été validé avant le premier déplacement ; sa copie initiale et
le journal des opérations sont dans la sauvegarde.

Le manifeste final conserve séparément l'original d'un fichier de statistiques
PostgreSQL éphémère, régénéré par les essais. Les 63 254 destinations finales
existent. La copie Python produite par le test de réparation reste aussi dans la
sauvegarde privée ; l'environnement actif conserve les versions d'origine.

Les modèles et résultats binaires sont conservés sans déduplication. Les fichiers
historiques sont archivés. Les anciennes sorties SvelteKit/Vite et le bytecode
ont été archivés avant leur régénération. Les caches actifs dans `.local/cache/`
et la base dans `.local/postgres/` gardent leur emplacement.

Les anciens README sont dans `docs/archive/`. Les références `_birch.py`, leurs
tests et `hdbscan_.py` sont dans `archives/references/` et ne sont pas sur le chemin
d'import du serveur. Aucun module `backend/hdbscan.py` n'a été créé.

## Restauration

1. Arrêter les services du projet courant avec `run.cmd --stop`.
2. Conserver le dossier courant sous un autre nom, sans le fusionner avec la copie.
3. Recopier intégralement le sous-dossier `project/` de la sauvegarde vers le chemin
   original `D:\pfas-data-hub-analytics-main`.
4. Comparer les fichiers restaurés avec `file-inventory.json` avant de redémarrer.
5. Lancer `run.cmd --no-open --check --test` depuis le dossier restauré.

Ne pas remplacer les fichiers d'une instance PostgreSQL en fonctionnement.
Ne pas supprimer la sauvegarde après la livraison.
