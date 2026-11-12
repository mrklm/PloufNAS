import logging
import sys
import time
from datetime import datetime

import requests
import serial

# ============================================================
# CONFIGURATION — À PERSONNALISER
# ============================================================
port_serie  = '/dev/arduino_nas'
fichier_log = '/srv/dev-disk-by-uuid-VOTRE_UUID/monitoring/climat.csv'

# Seuils d'alerte
TEMP_MAX = 30.0    # °C
HUM_MAX  = 80.0    # %

# Hystérésis : retour à la normale seulement sous (seuil - hystérésis).
# Évite les rafales de notifications quand la valeur oscille autour du seuil.
TEMP_HYSTERESIS = 1.0   # °C
HUM_HYSTERESIS  = 2.0   # %

# ntfy (instance locale)
NTFY_URL = "http://localhost:8080/VOTRE-TOPIC"

# Alerte "pas de données" : délai sans réception avant alerte
DELAI_SANS_DONNEES = 15 * 60   # 15 minutes

# Fréquences
INTERVALLE_LECTURE  = 5        # secondes entre deux lectures du port série
INTERVALLE_ECRITURE = 60       # secondes entre deux écritures dans le CSV
DELAI_RECONNEXION   = 10       # secondes entre deux tentatives d'ouverture du port

# Plages physiquement plausibles (capteur SHT31) : au-delà, la ligne est rejetée
TEMP_PLAGE = (-40.0, 125.0)
HUM_PLAGE  = (0.0, 100.0)

ENTETE_CSV = "Date et Heure,Temperature_C,Humidite_Pct\n"

log = logging.getLogger("monitor_climat")


# ============================================================
# NOTIFICATIONS
# ============================================================
def envoyer_ntfy(titre, message, priorite="default", tags="warning"):
    """Envoie une notification via ntfy. Retourne True si elle a été acceptée.

    IMPORTANT : les emojis ne doivent JAMAIS être dans le titre (header HTTP),
    car requests encode les headers en latin-1 par défaut.
    Les emojis sont OK dans le corps du message (encodé en UTF-8).
    """
    try:
        reponse = requests.post(
            NTFY_URL,
            data=message.encode('utf-8'),
            headers={
                "Title": titre,
                "Priority": priorite,
                "Tags": tags
            },
            timeout=5
        )
    except requests.RequestException as e:
        log.warning("Erreur envoi ntfy : %s", e)
        return False
    if not reponse.ok:
        log.warning("ntfy a refusé la notification (HTTP %s)", reponse.status_code)
        return False
    return True


# ============================================================
# LECTURE SÉRIE
# ============================================================
def analyser_ligne(brut):
    """Analyse une ligne brute (bytes) reçue de l'Arduino.

    Retourne :
      - (temp, hum) pour une ligne DATA complète et plausible ;
      - "ERR" si l'Arduino signale une erreur capteur ;
      - None sinon (ligne tronquée, illisible, hors plage, message d'info).
    """
    # Une ligne sans fin de ligne a été coupée par le timeout de readline() :
    # "DATA,22.4,4" serait sinon lu comme 4 % d'humidité.
    if not brut.endswith(b"\n"):
        return None
    try:
        ligne = brut.decode('utf-8').strip()
    except UnicodeDecodeError:
        return None

    if ligne.startswith("ERR"):
        return "ERR"
    if not ligne.startswith("DATA,"):
        return None

    try:
        _, temp, hum = ligne.split(",")
        temp, hum = float(temp), float(hum)
    except ValueError:
        return None

    # float() accepte "nan" et "inf" : les comparaisons ci-dessous les rejettent.
    if not (TEMP_PLAGE[0] <= temp <= TEMP_PLAGE[1]):
        return None
    if not (HUM_PLAGE[0] <= hum <= HUM_PLAGE[1]):
        return None
    return temp, hum


def lire_derniere_valeur(ser):
    """Vide le buffer série et retourne le résultat le plus récent.

    On lit tout ce qui est disponible et on garde la dernière ligne exploitable
    (mesure ou erreur), pour ne pas traiter une valeur ancienne restée en buffer.
    Lève serial.SerialException / OSError si le port a disparu.
    """
    resultat = None
    while ser.in_waiting > 0:
        analyse = analyser_ligne(ser.readline())
        if analyse is not None:
            resultat = analyse
    return resultat


