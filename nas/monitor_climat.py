import logging
import os
import sys
import time
from datetime import datetime

import requests
import serial

import config
import systeme

# ============================================================
# CONFIGURATION
# ============================================================
# Port série, fichier CSV, URL ntfy et seuils se règlent dans config.json
# (voir config.py). Les valeurs ci-dessous sont remplacées au démarrage, puis à
# chaque modification de config.json (par exemple depuis le dashboard).
port_serie      = config.DEFAUTS["port_serie"]
fichier_log     = config.chemin_csv(config.DEFAUTS)
NTFY_URL        = config.DEFAUTS["ntfy_url"]
TEMP_MAX        = config.DEFAUTS["seuils"]["temp_max"]          # °C
HUM_MAX         = config.DEFAUTS["seuils"]["hum_max"]           # %
# Hystérésis : retour à la normale seulement sous (seuil - hystérésis).
# Évite les rafales de notifications quand la valeur oscille autour du seuil.
TEMP_HYSTERESIS = config.DEFAUTS["seuils"]["temp_hysteresis"]   # °C
HUM_HYSTERESIS  = config.DEFAUTS["seuils"]["hum_hysteresis"]    # %

ALERTES_SYSTEME = config.DEFAUTS["alertes_systeme"]   # CPU, disques, SMART

# Réglages avancés (modifiables ici uniquement)
# Alerte "pas de données" : délai sans réception avant alerte
DELAI_SANS_DONNEES = 15 * 60   # 15 minutes

# Fréquences
INTERVALLE_LECTURE  = 5        # secondes entre deux lectures du port série
INTERVALLE_ECRITURE = 60       # secondes entre deux écritures dans le CSV
INTERVALLE_SYSTEME  = 60       # secondes entre deux relevés matériels (disques : toutes les 5 min)
HYSTERESIS_CPU      = 3.0      # °C sous le seuil avant le retour à la normale
HYSTERESIS_DISQUE   = 2.0      # °C
ECHECS_DISQUE_MUET  = 2        # relevés SMART ratés de suite avant l'alerte « ne répond plus »
DELAI_RECONNEXION   = 10       # secondes entre deux tentatives d'ouverture du port

# Plages physiquement plausibles (capteur SHT31) : au-delà, la ligne est rejetée
TEMP_PLAGE = (-40.0, 125.0)
HUM_PLAGE  = (0.0, 100.0)

ENTETE_CSV = "Date et Heure,Temperature_C,Humidite_Pct\n"

log = logging.getLogger("monitor_climat")


# ============================================================
# CONFIG (chargement et rechargement à chaud)
# ============================================================
def appliquer_config(cfg):
    """Reporte une config validée dans les variables utilisées par le script."""
    global port_serie, fichier_log, NTFY_URL
    global TEMP_MAX, HUM_MAX, TEMP_HYSTERESIS, HUM_HYSTERESIS, ALERTES_SYSTEME
    port_serie = cfg["port_serie"]
    fichier_log = config.chemin_csv(cfg)
    NTFY_URL = cfg["ntfy_url"]
    seuils = cfg["seuils"]
    TEMP_MAX = seuils["temp_max"]
    HUM_MAX = seuils["hum_max"]
    TEMP_HYSTERESIS = seuils["temp_hysteresis"]
    HUM_HYSTERESIS = seuils["hum_hysteresis"]
    ALERTES_SYSTEME = cfg["alertes_systeme"]


class SuiviConfig:
    """Recharge config.json quand il a été modifié. Une config invalide est ignorée."""

    def __init__(self, chemin=None):
        self.chemin = chemin or config.CHEMIN_CONFIG
        self.signature = None

    def _signature(self):
        try:
            st = os.stat(self.chemin)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def charger_initial(self):
        cfg = config.charger(self.chemin)      # lève ConfigInvalide
        self.signature = self._signature()
        appliquer_config(cfg)
        return cfg

    def recharger_si_modifiee(self):
        """Retourne True si une nouvelle config a été appliquée."""
        signature = self._signature()
        if signature is None or signature == self.signature:
            return False
        self.signature = signature
        try:
            cfg = config.charger(self.chemin, creer=False)
        except ConfigInvalide as e:
            log.error("config.json invalide, l'ancienne configuration reste active : %s", e)
            return False
        appliquer_config(cfg)
        log.info("Configuration rechargée : seuils %s°C / %s%%, hystérésis %s°C / %s%%.",
                 TEMP_MAX, HUM_MAX, TEMP_HYSTERESIS, HUM_HYSTERESIS)
        return True


