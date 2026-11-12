# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### À venir
- Support pour l'accès distant aux alertes ?
- Ajout d'un second capteur pour comparaison ?
- joindre un fichier STL pour mettre l'arduino dans le compartiement cdrom
  avec LCD et bouton en facade + capteurs int/ext ?
- Mode « accès extérieur » optionnel : authentification ntfy par jeton, consultation du
  dashboard protégée, écoute derrière un reverse proxy HTTPS, limite des tentatives de
  mot de passe, services sans root

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

[Non publié]: https://github.com/mrklm/PloufNAS/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/mrklm/PloufNAS/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/mrklm/PloufNAS/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/mrklm/PloufNAS/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mrklm/PloufNAS/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mrklm/PloufNAS/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mrklm/PloufNAS/releases/tag/v0.1.0