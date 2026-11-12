# 💧 PloufNAS

> [!WARNING]
> 🚧 **PROJET EN DÉVELOPPEMENT — VERSION EXPÉRIMENTALE**
>
> **Cette version ne doit pas être utilisée comme seul moyen de surveillance d’un NAS.** Les défauts identifiés sur les alertes et la procédure d’installation ont été corrigés en v0.4.0, mais ces corrections n’ont pas encore été validées sur matériel.
>
> Le mode avancé affiche actuellement des **données de démonstration pour le CPU et les disques**. Ses réglages d’alertes matérielles ne sont pas encore opérationnels.
>
> Les corrections et les essais sur matériel sont prévus avant de considérer cette version comme fiable.

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
- **Dashboard Web** : Interface légère en Flask + Chart.js, accessible sur tout le réseau local.
- **Thèmes personnalisés** : 16 thèmes intégrés (Sombres, Clairs, et "Pouêt-Pouêt") avec sélection aléatoire au chargement.
- **Alertes push** : Notifications en temps réel via **ntfy** (auto-hébergé) si les seuils de température ou d'humidité sont dépassés.
- **Alerte "pas de données"** : Notification si aucune donnée n'est reçue depuis plus de 15 minutes (détection d'un capteur débranché ou d'un service planté).
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
2. Téléversez le code situé dans `arduino/sht31_nas_monitor.ino`.
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

**2. Copiez les scripts et les images au bon endroit :**

```bash
MON=/srv/dev-disk-by-uuid-$UUID/monitoring

# Créer le dossier monitoring (et le sous-dossier des images) sur le volume
sudo mkdir -p $MON/assets

# Copier les scripts depuis le repo cloné
sudo cp ~/PloufNAS/nas/monitor_climat.py \
        ~/PloufNAS/nas/setup_dashboard.py \
        $MON/

# Copier les images du dashboard (sinon elles n'apparaissent pas)
sudo cp ~/PloufNAS/assets/NAS.png ~/PloufNAS/assets/CPU.png \
        ~/PloufNAS/assets/GPU.png ~/PloufNAS/assets/DD.png \
        $MON/assets/

# Renseigner automatiquement le chemin du CSV dans monitor_climat.py
sudo sed -i "s/VOTRE_UUID/$UUID/" $MON/monitor_climat.py

# Générer dashboard.py
cd $MON
sudo python3 setup_dashboard.py

# Vérifier
ls -la $MON $MON/assets
```

**3. Personnalisez `monitor_climat.py` :**

Éditez le fichier (`sudo nano $MON/monitor_climat.py`) et vérifiez la section **CONFIGURATION** en haut. Le chemin du CSV a déjà été renseigné ; il reste au minimum à remplacer `VOTRE-TOPIC` :

```python
port_serie  = '/dev/arduino_nas'
fichier_log = '/srv/dev-disk-by-uuid-VOTRE_UUID/monitoring/climat.csv'

TEMP_MAX = 30.0    # °C
HUM_MAX  = 80.0    # %

NTFY_URL = "http://localhost:8080/VOTRE-TOPIC"
```

---

### Étape 6 : Installation des dépendances Python

En SSH sur le NAS :

```bash
sudo apt update
sudo apt install -y python3 python3-serial python3-flask python3-requests curl
```

> 💡 N'utilisez pas `sudo pip3 install` : sur OMV 7 (Debian 12), pip refuse d'installer des paquets dans le Python système (erreur `externally-managed-environment`). Les paquets `python3-*` de Debian font la même chose proprement et sont mis à jour avec le système.

> ⚠️ Les services fournis dans `nas/*.service` utilisent `User=root` et `/usr/bin/python3` (Python système, pas de venv). C'est fonctionnel mais peu élégant côté sécurité. Pour un usage domestique sur réseau local, ça reste acceptable.

---

### Étape 7 : Test manuel avant systemd

**Testez toujours à la main avant d'activer les services** — sinon vous déboguez à l'aveugle.

