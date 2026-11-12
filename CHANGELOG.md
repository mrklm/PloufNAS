# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### À venir
- Ajout d'un second capteur pour comparaison ?
- joindre un fichier STL pour mettre l'arduino dans le compartiement cdrom
  avec LCD et bouton en facade + capteurs int/ext ?

### Ajouté
- README : guide « Accès depuis l'extérieur » — VPN Tailscale (recommandé) ou WireGuard,
  reverse proxy HTTPS avec Caddy (réglages du dashboard et de ntfy, vérifications)

### Corrigé
- README : passage à la 1.3.0 validé sur OMV 8 ; retrait des ACL qu'OMV pose sur un dossier
  partagé (elles rendaient le dossier `monitoring`, et donc les scripts exécutés en root,
  modifiables par les utilisateurs du NAS), avec sauvegarde et restauration

## [1.3.0] - 2026-11-12

### Modifié
- **Dashboard sans root** : compte système `ploufnas` et service systemd durci (système en
  lecture seule sauf `reglages/`, aucun privilège possible)
- Configuration répartie en trois fichiers, répartition automatique de l'ancien `config.json` :
  `config.json` (lu par le dashboard), `ntfy.json` (adresse ntfy et jeton, root uniquement)
  et `reglages/reglages.json` (seuils, alertes et couleurs, seul fichier écrit par le dashboard)
- La surveillance ne lit dans `reglages/reglages.json` que les seuils, alertes et couleurs :
  un fichier falsifié ne peut changer ni ntfy, ni le port série, ni le fichier CSV
- Les fichiers de configuration réécrits conservent leurs droits et leur groupe ; les liens
  symboliques ne sont jamais suivis
- `config.py --verifier` signale les clés de `config.json` devenues sans effet
- README : création du compte `ploufnas`, droits des fichiers, procédure de passage à la 1.3.0

### Sécurité
- Configuration illisible ou invalide : le dashboard refuse de servir la page (erreur 503)
  au lieu de l'ouvrir sans tenir compte de « consultation protégée »

## [1.2.0] - 2026-11-12

### Ajouté
- Dashboard : bouton **?** à droite de « Paramètres », qui ouvre une aide résumée en
  5 sections (fermeture par ×, Échap ou clic à côté)