ConfigInvalide = config.ConfigInvalide


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
# ALERTES SYSTÈME (CPU, disques, SMART)
# ============================================================
def nom_disque(d):
    """Désignation lisible et stable : le nom /dev peut changer, le n° de série non."""
    details = ", ".join(x for x in (d.get("modele"), d.get("serie") and f"n° {d['serie']}") if x)
    return f"{d.get('nom')} ({details})" if details else str(d.get("nom"))


class AlertesSysteme:
    """Mêmes règles que Surveillance : notification aux transitions uniquement, et état
    modifié seulement si la notification est partie (sinon retentée au relevé suivant)."""

    def __init__(self, notifier=envoyer_ntfy):
        self.notifier = notifier
        self.etats = {}     # clé -> "alerte" (absente = normal)

    def _transition(self, cle, alerte, titre_alerte, message_alerte, titre_ok, message_ok):
        en_alerte = self.etats.get(cle) == "alerte"
        if alerte and not en_alerte:
            if self.notifier(titre_alerte, message_alerte, priorite="urgent",
                             tags="warning,rotating_light"):
                self.etats[cle] = "alerte"
        elif alerte is False and en_alerte:
            if self.notifier(titre_ok, message_ok, priorite="default", tags="white_check_mark"):
                del self.etats[cle]

    @staticmethod
    def _niveau(valeur, seuil, hysteresis, en_alerte):
        """True : alerte ; False : normal ; None : zone d'hystérésis (pas de changement)."""
        if valeur > seuil:
            return True
        if valeur <= seuil - hysteresis:
            return False
        return None if en_alerte else False

    def _desactiver(self, prefixe):
        # Alerte décochée dans le dashboard : on oublie l'état sans notifier
        for cle in [k for k in self.etats if k.startswith(prefixe)]:
            del self.etats[cle]

    def _verifier_presence(self, ident, nom, d):
        cle = f"absent:{ident}"
        etat = d.get("etat")
        if etat == "absent":
            alerte = True
            message = (f"💽 Le disque {nom} n'apparaît plus dans la liste des disques "
                       "(débranché ou défaillant).\nVérifiez l'état du RAID et vos sauvegardes.")
        elif etat == "indisponible":
            # Un seul relevé raté ne suffit pas : on attend qu'il se répète
            alerte = True if d.get("echecs", 0) >= ECHECS_DISQUE_MUET else None
            detail = f" ({d['message']})" if d.get("message") else ""
            message = (f"💽 Le disque {nom} ne répond plus aux requêtes SMART{detail}.\n"
                       "Vérifiez l'état du RAID et vos sauvegardes.")
        else:
            alerte, message = False, ""
        if alerte is None:
            return
        self._transition(
            cle, alerte,
            "[URGENT] Disque disparu ou muet", message,
            "[OK] Disque de nouveau detecte",
            f"💽 Le disque {nom} répond de nouveau.")

    def verifier(self, releve, reglages):
        cpu = releve.get("cpu") or {}
        r_cpu = reglages.get("cpu", {})
        if not r_cpu.get("enabled"):
            self._desactiver("cpu")
        elif cpu.get("temp") is not None:
            seuil = r_cpu["threshold"]
            niveau = self._niveau(cpu["temp"], seuil, HYSTERESIS_CPU,
                                  self.etats.get("cpu") == "alerte")
            self._transition(
                "cpu", niveau,
                "[ALERTE] Temperature CPU NAS",
                f"🔥 Processeur à {cpu['temp']} °C (seuil {seuil} °C).",
                "[OK] Temperature CPU revenue a la normale",
                f"🔥 Processeur à {cpu['temp']} °C.")

        r_temp = reglages.get("disks", {})
        r_smart = reglages.get("smart", {})
        r_absent = reglages.get("absent", {})
        if not r_absent.get("enabled"):
            self._desactiver("absent:")
        if not r_temp.get("enabled"):
            self._desactiver("temp:")
        if not r_smart.get("enabled"):
            self._desactiver("smart:")

        for d in releve.get("disques") or []:
            ident = d.get("serie") or d.get("nom")
            nom = nom_disque(d)

            if r_absent.get("enabled"):
                self._verifier_presence(ident, nom, d)

            if d.get("etat") != "actif":
                continue        # en veille, illisible ou absent : état température/SMART inchangé

            if r_temp.get("enabled") and d.get("temp") is not None:
                cle, seuil = f"temp:{ident}", r_temp["threshold"]
                niveau = self._niveau(d["temp"], seuil, HYSTERESIS_DISQUE,
                                      self.etats.get(cle) == "alerte")
                self._transition(
                    cle, niveau,
                    "[ALERTE] Temperature disque NAS",
                    f"🌡️ Disque {nom} à {d['temp']} °C (seuil {seuil} °C).",
                    "[OK] Temperature disque revenue a la normale",
                    f"🌡️ Disque {nom} à {d['temp']} °C.")

            if r_smart.get("enabled") and d.get("smart_ok") is not None:
                self._transition(
                    f"smart:{ident}", not d["smart_ok"],
                    "[URGENT] Etat SMART degrade",
                    f"💽 Disque {nom} : {', '.join(d.get('problemes') or [])}.\n"
                    "Vérifiez le disque et vos sauvegardes.",
                    "[OK] Etat SMART redevenu normal",
                    f"💽 Disque {nom} : plus d'anomalie SMART.")


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


