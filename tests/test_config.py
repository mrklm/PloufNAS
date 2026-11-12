"""Tests de la configuration partagée (nas/config.py)."""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "nas"))

import config  # noqa: E402


class TestValidation(unittest.TestCase):
    def test_config_vide_donne_les_defauts(self):
        self.assertEqual(config.valider_config({}), config.DEFAUTS)

    def test_reglages_valides(self):
        cfg = config.valider_reglages_dashboard(
            {"seuils": {"temp_max": 32, "hum_max": 70.5},
             "alertes_systeme": {"cpu": {"enabled": False, "threshold": 80}},
             "couleurs": {"temperature": "#00ff00"}},
            config.DEFAUTS)
        self.assertEqual(cfg["seuils"]["temp_max"], 32.0)
        self.assertEqual(cfg["seuils"]["hum_max"], 70.5)
        self.assertEqual(cfg["alertes_systeme"]["cpu"], {"enabled": False, "threshold": 80})
        self.assertEqual(cfg["couleurs"]["temperature"], "#00FF00")

    def test_base_non_modifiee(self):
        base = config.valider_config({})
        config.valider_reglages_dashboard({"seuils": {"temp_max": 40}}, base)
        self.assertEqual(base["seuils"]["temp_max"], 30.0)

    def test_valeurs_refusees(self):
        refus = [
            {"seuils": {"hum_max": 150}},
            {"seuils": {"temp_max": "30"}},
            {"seuils": {"temp_max": True}},
            {"seuils": {"temp_max": float("nan")}},
            {"alertes_systeme": {"cpu": {"threshold": 500}}},
            {"alertes_systeme": {"cpu": {"enabled": "oui"}}},
            {"couleurs": {"humidity": "red"}},
            {"couleurs": {"humidity": "#12345<"}},
            {"seuils": []},
            [],
        ]
        for donnees in refus:
            with self.subTest(donnees=donnees):
                with self.assertRaises(config.ConfigInvalide):
                    config.valider_reglages_dashboard(donnees, config.DEFAUTS)

    def test_le_dashboard_ne_peut_pas_modifier_ntfy_ni_le_mot_de_passe(self):
        cfg = config.valider_reglages_dashboard(
            {"ntfy_url": "http://pirate/x", "mot_de_passe_hash": "", "port_serie": "/dev/x",
             "alertes_systeme": {"inconnu": {"enabled": True}}},
            dict(config.DEFAUTS, mot_de_passe_hash="h"))
        self.assertEqual(cfg["ntfy_url"], config.DEFAUTS["ntfy_url"])
        self.assertEqual(cfg["mot_de_passe_hash"], "h")
        self.assertEqual(cfg["port_serie"], config.DEFAUTS["port_serie"])
        self.assertNotIn("inconnu", cfg["alertes_systeme"])

    def test_section_dashboard(self):
        cfg = config.valider_config({"dashboard": {"adresse": "127.0.0.1", "port": 8090,
                                                   "consultation_protegee": True}})
        self.assertEqual(cfg["dashboard"], {"adresse": "127.0.0.1", "port": 8090,
                                            "consultation_protegee": True,
                                            "derriere_proxy": False})
        for invalide in ({"port": 70000}, {"port": "5000"}, {"adresse": ""},
                         {"consultation_protegee": "oui"}, {"derriere_proxy": 1}):
            with self.subTest(invalide=invalide):
                with self.assertRaises(config.ConfigInvalide):
                    config.valider_config({"dashboard": invalide})

    def test_jeton_ntfy(self):
        self.assertEqual(config.valider_config({"ntfy_jeton": "tk_AbC-12_x"})["ntfy_jeton"],
                         "tk_AbC-12_x")
        for invalide in ("tk_a b", "tk_abc\n", "tk_a\nX-Autre: 1", 12, "x" * 129):
            with self.subTest(invalide=invalide):
                with self.assertRaises(config.ConfigInvalide):
                    config.valider_config({"ntfy_jeton": invalide})

    def test_le_dashboard_conserve_le_jeton(self):
        cfg = config.valider_reglages_dashboard(
            {"ntfy_jeton": "tk_pirate", "seuils": {"temp_max": 31}},
            dict(config.DEFAUTS, ntfy_jeton="tk_vrai"))
        self.assertEqual(cfg["ntfy_jeton"], "tk_vrai")

    def test_vue_publique_sans_secret(self):
        vue = config.vue_publique(dict(config.DEFAUTS, mot_de_passe_hash="h",
                                       ntfy_url="http://x/secret", ntfy_jeton="tk_secret"))
        self.assertNotIn("ntfy_url", vue)
        self.assertNotIn("tk_secret", json.dumps(vue))
        self.assertNotIn("mot_de_passe_hash", vue)
        self.assertTrue(vue["mot_de_passe_defini"])