### Modifié
- Paramètres : mot de passe obligatoire dès qu'un seuil, une alerte ou une couleur est
  modifié (bouton « Enregistrer sur le NAS » grisé et champ signalé tant qu'il manque) ;
  l'affichage (mode, composants, thème) reste modifiable sans mot de passe
- Paramètres : fermer le panneau sans enregistrer annule les modifications des réglages du NAS
- Paramètres : fermeture par la touche Échap

### Corrigé
- Guide « Protéger ntfy par un jeton » validé sur OMV 8 et précisé : recréation du
  conteneur par **Up**, mots de passe ntfy sans saisie interactive (`NTFY_PASSWORD`),
  adresse du serveur identique dans l'application, remplacement d'un jeton divulgué,
  vérification sans afficher les jetons (`ntfy token list` les montre en entier)

## [1.1.0] - 2026-11-12

### Ajouté
- Authentification ntfy par jeton, facultative : `sudo python3 config.py --jeton-ntfy`
  (clé `ntfy_jeton` de `config.json`, prise en compte sans redémarrage)
- Message clair dans `journalctl` quand ntfy refuse la notification (HTTP 401/403)
- Avertissement au démarrage si le jeton part en HTTP non chiffré vers une autre machine
- README : guide « Protéger ntfy par un jeton » (comptes ntfy, jeton, téléphone)

### Sécurité
- Le jeton n'est jamais transmis au navigateur, ni modifiable depuis le dashboard ;
  `config.py --verifier` le masque

## [1.0.0] - 2026-11-12

Première version stable, validée en conditions réelles sur OpenMediaVault 8 (Debian 13) :
alertes climat et matérielles, redémarrage du NAS, mise à jour depuis les versions 0.x.

### Modifié
- README : le bandeau « version expérimentale » est remplacé par l'état de validation
- Icônes du dashboard réduites à 256 pixels de large : 6,7 Mo → 0,3 Mo à chaque ouverture
- Changelog renommé `CHANGELOG.md`
- Sketch Arduino rangé dans `arduino/sht31_nas_monitor/` (dossier exigé par l'IDE Arduino)

### Vérifié
- Sketch Arduino téléversé et validé sur matériel : erreurs `ERR,...` signalées au NAS quand le capteur ne répond plus, reprise des mesures sans redémarrage quand il revient

## [0.8.0] - 2026-11-12

Première étape du mode « accès extérieur » : tout est optionnel, le comportement
par défaut en réseau local est inchangé.

### Ajouté
- Section `dashboard` de `config.json` (modifiable uniquement dans le fichier) : adresse et
  port d'écoute, `consultation_protegee` (mot de passe dès l'ouverture), `derriere_proxy`
  (prise en compte des en-têtes `X-Forwarded-*`)
- **Blocage des mots de passe faux** : 5 échecs en 15 min bloquent l'adresse IP jusqu'à la
  fin de ce délai (remplace le simple délai d'une seconde)
- **En-têtes de sécurité HTTP** : politique CSP stricte, interdiction d'affichage dans un
  cadre, pas de mise en cache des réponses de l'API
- Refus des réglages envoyés depuis un autre site ou dans un autre format que JSON
- Serveur de production **waitress** utilisé s'il est installé (`python3-waitress`)
- Tests de sécurité du dashboard

### Modifié
- Plus aucun code JavaScript dans la page HTML (`onclick`, `onerror`) : tout est relié
  depuis `app.js`, condition de la politique CSP
- `python3-waitress` ajouté aux dépendances recommandées

### Sécurité
- Consultation protégée demandée sans mot de passe défini : le dashboard refuse l'accès
  au lieu de rester ouvert

## [0.7.0] - 2026-11-12

### Ajouté
- **Alerte « disque disparu ou muet »** : notification si un disque connu n'est plus listé
  par le système, ou ne répond plus à SMART deux relevés de suite (~10 min) ; notification
  de retour quand il répond de nouveau
- Détection d'un disque qui n'a pas redémarré avec le NAS (souvenir du dernier relevé)
- Case « Alerte disque disparu ou qui ne répond plus » dans le panneau Paramètres
- Disque disparu affiché « ⚠️ absent » dans le dashboard, avec ses dernières valeurs connues

### Modifié
- Disques identifiés par leur n° de série : un changement de nom `/dev/sdX` au démarrage ne
  provoque pas de fausse alerte
- Un échec de `lsblk` ne déclare plus tous les disques absents

## [0.6.0] - 2026-11-12

### Ajouté
- **Vraies données matérielles** dans le mode complet du dashboard (fin des données de
  démonstration) : modèle, température, fréquence et charge du CPU ; modèle, n° de série,
  capacité, température, état SMART et heures de fonctionnement de chaque disque
- **Alertes système opérationnelles** : température CPU, température disques et état SMART
  dégradé (auto-diagnostic en échec, secteurs réalloués, en attente ou irrécupérables),
  avec hystérésis et renvoi en cas d'échec de ntfy, comme pour le climat
- Module `nas/systeme.py` ; le relevé est fait par le service de surveillance et écrit dans
  `systeme.json`, lu par le dashboard (route `/api/systeme`)
- Commande de vérification `python3 systeme.py`
- Valeurs au-dessus du seuil affichées en rouge dans le dashboard
- Tests du relevé matériel et des alertes système

### Modifié
- Les disques en veille ne sont **jamais réveillés** (`smartctl -n standby`) : leur dernière
  valeur connue est affichée avec 💤
- Dépendance `smartmontools` ajoutée à l'installation
- Dashboard construit sans `innerHTML` pour les données des disques

## [0.5.1] - 2026-11-12

### Corrigé
- `config.py --mot-de-passe` : une saisie vide (touche Entrée en double) est redemandée
  au lieu de faire échouer la confirmation
- README : les commandes `rm` de la mise à jour refusent de s'exécuter si `MON` n'est pas défini

## [0.5.0] - 2026-11-12

### Ajouté
- **Configuration unique `config.json`**, partagée par la surveillance et le dashboard
  (`nas/config.py`), créée au premier lancement avec reprise de l'ancien `alertes.json`
- Commandes `config.py --init`, `--mot-de-passe` et `--verifier`
- **Mot de passe** pour enregistrer les réglages depuis le dashboard (empreinte PBKDF2,
  valeurs validées côté serveur, topic ntfy jamais envoyé au navigateur)
- Seuils de température et d'humidité réglables depuis le dashboard, **appliqués sans
  redémarrage** (`monitor_climat.py` relit `config.json` quand il change)
- Procédure « Mise à jour depuis une version précédente » dans le README
- Tests de la configuration et du dashboard

### Modifié
- Dashboard livré en fichiers (`nas/dashboard.py`, `nas/static/`) au lieu d'être généré
  par `setup_dashboard.py`
- **Chart.js 4.4.1 servi en local** : le graphique fonctionne sans Internet et ne change
  plus de version tout seul
- Icônes du dashboard déplacées de `assets/` vers `nas/static/img/`
- L'API ne lit plus que la fin du CSV (au lieu du fichier entier toutes les 5 s)
- Chemin du CSV relatif au dossier des scripts : plus d'UUID à recopier dans `monitor_climat.py`

### Corrigé
- La case « Garder le thème au rechargement » n'avait aucun effet ; le mode d'affichage
  et les composants choisis sont désormais aussi conservés (par navigateur)
- Le graphique coupait l'humidité au-dessus de 80 % (justement en cas d'alerte)
- Textes et graduations du graphique illisibles selon le thème (couleur non appliquée)

### Supprimé
- `nas/setup_dashboard.py` et `nas/alertes.json` (remplacés par `config.json`)

## [0.4.0] - 2026-11-12

Version expérimentale : le mode avancé du dashboard affiche encore des données
de démonstration pour le CPU et les disques.

### Ajouté
- Dashboard : **mode complet** (en plus du mode basique) avec blocs disques, CPU et GPU
  (données de démonstration pour l'instant)
- Dashboard : panneau **Paramètres** (mode d'affichage, composants affichés, couleurs
  des courbes, thème conservé au rechargement)
- Dashboard : réglages d'alertes système (CPU, disques, SMART, GPU) enregistrés dans
  `alertes.json` via `/api/alertes` (pas encore pris en compte par la surveillance)
- Icônes du dashboard (`assets/NAS.png`, `CPU.png`, `DD.png`, `GPU.png`) servies par Flask
- Capture de l'interface avancée dans le README
- Hystérésis sur les seuils de température et d'humidité
- Alerte unique si le CSV ne peut pas être écrit
- Journalisation via `logging`, visible en direct dans `journalctl`
- Tests unitaires (`tests/test_monitor_climat.py`)
- Notification de démarrage retentée tant que ntfy n'est pas joignable
- Règle udev : procédure pour la restreindre au numéro de série de la carte

### Modifié
- Numéro de version du dashboard aligné sur celui du projet (`v3.0` → `v0.4.0`)
- README : avertissement sur le statut expérimental du projet
- Topic ntfy anonymisé dans `monitor_climat.py` (`VOTRE-TOPIC`)

### Corrigé
- Dashboard : redimensionnement incohérent des graphiques et placement des blocs
  (mode plein écran)
- Alerte « pas de données » active dès le démarrage (un capteur muet n'était jamais signalé)
- Une notification ntfy en échec est retentée au lieu d'être perdue
- Lignes série tronquées et valeurs hors plage ignorées (fausses valeurs d'humidité)
- Arduino débranché : reconnexion automatique au lieu d'un plantage et d'une rafale de notifications
- Arduino : la lecture du SHT31 est vérifiée, une ligne `ERR` est envoyée en cas d'échec,
  et l'initialisation du capteur est retentée
- Règle udev renommée `99-arduino-nas.rules` (l'extension `.rb` faisait échouer la copie indiquée dans le README)
- Installation des dépendances via `apt` au lieu de `pip3` (refusé sur OMV 7 / Debian 12)
- Services systemd : attente du montage du volume (`RequiresMountsFor`), du réseau et de Docker ;
  logs non tamponnés
- README : copie des images du dashboard et remplacement de l'UUID dans les services

## [0.3.0] - 2026-09-18

### Modifié
- **Renommage du projet** : `Monitoring-Climatique-NAS` → **`PloufNAS`**
- **Titre du dashboard** : « Monitoring Climatique NAS » → « PloufNAS »
- **Titre du README** et passage au vouvoiement dans toute la documentation

### Ajouté
- Fichier **`.gitignore`** (exclusion des fichiers `.bak`, `__pycache__`, etc.)

### Supprimé
- Fichier `nas/monitor_climat.py.bak` (n'avait pas sa place dans le dépôt)

## [0.2.0] - 2026-09-18

### Ajouté
- **Alertes push via ntfy** auto-hébergé (Docker)
  - Notifications en temps réel sur température et humidité
  - Alerte « pas de données » si le capteur ne répond plus pendant 15 minutes
  - Notification de démarrage du service
- **Fichier `LICENSE`** (GPL v3)
- **Fichier `CHANGELOG.md`** (ce fichier)
- **Règle udev** `nas/99-arduino-nas.rules` pour un port série fixe (`/dev/arduino_nas`)
- Section « Alertes ntfy » dans le README
- Section « Personnalisation des alertes » dans le README

### Modifié
- **README** : refonte complète (intro, étapes d'installation, dépannage, sécurité)
- **Licence** : passage de MIT à **GPL v3**
- **Noms de services systemd** :
  - `monitor_climat.service` → `monitor-climat.service`
  - `dashboard.service` → `dashboard-climat.service`
- **Format CSV** : `Date et Heure,Temperature_C,Humidite_Pct`
- **Lecture du port série** : lit désormais tout le buffer et garde la dernière valeur
  (corrige le décalage entre les valeurs affichées sur le LCD et celles enregistrées)

### Corrigé
- Bug d'encodage **latin-1** lors de l'envoi ntfy : les emojis ne doivent plus
  être placés dans le titre (header HTTP), mais uniquement dans le corps du message
- Décalage entre les valeurs LCD et les valeurs enregistrées dans le CSV :
  le script ne lit plus la première ligne du buffer, mais la dernière
- Bloc de code mal fermé à l'Étape 3 du README (règle udev)

## [0.1.0] - 2026-09-17

### Ajouté
- Version initiale du projet
- Code Arduino `sht31_nas_monitor.ino` (lecture SHT31 + affichage LCD)
- Script `monitor_climat.py` (lecture série → CSV)
- Script `setup_dashboard.py` (génération du dashboard Flask)
- Dashboard web avec 16 thèmes et sélection aléatoire
- Services systemd pour le démarrage automatique
- Documentation initiale (README)

[Non publié]: https://github.com/mrklm/PloufNAS/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/mrklm/PloufNAS/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/mrklm/PloufNAS/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/mrklm/PloufNAS/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mrklm/PloufNAS/compare/v0.8.0...v1.0.0
[0.8.0]: https://github.com/mrklm/PloufNAS/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/mrklm/PloufNAS/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/mrklm/PloufNAS/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/mrklm/PloufNAS/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/mrklm/PloufNAS/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/mrklm/PloufNAS/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mrklm/PloufNAS/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mrklm/PloufNAS/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mrklm/PloufNAS/releases/tag/v0.1.0