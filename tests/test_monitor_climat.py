"""Tests de la logique de surveillance (sans matériel ni ntfy).

Lancement depuis la racine du dépôt :
    python3 -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "nas"))

import monitor_climat as mc  # noqa: E402


class HorlogeFactice:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class NotifierFactice:
    def __init__(self, succes=True):
        self.succes = succes
        self.titres = []

    def __call__(self, titre, message, priorite="default", tags="warning"):
        self.titres.append(titre)
        return self.succes


class PortFactice:
    def __init__(self, lignes):
        self.lignes = list(lignes)

    @property
    def in_waiting(self):
        return len(self.lignes)

    def readline(self):
        return self.lignes.pop(0)


def nouvelle_surveillance(succes=True):
    notif = NotifierFactice(succes)
    horloge = HorlogeFactice()
    return mc.Surveillance(notifier=notif, horloge=horloge), notif, horloge


class TestAnalyserLigne(unittest.TestCase):
    def test_ligne_valide(self):
        self.assertEqual(mc.analyser_ligne(b"DATA,22.4,47.2\r\n"), (22.4, 47.2))

    def test_ligne_tronquee_rejetee(self):
        self.assertIsNone(mc.analyser_ligne(b"DATA,22.4,4"))

    def test_erreur_capteur(self):
        self.assertEqual(mc.analyser_ligne(b"ERR,read,130\r\n"), "ERR")

    def test_message_info_ignore(self):
        self.assertIsNone(mc.analyser_ligne(b"SHT31 initialise avec succes.\r\n"))

    def test_valeurs_hors_plage(self):
        self.assertIsNone(mc.analyser_ligne(b"DATA,22.4,130.0\n"))
        self.assertIsNone(mc.analyser_ligne(b"DATA,-60.0,40.0\n"))
        self.assertIsNone(mc.analyser_ligne(b"DATA,nan,40.0\n"))

    def test_ligne_illisible(self):
        self.assertIsNone(mc.analyser_ligne(b"DATA,\xff\xfe,1\n"))
        self.assertIsNone(mc.analyser_ligne(b"DATA,22.4\n"))
        self.assertIsNone(mc.analyser_ligne(b"DATA,a,b\n"))


class TestLireDerniereValeur(unittest.TestCase):
    def test_garde_la_derniere_ligne_valide(self):
        port = PortFactice([b"DATA,20.0,40.0\n", b"DATA,21.0,41.0\n", b"DATA,22.0,4"])
        self.assertEqual(mc.lire_derniere_valeur(port), (21.0, 41.0))

    def test_buffer_vide(self):
        self.assertIsNone(mc.lire_derniere_valeur(PortFactice([])))


class TestSeuils(unittest.TestCase):
    def test_alerte_puis_retour(self):
        s, notif, _ = nouvelle_surveillance()
        s.enregistrer_mesure(22.0, 85.0)
        self.assertEqual(s.etat_hum, "alerte")
        s.enregistrer_mesure(22.0, 70.0)
        self.assertEqual(s.etat_hum, "normal")
        self.assertEqual(notif.titres, ["[ALERTE] Humidite NAS",
                                        "[OK] Humidite NAS revenue a la normale"])

    def test_pas_de_spam_en_alerte(self):
        s, notif, _ = nouvelle_surveillance()
        for _ in range(5):
            s.enregistrer_mesure(31.0, 50.0)
        self.assertEqual(notif.titres, ["[ALERTE] Temperature NAS"])

    def test_hysteresis(self):
        s, notif, _ = nouvelle_surveillance()
        # Oscillation autour de 80 % : une seule alerte, pas de retour à la normale
        for hum in (80.5, 79.5, 80.5, 79.0, 80.2):
            s.enregistrer_mesure(22.0, hum)
        self.assertEqual(notif.titres, ["[ALERTE] Humidite NAS"])
        s.enregistrer_mesure(22.0, mc.HUM_MAX - mc.HUM_HYSTERESIS)
        self.assertEqual(s.etat_hum, "normal")

    def test_echec_envoi_retente(self):
        s, notif, _ = nouvelle_surveillance(succes=False)
        s.enregistrer_mesure(22.0, 85.0)
        self.assertEqual(s.etat_hum, "normal")   # alerte non perdue : état inchangé
        notif.succes = True
        s.enregistrer_mesure(22.0, 85.0)
        self.assertEqual(s.etat_hum, "alerte")
        self.assertEqual(notif.titres.count("[ALERTE] Humidite NAS"), 2)


class TestSilence(unittest.TestCase):
    def test_capteur_muet_des_le_demarrage(self):
        s, notif, horloge = nouvelle_surveillance()
        horloge.t += mc.DELAI_SANS_DONNEES + 1
        s.verifier_silence()
        self.assertEqual(notif.titres, ["[URGENT] Plus de donnees du capteur"])

    def test_pas_d_alerte_avant_le_delai(self):
        s, notif, horloge = nouvelle_surveillance()
        horloge.t += mc.DELAI_SANS_DONNEES - 1
        s.verifier_silence()
        self.assertEqual(notif.titres, [])

    def test_erreurs_capteur_ne_comptent_pas_comme_mesures(self):
        s, notif, horloge = nouvelle_surveillance()
        for _ in range(10):
            horloge.t += mc.DELAI_SANS_DONNEES / 9
            s.enregistrer_erreur_capteur()
            s.verifier_silence()
        self.assertEqual(notif.titres, ["[URGENT] Plus de donnees du capteur"])

    def test_retour_des_donnees(self):
        s, notif, horloge = nouvelle_surveillance()
        horloge.t += mc.DELAI_SANS_DONNEES + 1
        s.verifier_silence()
        s.verifier_silence()   # pas de doublon
        s.enregistrer_mesure(22.0, 50.0)
        s.verifier_silence()
        self.assertEqual(notif.titres, ["[URGENT] Plus de donnees du capteur",
                                        "[OK] Capteur de nouveau operationnel"])

    def test_echec_envoi_silence_retente(self):
        s, notif, horloge = nouvelle_surveillance(succes=False)
        horloge.t += mc.DELAI_SANS_DONNEES + 1
        s.verifier_silence()
        self.assertEqual(s.etat_donnees, "normal")
        notif.succes = True
        s.verifier_silence()
        self.assertEqual(s.etat_donnees, "alerte")


class TestEcriture(unittest.TestCase):
    def test_alerte_unique_puis_retablissement(self):
        s, notif, _ = nouvelle_surveillance()
        s.signaler_ecriture(False, OSError("absent"))
        s.signaler_ecriture(False, OSError("absent"))
        s.signaler_ecriture(True)
        self.assertEqual(notif.titres, ["[URGENT] Ecriture CSV impossible",
                                        "[OK] Ecriture CSV retablie"])

    def test_ecrire_csv_cree_l_entete(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "climat.csv")
            with mock.patch.object(mc, "fichier_log", chemin):
                mc.ecrire_csv("2026-11-12 10:00:00", 22.4, 47.2)
                mc.ecrire_csv("2026-11-12 10:01:00", 22.5, 47.0)
            with open(chemin) as f:
                contenu = f.read()
        self.assertEqual(contenu, mc.ENTETE_CSV
                         + "2026-11-12 10:00:00,22.4,47.2\n"
                         + "2026-11-12 10:01:00,22.5,47.0\n")

    def test_dossier_absent_leve_oserror(self):
        with mock.patch.object(mc, "fichier_log", "/chemin/inexistant/climat.csv"):
            with self.assertRaises(OSError):
                mc.ecrire_csv("2026-11-12 10:00:00", 22.4, 47.2)


class TestRechargementConfig(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = os.path.join(self.dossier.name, "config.json")
        # Sauvegarde des variables globales modifiées par appliquer_config()
        self.sauvegarde = {k: getattr(mc, k) for k in (
            "port_serie", "fichier_log", "NTFY_URL", "TEMP_MAX", "HUM_MAX",
            "TEMP_HYSTERESIS", "HUM_HYSTERESIS")}
        self.patch = mock.patch.object(mc.config, "CHEMIN_CONFIG", self.chemin)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for k, v in self.sauvegarde.items():
            setattr(mc, k, v)
        self.dossier.cleanup()

    def ecrire(self, contenu):
        with open(self.chemin, "w") as f:
            f.write(contenu)
        # Garantit une signature différente même si l'écriture tombe dans la même ns
        os.utime(self.chemin, ns=(time.time_ns(), time.time_ns() + self.decalage))
        self.decalage += 1_000_000

    decalage = 0

    def test_chargement_et_rechargement(self):
        suivi = mc.SuiviConfig()
        suivi.charger_initial()     # crée config.json avec les valeurs par défaut
        self.assertEqual(mc.HUM_MAX, 80.0)
        self.assertEqual(mc.fichier_log, os.path.join(self.dossier.name, "climat.csv"))
        self.assertFalse(suivi.recharger_si_modifiee())

        self.ecrire(json.dumps({"seuils": {"hum_max": 65}, "ntfy_url": "http://n/t"}))
        self.assertTrue(suivi.recharger_si_modifiee())
        self.assertEqual(mc.HUM_MAX, 65.0)
        self.assertEqual(mc.NTFY_URL, "http://n/t")

    def test_config_invalide_ignoree(self):
        suivi = mc.SuiviConfig()
        suivi.charger_initial()
        self.ecrire('{"seuils": {"hum_max": 500}}')
        self.assertFalse(suivi.recharger_si_modifiee())
        self.assertEqual(mc.HUM_MAX, 80.0)

    def test_nouveau_seuil_utilise_par_la_surveillance(self):
        suivi = mc.SuiviConfig()
        suivi.charger_initial()
        s, notif, _ = nouvelle_surveillance()
        s.enregistrer_mesure(22.0, 70.0)
        self.assertEqual(notif.titres, [])
        self.ecrire(json.dumps({"seuils": {"hum_max": 65}}))
        suivi.recharger_si_modifiee()
        s.enregistrer_mesure(22.0, 70.0)
        self.assertEqual(notif.titres, ["[ALERTE] Humidite NAS"])


class TestEnvoyerNtfy(unittest.TestCase):
    def test_succes(self):
        with mock.patch.object(mc.requests, "post", return_value=mock.Mock(ok=True)):
            self.assertTrue(mc.envoyer_ntfy("t", "m"))

    def test_refus_http(self):
        with mock.patch.object(mc.requests, "post",
                               return_value=mock.Mock(ok=False, status_code=500)):
            self.assertFalse(mc.envoyer_ntfy("t", "m"))

    def test_serveur_injoignable(self):
        with mock.patch.object(mc.requests, "post",
                               side_effect=mc.requests.ConnectionError("down")):
            self.assertFalse(mc.envoyer_ntfy("t", "m"))

    def entetes_envoyes(self, jeton, statut=200):
        with mock.patch.object(mc, "NTFY_JETON", jeton), \
             mock.patch.object(mc.requests, "post", return_value=mock.Mock(
                 ok=statut < 400, status_code=statut)) as post:
            resultat = mc.envoyer_ntfy("t", "m")
        return resultat, post.call_args.kwargs["headers"]

    def test_sans_jeton_pas_d_authentification(self):
        _, entetes = self.entetes_envoyes("")
        self.assertNotIn("Authorization", entetes)

    def test_jeton_envoye(self):
        ok, entetes = self.entetes_envoyes("tk_abc")
        self.assertTrue(ok)
        self.assertEqual(entetes["Authorization"], "Bearer tk_abc")

    def test_jeton_refuse(self):
        for statut in (401, 403):
            with self.subTest(statut=statut), self.assertLogs("monitor_climat", "WARNING") as logs:
                ok, _ = self.entetes_envoyes("tk_faux", statut)
            self.assertFalse(ok)
            self.assertIn("ntfy_jeton", logs.output[0])

    def test_jeton_exige_par_le_serveur(self):
        with self.assertLogs("monitor_climat", "WARNING") as logs:
            ok, _ = self.entetes_envoyes("", 403)
        self.assertFalse(ok)
        self.assertIn("--jeton-ntfy", logs.output[0])

    def test_jeton_en_clair(self):
        self.assertFalse(mc.jeton_en_clair("http://localhost:8080/t", "tk_a"))
        self.assertFalse(mc.jeton_en_clair("http://127.0.0.1:8080/t", "tk_a"))
        self.assertFalse(mc.jeton_en_clair("https://ntfy.example.org/t", "tk_a"))
        self.assertFalse(mc.jeton_en_clair("http://192.168.1.10:8080/t", ""))
        self.assertTrue(mc.jeton_en_clair("http://192.168.1.10:8080/t", "tk_a"))

    def test_jeton_recharge_avec_la_config(self):
        cfg = mc.config.valider_config({"ntfy_jeton": "tk_nouveau"})
        ancien = mc.NTFY_JETON
        try:
            mc.appliquer_config(cfg)
            self.assertEqual(mc.NTFY_JETON, "tk_nouveau")
        finally:
            mc.appliquer_config(mc.config.valider_config({"ntfy_jeton": ancien}))


if __name__ == "__main__":
    unittest.main()
