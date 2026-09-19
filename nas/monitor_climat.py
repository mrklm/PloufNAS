import serial
import time
import requests
from datetime import datetime

# ============================================================
# CONFIGURATION — À PERSONNALISER
# ============================================================
port_serie  = '/dev/arduino_nas'
fichier_log = '/srv/dev-disk-by-uuid-4a6d87ff-3fee-405f-a4ef-313d1775bb47/monitoring/climat.csv'

# Seuils d'alerte
TEMP_MAX = 30.0    # °C
HUM_MAX  = 80.0    # %

# ntfy (instance locale)
NTFY_URL = "http://localhost:8080/VOTRE-TOPIC"

# Alerte "pas de données" : délai sans réception avant alerte
DELAI_SANS_DONNEES = 15 * 60   # 15 minutes

# Fréquences
INTERVALLE_LECTURE  = 5        # secondes entre deux lectures du port série
INTERVALLE_ECRITURE = 60       # secondes entre deux écritures dans le CSV


# ============================================================
# FONCTIONS
# ============================================================
def envoyer_ntfy(titre, message, priorite="default", tags="warning"):
    """Envoie une notification via ntfy.
    
    IMPORTANT : les emojis ne doivent JAMAIS être dans le titre (header HTTP),
    car requests encode les headers en latin-1 par défaut.
    Les emojis sont OK dans le corps du message (encodé en UTF-8).
    """
    try:
        requests.post(
            NTFY_URL,
            data=message.encode('utf-8'),
            headers={
                "Title": titre,
                "Priority": priorite,
                "Tags": tags
            },
            timeout=5
        )
    except Exception as e:
        print(f"Erreur envoi ntfy: {e}")


# États : "normal" ou "alerte"
etat_temp_precedent    = "normal"
etat_hum_precedent     = "normal"
etat_donnees_precedent = "normal"

# Initialisé à None tant qu'aucune donnée n'a été reçue depuis le démarrage.
derniere_reception = None


def verifier_seuils(temp, hum):
    """Compare aux seuils et envoie une notif aux transitions."""
    global etat_temp_precedent, etat_hum_precedent

    # --- Température ---
    etat_temp = "alerte" if temp > TEMP_MAX else "normal"
    if etat_temp != etat_temp_precedent:
        if etat_temp == "alerte":
            envoyer_ntfy(
                "[ALERTE] Temperature NAS",
                f"🌡️ Température élevée : {temp}°C (seuil {TEMP_MAX}°C)",
                priorite="urgent",
                tags="warning,thermometer"
            )
        else:
            envoyer_ntfy(
                "[OK] Temperature NAS revenue a la normale",
                f"🌡️ Température : {temp}°C",
                priorite="default",
                tags="white_check_mark"
            )
        etat_temp_precedent = etat_temp

    # --- Humidité ---
    etat_hum = "alerte" if hum > HUM_MAX else "normal"
    if etat_hum != etat_hum_precedent:
        if etat_hum == "alerte":
            envoyer_ntfy(
                "[ALERTE] Humidite NAS",
                f"💧 Humidité élevée : {hum}% (seuil {HUM_MAX}%)",
                priorite="urgent",
                tags="warning,droplet"
            )
        else:
            envoyer_ntfy(
                "[OK] Humidite NAS revenue a la normale",
                f"💧 Humidité : {hum}%",
                priorite="default",
                tags="white_check_mark"
            )
        etat_hum_precedent = etat_hum


def verifier_silence():
    """Alerte si plus de données reçues depuis trop longtemps.
    Ne fait rien tant qu'aucune donnée n'a jamais été reçue (démarrage)."""
    global etat_donnees_precedent
    if derniere_reception is None:
        return

    ecart = (datetime.now() - derniere_reception).total_seconds()

    if ecart > DELAI_SANS_DONNEES and etat_donnees_precedent == "normal":
        envoyer_ntfy(
            "[URGENT] Plus de donnees du capteur",
            f"🚨 Aucune donnée reçue depuis {int(ecart/60)} minutes.\n"
            f"Vérifier l'Arduino, le câble USB et le service.",
            priorite="urgent",
            tags="rotating_light,electric_plug"
        )
        etat_donnees_precedent = "alerte"

    elif ecart <= DELAI_SANS_DONNEES and etat_donnees_precedent == "alerte":
        envoyer_ntfy(
            "[OK] Capteur de nouveau operationnel",
            "✅ Les données sont de nouveau reçues.",
            priorite="default",
            tags="white_check_mark"
        )
        etat_donnees_precedent = "normal"


def lire_derniere_valeur(ser):
    """Vide le buffer série et retourne la DERNIÈRE ligne DATA valide.
    
    C'est le point crucial : on ne lit pas la première ligne qui traîne,
    on lit tout ce qui est disponible et on garde la plus récente.
    
    Retourne un tuple (temp, hum) ou None si rien de valide.
    """
    derniere_valide = None

    # Lire TOUT ce qui est disponible dans le buffer
    while ser.in_waiting > 0:
        try:
            ligne = ser.readline().decode('utf-8').strip()
            if ligne.startswith("DATA,"):
                derniere_valide = ligne
        except UnicodeDecodeError:
            continue

    if derniere_valide is None:
        return None

    try:
        _, temp, hum = derniere_valide.split(",")
        return float(temp), float(hum)
    except (ValueError, IndexError):
        return None


# ============================================================
# BOUCLE PRINCIPALE
# ============================================================
try:
    ser = serial.Serial(port_serie, 9600, timeout=1)
    print("Surveillance active (Temp + Hum).")

    try:
        with open(fichier_log, "x") as f:
            f.write("Date et Heure,Temperature_C,Humidite_Pct\n")
    except FileExistsError:
        pass

    envoyer_ntfy(
        "[OK] Monitoring climatique demarre",
        "🟢 Le service de surveillance est actif.",
        priorite="low",
        tags="white_check_mark"
    )

    derniere_ecriture = 0

    while True:
        resultat = lire_derniere_valeur(ser)

        if resultat is not None:
            temp, hum = resultat
            maintenant = datetime.now()
            derniere_reception = maintenant

            # Vérifier les seuils à CHAQUE lecture (pour ne pas rater un pic)
            verifier_seuils(temp, hum)

            # Écrire dans le CSV seulement toutes les INTERVALLE_ECRITURE secondes
            if (maintenant.timestamp() - derniere_ecriture) >= INTERVALLE_ECRITURE:
                horodatage = maintenant.strftime("%Y-%m-%d %H:%M:%S")
                with open(fichier_log, "a") as f:
                    f.write(f"{horodatage},{temp},{hum}\n")
                derniere_ecriture = maintenant.timestamp()

                if temp > TEMP_MAX or hum > HUM_MAX:
                    print(f"ALERTE: Temp {temp}C | Hum {hum}%")
                else:
                    print(f"Temp: {temp}C | Hum: {hum}%")

        verifier_silence()
        time.sleep(INTERVALLE_LECTURE)

except KeyboardInterrupt:
    print("Arret du script.")
except Exception as e:
    print("Erreur: " + str(e))
    envoyer_ntfy(
        "[URGENT] Erreur du script monitoring",
        f"🚨 Le script s'est arrêté : {e}",
        priorite="urgent",
        tags="rotating_light"
    )
    raise
