"""Dashboard web de PloufNAS (Flask).

Lancement : python3 dashboard.py   →   http://IP-DU-NAS:5000
"""
import base64
import csv
import io
import logging
import os
import threading
import time

from flask import Flask, jsonify, request, send_from_directory

import config
import systeme

VERSION = "0.6.0"
NB_POINTS = 30          # nombre de mesures renvoyées par /api (30 min à 1 mesure/min)
PORT = 5000

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DOSSIER_STATIC = os.path.join(DOSSIER, "static")

app = Flask(__name__, static_folder=DOSSIER_STATIC, static_url_path="/static")
log = logging.getLogger("dashboard")
_verrou_config = threading.Lock()


# ============================================================
# LECTURE DU CSV
# ============================================================
def lire_dernieres_lignes(chemin, n, taille_bloc=4096):
    """Retourne les n dernières lignes d'un fichier texte, sans le lire en entier."""
    with open(chemin, "rb") as f:
        f.seek(0, os.SEEK_END)
        position = f.tell()
        morceaux = []
        nb_sauts = 0
        while position > 0 and nb_sauts <= n:
            lecture = min(taille_bloc, position)
            position -= lecture
            f.seek(position)
            bloc = f.read(lecture)
            morceaux.append(bloc)
            nb_sauts += bloc.count(b"\n")
    texte = b"".join(reversed(morceaux)).decode("utf-8", errors="replace")
    return texte.splitlines()[-n:]


def dernieres_mesures(chemin, n=NB_POINTS):
    try:
        lignes = lire_dernieres_lignes(chemin, n + 1)   # +1 : l'en-tête si le fichier est court
    except FileNotFoundError:
        return []
    mesures = []
    for ligne in csv.reader(io.StringIO("\n".join(lignes))):
        if len(ligne) != 3:
            continue
        horodatage, temp, hum = ligne
        try:
            mesures.append({"time": horodatage, "temp": float(temp), "hum": float(hum)})
        except ValueError:
            continue    # en-tête ou ligne abîmée
    return mesures[-n:]


# ============================================================
# AUTHENTIFICATION
# ============================================================
def mot_de_passe_recu():
    """Mot de passe envoyé en HTTP Basic (le nom d'utilisateur est ignoré)."""
    entete = request.headers.get("Authorization", "")
    if not entete.startswith("Basic "):
        return None
    try:
        decode = base64.b64decode(entete[6:], validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return decode.partition(":")[2]


def erreur(message, code):
    # Pas d'en-tête WWW-Authenticate : le dashboard affiche son propre champ
    # mot de passe, au lieu de la fenêtre de connexion du navigateur.
    return jsonify({"status": "error", "message": message}), code


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def index():
    return send_from_directory(DOSSIER_STATIC, "index.html")


@app.route("/api")
def api():
    try:
        cfg = config.charger()
    except config.ConfigInvalide as e:
        log.error("Configuration invalide : %s", e)
        return jsonify([])
    return jsonify(dernieres_mesures(config.chemin_csv(cfg)))


@app.route("/api/systeme")
def api_systeme():
    """Dernier relevé matériel écrit par monitor_climat.py (il ne relit pas les disques)."""
    chemin = os.path.join(os.path.dirname(os.path.abspath(config.CHEMIN_CONFIG)), "systeme.json")
    releve = systeme.lire(chemin)
    if releve is None:
        return jsonify({"disponible": False})
    age = max(0, round(time.time() - releve.get("horodatage", 0)))
    return jsonify(dict(releve, disponible=True, age=age))


@app.route("/api/config", methods=["GET"])
def lire_config():
    try:
        cfg = config.charger()
    except config.ConfigInvalide as e:
        return erreur(f"Configuration invalide sur le NAS : {e}", 500)
    return jsonify(dict(config.vue_publique(cfg), version=VERSION))


@app.route("/api/config", methods=["POST"])
def enregistrer_config():
    with _verrou_config:
        try:
            cfg = config.charger()
        except config.ConfigInvalide as e:
            return erreur(f"Configuration invalide sur le NAS : {e}", 500)

        if not cfg["mot_de_passe_hash"]:
            return erreur("Aucun mot de passe n'est défini. Sur le NAS, lancez : "
                          "sudo python3 config.py --mot-de-passe", 403)
        mdp = mot_de_passe_recu()
        if mdp is None or not config.verifier_mot_de_passe(mdp, cfg["mot_de_passe_hash"]):
            time.sleep(1)   # ralentit les essais en série
            return erreur("Mot de passe incorrect.", 401)

        try:
            nouvelle = config.valider_reglages_dashboard(request.get_json(silent=True), cfg)
        except config.ConfigInvalide as e:
            return erreur(str(e), 400)
        try:
            config.enregistrer(nouvelle)
        except OSError as e:
            log.error("Écriture de config.json impossible : %s", e)
            return erreur("Impossible d'enregistrer la configuration sur le NAS.", 500)

    log.info("Réglages enregistrés depuis %s.", request.remote_addr)
    return jsonify(dict(config.vue_publique(nouvelle), status="ok"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config.charger()    # crée config.json au premier lancement, signale une config invalide
    except config.ConfigInvalide as e:
        log.error("Configuration invalide : %s", e)
    app.run(host="0.0.0.0", port=PORT)
