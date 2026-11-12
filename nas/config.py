"""Configuration partagée de PloufNAS (monitor_climat.py et dashboard.py).

Trois fichiers, à côté des scripts, pour que le dashboard (qui peut tourner sans
les droits root) n'ait accès qu'au strict nécessaire :

    config.json              port série, CSV, mot de passe, section « dashboard »
                             (root ; lisible par le dashboard)
    ntfy.json                adresse ntfy et jeton (root uniquement)
    reglages/reglages.json   seuils, alertes et couleurs (modifiables par le dashboard)

Ils sont créés avec les valeurs par défaut au premier lancement. Un config.json
d'une version précédente (tout dans un seul fichier) est réparti automatiquement.

Usage en ligne de commande (depuis le dossier monitoring) :
    sudo python3 config.py --init           crée config.json s'il n'existe pas
    sudo python3 config.py --mot-de-passe   définit le mot de passe du dashboard
    sudo python3 config.py --jeton-ntfy     enregistre le jeton d'accès ntfy (facultatif)
    sudo python3 config.py --verifier       valide config.json et affiche son contenu
"""
import argparse
import copy
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile

DOSSIER = os.path.dirname(os.path.abspath(__file__))
CHEMIN_CONFIG = os.path.join(DOSSIER, "config.json")
CHEMIN_ANCIENNES_ALERTES = os.path.join(DOSSIER, "alertes.json")
NOM_NTFY = "ntfy.json"
DOSSIER_REGLAGES = "reglages"
NOM_REGLAGES = "reglages.json"

CLES_NTFY = ("ntfy_url", "ntfy_jeton")                       # rangées dans ntfy.json
CLES_REGLAGES = ("seuils", "alertes_systeme", "couleurs")    # rangées dans reglages.json

NTFY_NON_CONFIGURE = "http://localhost:8080/VOTRE-TOPIC"

DEFAUTS = {
    # --- Réglages modifiables uniquement dans ce fichier ---
    "port_serie": "/dev/arduino_nas",
    "fichier_csv": "climat.csv",          # relatif au dossier des scripts, ou absolu
    "ntfy_url": NTFY_NON_CONFIGURE,
    "ntfy_jeton": "",                     # facultatif : python3 config.py --jeton-ntfy
    "mot_de_passe_hash": "",              # à définir avec : python3 config.py --mot-de-passe
    "dashboard": {
        "adresse": "0.0.0.0",             # 127.0.0.1 derrière un reverse proxy sur le NAS
        "port": 5000,
        "consultation_protegee": False,   # True : mot de passe demandé dès l'ouverture
        "derriere_proxy": False,          # True : faire confiance à X-Forwarded-For/-Proto
    },
    # --- Réglages modifiables depuis le dashboard ---
    "seuils": {
        "temp_max": 30.0,
        "hum_max": 80.0,
        "temp_hysteresis": 1.0,
        "hum_hysteresis": 2.0,
    },
    "alertes_systeme": {
        "cpu": {"enabled": True, "threshold": 75},
        "disks": {"enabled": True, "threshold": 50},
        "smart": {"enabled": True},
        "absent": {"enabled": True},      # disque disparu ou qui ne répond plus
        "gpu": {"enabled": False, "threshold": 80},
    },
    "couleurs": {
        "temperature": "#FF3B3B",
        "humidity": "#3B8BFF",
    },
}

# Plages acceptées : protège contre une saisie absurde ou un fichier abîmé.
PLAGES_SEUILS = {
    "temp_max": (0.0, 80.0),
    "hum_max": (1.0, 100.0),
    "temp_hysteresis": (0.0, 10.0),
    "hum_hysteresis": (0.0, 20.0),
}
PLAGE_ALERTES_SYSTEME = (20, 120)        # °C
RE_COULEUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
RE_JETON = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")   # jetons ntfy : tk_ + 29 caractères


class ConfigInvalide(ValueError):
    """Valeur refusée ; le message est destiné à l'utilisateur."""