```bash
cd /srv/dev-disk-by-uuid-VOTRE_UUID/monitoring/

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

Les fichiers sont fournis dans `nas/`. Il faut les copier dans `/etc/systemd/system/` puis y remplacer `VOTRE_UUID` (variable `UUID` définie à l'étape 5) :

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

**Optionnel** — accès depuis l'extérieur : passez **obligatoirement** par un reverse-proxy (nginx d'OMV) avec HTTPS et une authentification. ⚠️ **N'exposez jamais Flask directement sur Internet.**

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

---

## 🔔 Personnalisation des alertes

Tous les paramètres sont regroupés en haut de `monitor_climat.py` :

| Paramètre | Description | Valeur par défaut |
|---|---|---|
| `TEMP_MAX` | Seuil de température (°C) | `30.0` |
| `HUM_MAX` | Seuil d'humidité (%) | `80.0` |
| `NTFY_URL` | URL ntfy + topic | `http://localhost:8080/VOTRE-TOPIC` |
| `DELAI_SANS_DONNEES` | Délai avant alerte "pas de données" | `15 * 60` (15 min) |
| `INTERVALLE_LECTURE` | Fréquence de lecture du port série | `5` (secondes) |
| `INTERVALLE_ECRITURE` | Fréquence d'écriture dans le CSV | `60` (secondes) |
| `TEMP_HYSTERESIS` | Écart sous le seuil avant le retour à la normale (température) | `1.0` (°C) |
| `HUM_HYSTERESIS` | Écart sous le seuil avant le retour à la normale (humidité) | `2.0` (%) |
| `DELAI_RECONNEXION` | Délai entre deux tentatives d'ouverture du port série | `10` (secondes) |

**Logique anti-spam** : le script n'envoie une notification **qu'aux transitions** :
- Normal → Alerte : 1 notification
- Alerte → Normal : 1 notification (retour à la normale)
- Alerte → Alerte : aucune notification (pas de spam)
- Le retour à la normale n'a lieu que sous `seuil - hystérésis` (ex. 78 % pour un seuil à 80 %), pour éviter les rafales quand la valeur oscille autour du seuil.
- Si l'envoi d'une notification échoue (ntfy indisponible), l'état n'est pas modifié : la notification est retentée au cycle suivant.

**Robustesse** :
- L'alerte « pas de données » est active dès le démarrage : un capteur muet dès le départ est aussi signalé.
- Un Arduino débranché ne fait plus planter le service : le port est rouvert automatiquement, et l'absence de données déclenche l'alerte au bout de `DELAI_SANS_DONNEES`.
- Les lignes série tronquées ou les valeurs hors plage sont ignorées.
- L'Arduino envoie `ERR,...` quand la lecture du SHT31 échoue. Ces lignes ne comptent pas comme des mesures.
- Si le CSV ne peut pas être écrit (volume non monté...), une notification unique est envoyée et les alertes restent actives.

**Tests** (depuis la racine du dépôt, sans matériel) :

```bash
python3 -m unittest discover -s tests
```

---

## 🔧 Dépannage

| Symptôme | Piste à explorer |
|---|---|
| Port série absent | Vérifiez `/dev/ttyUSB*` / `/dev/ttyACM*`, `lsusb`, `dmesg \| tail` |
| Données illisibles | Baudrate 9600 ? Droits série (`dialout`) ? |
| CSV vide | `journalctl -u monitor-climat -n 50` |
| `dashboard.py` introuvable | Relancez `sudo python3 setup_dashboard.py` |
| Dashboard inaccessible | Bonne IP ? Pare-feu OMV ? Port 5000 ouvert ? |
| Thème ne change pas | Videz le cache navigateur (Ctrl+F5) |
| Service ne démarre pas | `journalctl -u <monitor-climat\|dashboard-climat> -xe` |
| Erreur "UUID not found" | Vérifiez que `VOTRE_UUID` a bien été remplacé |
| Service bloqué au démarrage (`Dependency failed`) | Le volume n'est pas monté ou l'UUID est faux : `grep RequiresMountsFor /etc/systemd/system/*-climat.service` puis `ls /srv/` |
| Erreur `externally-managed-environment` | N'utilisez pas `pip3` : installez les paquets `python3-*` avec `apt` (étape 6) |
| Images absentes du dashboard | Copiez les images dans `monitoring/assets/` (étape 5) |
| **Erreur `latin-1 codec can't encode`** | Un emoji est présent dans un **titre** de notification. Les titres ne doivent contenir que de l'ASCII — les emojis sont OK dans le **corps** du message. |
| Notification ntfy non reçue | Vérifiez que le conteneur tourne : `docker ps \| grep ntfy` |
| ntfy inaccessible | Testez `curl http://localhost:8080/v1/health` sur le NAS |
| Alerte humidité non déclenchée | Le script lit le buffer série en entier (corrigé). Si le problème persiste, vérifiez le code Arduino. |

---

## 🔐 Sécurité

- ❌ Ne **jamais** exposer Flask ou ntfy directement sur Internet
- ✅ Ajouter une **authentification** (`flask-httpauth` pour le dashboard, ou auth ntfy)
- ✅ Restreindre l'accès au **LAN** via pare-feu
- ✅ Les services tournent en `root` — acceptable en LAN, à durcir (user dédié) si exposé
- ✅ Choisir un **nom de topic ntfy long et aléatoire** (il fait office de mot de passe)
- ✅ Garder le système à jour (`sudo apt update && sudo apt upgrade`)

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
