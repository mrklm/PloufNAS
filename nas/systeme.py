"""Relevé matériel du NAS : CPU (température, charge) et disques (température, SMART).

Utilisé par monitor_climat.py, qui écrit le résultat dans systeme.json ; le dashboard
se contente de lire ce fichier (les disques ne sont donc interrogés qu'une fois).

Les disques en veille ne sont jamais réveillés (smartctl -n standby) : leur dernière
valeur connue est conservée et marquée « en veille ».

Vérification sur le NAS (en root) :  python3 systeme.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

INTERVALLE_DISQUES = 5 * 60       # secondes entre deux relevés SMART
DELAI_SMARTCTL = 30               # secondes avant d'abandonner un appel à smartctl
CODE_VEILLE = 3                   # code de sortie demandé à smartctl si le disque dort

# Attributs SMART dont une valeur brute non nulle signale un disque qui se dégrade
ATTRIBUTS_CRITIQUES = {
    5: "secteurs réalloués",
    197: "secteurs en attente",
    198: "secteurs irrécupérables",
}

HWMON = "/sys/class/hwmon"
CAPTEURS_CPU = ("coretemp", "k10temp", "zenpower", "cpu_thermal")


# ============================================================
# CPU
# ============================================================
def _lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return f.read().strip()


def temperature_cpu(racine=HWMON):
    """Température du processeur (°C), ou None si aucun capteur n'est trouvé.

    Prend la valeur « package » (Intel : « Package id 0 », AMD : « Tctl »/« Tdie »),
    sinon la plus haute des températures du capteur.
    """
    try:
        dossiers = sorted(os.listdir(racine))
    except OSError:
        return None
    for dossier in dossiers:
        chemin = os.path.join(racine, dossier)
        try:
            nom = _lire(os.path.join(chemin, "name"))
        except OSError:
            continue
        if nom not in CAPTEURS_CPU:
            continue
        valeurs, package = [], None
        for fichier in sorted(os.listdir(chemin)):
            if not (fichier.startswith("temp") and fichier.endswith("_input")):
                continue
            try:
                valeur = int(_lire(os.path.join(chemin, fichier))) / 1000
            except (OSError, ValueError):
                continue
            valeurs.append(valeur)
            try:
                label = _lire(os.path.join(chemin, fichier.replace("_input", "_label")))
            except OSError:
                label = ""
            if label.startswith(("Package", "Tctl", "Tdie")):
                package = valeur
        if package is not None:
            return round(package, 1)
        if valeurs:
            return round(max(valeurs), 1)
    return None


def infos_cpuinfo(chemin="/proc/cpuinfo"):
    """Modèle et fréquence moyenne (MHz) du processeur."""
    modele, frequences = None, []
    try:
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                cle, _, valeur = ligne.partition(":")
                cle, valeur = cle.strip(), valeur.strip()
                if cle == "model name" and modele is None:
                    modele = " ".join(valeur.split())
                elif cle == "cpu MHz":
                    try:
                        frequences.append(float(valeur))
                    except ValueError:
                        pass
    except OSError:
        pass
    freq = round(sum(frequences) / len(frequences)) if frequences else None
    return modele, freq


def lire_proc_stat(chemin="/proc/stat"):
    """Compteurs (total, inactif) de la ligne « cpu » de /proc/stat."""
    try:
        with open(chemin, encoding="utf-8") as f:
            champs = f.readline().split()
    except OSError:
        return None
    if not champs or champs[0] != "cpu":
        return None
    valeurs = [int(v) for v in champs[1:]]
    inactif = valeurs[3] + (valeurs[4] if len(valeurs) > 4 else 0)   # idle + iowait
    return sum(valeurs), inactif


def charge_cpu(avant, apres):
    """Charge CPU (%) entre deux relevés de /proc/stat."""
    if not avant or not apres:
        return None
    total = apres[0] - avant[0]
    if total <= 0:
        return None
    return round(100 * (1 - (apres[1] - avant[1]) / total))


# ============================================================
# DISQUES
# ============================================================
def lister_disques(executer=subprocess.run):
    """Disques physiques (lsblk), sans les partitions, périphériques loop, zram, etc."""
    try:
        res = executer(["lsblk", "-J", "-d", "-b", "-o", "NAME,MODEL,SERIAL,SIZE,ROTA,TRAN,TYPE"],
                       capture_output=True, text=True, timeout=10)
        donnees = json.loads(res.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    disques = []
    for d in donnees.get("blockdevices", []):
        if d.get("type") != "disk" or str(d.get("name", "")).startswith(("zram", "loop")):
            continue
        rota = d.get("rota")
        disques.append({
            "nom": d.get("name"),
            "modele": (d.get("model") or "").strip() or None,
            "serie": (d.get("serial") or "").strip() or None,
            "taille": int(d["size"]) if str(d.get("size", "")).isdigit() else None,
            "type": "HDD" if rota in (True, "1", 1) else "SSD",
            "connexion": d.get("tran"),
        })
    return disques


def analyser_smartctl(code, sortie):
    """Interprète la sortie JSON de smartctl. Retourne un dict d'état du disque."""
    if code == CODE_VEILLE:
        return {"etat": "veille"}
    try:
        donnees = json.loads(sortie)
    except ValueError:
        return {"etat": "indisponible"}
    messages = " ".join(m.get("string", "") for m in donnees.get("smartctl", {}).get("messages", []))
    if "STANDBY" in messages.upper() or "SLEEP" in messages.upper():
        return {"etat": "veille"}
    if "smart_status" not in donnees and "temperature" not in donnees:
        return {"etat": "indisponible", "message": messages or None}

    passe = donnees.get("smart_status", {}).get("passed")
    problemes = []
    if passe is False:
        problemes.append("auto-diagnostic SMART en échec")
    for attr in donnees.get("ata_smart_attributes", {}).get("table", []):
        nom = ATTRIBUTS_CRITIQUES.get(attr.get("id"))
        brut = attr.get("raw", {}).get("value")
        if nom and isinstance(brut, int) and brut > 0:
            problemes.append(f"{brut} {nom}")
    nvme = donnees.get("nvme_smart_health_information_log", {})
    if nvme.get("critical_warning"):
        problemes.append("avertissement critique NVMe")
    if nvme.get("media_errors"):
        problemes.append(f"{nvme['media_errors']} erreurs média")

    return {
        "etat": "actif",
        "temp": donnees.get("temperature", {}).get("current"),
        "smart_ok": None if passe is None and not problemes else not problemes,
        "problemes": problemes,
        "heures": donnees.get("power_on_time", {}).get("hours"),
    }