# ============================================================
# SURVEILLANCE (états et transitions)
# ============================================================
class Surveillance:
    """Mémorise les états et n'envoie une notification qu'aux transitions.

    Un état ne change que si la notification correspondante a bien été envoyée :
    en cas d'échec (ntfy indisponible), la transition est retentée au cycle suivant.
    """

    def __init__(self, notifier=envoyer_ntfy, horloge=time.monotonic):
        self.notifier = notifier
        self.horloge = horloge
        self.etat_temp = "normal"
        self.etat_hum = "normal"
        self.etat_donnees = "normal"
        self.etat_ecriture = "normal"
        # Le délai de silence court dès le démarrage : un capteur muet dès le
        # départ déclenche donc lui aussi l'alerte.
        self.derniere_reception = horloge()
        self.derniere_erreur_capteur = False

    @staticmethod
    def _nouvel_etat(valeur, seuil, hysteresis, etat_actuel):
        if valeur > seuil:
            return "alerte"
        if valeur <= seuil - hysteresis:
            return "normal"
        return etat_actuel   # zone d'hystérésis : on ne change rien

    def enregistrer_mesure(self, temp, hum):
        self.derniere_reception = self.horloge()
        self.derniere_erreur_capteur = False
        self.verifier_seuils(temp, hum)

    def enregistrer_erreur_capteur(self):
        # Ne remet pas à zéro le délai de silence : une erreur n'est pas une mesure.
        self.derniere_erreur_capteur = True

    def verifier_seuils(self, temp, hum):
        etat = self._nouvel_etat(temp, TEMP_MAX, TEMP_HYSTERESIS, self.etat_temp)
        if etat != self.etat_temp:
            if etat == "alerte":
                envoye = self.notifier(
                    "[ALERTE] Temperature NAS",
                    f"🌡️ Température élevée : {temp}°C (seuil {TEMP_MAX}°C)",
                    priorite="urgent",
                    tags="warning,thermometer"
                )
            else:
                envoye = self.notifier(
                    "[OK] Temperature NAS revenue a la normale",
                    f"🌡️ Température : {temp}°C",
                    priorite="default",
                    tags="white_check_mark"
                )
            if envoye:
                self.etat_temp = etat

        etat = self._nouvel_etat(hum, HUM_MAX, HUM_HYSTERESIS, self.etat_hum)
        if etat != self.etat_hum:
            if etat == "alerte":
                envoye = self.notifier(
                    "[ALERTE] Humidite NAS",
                    f"💧 Humidité élevée : {hum}% (seuil {HUM_MAX}%)",
                    priorite="urgent",
                    tags="warning,droplet"
                )
            else:
                envoye = self.notifier(
                    "[OK] Humidite NAS revenue a la normale",
                    f"💧 Humidité : {hum}%",
                    priorite="default",
                    tags="white_check_mark"
                )
            if envoye:
                self.etat_hum = etat

    def verifier_silence(self):
        ecart = self.horloge() - self.derniere_reception

        if ecart > DELAI_SANS_DONNEES and self.etat_donnees == "normal":
            cause = ("L'Arduino signale une erreur de lecture du capteur SHT31."
                     if self.derniere_erreur_capteur
                     else "Vérifier l'Arduino, le câble USB et le service.")
            if self.notifier(
                "[URGENT] Plus de donnees du capteur",
                f"🚨 Aucune donnée valide reçue depuis {int(ecart / 60)} minutes.\n{cause}",
                priorite="urgent",
                tags="rotating_light,electric_plug"
            ):
                self.etat_donnees = "alerte"

        elif ecart <= DELAI_SANS_DONNEES and self.etat_donnees == "alerte":
            if self.notifier(
                "[OK] Capteur de nouveau operationnel",
                "✅ Les données sont de nouveau reçues.",
                priorite="default",
                tags="white_check_mark"
            ):
                self.etat_donnees = "normal"

    def signaler_ecriture(self, succes, erreur=None):
        """Alerte une seule fois si l'écriture du CSV échoue (volume non monté...)."""
        if not succes and self.etat_ecriture == "normal":
            if self.notifier(
                "[URGENT] Ecriture CSV impossible",
                f"🚨 Impossible d'écrire dans {fichier_log} : {erreur}\n"
                "Les alertes restent actives, mais l'historique n'est plus enregistré.",
                priorite="high",
                tags="rotating_light,floppy_disk"
            ):
                self.etat_ecriture = "alerte"
        elif succes and self.etat_ecriture == "alerte":
            if self.notifier(
                "[OK] Ecriture CSV retablie",
                "✅ L'historique est de nouveau enregistré.",
                priorite="default",
                tags="white_check_mark"
            ):
                self.etat_ecriture = "normal"