# ============================================================
# VALIDATION
# ============================================================
def _nombre(valeur, nom, plage):
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise ConfigInvalide(f"« {nom} » doit être un nombre.")
    valeur = float(valeur)
    if not (plage[0] <= valeur <= plage[1]):
        raise ConfigInvalide(f"« {nom} » doit être compris entre {plage[0]:g} et {plage[1]:g}.")
    return valeur


def _booleen(valeur, nom):
    if not isinstance(valeur, bool):
        raise ConfigInvalide(f"« {nom} » doit valoir true ou false.")
    return valeur


def valider_reglages_dashboard(donnees, base):
    """Fusionne dans une copie de `base` les réglages modifiables depuis le dashboard.

    Seules les clés connues sont prises en compte ; toute valeur invalide lève
    ConfigInvalide et rien n'est modifié.
    """
    if not isinstance(donnees, dict):
        raise ConfigInvalide("Format de réglages invalide.")
    resultat = copy.deepcopy(base)

    seuils = donnees.get("seuils", {})
    if not isinstance(seuils, dict):
        raise ConfigInvalide("« seuils » doit être un objet.")
    for cle, plage in PLAGES_SEUILS.items():
        if cle in seuils:
            resultat["seuils"][cle] = _nombre(seuils[cle], cle, plage)

    alertes = donnees.get("alertes_systeme", {})
    if not isinstance(alertes, dict):
        raise ConfigInvalide("« alertes_systeme » doit être un objet.")
    for composant, valeurs in alertes.items():
        if composant not in DEFAUTS["alertes_systeme"]:
            continue
        if not isinstance(valeurs, dict):
            raise ConfigInvalide(f"« {composant} » doit être un objet.")
        cible = resultat["alertes_systeme"][composant]
        if "enabled" in valeurs:
            cible["enabled"] = _booleen(valeurs["enabled"], f"{composant}.enabled")
        if "threshold" in valeurs and "threshold" in cible:
            cible["threshold"] = int(_nombre(valeurs["threshold"],
                                             f"{composant}.threshold", PLAGE_ALERTES_SYSTEME))

    couleurs = donnees.get("couleurs", {})
    if not isinstance(couleurs, dict):
        raise ConfigInvalide("« couleurs » doit être un objet.")
    for cle in DEFAUTS["couleurs"]:
        if cle in couleurs:
            if not isinstance(couleurs[cle], str) or not RE_COULEUR.match(couleurs[cle]):
                raise ConfigInvalide(f"Couleur « {cle} » invalide (format attendu : #RRGGBB).")
            resultat["couleurs"][cle] = couleurs[cle].upper()

    return resultat


def valider_config(donnees):
    """Valide un config.json complet ; les clés absentes prennent la valeur par défaut."""
    if not isinstance(donnees, dict):
        raise ConfigInvalide("config.json doit contenir un objet JSON.")
    resultat = copy.deepcopy(DEFAUTS)
    for cle in ("port_serie", "fichier_csv", "ntfy_url", "ntfy_jeton", "mot_de_passe_hash"):
        if cle in donnees:
            if not isinstance(donnees[cle], str):
                raise ConfigInvalide(f"« {cle} » doit être une chaîne de caractères.")
            resultat[cle] = donnees[cle]
    if not resultat["port_serie"] or not resultat["fichier_csv"]:
        raise ConfigInvalide("« port_serie » et « fichier_csv » ne peuvent pas être vides.")
    if resultat["ntfy_jeton"] and not RE_JETON.match(resultat["ntfy_jeton"]):
        raise ConfigInvalide("« ntfy_jeton » invalide (lettres, chiffres, _ et - uniquement).")

    dashboard = donnees.get("dashboard", {})
    if not isinstance(dashboard, dict):
        raise ConfigInvalide("« dashboard » doit être un objet.")
    cible = resultat["dashboard"]
    if "adresse" in dashboard:
        if not isinstance(dashboard["adresse"], str) or not dashboard["adresse"].strip():
            raise ConfigInvalide("« dashboard.adresse » doit être une adresse IP (ex. 0.0.0.0).")
        cible["adresse"] = dashboard["adresse"].strip()
    if "port" in dashboard:
        cible["port"] = int(_nombre(dashboard["port"], "dashboard.port", (1, 65535)))
    for cle in ("consultation_protegee", "derriere_proxy"):
        if cle in dashboard:
            cible[cle] = _booleen(dashboard[cle], f"dashboard.{cle}")
    return valider_reglages_dashboard(donnees, resultat)


