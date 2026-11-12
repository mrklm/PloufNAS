"""Dashboard web de PloufNAS (Flask).

Lancement : python3 dashboard.py   →   http://IP-DU-NAS:5000

Utilise le serveur de production waitress s'il est installé (paquet python3-waitress),
sinon le serveur intégré de Flask. Adresse, port, protection de la consultation et
reverse proxy se règlent dans la section « dashboard » de config.json.
Prévu pour tourner sans les droits root (compte « ploufnas », voir dashboard-climat.service).
"""
import base64
import csv
import io
import logging
import os
import threading
import time

from flask import Flask, Response, jsonify, request, send_from_directory

import config
import systeme

VERSION = "1.3.0"
NB_POINTS = 30          # nombre de mesures renvoyées par /api (30 min à 1 mesure/min)

# Limitation des mots de passe faux, par adresse IP
ESSAIS_MAX = 5          # échecs autorisés…
FENETRE_ESSAIS = 15 * 60   # …sur cette durée (s), puis blocage jusqu'à la fin de la fenêtre

# Politique de sécurité : la page ne charge que ses propres fichiers (aucun script en ligne)
EN_TETES_SECURITE = {
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; "
                                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
                                "form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

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


class Limiteur:
    """Bloque une adresse IP après ESSAIS_MAX mots de passe faux en FENETRE_ESSAIS secondes."""

    def __init__(self, essais_max=ESSAIS_MAX, fenetre=FENETRE_ESSAIS, horloge=time.monotonic):
        self.essais_max = essais_max
        self.fenetre = fenetre
        self.horloge = horloge
        self.echecs = {}        # ip -> horodatages des échecs récents
        self.verrou = threading.Lock()

    def _recents(self, ip):
        limite = self.horloge() - self.fenetre
        recents = [t for t in self.echecs.get(ip, []) if t > limite]
        if recents:
            self.echecs[ip] = recents
        else:
            self.echecs.pop(ip, None)
        return recents

    def attente(self, ip):
        """Secondes restantes de blocage (0 si l'adresse peut essayer)."""
        with self.verrou:
            recents = self._recents(ip)
            if len(recents) < self.essais_max:
                return 0
            return max(1, round(recents[0] + self.fenetre - self.horloge()))

    def echec(self, ip):
        with self.verrou:
            self._recents(ip)
            self.echecs.setdefault(ip, []).append(self.horloge())

    def succes(self, ip):
        with self.verrou:
            self.echecs.pop(ip, None)


limiteur = Limiteur()


def message_blocage(secondes):
    minutes = max(1, round(secondes / 60))
    return f"Trop de mots de passe incorrects. Réessayez dans {minutes} min."


def verifier_acces(cfg):
    """Contrôle le mot de passe reçu. Retourne None si correct, sinon (message, code HTTP)."""
    ip = request.remote_addr or "?"
    attente = limiteur.attente(ip)
    if attente:
        return message_blocage(attente), 429
    mdp = mot_de_passe_recu()
    if mdp is None or not config.verifier_mot_de_passe(mdp, cfg["mot_de_passe_hash"]):
        limiteur.echec(ip)
        log.warning("Mot de passe incorrect depuis %s.", ip)
        return "Mot de passe incorrect.", 401
    limiteur.succes(ip)
    return None


# ============================================================
# CONTRÔLES COMMUNS À TOUTES LES REQUÊTES
# ============================================================
@app.before_request
def controle_consultation():
    """Option « consultation_protegee » : mot de passe exigé pour toute la page."""
    if request.method == "POST" and request.path == "/api/config":
        return None    # contrôle dédié (sans fenêtre de connexion du navigateur)
    try:
        cfg = config.charger()
    except config.ConfigInvalide as e:
        # Impossible de savoir si la consultation est protégée : on refuse plutôt qu'ouvrir
        log.error("Configuration invalide : %s", e)
        return Response("Configuration du NAS illisible ou invalide : consultez le journal "
                        "(journalctl -u dashboard-climat).\n", 503, mimetype="text/plain")
    if not cfg["dashboard"]["consultation_protegee"]:
        return None
    if not cfg["mot_de_passe_hash"]:
        # Protection demandée mais aucun mot de passe : on refuse plutôt qu'ouvrir
        return Response("Consultation protégée, mais aucun mot de passe n'est défini.\n"
                        "Sur le NAS : python3 config.py --mot-de-passe\n",
                        503, mimetype="text/plain")
    refus = verifier_acces(cfg)
    if refus is None:
        return None
    message, code = refus
    entetes = {"WWW-Authenticate": 'Basic realm="PloufNAS", charset="UTF-8"'} if code == 401 else {}
    return Response(message + "\n", code, headers=entetes, mimetype="text/plain")


@app.after_request
def en_tetes_securite(reponse):
    for nom, valeur in EN_TETES_SECURITE.items():
        reponse.headers.setdefault(nom, valeur)
    if request.path.startswith("/api"):
        reponse.headers["Cache-Control"] = "no-store"
    return reponse


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
        # Requête venue d'un autre site (le navigateur l'indique) : refusée
        if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            return erreur("Requête refusée (origine extérieure).", 403)
        if not request.is_json:
            return erreur("Format de réglages invalide.", 400)
        refus = verifier_acces(cfg)
        if refus is not None:
            return erreur(*refus)

        try:
            nouvelle = config.valider_reglages_dashboard(request.get_json(silent=True), cfg)
        except config.ConfigInvalide as e:
            return erreur(str(e), 400)
        try:
            config.enregistrer_reglages(nouvelle)   # seuils, alertes, couleurs uniquement
        except OSError as e:
            log.error("Écriture des réglages impossible : %s", e)
            return erreur("Impossible d'enregistrer la configuration sur le NAS.", 500)

    log.info("Réglages enregistrés depuis %s.", request.remote_addr)
    return jsonify(dict(config.vue_publique(nouvelle), status="ok"))


def demarrer():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = config.charger()  # crée config.json au premier lancement
    except config.ConfigInvalide as e:
        log.error("Configuration invalide, valeurs par défaut utilisées : %s", e)
        cfg = config.valider_config({})
    reglages = cfg["dashboard"]

    application = app
    if reglages["derriere_proxy"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        # Un seul proxy de confiance : adresse réelle du visiteur et HTTPS d'origine
        application.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        log.info("Mode reverse proxy : en-têtes X-Forwarded-* pris en compte.")
    if reglages["consultation_protegee"]:
        log.info("Consultation protégée par mot de passe.")

    adresse, port = reglages["adresse"], reglages["port"]
    try:
        from waitress import serve
    except ImportError:
        log.info("waitress absent : serveur intégré de Flask (apt install python3-waitress "
                 "pour un serveur de production).")
        application.run(host=adresse, port=port)
    else:
        log.info("Serveur waitress sur %s:%s.", adresse, port)
        serve(application, host=adresse, port=port, threads=8, ident="PloufNAS")


if __name__ == "__main__":
    demarrer()
