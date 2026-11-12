# 💧 PloufNAS

> [!NOTE]
> ✅ **Version 1.0 — stable.** Validée en conditions réelles sur OpenMediaVault 8 (Debian 13) : capteur SHT31 sur Arduino, processeur Intel Core i3, RAID de 5 disques WD Red et SSD système. Alertes climat, matériel (CPU, disques, SMART, disque disparu), redémarrage du NAS et mise à jour depuis les versions précédentes testés.
>
> PloufNAS surveille votre NAS ; il ne remplace pas une **sauvegarde** de vos données. La détection du GPU n’est pas encore disponible.

Un NAS, comme tout ordinateur, possède des capteurs de température mais pas de capteur d'humidité !

C'est pourquoi je vous propose un système complet et robuste de surveillance de la température et de l'humidité, connecté à un NAS OpenMediaVault (OMV). Ce projet combine un capteur SHT31 branché sur une carte Arduino, un stockage sécurisé sur RAID et un tableau de bord web personnalisé avec thèmes dynamiques et alertes push via serveur de notification ntfy (ici déployé avec Docker).

![License](https://img.shields.io/badge/License-GPLv3-blue)

## 📸 Aperçu du projet

<table>
  <tr>
    <td align="center"><img src="assets/1.jpeg" alt="SHT31" width="300"/><br><i>Capteur SHT31</i></td>
    <td align="center"><img src="assets/2.jpg" alt="NAS" width="300"/><br><i>NAS</i></td>
    <td align="center"><img src="assets/3.jpg" alt="Prototype" width="300"/><br><i>Prototype</i></td>
  </tr>
  <tr>
    <td align="center" colspan="1"><img src="assets/4.png" alt="Interface Basique" width="300"/><br><i>Interface Web Basique</i></td>
    <td align="center" colspan="2"><img src="assets/5.png" alt="Interface Avancée" width="600"/><br><i>Interface Web Avancée</i></td>
  </tr>
</table>

---

## ✨ Fonctionnalités

- **Acquisition fiable** : Lecture du capteur SHT31 (Température + Humidité) via Arduino.
- **Stockage robuste** : Enregistrement continu des données dans un fichier CSV sur le volume de stockage.
- **Dashboard Web** : Interface légère en Flask + Chart.js (servi en local, fonctionne sans Internet), accessible sur tout le réseau local.
- **Réglages depuis le navigateur** : seuils d'alerte modifiables dans le dashboard (protégés par mot de passe), appliqués sans redémarrage.
- **Thèmes personnalisés** : 16 thèmes intégrés (Sombres, Clairs, et "Pouêt-Pouêt") avec sélection aléatoire au chargement.
- **Alertes push** : Notifications en temps réel via **ntfy** (auto-hébergé) si les seuils de température ou d'humidité sont dépassés.
- **Alerte "pas de données"** : Notification si aucune donnée n'est reçue depuis plus de 15 minutes (détection d'un capteur débranché ou d'un service planté).
- **Surveillance matérielle** : température et charge du CPU, température et état SMART de chaque disque, avec alertes ntfy (seuils réglables dans le dashboard). Les disques en veille ne sont jamais réveillés.
- **Démarrage automatique** : Gestion via `systemd` pour une exécution en arrière-plan au démarrage du NAS.

---

## 🛠️ Matériel requis

- 1x Arduino (Uno, Nano ou compatible)
- 1x Capteur de température et d'humidité **SHT31** (interface I2C)
- 1x Écran LCD I2C 16x2 (optionnel, pour affichage local sur l'Arduino)
- 1x Câble USB **de données** (Attention : beaucoup de câbles USB ne font que la charge !)
- 1x NAS sous OpenMediaVault (OMV) avec un dossier partagé configuré

---

## 🔌 Câblage

| Composant | Broche | Connexion Arduino |
| :--- | :---: | :--- |
| **SHT31** | VIN | 3.3V |
| | GND | GND |
| | SCL-T | A5 (SCL) |
| | SAA-RH | A4 (SDA) |
| **LCD I2C** | VCC | 5V |
| | GND | GND |
| | SDA | A4 (SDA) |
| | SCL | A5 (SCL) |

*(Les broches AL/AD du SHT31 doivent rester non connectées pour utiliser l'adresse I2C par défaut `0x44`)*.

---

## 💻 Installation

### Étape 1 : Configuration Arduino

1. Installez les bibliothèques suivantes via le gestionnaire de bibliothèques de l'IDE Arduino :
   - `LiquidCrystal I2C` (par Frank de Brabander)
   - `SHT31` (par Rob Tillaart)
2. Téléversez le code situé dans `arduino/sht31_nas_monitor/sht31_nas_monitor.ino`.
3. Ouvrez le moniteur série à **9600 bauds** pour vérifier que les données `DATA,Temp,Hum` s'affichent.

### Étape 2 : Préparation du NAS (OpenMediaVault)

1. Créez un dossier partagé nommé `monitoring` sur votre volume de stockage principal via l'interface OMV.
2. Notez le chemin réel de ce dossier. Vous pouvez le trouver via l'interface OMV ou en tapant `lsblk -f` dans le terminal.

### Étape 3 : Règle Udev (Port Série Fixe)

Pour éviter que le nom du port Arduino (`/dev/ttyUSB0`) ne change au redémarrage :

1. Copiez le fichier `nas/99-arduino-nas.rules` dans `/etc/udev/rules.d/` sur le NAS.
2. Rechargez les règles et redémarrez le service udev :

   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

3. Vérifiez que le symlink a bien été créé :

   ```bash
   ls -l /dev/arduino_nas
   ```

   → Doit afficher un lien vers `/dev/ttyUSB0` (ou `ttyACM0`).

> 💡 Si le symlink n'apparaît pas, débranchez/rebranchez l'Arduino et relancez `sudo udevadm trigger`.

> ⚠️ Les règles CH340 et FTDI reconnaissent n'importe quel appareil équipé de ces puces (un onduleur USB, par exemple). Si un autre appareil USB-série est branché sur le NAS, restreignez la règle au numéro de série de votre carte : la marche à suivre est décrite en tête du fichier `nas/99-arduino-nas.rules`.

---

### Étape 4 : Installation de ntfy (alertes push)

Le projet utilise **ntfy** pour l'envoi des notifications. Nous allons l'auto-héberger sur le NAS via Docker.

#### 4.1 — Installation de Docker sur OMV

Dans l'interface web OMV :

1. **Système → omv-extras** : cochez le dépôt **Docker repo**, enregistrez.
2. **Système → Plugins** : installez `openmediavault-compose`.
3. **Services → Compose → Paramètres** :
   - **Compose Files** : sélectionnez un dossier partagé (ex. `docker-compose`)
   - **Data** : sélectionnez un dossier partagé (ex. `docker-data`)
   - **Docker storage** : sélectionnez un dossier partagé (ex. `docker`)
   - Enregistrez et appliquez.

> 💡 Il faut **trois dossiers partagés distincts** pour que le plugin Compose fonctionne correctement.

#### 4.2 — Création du conteneur ntfy

Allez dans **Services → Compose → Fichiers → Ajouter** :

- **Nom** : `ntfy`
- **Contenu** :

```yaml
services:
  ntfy:
    image: binwiederhier/ntfy
    container_name: ntfy
    command: serve
    environment:
      - TZ=Europe/Paris
    volumes:
      - CHANGE_TO_COMPOSE_DATA_PATH/ntfy/cache:/var/cache/ntfy
      - CHANGE_TO_COMPOSE_DATA_PATH/ntfy/config:/etc/ntfy
    ports:
      - "8080:80"
    restart: unless-stopped
```

Enregistrez, puis allez dans **Services → Compose → Services** et démarrez `ntfy`.

#### 4.3 — Configuration du téléphone

1. Installez l'application **ntfy** :
   - [Android (Play Store)](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   - [Android (F-Droid)](https://f-droid.org/packages/io.heckel.ntfy/)
   - [iOS (App Store)](https://apps.apple.com/app/ntfy/id1625396347)
2. Dans l'app, ajoutez un serveur personnalisé : `http://IP-DU-NAS:8080`
3. Abonnez-vous à un topic, par exemple `mon-nas-climat-alerte`.

> ⚠️ **IMPORTANT — Choisissez votre propre topic !**
>
> Le topic ntfy fait office de **mot de passe** : quiconque connaît son nom peut lire et écrire dedans (si vous n'activez pas l'authentification).
>
> Utilisez un nom **long, unique et difficile à deviner**, par exemple :
> ```bash
> echo "mon-nas-climat-$(openssl rand -hex 6)"
> # → ex: mon-nas-climat-a7f3k9x2m4p8
> ```
>
> Ne réutilisez **jamais** un nom de topic trouvé dans un tuto ou un exemple public.
>
> Pour aller plus loin (serveur ntfy accessible depuis Internet), protégez ntfy par un **jeton** : voir [Protéger ntfy par un jeton](#protéger-ntfy-par-un-jeton-facultatif).

#### 4.4 — Test de la chaîne

Depuis le NAS en SSH :

```bash
curl -d "Test alerte climat" http://localhost:8080/VOTRE-TOPIC
```

→ La notification doit apparaître sur le téléphone en quelques secondes.

---

### Étape 5 : Déploiement des scripts sur le volume de stockage

**1. Trouvez l'UUID de votre volume :**

```bash
lsblk -f
```

Repérez la ligne correspondant à votre disque/RAID, et copiez la valeur dans la colonne `UUID`.
Placez-la dans une variable : les commandes suivantes l'utilisent pour éviter les erreurs de copie.

```bash
UUID=collez-ici-votre-uuid
ls -d /srv/dev-disk-by-uuid-$UUID   # doit afficher le dossier, sinon l'UUID est faux
```

> 💡 La variable est perdue si vous fermez la session SSH : redéfinissez-la avant de reprendre aux étapes 5 ou 8.

**2. Copiez les scripts et l'interface web au bon endroit :**

```bash
MON=/srv/dev-disk-by-uuid-$UUID/monitoring
sudo mkdir -p $MON

# Scripts + dossier static/ (page web, styles, icônes, Chart.js)
sudo cp -r ~/PloufNAS/nas/monitor_climat.py \
           ~/PloufNAS/nas/config.py \
           ~/PloufNAS/nas/systeme.py \
           ~/PloufNAS/nas/dashboard.py \
           ~/PloufNAS/nas/static \
           $MON/

# Vérifier
ls -la $MON $MON/static
```

**3. Créez et personnalisez la configuration :**

Les réglages sont répartis en trois fichiers, pour que le dashboard n'ait accès qu'au strict nécessaire (voir [Dashboard sans root](#dashboard-sans-root)) :

| Fichier | Contenu | Accès du dashboard |
|---|---|---|
| `config.json` | port série, fichier CSV, empreinte du mot de passe, section `dashboard` | lecture |
| `ntfy.json` | adresse ntfy (avec votre topic) et jeton | aucun |
| `reglages/reglages.json` | seuils, alertes et couleurs | lecture et écriture |

Les chemins sont relatifs au dossier `monitoring` : vous n'avez pas à y recopier l'UUID.

```bash
cd $MON
sudo python3 config.py --init         # crée les trois fichiers avec les valeurs par défaut
sudo nano ntfy.json                   # remplacez VOTRE-TOPIC dans "ntfy_url"
sudo python3 config.py --mot-de-passe # mot de passe pour enregistrer les réglages depuis le dashboard
sudo python3 config.py --verifier     # contrôle la configuration et l'affiche
```

Contenu de `ntfy.json` :

```json
{
    "ntfy_url": "http://localhost:8080/VOTRE-TOPIC",
    "ntfy_jeton": ""
}
```

> 🔒 Le mot de passe lui-même n'est jamais enregistré, seulement son empreinte. Les trois fichiers sont exclus du dépôt Git.

---

### Étape 6 : Installation des dépendances Python

En SSH sur le NAS :

```bash
sudo apt update
sudo apt install -y python3 python3-serial python3-flask python3-requests python3-waitress smartmontools curl
```

> 💡 N'utilisez pas `sudo pip3 install` : sur OMV 7 (Debian 12), pip refuse d'installer des paquets dans le Python système (erreur `externally-managed-environment`). Les paquets `python3-*` de Debian font la même chose proprement et sont mis à jour avec le système.

> 💡 Les services utilisent `/usr/bin/python3` (Python système, pas de venv). La surveillance tourne en `root`, car elle lit le port série et l'état SMART des disques. Le dashboard, seul service accessible par le réseau, tourne sous un compte dédié sans droits (étape 8).

---

### Étape 7 : Test manuel avant systemd

**Testez toujours à la main avant d'activer les services** — sinon vous déboguez à l'aveugle.

```bash
cd /srv/dev-disk-by-uuid-$UUID/monitoring/

# Terminal 1 : collecteur (lecture série → CSV + alertes ntfy)
sudo python3 monitor_climat.py

# Terminal 2 : dashboard Flask
sudo python3 dashboard.py
```

→ Vous devez recevoir une notification `[OK] Monitoring climatique demarre` sur le téléphone.
→ Puis depuis un navigateur du réseau : `http://IP-DU-NAS:5000`

Si tout fonctionne → passez à systemd. Sinon → inspectez les erreurs affichées.

---

### Étape 8 : Installation des services systemd

**1. Créez le compte du dashboard** et réglez les droits des fichiers de configuration (variables `UUID` et `MON` de l'étape 5) :

```bash
# OMV : un dossier partagé reçoit des ACL qui le rendent modifiable par les utilisateurs
# du NAS (le « + » dans ls -l). Ils pourraient alors modifier les scripts exécutés en root.
# Sauvegarde des ACL, puis seul root peut écrire (la lecture reste possible pour tous).
sudo sh -c 'getfacl -R -p "$0" > /root/monitoring-acl.sauvegarde' "${MON:?}"
sudo setfacl -R -b "${MON:?}"
sudo chown -R root:root "${MON:?}" && sudo chmod g-s "${MON:?}" && sudo chmod -R go-w "${MON:?}"

# Compte système sans mot de passe ni connexion possible
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ploufnas

# Le dashboard lit config.json, écrit dans reglages/, et ne peut pas lire ntfy.json
sudo mkdir -p "${MON:?}/reglages"
sudo chown -R ploufnas:ploufnas "${MON:?}/reglages" && sudo chmod 750 "${MON:?}/reglages"
sudo chgrp ploufnas "${MON:?}/config.json" && sudo chmod 640 "${MON:?}/config.json"
sudo chmod 600 "${MON:?}/ntfy.json"

# Vérification : « OK » puis « refusé », et aucun « + » dans la liste
sudo -u ploufnas test -r "${MON:?}/config.json" && echo OK
sudo -u ploufnas test -r "${MON:?}/ntfy.json" || echo refusé
ls -la "${MON:?}"
```

> 💡 Pour annuler le retrait des ACL : `sudo setfacl --restore=/root/monitoring-acl.sauvegarde`. Pour donner accès aux données depuis le réseau, partagez-les en **lecture seule** (privilèges du dossier partagé dans OMV), jamais en écriture.

**2. Installez les services.** Les fichiers sont fournis dans `nas/`. Il faut les copier dans `/etc/systemd/system/` puis y remplacer `VOTRE_UUID` :

```bash
sudo cp ~/PloufNAS/nas/monitor-climat.service /etc/systemd/system/
sudo cp ~/PloufNAS/nas/dashboard-climat.service /etc/systemd/system/
sudo sed -i "s/VOTRE_UUID/$UUID/g" /etc/systemd/system/monitor-climat.service \
                                    /etc/systemd/system/dashboard-climat.service

# Vérifier qu'il ne reste aucun VOTRE_UUID (la commande ne doit rien afficher)
grep VOTRE_UUID /etc/systemd/system/*-climat.service

# Recharger systemd
sudo systemctl daemon-reload

# Activer + démarrer
sudo systemctl enable --now monitor-climat.service
sudo systemctl enable --now dashboard-climat.service

# Vérifier l'état
systemctl status monitor-climat.service
systemctl status dashboard-climat.service

# Logs en direct
journalctl -u monitor-climat.service -f
journalctl -u dashboard-climat.service -f
```

---

### Étape 9 : Accès au dashboard

Depuis un navigateur sur le réseau local :

```
http://IP-DU-NAS:5000
```

Pour trouver l'IP du NAS :

```bash
hostname -I
```

Le bouton **?**, à droite de **⚙️ Paramètres**, ouvre une aide résumée du dashboard (affichage, alertes, paramètres, dépannage).

Dans **⚙️ Paramètres**, l'affichage (mode, composants, thème) est propre à chaque navigateur et se modifie librement. Les seuils, les alertes et les couleurs sont enregistrés sur le NAS : dès que l'un d'eux est modifié, le bouton devient **Enregistrer sur le NAS** et reste grisé tant que le mot de passe n'est pas saisi. Fermer le panneau sans enregistrer annule ces modifications.

**Optionnel** — accès depuis l'extérieur : voir [Accès depuis l'extérieur](#accès-depuis-lextérieur) (VPN recommandé, ou reverse proxy HTTPS). ⚠️ **N'exposez jamais le dashboard directement sur Internet**.

---

### Étape 10 : Vérification du bon fonctionnement

Checklist après installation :

- [ ] Le fichier CSV se remplit bien (1 ligne/minute)
- [ ] Le dashboard affiche les données
- [ ] Les valeurs changent si on souffle sur le capteur
- [ ] Après `sudo reboot`, les deux services redémarrent seuls
- [ ] La notification de démarrage `[OK]` arrive sur le téléphone
- [ ] L'alerte humidité > 80 % se déclenche (souffler sur le capteur)
- [ ] L'alerte température > 30 °C se déclenche (si testable)
- [ ] En mode complet, le CPU et chaque disque affichent leur température (survol : modèle, SMART, heures de fonctionnement)

---

### Mise à jour depuis une version précédente (≤ 0.4.0)

Jusqu'à la version 0.4.0, le dashboard était généré par `setup_dashboard.py` et les réglages étaient écrits dans `monitor_climat.py`. Depuis la 0.5.0, ils sont dans des fichiers de configuration. En SSH sur le NAS :

```bash
UUID=collez-ici-votre-uuid
MON=/srv/dev-disk-by-uuid-$UUID/monitoring
ls -d $MON                                    # doit afficher le dossier

# 1. Récupérer la nouvelle version du dépôt
cd ~/PloufNAS && git pull

# 2. Noter votre topic ntfy actuel (il sera à reporter dans ntfy.json)
grep NTFY_URL $MON/monitor_climat.py

# 3. Arrêter les services et sauvegarder le dossier (dont l'historique climat.csv)
sudo systemctl stop monitor-climat dashboard-climat
sudo cp -a $MON $MON.sauvegarde-$(date +%F)

# 4. Dépendances (sans effet si elles sont déjà installées)
sudo apt update
sudo apt install -y python3-serial python3-flask python3-requests python3-waitress smartmontools

# 5. Supprimer les fichiers des anciennes versions
#    (alertes.json est conservé : ses réglages sont repris automatiquement)
# ${MON:?} : la commande est refusée si MON n'est pas défini (au lieu de viser /)
sudo rm -f "${MON:?}"/setup_dashboard.py "${MON:?}"/index.html
sudo rm -rf "${MON:?}"/assets "${MON:?}"/__pycache__

# 6. Copier la nouvelle version, puis créer la configuration
sudo cp -r ~/PloufNAS/nas/monitor_climat.py ~/PloufNAS/nas/config.py ~/PloufNAS/nas/systeme.py \
           ~/PloufNAS/nas/dashboard.py ~/PloufNAS/nas/static $MON/
cd $MON
sudo python3 config.py --init
sudo nano ntfy.json                   # reportez le topic noté à l'étape 2 dans "ntfy_url"
sudo python3 config.py --mot-de-passe
sudo python3 config.py --verifier

# 7. Règle udev (l'ancien fichier pouvait s'appeler 99-arduino-nas.rules.rb)
ls /etc/udev/rules.d/ | grep -i arduino
sudo rm -f /etc/udev/rules.d/99-arduino-nas.rules.rb
sudo cp ~/PloufNAS/nas/99-arduino-nas.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -l /dev/arduino_nas

# 8. Compte du dashboard et droits des fichiers (voir étape 8.1 de l'installation)
# OMV : un dossier partagé reçoit des ACL qui le rendent modifiable par les utilisateurs
# du NAS (le « + » dans ls -l). Ils pourraient alors modifier les scripts exécutés en root.
# Sauvegarde des ACL, puis seul root peut écrire (la lecture reste possible pour tous).
sudo sh -c 'getfacl -R -p "$0" > /root/monitoring-acl.sauvegarde' "${MON:?}"
sudo setfacl -R -b "${MON:?}"
sudo chown -R root:root "${MON:?}" && sudo chmod g-s "${MON:?}" && sudo chmod -R go-w "${MON:?}"
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ploufnas
sudo mkdir -p "${MON:?}/reglages"
sudo chown -R ploufnas:ploufnas "${MON:?}/reglages" && sudo chmod 750 "${MON:?}/reglages"
sudo chgrp ploufnas "${MON:?}/config.json" && sudo chmod 640 "${MON:?}/config.json"
sudo chmod 600 "${MON:?}/ntfy.json"

# 9. Services systemd
sudo cp ~/PloufNAS/nas/monitor-climat.service ~/PloufNAS/nas/dashboard-climat.service /etc/systemd/system/
sudo sed -i "s/VOTRE_UUID/$UUID/g" /etc/systemd/system/monitor-climat.service \
                                    /etc/systemd/system/dashboard-climat.service
grep VOTRE_UUID /etc/systemd/system/*-climat.service   # ne doit rien afficher
sudo systemctl daemon-reload
sudo systemctl enable --now monitor-climat dashboard-climat

# 10. Vérifier
systemctl status monitor-climat dashboard-climat --no-pager
journalctl -u monitor-climat -n 20 --no-pager
```

Une fois que tout fonctionne, vous pouvez supprimer `$MON/alertes.json` et, après quelques jours, la sauvegarde `$MON.sauvegarde-*`.

> 💡 Le nouveau sketch Arduino (`arduino/sht31_nas_monitor/sht31_nas_monitor.ino`) signale les erreurs de lecture du capteur. Il est conseillé de le téléverser, mais la surveillance fonctionne aussi avec l'ancien.

---

## 🔔 Personnalisation des alertes

Les seuils se règlent dans le panneau **⚙️ Paramètres** du dashboard (section « Alertes climat », mot de passe requis) ou dans `reglages/reglages.json`. Ils sont pris en compte **sans redémarrer** le service : `monitor_climat.py` relit les fichiers de configuration dès qu'ils changent. Une configuration invalide est ignorée (l'ancienne reste active) et signalée dans `journalctl`.

Paramètres (`seuils.*` dans `reglages/reglages.json`, `ntfy_*` dans `ntfy.json`, les autres dans `config.json`) :

| Paramètre | Description | Valeur par défaut |
|---|---|---|
| `seuils.temp_max` | Seuil de température (°C) | `30.0` |
| `seuils.hum_max` | Seuil d'humidité (%) | `80.0` |
| `seuils.temp_hysteresis` | Écart sous le seuil avant le retour à la normale (température) | `1.0` (°C) |
| `seuils.hum_hysteresis` | Écart sous le seuil avant le retour à la normale (humidité) | `2.0` (%) |
| `ntfy_url` | URL ntfy + topic | `http://localhost:8080/VOTRE-TOPIC` |
| `ntfy_jeton` | Jeton d'accès ntfy, à enregistrer avec `sudo python3 config.py --jeton-ntfy` (facultatif) | vide (pas d'authentification) |
| `port_serie` | Port série de l'Arduino | `/dev/arduino_nas` |
| `fichier_csv` | Historique (relatif au dossier `monitoring`, ou chemin absolu) | `climat.csv` |

**Alertes système** (panneau ⚙️ Paramètres → « Alertes système », ou `alertes_systeme` dans `reglages/reglages.json`) :

| Alerte | Déclenchement | Retour à la normale |
|---|---|---|
| Température CPU | au-dessus du seuil (75 °C par défaut) | 3 °C sous le seuil |
| Température disques | un disque au-dessus du seuil (50 °C par défaut) | 2 °C sous le seuil |
| État SMART dégradé | auto-diagnostic SMART en échec, ou secteurs réalloués / en attente / irrécupérables | plus aucune anomalie |
| Disque disparu ou muet | un disque connu n'est plus listé par le système, ou ne répond plus à SMART deux relevés de suite (~10 min) | le disque répond de nouveau |

Le CPU est relevé chaque minute, les disques toutes les 5 minutes avec `smartctl -n standby` : **un disque en veille n'est jamais réveillé**, il garde sa dernière valeur connue et n'est pas pris en compte pour les alertes tant qu'il dort. Les disques sont identifiés par leur n° de série (le nom `/dev/sdX` peut changer au redémarrage, sans fausse alerte).

**Disque disparu** : le service se souvient des disques du dernier relevé (`systeme.json`). Un disque qui ne revient pas après un redémarrage du NAS est donc signalé dès le démarrage. Si vous retirez un disque **volontairement**, l'alerte part une fois ; le disque est oublié au redémarrage suivant du service (`sudo systemctl restart monitor-climat`). Le relevé est écrit dans `systeme.json`, que le dashboard lit sans interroger les disques.

Réglages avancés, en haut de `monitor_climat.py` (redémarrage du service nécessaire) :

| Paramètre | Description | Valeur par défaut |
|---|---|---|
| `DELAI_SANS_DONNEES` | Délai avant alerte "pas de données" | `15 * 60` (15 min) |
| `INTERVALLE_LECTURE` | Fréquence de lecture du port série | `5` (secondes) |
| `INTERVALLE_ECRITURE` | Fréquence d'écriture dans le CSV | `60` (secondes) |
| `DELAI_RECONNEXION` | Délai entre deux tentatives d'ouverture du port série | `10` (secondes) |
| `INTERVALLE_SYSTEME` | Fréquence du relevé matériel (les disques : `INTERVALLE_DISQUES` de `systeme.py`, 5 min) | `60` (secondes) |

**Logique anti-spam** : le script n'envoie une notification **qu'aux transitions** :
- Normal → Alerte : 1 notification
- Alerte → Normal : 1 notification (retour à la normale)
- Alerte → Alerte : aucune notification (pas de spam)
- Le retour à la normale n'a lieu que sous `seuil - hystérésis` (ex. 78 % pour un seuil à 80 %), pour éviter les rafales quand la valeur oscille autour du seuil.
- Si l'envoi d'une notification échoue (ntfy indisponible), l'état n'est pas modifié : la notification est retentée au cycle suivant.

**Robustesse** :
- L'alerte « pas de données » est active dès le démarrage : un capteur muet dès le départ est aussi signalé.
- Un Arduino débranché ne fait plus planter le service : le port est rouvert automatiquement, et l'absence de données déclenche l'alerte au bout de `DELAI_SANS_DONNEES`.
- Les préférences d'affichage (mode, composants, thème conservé) sont propres à chaque navigateur ; les seuils, alertes et couleurs sont enregistrés sur le NAS.
- Les lignes série tronquées ou les valeurs hors plage sont ignorées.
- L'Arduino envoie `ERR,...` quand la lecture du SHT31 échoue. Ces lignes ne comptent pas comme des mesures.
- Si le CSV ne peut pas être écrit (volume non monté...), une notification unique est envoyée et les alertes restent actives.

**Tests** (depuis la racine du dépôt, sans matériel) :

```bash
python3 -m unittest discover -s tests
```

Les tests du dashboard sont ignorés si Flask n'est pas installé sur la machine.

---

## 🔧 Dépannage

| Symptôme | Piste à explorer |
|---|---|
| Port série absent | Vérifiez `/dev/ttyUSB*` / `/dev/ttyACM*`, `lsusb`, `dmesg \| tail` |
| Données illisibles | Baudrate 9600 ? Droits série (`dialout`) ? |
| CSV vide | `journalctl -u monitor-climat -n 50` |
| `dashboard.py` introuvable | Recopiez `nas/dashboard.py` et le dossier `nas/static/` dans `monitoring` (étape 5) |
| « Mot de passe incorrect » / « Aucun mot de passe n'est défini » | Sur le NAS : `cd $MON && sudo python3 config.py --mot-de-passe` |
| `Configuration invalide` dans les logs | `sudo python3 config.py --verifier` indique la valeur en cause |
| Dashboard inaccessible | Bonne IP ? Pare-feu OMV ? Port 5000 ouvert ? |
| Thème ne change pas | Videz le cache navigateur (Ctrl+F5) |
| Service ne démarre pas | `journalctl -u <monitor-climat\|dashboard-climat> -xe` |
| Erreur "UUID not found" | Vérifiez que `VOTRE_UUID` a bien été remplacé |
| Service bloqué au démarrage (`Dependency failed`) | Le volume n'est pas monté ou l'UUID est faux : `grep RequiresMountsFor /etc/systemd/system/*-climat.service` puis `ls /srv/` |
| Erreur `externally-managed-environment` | N'utilisez pas `pip3` : installez les paquets `python3-*` avec `apt` (étape 6) |
| Mode complet : « Relevé matériel indisponible » | Le relevé est fait par `monitor-climat` : vérifiez qu'il tourne (`systemctl is-active monitor-climat`). Le premier relevé arrive 30 s après son démarrage |
| Disque affiché `-- °C` ou « Lecture impossible » | Testez `sudo smartctl -j -H -A /dev/sdX` ; installez `smartmontools` si la commande est absente |
| Disque affiché ⚠️ absent | Il n'est plus vu par le système : vérifiez câble, alimentation et `cat /proc/mdstat`. Retiré volontairement : `sudo systemctl restart monitor-climat` pour l'oublier |
| Disque affiché 💤 | Il est en veille : PloufNAS ne le réveille pas et montre sa dernière valeur connue |
| Images ou graphique absents du dashboard | Le dossier `monitoring/static/` est incomplet : recopiez `nas/static` (étape 5) |
| **Erreur `latin-1 codec can't encode`** | Un emoji est présent dans un **titre** de notification. Les titres ne doivent contenir que de l'ASCII — les emojis sont OK dans le **corps** du message. |
| Notification ntfy non reçue | Vérifiez que le conteneur tourne : `docker ps \| grep ntfy` |
| Dashboard : « Configuration du NAS illisible ou invalide » | Droits des fichiers à revoir (étape 8.1), ou fichier abîmé : `sudo python3 config.py --verifier` et `journalctl -u dashboard-climat -n 20` |
| ntfy inaccessible | Testez `curl http://localhost:8080/v1/health` sur le NAS |
| `ntfy a refusé la notification (HTTP 401)` ou `(HTTP 403)` | Le serveur ntfy exige un jeton, ou refuse celui de `ntfy.json` : voir [Protéger ntfy par un jeton](#protéger-ntfy-par-un-jeton-facultatif) |
| Alerte humidité non déclenchée | Le script lit le buffer série en entier (corrigé). Si le problème persiste, vérifiez le code Arduino. |

---

## 🔐 Sécurité

- ❌ Ne **jamais** exposer Flask ou ntfy directement sur Internet : passez par un VPN ou un reverse proxy HTTPS ([Accès depuis l'extérieur](#accès-depuis-lextérieur))
- ✅ L'enregistrement des réglages depuis le dashboard est protégé par **mot de passe** (empreinte PBKDF2 dans `config.json`). Par défaut, la consultation reste ouverte au réseau local. Pour ntfy, activez son authentification si besoin ([jeton](#protéger-ntfy-par-un-jeton-facultatif)).
- ✅ Après **5 mots de passe incorrects en 15 minutes**, l'adresse IP concernée est bloquée jusqu'à la fin de ce délai.
- ✅ La page applique une politique de sécurité stricte (CSP : aucun script extérieur ni en ligne, pas d'affichage dans un cadre) et les réglages ne peuvent pas être envoyés depuis un autre site.
- ✅ Restreindre l'accès au **LAN** via pare-feu
- ✅ Le dashboard tourne sous un compte dédié **sans droits**, dans un service systemd durci : il ne peut ni lire l'adresse ntfy et son jeton, ni modifier les scripts ; il n'écrit que les seuils, alertes et couleurs (voir [Dashboard sans root](#dashboard-sans-root))
- ✅ Choisir un **nom de topic ntfy long et aléatoire** (il fait office de mot de passe)
- ✅ Garder le système à jour (`sudo apt update && sudo apt upgrade`)

### Dashboard sans root

Le dashboard est le seul service accessible par le réseau : s'il présentait une faille, il ne faudrait pas qu'elle donne la main sur le NAS. Depuis la 1.3.0 :

- il tourne sous le compte système `ploufnas`, sans mot de passe ni shell, dans un service systemd durci (système en lecture seule, aucun privilège possible) ;
- il **lit** `config.json` (groupe `ploufnas`, droits `640`) pour vérifier le mot de passe, mais ne peut pas le modifier ;
- il ne peut **pas lire** `ntfy.json` : impossible pour un attaquant d'envoyer de fausses notifications sur votre téléphone ;
- il n'**écrit** que dans `reglages/`, et la surveillance n'y lit que les seuils, alertes et couleurs, toujours validés : un fichier falsifié ne peut rien faire d'autre que changer un seuil.

**Passer à la 1.3.0 depuis une version 0.5.0 ou plus récente** (en SSH sur le NAS) :

```bash
UUID=collez-ici-votre-uuid
MON=/srv/dev-disk-by-uuid-$UUID/monitoring
cd ~/PloufNAS && git pull
sudo cp nas/config.py nas/monitor_climat.py nas/dashboard.py "${MON:?}/" && sudo cp -r nas/static/. "${MON:?}/static/"

# Répartition automatique de config.json en trois fichiers (vos réglages sont conservés)
sudo systemctl restart monitor-climat
ls "${MON:?}/ntfy.json" "${MON:?}/reglages/reglages.json"
```

Puis suivez l'[étape 8](#étape-8--installation-des-services-systemd) : ACL d'OMV, création du compte et droits (8.1), copie du nouveau `dashboard-climat.service` avec remplacement de l'UUID (8.2), et enfin `sudo systemctl daemon-reload && sudo systemctl restart dashboard-climat`.

### Options du dashboard (section `dashboard` de `config.json`)

Elles se règlent uniquement dans le fichier (jamais depuis le navigateur), puis `sudo systemctl restart dashboard-climat`.

| Option | Rôle | Par défaut |
|---|---|---|
| `adresse` | Adresse d'écoute. `127.0.0.1` : accessible seulement depuis le NAS (derrière un reverse proxy installé sur le NAS) | `0.0.0.0` (tout le réseau) |
| `port` | Port d'écoute | `5000` |
| `consultation_protegee` | `true` : le mot de passe est demandé dès l'ouverture du dashboard (fenêtre du navigateur, nom d'utilisateur libre) | `false` |
| `derriere_proxy` | `true` : le dashboard est derrière un reverse proxy, dont il prend en compte les en-têtes `X-Forwarded-*` (adresse réelle du visiteur, pour le blocage des mots de passe faux) | `false` |

> ⚠️ Le mot de passe circule en clair en HTTP. Si le dashboard est accessible hors de votre réseau, il doit l'être **uniquement en HTTPS** (reverse proxy) ou **via un VPN**, avec `consultation_protegee` à `true`. Ne mettez `derriere_proxy` à `true` que si un proxy est réellement devant le dashboard : sinon un visiteur pourrait se faire passer pour une autre adresse et contourner le blocage.

Le dashboard utilise le serveur de production **waitress** s'il est installé (`sudo apt install python3-waitress`), sinon le serveur intégré de Flask, réservé à un usage en réseau local.

### Protéger ntfy par un jeton (facultatif)

Sans authentification, quiconque connaît le nom du topic peut lire vos alertes ou en envoyer de fausses. En réseau local, un topic long et aléatoire suffit. Si votre serveur ntfy est **accessible depuis Internet**, activez son authentification : PloufNAS envoie alors ses notifications avec un **jeton**, et le téléphone se connecte avec son propre compte.

**1. Activer l'authentification de ntfy.** Dans le fichier Compose de ntfy (**Services → Compose → Fichiers**), ajoutez deux variables et un volume pour la base des utilisateurs :

```yaml
    environment:
      - TZ=Europe/Paris
      - NTFY_AUTH_FILE=/var/lib/ntfy/user.db
      - NTFY_AUTH_DEFAULT_ACCESS=deny-all
    volumes:
      - CHANGE_TO_COMPOSE_DATA_PATH/ntfy/cache:/var/cache/ntfy
      - CHANGE_TO_COMPOSE_DATA_PATH/ntfy/config:/etc/ntfy
      - CHANGE_TO_COMPOSE_DATA_PATH/ntfy/lib:/var/lib/ntfy
```

Enregistrez, puis cliquez sur **Up** sur la ligne `ntfy` : le conteneur est recréé avec les nouveaux réglages (un simple redémarrage ne suffit pas). Vérifiez avec `sudo docker exec ntfy ntfy user list` : la ligne `no access to any (other) topics` confirme l'activation. À partir de là, plus personne ne peut lire ni écrire sans compte : les notifications sont suspendues jusqu'à l'étape 3.

**2. Créer les comptes et le jeton** (en SSH sur le NAS, remplacez `VOTRE-TOPIC`) :

```bash
# Compte utilisé par PloufNAS : il peut seulement publier.
# Son mot de passe, tiré au hasard, ne sert jamais (PloufNAS utilise le jeton).
sudo docker exec -e NTFY_PASSWORD="$(openssl rand -hex 16)" ntfy ntfy user add ploufnas
sudo docker exec ntfy ntfy access ploufnas VOTRE-TOPIC write-only
sudo docker exec ntfy ntfy token add ploufnas        # affiche un jeton tk_…

# Compte du téléphone : il peut seulement lire.
# Le mot de passe n'est écrit qu'une fois, dans P ; history -c l'efface de l'historique.
P='MotDePasseTelephone'; history -c
sudo docker exec -e NTFY_PASSWORD="$P" ntfy ntfy user add telephone
sudo docker exec ntfy ntfy access telephone VOTRE-TOPIC read-only
# Vérification : doit afficher les messages du topic, et non « unauthorized »
curl -s -u "telephone:$P" "http://localhost:8080/VOTRE-TOPIC/json?poll=1&since=1h"; unset P
```

> 💡 La variable `NTFY_PASSWORD` évite la saisie interactive de ntfy, qui échoue souvent quand la commande est collée (la touche Entrée en trop envoie un mot de passe vide). Pour changer un mot de passe plus tard : `ntfy user change-pass` au lieu de `ntfy user add`.

**3. Enregistrer le jeton dans PloufNAS**, puis vérifier :

```bash
cd /srv/dev-disk-by-uuid-$UUID/monitoring   # UUID : voir l'étape 5
sudo python3 config.py --jeton-ntfy      # collez le jeton tk_… affiché à l'étape 2
sudo systemctl restart monitor-climat    # envoie la notification de démarrage
journalctl -u monitor-climat -n 5 --no-pager
```

Le jeton est pris en compte sans redémarrage ; le redémarrage sert seulement à envoyer une notification de test. Il est conservé dans `ntfy.json` (lisible par `root` uniquement) et n'est jamais transmis au navigateur.

**4. Connecter le téléphone.** Dans l'application ntfy : **Paramètres → Gérer les utilisateurs → Ajouter**, indiquez l'adresse du serveur et le compte `telephone`. La notification de démarrage doit apparaître.

> ⚠️ L'adresse du serveur doit être **exactement** celle de l'abonnement au topic, au caractère près : `http://IP-DU-NAS:8080` et `http://IP-DU-NAS:8080/` sont deux serveurs différents pour l'application, qui affiche alors une erreur 401/403. L'adresse d'un compte ne se modifie pas : supprimez-le et ajoutez-le de nouveau.
>
> Si un jeton a été divulgué : `ntfy token add ploufnas`, `sudo python3 config.py --jeton-ntfy` avec le nouveau, puis `ntfy token remove ploufnas tk_ancien`. Attention : `ntfy token list` affiche les jetons **en entier** ; pour vérifier sans les montrer, comptez-les avec `sudo docker exec ntfy ntfy token list ploufnas | grep -c tk_`.

> ⚠️ Hors du réseau local, `ntfy_url` doit commencer par `https://` : en HTTP, le jeton circule en clair. PloufNAS le signale au démarrage dans `journalctl`.
>
> Pour revenir sans authentification : retirez les deux variables `NTFY_AUTH_*` du fichier Compose et mettez `"ntfy_jeton": ""` dans `ntfy.json`.

### Accès depuis l'extérieur

Par défaut, PloufNAS n'est accessible que sur votre réseau local, et c'est le plus sûr. Pour consulter le dashboard ou recevoir les alertes hors de chez vous, **n'ouvrez jamais** les ports 5000 (dashboard) ou 8080 (ntfy) sur votre box : passez par un **VPN** (recommandé) ou par un **reverse proxy HTTPS**.

| | VPN (Tailscale, WireGuard) | Reverse proxy HTTPS (Caddy) |
|---|---|---|
| Ce qui est visible sur Internet | rien | le dashboard et ntfy, protégés par mot de passe |
| Nom de domaine, ouverture de ports | non (Tailscale) | oui (domaine, ports 80 et 443) |
| Sur le téléphone | l'application VPN doit être active | rien de plus |
| Difficulté | faible | moyenne |

#### Option 1 — VPN avec Tailscale (recommandé)

Tailscale crée un réseau privé chiffré entre vos appareils, sans ouvrir de port sur la box.

```bash
# Sur le NAS
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up            # affiche un lien : ouvrez-le pour connecter le NAS à votre compte
tailscale ip -4              # adresse du NAS sur le réseau Tailscale (100.x.y.z)
```

Installez ensuite l'application **Tailscale** sur le téléphone, avec le même compte. Le dashboard est alors accessible partout à l'adresse `http://100.x.y.z:5000`.

> 💡 **ntfy** : dans l'application, abonnez-vous au topic sur le serveur `http://100.x.y.z:8080`, l'adresse Tailscale, plutôt que sur l'adresse locale. Elle fonctionne à la maison comme à l'extérieur, et vous évite deux abonnements. Si l'authentification ntfy est active, le compte `telephone` doit être déclaré pour cette même adresse.

Alternative sans compte extérieur : **WireGuard**, à installer sur le NAS (plugin `openmediavault-wireguard` d'omv-extras, s'il est disponible pour votre version d'OMV). Il faut alors ouvrir **un seul** port UDP sur la box, celui du VPN.

#### Option 2 — Reverse proxy HTTPS avec Caddy

À réserver aux cas où un VPN n'est pas possible. Il faut un nom de domaine (par exemple `nas.example.org` et `ntfy.example.org`) qui pointe vers votre adresse IP publique, et rediriger les ports **80 et 443** de la box vers le NAS. Caddy obtient et renouvelle seul les certificats HTTPS.

**1. Libérer les ports 80 et 443.** L'interface web d'OMV les utilise : changez son port dans **Système → Workbench** (par exemple 8000), puis reconnectez-vous sur `http://IP-DU-NAS:8000`.

**2. Réserver le dashboard et ntfy au proxy.** Dans `config.json`, section `dashboard` :

```json
"dashboard": {
    "adresse": "127.0.0.1",
    "port": 5000,
    "consultation_protegee": true,
    "derriere_proxy": true
}
```

puis `sudo systemctl restart dashboard-climat`. Dans le fichier Compose de ntfy, remplacez `"8080:80"` par `"127.0.0.1:8080:80"`, ajoutez `NTFY_BASE_URL=https://ntfy.example.org` et `NTFY_BEHIND_PROXY=true` aux variables d'environnement, **activez l'authentification** ([jeton](#protéger-ntfy-par-un-jeton-facultatif)), puis cliquez sur **Up**. `ntfy_url` (dans `ntfy.json`) peut rester sur `http://localhost:8080/…` : la surveillance publie depuis le NAS lui-même.

**3. Créer le conteneur Caddy** (Services → Compose → Fichiers) :

```yaml
services:
  caddy:
    image: caddy:2
    container_name: caddy
    network_mode: host          # pour joindre 127.0.0.1:5000 et 127.0.0.1:8080
    volumes:
      - CHANGE_TO_COMPOSE_DATA_PATH/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - CHANGE_TO_COMPOSE_DATA_PATH/caddy/data:/data
    restart: unless-stopped
```

avec ce fichier `Caddyfile` :

```
nas.example.org {
    reverse_proxy 127.0.0.1:5000
}
ntfy.example.org {
    reverse_proxy 127.0.0.1:8080
}
```

**4. Vérifier depuis l'extérieur** (téléphone en 4G, Wi-Fi coupé) : `https://nas.example.org` doit demander le mot de passe, et `http://VOTRE-IP-PUBLIQUE:5000` ne doit **pas** répondre. Dans l'application ntfy, abonnez-vous sur `https://ntfy.example.org` avec le compte `telephone`.

> ⚠️ Avec un reverse proxy, le dashboard est visible de tout Internet : choisissez un mot de passe long, gardez le système à jour, et n'exposez **jamais** l'interface d'OMV de la même façon. Après 5 mots de passe faux, une adresse est bloquée 15 minutes ; cela ne remplace pas un VPN.

---

## 📄 Format du fichier CSV

```csv
Date et Heure,Temperature_C,Humidite_Pct
2026-09-17 19:15:00,22.4,47.2
2026-09-17 19:16:00,22.5,47.0
```

---

## 📜 Licence

Ce projet est placé sous licence **GNU General Public License v3.0** — voir le fichier [`LICENSE`](./LICENSE).

### 💡 Pourquoi ce projet est-il sous licence libre ?

Ce projet s'inscrit dans la philosophie du logiciel libre, promue par des associations comme [April](https://www.april.org/).

Le partage des connaissances et des outils est essentiel pour une société numérique plus juste et transparente.

---

## 🤝 Contribution

Les PR sont bienvenues ! Ouvrez d'abord une *issue* pour discuter de votre idée avant de coder.

---

## 🙏 Remerciements

- [Rob Tillaart](https://github.com/RobTillaart/SHT31) pour la bibliothèque `SHT31`
- [Frank de Brabander](https://github.com/johnrickman/LiquidCrystal_I2C) pour `LiquidCrystal I2C`
- [binwiederhier](https://github.com/binwiederhier/ntfy) pour **ntfy**
- La communauté OpenMediaVault pour la documentation