# ============================================================
# LECTURE / ÉCRITURE
# ============================================================
def _depuis_anciennes_alertes(chemin):
    """Reprend les réglages d'un alertes.json (versions ≤ 0.4.0), s'il existe."""
    try:
        with open(chemin, encoding="utf-8") as f:
            ancien = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(ancien, dict):
        return {}
    reprise = {"alertes_systeme": {k: ancien[k] for k in ("cpu", "disks", "smart", "gpu")
                                   if k in ancien}}
    if "colors" in ancien:
        reprise["couleurs"] = ancien["colors"]
    try:
        valider_reglages_dashboard(reprise, DEFAUTS)
    except ConfigInvalide:
        return {}
    return reprise


def chemins(chemin=None):
    """Chemins de config.json, ntfy.json et reglages/reglages.json."""
    chemin = os.path.abspath(chemin or CHEMIN_CONFIG)
    dossier = os.path.dirname(chemin)
    return (chemin, os.path.join(dossier, NOM_NTFY),
            os.path.join(dossier, DOSSIER_REGLAGES, NOM_REGLAGES))


def _lire_json(chemin):
    """Objet JSON contenu dans le fichier, ou None s'il n'existe pas."""
    try:
        with open(chemin, encoding="utf-8") as f:
            contenu = f.read()
    except FileNotFoundError:
        return None
    try:
        donnees = json.loads(contenu)
    except ValueError as e:
        raise ConfigInvalide(f"{chemin} n'est pas un JSON valide : {e}") from e
    if not isinstance(donnees, dict):
        raise ConfigInvalide(f"{chemin} doit contenir un objet JSON.")
    return donnees


def _ecrire_json(chemin, donnees, mode):
    """Écriture atomique : un lecteur ne voit jamais un fichier à moitié écrit.

    Un fichier existant garde son propriétaire, son groupe et ses droits (réglés à
    l'installation) ; un nouveau fichier reçoit `mode`.
    """
    dossier = os.path.dirname(os.path.abspath(chemin))
    os.makedirs(dossier, exist_ok=True)
    try:
        # Un lien symbolique (dossier reglages/ modifiable par le dashboard) n'est jamais
        # suivi : il est remplacé par un vrai fichier, sans recopier les droits de sa cible.
        existant = None if os.path.islink(chemin) else os.stat(chemin)
    except FileNotFoundError:
        existant = None
    fd, temporaire = tempfile.mkstemp(dir=dossier, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, indent=4, ensure_ascii=False)
            f.write("\n")
        if existant is None:
            os.chmod(temporaire, mode)
        else:
            os.chmod(temporaire, existant.st_mode & 0o777)
            try:
                os.chown(temporaire, existant.st_uid, existant.st_gid)
            except OSError:
                pass    # sans les droits root : le fichier appartient à celui qui l'écrit
        os.replace(temporaire, chemin)
    except BaseException:
        try:
            os.unlink(temporaire)
        except OSError:
            pass
        raise


def _partie(config, cles):
    return {k: config[k] for k in cles if k in config}


def _partie_base(config):
    return {k: v for k, v in config.items() if k not in CLES_NTFY + CLES_REGLAGES}


