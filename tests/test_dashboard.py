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
        self.patch_limiteur = mock.patch.object(dashboard, "limiteur", dashboard.Limiteur())
        self.patch_limiteur.start()
        self.client = dashboard.app.test_client()

    def tearDown(self):
        self.patch_limiteur.stop()
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

    def test_api_systeme(self):
        self.assertEqual(self.client.get("/api/systeme").get_json(), {"disponible": False})
        dashboard.systeme.ecrire({"horodatage": dashboard.time.time() - 120,
                                  "cpu": {"temp": 41.0}, "disques": []},
                                 os.path.join(self.dossier.name, "systeme.json"))
        data = self.client.get("/api/systeme").get_json()
        self.assertTrue(data["disponible"])
        self.assertEqual(data["cpu"]["temp"], 41.0)
        self.assertGreaterEqual(data["age"], 120)

    def modifier_config(self, **dashboard_):
        cfg = config.charger()
        cfg["dashboard"].update(dashboard_)
        config.enregistrer(cfg)

    def test_blocage_apres_plusieurs_echecs(self):
        for _ in range(dashboard.ESSAIS_MAX):
            self.assertEqual(self.post({"seuils": {"hum_max": 70}}, auth("faux")).status_code, 401)
        r = self.post({"seuils": {"hum_max": 70}}, auth("secret123"))   # même le bon est refusé
        self.assertEqual(r.status_code, 429)
        self.assertIn("Réessayez dans", r.get_json()["message"])

    def test_succes_remet_le_compteur_a_zero(self):
        for _ in range(dashboard.ESSAIS_MAX - 1):
            self.post({"seuils": {"hum_max": 70}}, auth("faux"))
        self.assertEqual(self.post({"seuils": {"hum_max": 70}}, auth("secret123")).status_code, 200)
        self.assertEqual(self.post({"seuils": {"hum_max": 70}}, auth("faux")).status_code, 401)

    def test_blocage_leve_apres_la_fenetre(self):
        horloge = [1000.0]
        l = dashboard.Limiteur(essais_max=2, fenetre=60, horloge=lambda: horloge[0])
        l.echec("1.2.3.4")
        l.echec("1.2.3.4")
        self.assertGreater(l.attente("1.2.3.4"), 0)
        self.assertEqual(l.attente("5.6.7.8"), 0)       # les autres adresses ne sont pas bloquées
        horloge[0] += 61
        self.assertEqual(l.attente("1.2.3.4"), 0)

    def test_requete_d_un_autre_site_refusee(self):
        r = self.post({"seuils": {"hum_max": 70}},
                      dict(auth("secret123"), **{"Sec-Fetch-Site": "cross-site"}))
        self.assertEqual(r.status_code, 403)

    def test_post_non_json_refuse(self):
        r = self.client.post("/api/config", data="seuils=1", content_type="text/plain",
                             headers=auth("secret123"))
        self.assertEqual(r.status_code, 400)

    def test_en_tetes_de_securite(self):
        r = self.client.get("/")
        self.assertIn("script-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        r.close()
        self.assertEqual(self.client.get("/api").headers["Cache-Control"], "no-store")

    def test_page_sans_code_en_ligne(self):
        r = self.client.get("/")
        page = r.get_data(as_text=True)
        r.close()
        self.assertNotRegex(page, r"\son[a-z]+=")       # onclick, onerror…
        self.assertNotIn("<script>", page)
        self.assertNotIn("style=", page)

    def test_consultation_libre_par_defaut(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        r.close()

    def test_consultation_protegee(self):
        self.modifier_config(consultation_protegee=True)
        r = self.client.get("/api")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Basic", r.headers["WWW-Authenticate"])   # fenêtre du navigateur
        self.assertEqual(self.client.get("/api", headers=auth("secret123")).status_code, 200)
        r = self.client.get("/static/js/app.js", headers=auth("faux"))
        self.assertEqual(r.status_code, 401)
        r.close()

    def test_consultation_protegee_post_sans_fenetre_navigateur(self):
        self.modifier_config(consultation_protegee=True)
        r = self.post({"seuils": {"hum_max": 70}}, auth("faux"))
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("WWW-Authenticate", r.headers)

    def test_consultation_protegee_sans_mot_de_passe(self):
        cfg = config.charger()
        cfg["mot_de_passe_hash"] = ""
        cfg["dashboard"]["consultation_protegee"] = True
        config.enregistrer(cfg)
        self.assertEqual(self.client.get("/").status_code, 503)    # fermé, pas ouvert

    def test_le_navigateur_ne_peut_pas_ouvrir_la_consultation(self):
        self.modifier_config(consultation_protegee=True)
        r = self.post({"dashboard": {"consultation_protegee": False}}, auth("secret123"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(config.charger()["dashboard"]["consultation_protegee"])

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
