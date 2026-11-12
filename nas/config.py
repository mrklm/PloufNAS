"""Configuration partagée de PloufNAS (monitor_climat.py et dashboard.py).

Un seul fichier, config.json, placé à côté des scripts. Il est créé avec les
valeurs par défaut au premier lancement (en reprenant un éventuel alertes.json).

Usage en ligne de commande (depuis le dossier monitoring) :
    sudo python3 config.py --init           crée config.json s'il n'existe pas
    sudo python3 config.py --mot-de-passe   définit le mot de passe du dashboard
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

NTFY_NON_CONFIGURE = "http://localhost:8080/VOTRE-TOPIC"

DEFAUTS = {
    # --- Réglages modifiables uniquement dans ce fichier ---
    "port_serie": "/dev/arduino_nas",
    "fichier_csv": "climat.csv",          # relatif au dossier des scripts, ou absolu
    "ntfy_url": NTFY_NON_CONFIGURE,
    "mot_de_passe_hash": "",              # à définir avec : python3 config.py --mot-de-passe
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
    for cle in ("port_serie", "fichier_csv", "ntfy_url", "mot_de_passe_hash"):
        if cle in donnees:
            if not isinstance(donnees[cle], str):
                raise ConfigInvalide(f"« {cle} » doit être une chaîne de caractères.")
            resultat[cle] = donnees[cle]
    if not resultat["port_serie"] or not resultat["fichier_csv"]:
        raise ConfigInvalide("« port_serie » et « fichier_csv » ne peuvent pas être vides.")
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


def charger(chemin=None, creer=True):
    """Charge et valide la config. La crée (avec reprise d'alertes.json) si elle est absente.

    Lève ConfigInvalide si le fichier existe mais est illisible ou invalide.
    """
    chemin = chemin or CHEMIN_CONFIG
    try:
        with open(chemin, encoding="utf-8") as f:
            contenu = f.read()
    except FileNotFoundError:
        ancien = os.path.join(os.path.dirname(chemin), "alertes.json")
        config = valider_config(_depuis_anciennes_alertes(ancien))
        if creer:
            enregistrer(config, chemin)
        return config
    try:
        donnees = json.loads(contenu)
    except ValueError as e:
        raise ConfigInvalide(f"{chemin} n'est pas un JSON valide : {e}") from e
    return valider_config(donnees)


def enregistrer(config, chemin=None):
    """Écrit la config de façon atomique : un lecteur ne voit jamais un fichier à moitié écrit."""
    chemin = chemin or CHEMIN_CONFIG
    dossier = os.path.dirname(os.path.abspath(chemin))
    fd, temporaire = tempfile.mkstemp(dir=dossier, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            f.write("\n")
        os.chmod(temporaire, 0o600)   # contient le hash du mot de passe
        os.replace(temporaire, chemin)
    except BaseException:
        try:
            os.unlink(temporaire)
        except OSError:
            pass
        raise


def chemin_csv(config, dossier=None):
    """Chemin absolu du CSV (un chemin relatif part du dossier de config.json)."""
    dossier = dossier or os.path.dirname(os.path.abspath(CHEMIN_CONFIG))
    return os.path.join(dossier, config["fichier_csv"])


def vue_publique(config):
    """Ce que le navigateur a le droit de voir (ni l'URL ntfy, ni le hash)."""
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
    groupe.add_argument("--init", action="store_true", help="crée config.json s'il n'existe pas")
    groupe.add_argument("--mot-de-passe", action="store_true",
                        help="définit le mot de passe d'enregistrement des réglages du dashboard")
    groupe.add_argument("--verifier", action="store_true", help="valide et affiche config.json")
    args = parser.parse_args(argv)

    try:
        existait = os.path.exists(CHEMIN_CONFIG)
        config = charger()
    except ConfigInvalide as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 1

    if args.init:
        print(("Configuration existante : " if existait else "Configuration créée : ") + CHEMIN_CONFIG)
        if config["ntfy_url"] == NTFY_NON_CONFIGURE:
            print("Pensez à renseigner « ntfy_url » (votre topic) dans ce fichier.")
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
        enregistrer(config)
        print("Mot de passe enregistré.")
        return 0

    affichage = dict(config, mot_de_passe_hash="(défini)" if config["mot_de_passe_hash"] else "")
    print(json.dumps(affichage, indent=4, ensure_ascii=False))
    print("\nConfiguration valide.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