def lire_smart(nom, executer=subprocess.run):
    """Interroge un disque avec smartctl, sans le réveiller s'il est en veille."""
    try:
        res = executer(["smartctl", "-j", "-n", f"standby,{CODE_VEILLE}", "-H", "-A", f"/dev/{nom}"],
                       capture_output=True, text=True, timeout=DELAI_SMARTCTL)
    except FileNotFoundError:
        return {"etat": "indisponible", "message": "smartctl absent (paquet smartmontools)"}
    except (OSError, subprocess.SubprocessError) as e:
        return {"etat": "indisponible", "message": str(e)}
    return analyser_smartctl(res.returncode, res.stdout)


# ============================================================
# COLLECTEUR
# ============================================================
class Collecteur:
    """Conserve l'état entre deux relevés (charge CPU, dernières valeurs des disques)."""

    def __init__(self, executer=subprocess.run, horloge=time.time, racine_hwmon=HWMON,
                 proc_stat="/proc/stat", cpuinfo="/proc/cpuinfo"):
        self.executer = executer
        self.horloge = horloge
        self.racine_hwmon = racine_hwmon
        self.proc_stat = proc_stat
        self.cpuinfo = cpuinfo
        self.stat_precedent = lire_proc_stat(proc_stat)
        self.disques = {}            # nom -> dernier état connu
        self.dernier_releve_disques = None

    def releve_cpu(self):
        modele, freq = infos_cpuinfo(self.cpuinfo)
        stat = lire_proc_stat(self.proc_stat)
        charge = charge_cpu(self.stat_precedent, stat)
        self.stat_precedent = stat
        return {
            "modele": modele,
            "threads": os.cpu_count(),
            "frequence_mhz": freq,
            "temp": temperature_cpu(self.racine_hwmon),
            "charge": charge,
        }

    def releve_disques(self, forcer=False):
        maintenant = self.horloge()
        if (not forcer and self.dernier_releve_disques is not None
                and maintenant - self.dernier_releve_disques < INTERVALLE_DISQUES):
            return list(self.disques.values())
        self.dernier_releve_disques = maintenant
        presents = {}
        for disque in lister_disques(self.executer):
            smart = lire_smart(disque["nom"], self.executer)
            ancien = self.disques.get(disque["nom"], {})
            if smart["etat"] == "actif":
                info = dict(disque, **smart, releve=maintenant)
            else:
                # En veille ou illisible : on garde les dernières valeurs connues
                info = dict(ancien, **disque, etat=smart["etat"],
                            message=smart.get("message"))
            presents[disque["nom"]] = info
        self.disques = presents
        return list(presents.values())

    def releve(self, forcer_disques=False):
        return {
            "horodatage": self.horloge(),
            "cpu": self.releve_cpu(),
            "disques": self.releve_disques(forcer_disques),
        }


# ============================================================
# FICHIER systeme.json
# ============================================================
def ecrire(releve, chemin):
    dossier = os.path.dirname(os.path.abspath(chemin))
    fd, temporaire = tempfile.mkstemp(dir=dossier, prefix=".systeme-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(releve, f, ensure_ascii=False)
        os.chmod(temporaire, 0o644)
        os.replace(temporaire, chemin)
    except BaseException:
        try:
            os.unlink(temporaire)
        except OSError:
            pass
        raise


def lire(chemin):
    """Dernier relevé écrit, ou None s'il n'existe pas encore."""
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    # Vérification manuelle : deux relevés CPU espacés d'1 s pour calculer la charge
    c = Collecteur()
    time.sleep(1)
    json.dump(c.releve(forcer_disques=True), sys.stdout, indent=4, ensure_ascii=False)
    print()