def charger(chemin=None, creer=True):
    """Charge et valide la configuration répartie dans les trois fichiers.

    Avec `creer`, crée les fichiers absents (reprise d'alertes.json, puis répartition
    d'un ancien config.json complet) ; sans les droits nécessaires, cette étape est
    simplement sautée. ntfy.json illisible (dashboard sans root) : valeurs par défaut.
    Lève ConfigInvalide si un fichier est illisible ou invalide.
    """
    c_config, c_ntfy, c_reglages = chemins(chemin)
    try:
        base = _lire_json(c_config)
        reglages = _lire_json(c_reglages)
    except PermissionError as e:
        raise ConfigInvalide(f"Lecture refusée : {e.filename}. Vérifiez les droits du fichier "
                             "(voir « Dashboard sans root » dans le README).") from e
    try:
        ntfy = _lire_json(c_ntfy)
        ntfy_lisible = True
    except PermissionError:
        ntfy, ntfy_lisible = None, False

    nouveau = base is None
    if nouveau:
        base = _depuis_anciennes_alertes(os.path.join(os.path.dirname(c_config), "alertes.json"))
    # Les fichiers séparés priment ; sinon, valeurs d'un ancien config.json complet
    donnees = _partie_base(base)
    donnees.update(_partie(ntfy if ntfy is not None else base, CLES_NTFY))
    donnees.update(_partie(reglages if reglages is not None else base, CLES_REGLAGES))
    config = valider_config(donnees)

    if creer:
        try:
            if ntfy is None and ntfy_lisible:
                enregistrer_ntfy(config, c_config)
            if reglages is None:
                enregistrer_reglages(config, c_config)
            if nouveau or any(k in base for k in CLES_NTFY + CLES_REGLAGES):
                enregistrer_base(config, c_config)
        except PermissionError:
            pass    # dashboard sans root : la répartition sera faite par root
    return config


def cles_ignorees(chemin=None):
    """Clés d'un config.json que les fichiers séparés rendent sans effet."""
    c_config, c_ntfy, c_reglages = chemins(chemin)
    try:
        base = _lire_json(c_config) or {}
    except (OSError, ConfigInvalide):
        return []
    ignorees = []
    if os.path.exists(c_ntfy):
        ignorees += [k for k in CLES_NTFY if k in base]
    if os.path.exists(c_reglages):
        ignorees += [k for k in CLES_REGLAGES if k in base]
    return ignorees


def enregistrer_base(config, chemin=None):
    """config.json : contient l'empreinte du mot de passe."""
    _ecrire_json(chemins(chemin)[0], _partie_base(config), 0o600)


def enregistrer_ntfy(config, chemin=None):
    """ntfy.json : adresse et jeton, lisibles par root uniquement."""
    _ecrire_json(chemins(chemin)[1], _partie(config, CLES_NTFY), 0o600)


def enregistrer_reglages(config, chemin=None):
    """reglages/reglages.json : seuils, alertes et couleurs (rien de secret)."""
    _ecrire_json(chemins(chemin)[2], _partie(config, CLES_REGLAGES), 0o644)


def enregistrer(config, chemin=None):
    """Écrit les trois fichiers."""
    enregistrer_ntfy(config, chemin)
    enregistrer_reglages(config, chemin)
    enregistrer_base(config, chemin)


def chemin_csv(config, dossier=None):
    """Chemin absolu du CSV (un chemin relatif part du dossier de config.json)."""
    dossier = dossier or os.path.dirname(os.path.abspath(CHEMIN_CONFIG))
    return os.path.join(dossier, config["fichier_csv"])


def vue_publique(config):
    """Ce que le navigateur a le droit de voir (ni l'URL ntfy, ni le jeton, ni le hash)."""
    return {
        "seuils": config["seuils"],
        "alertes_systeme": config["alertes_systeme"],
        "couleurs": config["couleurs"],
        "mot_de_passe_defini": bool(config["mot_de_passe_hash"]),
    }


# ============================================================
# MOT DE PASSE
# ============================================================
ITERATIONS = 200_000


