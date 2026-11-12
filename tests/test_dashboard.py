"""Tests du dashboard Flask (ignorés si Flask n'est pas installé)."""
import base64
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "nas"))

try:
    import flask  # noqa: F401
except ImportError:
    flask = None

import config  # noqa: E402

if flask is not None:
    import dashboard  # noqa: E402


def auth(mdp):
    return {"Authorization": "Basic " + base64.b64encode(f":{mdp}".encode()).decode()}


class TestDernieresLignes(unittest.TestCase):
    def test_fin_de_fichier(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "f.csv")
            with open(chemin, "w") as f:
                f.write("".join(f"ligne {i}\n" for i in range(5000)))
            if flask is None:
                self.skipTest("Flask non installé")
            lignes = dashboard.lire_dernieres_lignes(chemin, 3, taille_bloc=64)
        self.assertEqual(lignes, ["ligne 4997", "ligne 4998", "ligne 4999"])


@unittest.skipIf(flask is None, "Flask non installé")
class TestApi(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        d = self.dossier.name
        self.chemin_config = os.path.join(d, "config.json")
        cfg = dict(config.DEFAUTS, mot_de_passe_hash=config.hacher_mot_de_passe("secret123"),
                   ntfy_url="http://localhost:8080/topic-tres-secret")
        config.enregistrer(cfg, self.chemin_config)
        with open(os.path.join(d, "climat.csv"), "w") as f:
            f.write("Date et Heure,Temperature_C,Humidite_Pct\n")
            for i in range(40):
                f.write(f"2026-11-12 10:{i:02d}:00,22.{i % 10},5{i % 10}.0\n")
            f.write("ligne abîmée\n")
        self.patch = mock.patch.object(config, "CHEMIN_CONFIG", self.chemin_config)
        self.patch.start()
        self.patch_sleep = mock.patch.object(dashboard.time, "sleep")
        self.patch_sleep.start()
        self.client = dashboard.app.test_client()

    def tearDown(self):
        self.patch_sleep.stop()
        self.patch.stop()
        self.dossier.cleanup()

    def post(self, donnees, headers=None):
        return self.client.post("/api/config", data=json.dumps(donnees),
                                content_type="application/json", headers=headers or {})

    def test_api_mesures(self):
        data = self.client.get("/api").get_json()
        self.assertEqual(len(data), dashboard.NB_POINTS)
        self.assertEqual(data[-1], {"time": "2026-11-12 10:39:00", "temp": 22.9, "hum": 59.0})

    def test_get_config_sans_secret(self):
        data = self.client.get("/api/config").get_json()
        texte = json.dumps(data)
        self.assertNotIn("topic-tres-secret", texte)
        self.assertNotIn("pbkdf2", texte)
        self.assertTrue(data["mot_de_passe_defini"])
        self.assertEqual(data["version"], dashboard.VERSION)

    def test_post_sans_mot_de_passe(self):
        r = self.post({"seuils": {"hum_max": 70}})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("WWW-Authenticate", r.headers)
        self.assertEqual(config.charger()["seuils"]["hum_max"], 80.0)

    def test_post_mauvais_mot_de_passe(self):
        r = self.post({"seuils": {"hum_max": 70}}, auth("faux"))
        self.assertEqual(r.status_code, 401)

    def test_post_valide(self):
        r = self.post({"seuils": {"hum_max": 70}, "ntfy_url": "http://pirate/x"},
                      auth("secret123"))
        self.assertEqual(r.status_code, 200, r.get_json())
        cfg = config.charger()
        self.assertEqual(cfg["seuils"]["hum_max"], 70.0)
        self.assertEqual(cfg["ntfy_url"], "http://localhost:8080/topic-tres-secret")

    def test_post_valeur_invalide(self):
        r = self.post({"seuils": {"hum_max": 500}}, auth("secret123"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("hum_max", r.get_json()["message"])

    def test_post_sans_mot_de_passe_defini(self):
        cfg = config.charger()
        cfg["mot_de_passe_hash"] = ""
        config.enregistrer(cfg)
        r = self.post({"seuils": {"hum_max": 70}}, auth("secret123"))
        self.assertEqual(r.status_code, 403)
        self.assertIn("--mot-de-passe", r.get_json()["message"])

    def test_fichiers_statiques(self):
        for chemin in ("/", "/static/js/app.js", "/static/css/style.css",
                       "/static/vendor/chart.umd.min.js", "/static/img/NAS.png"):
            with self.subTest(chemin=chemin):
                r = self.client.get(chemin)
                self.assertEqual(r.status_code, 200)
                r.close()

    def test_pas_d_acces_hors_static(self):
        r = self.client.get("/static/../config.py")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