def notifier_demarrage():
    return envoyer_ntfy(
        "[OK] Monitoring climatique demarre",
        "🟢 Le service de surveillance est actif.",
        priorite="low",
        tags="white_check_mark"
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    # Le flux est vidé à chaque ligne, pour que journalctl affiche les logs en direct.
    sys.stdout.reconfigure(line_buffering=True)

    suivi = SuiviConfig()
    try:
        suivi.charger_initial()
    except ConfigInvalide as e:
        log.critical("Configuration invalide, arrêt : %s", e)
        sys.exit(1)
    if NTFY_URL == config.NTFY_NON_CONFIGURE:
        log.warning("ntfy_url n'est pas configurée dans %s : aucune notification ne "
                    "sera reçue.", suivi.chemin)

    surveillance = Surveillance()
    chemin_systeme = os.path.join(os.path.dirname(suivi.chemin), "systeme.json")
    # Le dernier relevé permet de repérer un disque qui n'a pas redémarré avec le NAS
    collecteur = systeme.Collecteur(precedent=systeme.lire(chemin_systeme))
    alertes_systeme = AlertesSysteme()
    prochain_releve = time.monotonic() + INTERVALLE_SYSTEME / 2   # laisse démarrer le série
    # Retentée à chaque cycle tant qu'elle n'est pas passée : au démarrage du NAS,
    # le conteneur ntfy peut être prêt après ce service.
    demarrage_notifie = notifier_demarrage()
    log.info("Surveillance active (Temp + Hum).")

    ser = None
    prochaine_connexion = 0.0
    echec_connexion_signale = False
    derniere_ecriture = None

    while True:
        ancien_port = port_serie
        if suivi.recharger_si_modifiee() and port_serie != ancien_port and ser is not None:
            log.info("Port série modifié : reconnexion sur %s.", port_serie)
            ser.close()
            ser = None
            prochaine_connexion = 0.0

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

        if time.monotonic() >= prochain_releve:
            prochain_releve = time.monotonic() + INTERVALLE_SYSTEME
            try:
                releve = collecteur.releve()
                systeme.ecrire(releve, chemin_systeme)
                alertes_systeme.verifier(releve, ALERTES_SYSTEME)
            except Exception:
                # Un souci de relevé matériel ne doit jamais arrêter la surveillance climat
                log.exception("Relevé matériel impossible")

        if not demarrage_notifie:
            demarrage_notifie = notifier_demarrage()
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