class TestFichier(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = os.path.join(self.dossier.name, "config.json")

    def tearDown(self):
        self.dossier.cleanup()

    def lire(self, fichier):
        chemin = dict(zip(("config", "ntfy", "reglages"), config.chemins(self.chemin)))[fichier]
        with open(chemin) as f:
            return json.load(f)

    def mode(self, fichier):
        chemin = dict(zip(("config", "ntfy", "reglages"), config.chemins(self.chemin)))[fichier]
        return os.stat(chemin).st_mode & 0o777

    def test_creation_au_premier_chargement(self):
        cfg = config.charger(self.chemin)
        self.assertEqual(cfg, config.DEFAUTS)
        self.assertEqual(self.mode("config"), 0o600)
        self.assertEqual(self.mode("ntfy"), 0o600)
        self.assertEqual(self.mode("reglages"), 0o644)
        self.assertEqual(set(self.lire("ntfy")), {"ntfy_url", "ntfy_jeton"})
        self.assertEqual(set(self.lire("reglages")), {"seuils", "alertes_systeme", "couleurs"})
        self.assertFalse(set(self.lire("config")) & set(config.CLES_NTFY + config.CLES_REGLAGES))

    def test_repartition_d_un_ancien_config_json(self):
        with open(self.chemin, "w") as f:
            json.dump({"ntfy_url": "http://localhost:8080/mon-topic", "ntfy_jeton": "tk_x",
                       "mot_de_passe_hash": "h", "seuils": {"temp_max": 33},
                       "port_serie": "/dev/ttyACM0"}, f)
        os.chmod(self.chemin, 0o640)
        cfg = config.charger(self.chemin)
        self.assertEqual((cfg["ntfy_url"], cfg["ntfy_jeton"]), ("http://localhost:8080/mon-topic", "tk_x"))
        self.assertEqual(cfg["seuils"]["temp_max"], 33.0)
        self.assertEqual(self.lire("ntfy")["ntfy_url"], "http://localhost:8080/mon-topic")
        self.assertEqual(self.lire("reglages")["seuils"]["temp_max"], 33.0)
        base = self.lire("config")
        self.assertEqual((base["mot_de_passe_hash"], base["port_serie"]), ("h", "/dev/ttyACM0"))
        self.assertNotIn("ntfy_url", base)
        self.assertNotIn("seuils", base)
        self.assertEqual(self.mode("config"), 0o640, "droits réglés à l'installation conservés")
        self.assertEqual(config.charger(self.chemin), cfg)

    def test_fichiers_separes_prioritaires(self):
        config.charger(self.chemin)
        with open(self.chemin, "w") as f:   # ajout manuel d'une clé désormais sans effet
            json.dump({"seuils": {"temp_max": 40}}, f)
        self.assertEqual(config.charger(self.chemin, creer=False)["seuils"]["temp_max"], 30.0)
        self.assertEqual(config.cles_ignorees(self.chemin), ["seuils"])

    def test_reglages_limites_a_leurs_cles(self):
        config.charger(self.chemin)
        _, _, c_reglages = config.chemins(self.chemin)
        with open(c_reglages, "w") as f:
            json.dump({"seuils": {"hum_max": 60}, "mot_de_passe_hash": "",
                       "dashboard": {"consultation_protegee": False}, "ntfy_url": "http://x/y"}, f)
        base = dict(self.lire("config"))
        cfg = config.charger(self.chemin)
        self.assertEqual(cfg["seuils"]["hum_max"], 60.0)
        self.assertEqual(cfg["ntfy_url"], config.DEFAUTS["ntfy_url"])
        self.assertEqual(self.lire("config"), base)

    def test_ntfy_illisible_dashboard_sans_root(self):
        cfg = dict(config.DEFAUTS, ntfy_url="http://localhost:8080/secret", mot_de_passe_hash="h")
        config.enregistrer(cfg, self.chemin)
        ouvrir = open

        def refuser_ntfy(chemin, *a, **k):
            if os.path.basename(chemin) == config.NOM_NTFY:
                raise PermissionError(13, "Permission denied", chemin)
            return ouvrir(chemin, *a, **k)

        with mock.patch("builtins.open", side_effect=refuser_ntfy):
            lu = config.charger(self.chemin)
        self.assertEqual(lu["ntfy_url"], config.DEFAUTS["ntfy_url"])
        self.assertEqual(lu["mot_de_passe_hash"], "h")
        self.assertEqual(self.lire("ntfy")["ntfy_url"], "http://localhost:8080/secret")

    def test_config_illisible(self):
        config.charger(self.chemin)
        with mock.patch("builtins.open", side_effect=PermissionError(13, "refusé", self.chemin)):
            with self.assertRaises(config.ConfigInvalide):
                config.charger(self.chemin)

    def test_lien_symbolique_non_suivi(self):
        config.charger(self.chemin)
        _, _, c_reglages = config.chemins(self.chemin)
        cible = os.path.join(self.dossier.name, "cible")
        with open(cible, "w") as f:
            f.write("{}")
        os.chmod(cible, 0o666)
        os.remove(c_reglages)
        os.symlink(cible, c_reglages)
        config.enregistrer_reglages(config.DEFAUTS, self.chemin)
        self.assertFalse(os.path.islink(c_reglages))
        self.assertEqual(self.mode("reglages"), 0o644)
        with open(cible) as f:
            self.assertEqual(f.read(), "{}")

    def test_reprise_de_alertes_json(self):
        with open(os.path.join(self.dossier.name, "alertes.json"), "w") as f:
            json.dump({"cpu": {"enabled": False, "threshold": 65},
                       "colors": {"temperature": "#111111", "humidity": "#222222"}}, f)
        cfg = config.charger(self.chemin)
        self.assertEqual(cfg["alertes_systeme"]["cpu"], {"enabled": False, "threshold": 65})
        self.assertEqual(cfg["couleurs"]["humidity"], "#222222")

    def test_alertes_json_invalide_ignore(self):
        with open(os.path.join(self.dossier.name, "alertes.json"), "w") as f:
            f.write("{pas du json")
        self.assertEqual(config.charger(self.chemin), config.DEFAUTS)

    def test_aller_retour(self):
        cfg = config.valider_reglages_dashboard({"seuils": {"hum_max": 65}}, config.DEFAUTS)
        config.enregistrer(cfg, self.chemin)
        self.assertEqual(config.charger(self.chemin), cfg)
        for dossier, _, fichiers in os.walk(self.dossier.name):
            self.assertEqual([n for n in fichiers if n.endswith(".tmp")], [], dossier)

    def test_json_invalide(self):
        with open(self.chemin, "w") as f:
            f.write('{"seuils": ')
        with self.assertRaises(config.ConfigInvalide):
            config.charger(self.chemin)

    def test_chemin_csv(self):
        cfg = dict(config.DEFAUTS)
        self.assertEqual(config.chemin_csv(cfg, "/srv/m"), "/srv/m/climat.csv")
        cfg["fichier_csv"] = "/autre/climat.csv"
        self.assertEqual(config.chemin_csv(cfg, "/srv/m"), "/autre/climat.csv")


class TestCommandeMotDePasse(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(config, "CHEMIN_CONFIG",
                                       os.path.join(self.dossier.name, "config.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dossier.cleanup()

    def lancer(self, saisies):
        with mock.patch.object(config.getpass, "getpass", side_effect=saisies), \
             mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            return config.main(["--mot-de-passe"])

    def test_entree_en_double_ignoree(self):
        # Une touche Entrée en trop envoie une saisie vide à la confirmation
        self.assertEqual(self.lancer(["motdepasse1", "", "motdepasse1"]), 0)
        self.assertTrue(config.verifier_mot_de_passe(
            "motdepasse1", config.charger()["mot_de_passe_hash"]))

    def test_saisies_differentes(self):
        self.assertEqual(self.lancer(["motdepasse1", "autrechose"]), 1)
        self.assertEqual(config.charger()["mot_de_passe_hash"], "")

    def test_trop_court(self):
        self.assertEqual(self.lancer(["court"]), 1)


class TestCommandeJetonNtfy(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(config, "CHEMIN_CONFIG",
                                       os.path.join(self.dossier.name, "config.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dossier.cleanup()

    def lancer(self, argv, saisies=()):
        sortie = io.StringIO()
        with mock.patch.object(config.getpass, "getpass", side_effect=list(saisies)), \
             mock.patch("sys.stdout", sortie), mock.patch("sys.stderr"):
            code = config.main(argv)
        return code, sortie.getvalue()

    def test_enregistrement(self):
        code, _ = self.lancer(["--jeton-ntfy"], ["", " tk_0123456789abcdef "])
        self.assertEqual(code, 0)
        self.assertEqual(config.charger()["ntfy_jeton"], "tk_0123456789abcdef")

    def test_jeton_invalide(self):
        code, _ = self.lancer(["--jeton-ntfy"], ["tk_avec espace"])
        self.assertEqual(code, 1)
        self.assertEqual(config.charger()["ntfy_jeton"], "")

    def test_verifier_masque_le_jeton(self):
        self.lancer(["--jeton-ntfy"], ["tk_secret"])
        code, sortie = self.lancer(["--verifier"])
        self.assertEqual(code, 0)
        self.assertNotIn("tk_secret", sortie)
        self.assertIn('"ntfy_jeton": "(défini)"', sortie)


class TestMotDePasse(unittest.TestCase):
    def test_verification(self):
        h = config.hacher_mot_de_passe("correct horse")
        self.assertTrue(config.verifier_mot_de_passe("correct horse", h))
        self.assertFalse(config.verifier_mot_de_passe("mauvais", h))
        self.assertNotIn("correct horse", h)

    def test_hash_absent_ou_abime(self):
        self.assertFalse(config.verifier_mot_de_passe("x", ""))
        self.assertFalse(config.verifier_mot_de_passe("x", "pbkdf2_sha256$abc$zz$00"))
        self.assertFalse(config.verifier_mot_de_passe("x", "md5$1$00$00"))


if __name__ == "__main__":
    unittest.main()
