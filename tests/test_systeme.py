"""Tests du relevé matériel (nas/systeme.py) et des alertes système de monitor_climat.py."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "nas"))

import monitor_climat as mc  # noqa: E402
import systeme  # noqa: E402


def smartctl_json(passed=True, temp=35, realloues=0, attente=0, heures=41000):
    """Sortie JSON réaliste de smartctl 7.x pour un disque ATA."""
    return json.dumps({
        "smartctl": {"version": [7, 4], "exit_status": 0},
        "device": {"name": "/dev/sdb", "type": "sat"},
        "smart_status": {"passed": passed},
        "ata_smart_attributes": {"table": [
            {"id": 5, "name": "Reallocated_Sector_Ct", "raw": {"value": realloues, "string": str(realloues)}},
            {"id": 9, "name": "Power_On_Hours", "raw": {"value": heures, "string": str(heures)}},
            {"id": 194, "name": "Temperature_Celsius", "raw": {"value": temp, "string": str(temp)}},
            {"id": 197, "name": "Current_Pending_Sector", "raw": {"value": attente, "string": str(attente)}},
        ]},
        "power_on_time": {"hours": heures},
        "temperature": {"current": temp},
    })


LSBLK = json.dumps({"blockdevices": [
    {"name": "sda", "model": "KINGSTON SA400S37/120G", "serial": "50026B77", "size": 120034123776,
     "rota": False, "tran": "sata", "type": "disk"},
    {"name": "sdb", "model": "WDC WD30EFRX-68EUZN0", "serial": "WD-WCC4N1", "size": 3000592982016,
     "rota": True, "tran": "sata", "type": "disk"},
    {"name": "sr0", "model": "DVD", "serial": None, "size": 1073741312, "rota": True,
     "tran": "sata", "type": "rom"},
    {"name": "zram0", "model": None, "serial": None, "size": 1000, "rota": False,
     "tran": None, "type": "disk"},
]})


class Executeur:
    """Remplace subprocess.run : répond selon la commande, et note les appels."""

    def __init__(self, smart=None):
        self.smart = smart or {}       # nom -> (code, sortie)
        self.appels = []

    def __call__(self, cmd, **kwargs):
        self.appels.append(cmd)
        if cmd[0] == "lsblk":
            return subprocess.CompletedProcess(cmd, 0, LSBLK, "")
        nom = cmd[-1].rsplit("/", 1)[-1]
        code, sortie = self.smart.get(nom, (0, smartctl_json()))
        return subprocess.CompletedProcess(cmd, code, sortie, "")


class TestSmartctl(unittest.TestCase):
    def test_disque_sain(self):
        r = systeme.analyser_smartctl(0, smartctl_json(temp=36))
        self.assertEqual(r["etat"], "actif")
        self.assertEqual(r["temp"], 36)
        self.assertTrue(r["smart_ok"])
        self.assertEqual(r["heures"], 41000)

    def test_secteurs_realloues(self):
        # smartctl renvoie un code non nul (bits d'attributs) mais un JSON complet
        r = systeme.analyser_smartctl(64, smartctl_json(realloues=8, attente=2))
        self.assertFalse(r["smart_ok"])
        self.assertEqual(r["problemes"], ["8 secteurs réalloués", "2 secteurs en attente"])

    def test_autodiagnostic_en_echec(self):
        r = systeme.analyser_smartctl(8, smartctl_json(passed=False))
        self.assertFalse(r["smart_ok"])
        self.assertIn("auto-diagnostic SMART en échec", r["problemes"])

    def test_veille(self):
        self.assertEqual(systeme.analyser_smartctl(systeme.CODE_VEILLE, "")["etat"], "veille")
        sortie = json.dumps({"smartctl": {"messages": [
            {"string": "Device is in STANDBY mode, exit(3)", "severity": "information"}]}})
        self.assertEqual(systeme.analyser_smartctl(0, sortie)["etat"], "veille")

    def test_sortie_illisible(self):
        self.assertEqual(systeme.analyser_smartctl(2, "")["etat"], "indisponible")
        sortie = json.dumps({"smartctl": {"messages": [{"string": "Permission denied"}]}})
        r = systeme.analyser_smartctl(2, sortie)
        self.assertEqual(r["etat"], "indisponible")
        self.assertIn("Permission denied", r["message"])

    def test_commande_ne_reveille_pas(self):
        ex = Executeur()
        systeme.lire_smart("sdb", ex)
        self.assertIn("-n", ex.appels[0])
        self.assertEqual(ex.appels[0][ex.appels[0].index("-n") + 1], f"standby,{systeme.CODE_VEILLE}")

    def test_smartctl_absent(self):
        def absent(*a, **k):
            raise FileNotFoundError("smartctl")
        r = systeme.lire_smart("sdb", absent)
        self.assertEqual(r["etat"], "indisponible")
        self.assertIn("smartmontools", r["message"])


class TestDisques(unittest.TestCase):
    def test_liste_filtree(self):
        disques = systeme.lister_disques(Executeur())
        self.assertEqual([d["nom"] for d in disques], ["sda", "sdb"])
        self.assertEqual(disques[0]["type"], "SSD")
        self.assertEqual(disques[1]["type"], "HDD")
        self.assertEqual(disques[1]["taille"], 3000592982016)

    def test_veille_garde_la_derniere_valeur(self):
        horloge = [1000.0]
        ex = Executeur()
        c = systeme.Collecteur(executer=ex, horloge=lambda: horloge[0])
        c.releve_disques()
        ex.smart["sdb"] = (systeme.CODE_VEILLE, "")
        horloge[0] += systeme.INTERVALLE_DISQUES
        sdb = {d["nom"]: d for d in c.releve_disques()}["sdb"]
        self.assertEqual(sdb["etat"], "veille")
        self.assertEqual(sdb["temp"], 35)          # dernière valeur connue
        self.assertTrue(sdb["smart_ok"])

    def test_intervalle_entre_deux_releves(self):
        horloge = [1000.0]
        ex = Executeur()
        c = systeme.Collecteur(executer=ex, horloge=lambda: horloge[0])
        c.releve_disques()
        n = len(ex.appels)
        horloge[0] += 60
        c.releve_disques()
        self.assertEqual(len(ex.appels), n)        # pas de nouvel appel à smartctl
        horloge[0] += systeme.INTERVALLE_DISQUES
        c.releve_disques()
        self.assertGreater(len(ex.appels), n)


class TestCpu(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        racine = self.dossier.name

        def capteur(nom, valeurs):
            d = os.path.join(racine, f"hwmon{len(os.listdir(racine))}")
            os.mkdir(d)
            with open(os.path.join(d, "name"), "w") as f:
                f.write(nom + "\n")
            for i, (label, mdeg) in enumerate(valeurs, start=1):
                with open(os.path.join(d, f"temp{i}_input"), "w") as f:
                    f.write(f"{mdeg}\n")
                if label:
                    with open(os.path.join(d, f"temp{i}_label"), "w") as f:
                        f.write(label + "\n")
        self.capteur = capteur

    def tearDown(self):
        self.dossier.cleanup()

    def test_coretemp_package(self):
        self.capteur("acpitz", [(None, 27800)])
        self.capteur("coretemp", [("Package id 0", 41000), ("Core 0", 45000), ("Core 1", 39000)])
        self.assertEqual(systeme.temperature_cpu(self.dossier.name), 41.0)

    def test_sans_label_prend_le_maximum(self):
        self.capteur("k10temp", [(None, 50250), (None, 48000)])
        self.assertEqual(systeme.temperature_cpu(self.dossier.name), 50.2)

    def test_aucun_capteur(self):
        self.capteur("acpitz", [(None, 27800)])
        self.assertIsNone(systeme.temperature_cpu(self.dossier.name))
        self.assertIsNone(systeme.temperature_cpu("/chemin/inexistant"))

    def test_charge(self):
        self.assertEqual(systeme.charge_cpu((1000, 800), (2000, 1550)), 25)
        self.assertIsNone(systeme.charge_cpu(None, (2000, 1550)))
        self.assertIsNone(systeme.charge_cpu((1000, 800), (1000, 800)))

    def test_cpuinfo(self):
        chemin = os.path.join(self.dossier.name, "cpuinfo")
        with open(chemin, "w") as f:
            f.write("model name\t: Intel(R) Core(TM) i3-3240 CPU @ 3.40GHz\ncpu MHz\t\t: 1600.000\n"
                    "model name\t: Intel(R) Core(TM) i3-3240 CPU @ 3.40GHz\ncpu MHz\t\t: 3400.000\n")
        self.assertEqual(systeme.infos_cpuinfo(chemin),
                         ("Intel(R) Core(TM) i3-3240 CPU @ 3.40GHz", 2500))

    def test_fichier_aller_retour(self):
        chemin = os.path.join(self.dossier.name, "systeme.json")
        self.assertIsNone(systeme.lire(chemin))
        systeme.ecrire({"cpu": {"temp": 40}}, chemin)
        self.assertEqual(systeme.lire(chemin), {"cpu": {"temp": 40}})


def lsblk(*disques):
    return json.dumps({"blockdevices": [
        {"name": nom, "model": "WDC", "serial": serie, "size": 3000592982016,
         "rota": True, "tran": "sata", "type": "disk"} for nom, serie in disques]})


class ExecuteurVariable(Executeur):
    """Comme Executeur, mais la liste lsblk est modifiable entre deux relevés."""

    def __init__(self, disques, smart=None):
        super().__init__(smart)
        self.liste = disques

    def __call__(self, cmd, **kwargs):
        if cmd[0] == "lsblk":
            self.appels.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, lsblk(*self.liste), "")
        return super().__call__(cmd, **kwargs)


class TestDisquesAbsents(unittest.TestCase):
    def setUp(self):
        self.horloge = [1000.0]
        self.ex = ExecuteurVariable([("sdb", "WD-1"), ("sdc", "WD-2")])

    def collecteur(self, precedent=None):
        return systeme.Collecteur(executer=self.ex, horloge=lambda: self.horloge[0],
                                  precedent=precedent)

    def suivant(self, c):
        self.horloge[0] += systeme.INTERVALLE_DISQUES
        return {d["serie"]: d for d in c.releve_disques()}

    def test_disque_disparu_puis_revenu(self):
        c = self.collecteur()
        c.releve_disques()
        self.ex.liste = [("sdb", "WD-1")]
        disques = self.suivant(c)
        self.assertEqual(disques["WD-2"]["etat"], "absent")
        self.assertEqual(disques["WD-2"]["temp"], 35)          # dernière valeur connue
        depuis = disques["WD-2"]["absent_depuis"]
        self.assertEqual(self.suivant(c)["WD-2"]["absent_depuis"], depuis)
        self.ex.liste = [("sdb", "WD-1"), ("sdc", "WD-2")]
        disques = self.suivant(c)
        self.assertEqual(disques["WD-2"]["etat"], "actif")
        self.assertNotIn("absent_depuis", disques["WD-2"])

    def test_noms_echanges_sans_fausse_alerte(self):
        c = self.collecteur()
        c.releve_disques()
        self.ex.liste = [("sdc", "WD-1"), ("sdb", "WD-2")]     # noms inversés au redémarrage
        disques = self.suivant(c)
        self.assertEqual({d["etat"] for d in disques.values()}, {"actif"})
        self.assertEqual(disques["WD-1"]["nom"], "sdc")

    def test_echec_de_lsblk_ignore(self):
        c = self.collecteur()
        c.releve_disques()
        self.ex.liste = []
        self.assertEqual({d["etat"] for d in self.suivant(c).values()}, {"actif"})

    def test_disque_absent_au_redemarrage(self):
        avant = self.collecteur()
        precedent = {"disques": avant.releve_disques()}
        self.ex.liste = [("sdb", "WD-1")]                       # WD-2 n'a pas redémarré
        disques = {d["serie"]: d for d in self.collecteur(precedent).releve_disques()}
        self.assertEqual(disques["WD-2"]["etat"], "absent")

    def test_disque_deja_absent_oublie_au_redemarrage(self):
        precedent = {"disques": [{"nom": "sdd", "serie": "WD-3", "etat": "absent"}]}
        disques = {d["serie"]: d for d in self.collecteur(precedent).releve_disques()}
        self.assertNotIn("WD-3", disques)

    def test_compteur_d_echecs(self):
        c = self.collecteur()
        c.releve_disques()
        self.ex.smart["sdc"] = (2, "")
        self.assertEqual(self.suivant(c)["WD-2"]["echecs"], 1)
        self.assertEqual(self.suivant(c)["WD-2"]["echecs"], 2)
        del self.ex.smart["sdc"]
        self.assertEqual(self.suivant(c)["WD-2"]["echecs"], 0)

    def test_veille_n_est_pas_un_echec(self):
        c = self.collecteur()
        c.releve_disques()
        self.ex.smart["sdc"] = (systeme.CODE_VEILLE, "")
        self.suivant(c)
        self.assertEqual(self.suivant(c)["WD-2"]["echecs"], 0)


REGLAGES = {"cpu": {"enabled": True, "threshold": 75},
            "disks": {"enabled": True, "threshold": 50},
            "smart": {"enabled": True},
            "absent": {"enabled": True},
            "gpu": {"enabled": False, "threshold": 80}}


def releve(cpu=40, disques=None):
    if disques is None:
        disques = [{"nom": "sdb", "serie": "WD-1", "modele": "WDC", "etat": "actif",
                    "temp": 35, "smart_ok": True, "problemes": []}]
    return {"cpu": {"temp": cpu}, "disques": disques}


def disque(**kw):
    d = {"nom": "sdb", "serie": "WD-1", "modele": "WDC", "etat": "actif",
         "temp": 35, "smart_ok": True, "problemes": []}
    d.update(kw)
    return d


class Notif:
    def __init__(self, succes=True):
        self.succes = succes
        self.titres = []
        self.messages = []

    def __call__(self, titre, message, **kw):
        self.titres.append(titre)
        self.messages.append(message)
        return self.succes


class TestAlertesSysteme(unittest.TestCase):
    def test_cpu_avec_hysteresis(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        for t in (70, 76, 74, 76, 73, 71):
            a.verifier(releve(cpu=t), REGLAGES)
        self.assertEqual(n.titres, ["[ALERTE] Temperature CPU NAS",
                                    "[OK] Temperature CPU revenue a la normale"])

    def test_temperature_disque(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        a.verifier(releve(disques=[disque(temp=52)]), REGLAGES)
        a.verifier(releve(disques=[disque(temp=53)]), REGLAGES)
        self.assertEqual(n.titres, ["[ALERTE] Temperature disque NAS"])
        self.assertIn("WD-1", n.messages[0])        # le n° de série identifie le disque

    def test_smart_degrade(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        mauvais = disque(smart_ok=False, problemes=["8 secteurs réalloués"])
        a.verifier(releve(disques=[mauvais]), REGLAGES)
        a.verifier(releve(disques=[mauvais]), REGLAGES)
        self.assertEqual(n.titres, ["[URGENT] Etat SMART degrade"])
        self.assertIn("8 secteurs réalloués", n.messages[0])

    def test_disque_en_veille_ignore(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        a.verifier(releve(disques=[disque(temp=55)]), REGLAGES)
        # En veille, la dernière température (55) ne doit ni relancer ni lever l'alerte
        a.verifier(releve(disques=[disque(etat="veille", temp=55)]), REGLAGES)
        a.verifier(releve(disques=[disque(etat="veille", temp=30)]), REGLAGES)
        self.assertEqual(n.titres, ["[ALERTE] Temperature disque NAS"])

    def test_alerte_desactivee(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        reglages = dict(REGLAGES, cpu={"enabled": False, "threshold": 75})
        a.verifier(releve(cpu=90), reglages)
        self.assertEqual(n.titres, [])

    def test_desactivation_en_cours_d_alerte(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        a.verifier(releve(cpu=90), REGLAGES)
        a.verifier(releve(cpu=90), dict(REGLAGES, cpu={"enabled": False, "threshold": 75}))
        a.verifier(releve(cpu=90), REGLAGES)
        # Réactivée : la situation est signalée de nouveau
        self.assertEqual(n.titres.count("[ALERTE] Temperature CPU NAS"), 2)

    def test_echec_envoi_retente(self):
        n = Notif(succes=False)
        a = mc.AlertesSysteme(n)
        a.verifier(releve(cpu=90), REGLAGES)
        n.succes = True
        a.verifier(releve(cpu=90), REGLAGES)
        a.verifier(releve(cpu=90), REGLAGES)
        self.assertEqual(n.titres.count("[ALERTE] Temperature CPU NAS"), 2)

    def test_disque_disparu(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        a.verifier(releve(disques=[disque()]), REGLAGES)
        a.verifier(releve(disques=[disque(etat="absent", temp=55)]), REGLAGES)
        a.verifier(releve(disques=[disque(etat="absent", temp=55)]), REGLAGES)
        a.verifier(releve(disques=[disque()]), REGLAGES)
        self.assertEqual(n.titres, ["[URGENT] Disque disparu ou muet",
                                    "[OK] Disque de nouveau detecte"])
        self.assertIn("WD-1", n.messages[0])
        self.assertIn("n'apparaît plus", n.messages[0])

    def test_disque_muet_apres_deux_echecs(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        a.verifier(releve(disques=[disque(etat="indisponible", echecs=1)]), REGLAGES)
        self.assertEqual(n.titres, [])
        a.verifier(releve(disques=[disque(etat="indisponible", echecs=2,
                                          message="I/O error")]), REGLAGES)
        self.assertEqual(n.titres, ["[URGENT] Disque disparu ou muet"])
        self.assertIn("I/O error", n.messages[0])
        # Retour en veille : le disque répond (CHECK POWER MODE), l'alerte est levée
        a.verifier(releve(disques=[disque(etat="veille")]), REGLAGES)
        self.assertEqual(n.titres[-1], "[OK] Disque de nouveau detecte")

    def test_disque_disparu_desactive(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        reglages = dict(REGLAGES, absent={"enabled": False})
        a.verifier(releve(disques=[disque(etat="absent")]), reglages)
        self.assertEqual(n.titres, [])

    def test_releve_incomplet(self):
        n = Notif()
        a = mc.AlertesSysteme(n)
        a.verifier({"cpu": {"temp": None}, "disques": [disque(temp=None, smart_ok=None)]}, REGLAGES)
        a.verifier({}, REGLAGES)
        self.assertEqual(n.titres, [])


if __name__ == "__main__":
    unittest.main()