def hacher_mot_de_passe(mot_de_passe):
    sel = secrets.token_hex(16)
    empreinte = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"),
                                    bytes.fromhex(sel), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${sel}${empreinte.hex()}"


def verifier_mot_de_passe(mot_de_passe, stocke):
    try:
        algo, iterations, sel, attendu = stocke.split("$")
        if algo != "pbkdf2_sha256":
            return False
        empreinte = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"),
                                        bytes.fromhex(sel), int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(empreinte.hex(), attendu)


# ============================================================
# LIGNE DE COMMANDE
# ============================================================
def saisir_non_vide(invite, essais=3):
    """Saisie masquée ; une saisie vide (touche Entrée en double, par exemple) est redemandée."""
    for _ in range(essais):
        valeur = getpass.getpass(invite)
        if valeur:
            return valeur
    return ""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Configuration de PloufNAS")
    groupe = parser.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--init", action="store_true",
                        help="crée les fichiers de configuration s'ils n'existent pas")
    groupe.add_argument("--mot-de-passe", action="store_true",
                        help="définit le mot de passe d'enregistrement des réglages du dashboard")
    groupe.add_argument("--jeton-ntfy", action="store_true",
                        help="enregistre le jeton d'accès ntfy (serveur ntfy avec authentification)")
    groupe.add_argument("--verifier", action="store_true",
                        help="valide et affiche la configuration")
    args = parser.parse_args(argv)

    try:
        existait = os.path.exists(CHEMIN_CONFIG)
        config = charger()
    except ConfigInvalide as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 1

    c_config, c_ntfy, c_reglages = chemins()
    if args.init:
        print(("Configuration existante : " if existait else "Configuration créée : ") + c_config)
        print("  adresse ntfy et jeton : " + c_ntfy)
        print("  seuils et alertes     : " + c_reglages)
        if config["ntfy_url"] == NTFY_NON_CONFIGURE:
            print(f"Pensez à renseigner « ntfy_url » (votre topic) dans {c_ntfy}.")
        if not config["mot_de_passe_hash"]:
            print("Pensez à définir le mot de passe : python3 config.py --mot-de-passe "
                  "(précédé de sudo si vous n'êtes pas root)")
        return 0

    if args.mot_de_passe:
        mdp = saisir_non_vide("Nouveau mot de passe : ")
        if len(mdp) < 8:
            print("Erreur : le mot de passe doit faire au moins 8 caractères.", file=sys.stderr)
            return 1
        if saisir_non_vide("Confirmez le mot de passe : ") != mdp:
            print("Erreur : les deux saisies ne correspondent pas.", file=sys.stderr)
            return 1
        config["mot_de_passe_hash"] = hacher_mot_de_passe(mdp)
        enregistrer_base(config)
        print("Mot de passe enregistré.")
        return 0

    if args.jeton_ntfy:
        jeton = saisir_non_vide("Jeton ntfy (commence par tk_) : ").strip()
        if not RE_JETON.match(jeton):
            print("Erreur : jeton invalide (lettres, chiffres, _ et - uniquement).", file=sys.stderr)
            return 1
        if not jeton.startswith("tk_"):
            print("Attention : un jeton ntfy commence normalement par « tk_ ».")
        config["ntfy_jeton"] = jeton
        enregistrer_ntfy(config)
        print("Jeton ntfy enregistré. Il sera utilisé dès la prochaine notification.")
        return 0

    affichage = dict(config,
                     mot_de_passe_hash="(défini)" if config["mot_de_passe_hash"] else "",
                     ntfy_jeton="(défini)" if config["ntfy_jeton"] else "")
    print(json.dumps(affichage, indent=4, ensure_ascii=False))
    print(f"\nFichiers : {c_config}, {c_ntfy}, {c_reglages}")
    ignorees = cles_ignorees()
    if ignorees:
        print("Attention : dans config.json, ces clés sont sans effet (elles sont lues dans "
              "ntfy.json ou reglages/reglages.json) : " + ", ".join(ignorees))
    print("Configuration valide.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