# ============================================================
# CSV
# ============================================================
def ecrire_csv(horodatage, temp, hum):
    """Ajoute une ligne au CSV (crée l'en-tête si besoin). Lève OSError en cas d'échec."""
    with open(fichier_log, "a") as f:
        if f.tell() == 0:
            f.write(ENTETE_CSV)
        f.write(f"{horodatage},{temp},{hum}\n")


# ============================================================
# BOUCLE PRINCIPALE
# ============================================================
def ouvrir_port(journaliser_echec=True):
    """Ouvre le port série, ou retourne None s'il est indisponible."""
    try:
        ser = serial.Serial(port_serie, 9600, timeout=1)
    except (serial.SerialException, OSError) as e:
        if journaliser_echec:
            log.warning("Port série %s indisponible : %s (nouvelles tentatives "
                        "toutes les %s s)", port_serie, e, DELAI_RECONNEXION)
        return None
    log.info("Port série %s ouvert.", port_serie)
    return ser


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    # Le flux est vidé à chaque ligne, pour que journalctl affiche les logs en direct.
    sys.stdout.reconfigure(line_buffering=True)

    surveillance = Surveillance()
    envoyer_ntfy(
        "[OK] Monitoring climatique demarre",
        "🟢 Le service de surveillance est actif.",
        priorite="low",
        tags="white_check_mark"
    )
    log.info("Surveillance active (Temp + Hum).")

    ser = None
    prochaine_connexion = 0.0
    echec_connexion_signale = False
    derniere_ecriture = None

    while True:
        # (Re)connexion au port série sans faire planter le service :
        # l'absence de données est signalée par l'alerte de silence.
        if ser is None and time.monotonic() >= prochaine_connexion:
            ser = ouvrir_port(journaliser_echec=not echec_connexion_signale)
            if ser is None:
                echec_connexion_signale = True
                prochaine_connexion = time.monotonic() + DELAI_RECONNEXION
            else:
                echec_connexion_signale = False

        if ser is not None:
            try:
                resultat = lire_derniere_valeur(ser)
            except (serial.SerialException, OSError) as e:
                log.warning("Port série perdu : %s", e)
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                prochaine_connexion = time.monotonic() + DELAI_RECONNEXION
                resultat = None

            if resultat == "ERR":
                log.warning("L'Arduino signale une erreur de lecture du capteur.")
                surveillance.enregistrer_erreur_capteur()
            elif resultat is not None:
                temp, hum = resultat
                # Vérifier les seuils à CHAQUE lecture (pour ne pas rater un pic)
                surveillance.enregistrer_mesure(temp, hum)

                # Écrire dans le CSV seulement toutes les INTERVALLE_ECRITURE secondes
                if (derniere_ecriture is None
                        or time.monotonic() - derniere_ecriture >= INTERVALLE_ECRITURE):
                    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        ecrire_csv(horodatage, temp, hum)
                        surveillance.signaler_ecriture(True)
                    except OSError as e:
                        log.error("Écriture CSV impossible : %s", e)
                        surveillance.signaler_ecriture(False, e)
                    derniere_ecriture = time.monotonic()

                    if temp > TEMP_MAX or hum > HUM_MAX:
                        log.warning("ALERTE : Temp %s°C | Hum %s%%", temp, hum)
                    else:
                        log.info("Temp : %s°C | Hum : %s%%", temp, hum)

        surveillance.verifier_silence()
        time.sleep(INTERVALLE_LECTURE)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Arrêt du script.")
    except Exception as e:
        log.exception("Erreur inattendue")
        envoyer_ntfy(
            "[URGENT] Erreur du script monitoring",
            f"🚨 Le script s'est arrêté : {e}",
            priorite="urgent",
            tags="rotating_light"
        )
        raise
