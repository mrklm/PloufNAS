#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <SHT31.h>

// Protocole série (9600 bauds), une ligne toutes les 2 s :
//   DATA,<temp>,<hum>   mesure valide
//   ERR,<code>          lecture impossible (le NAS ne la compte pas comme une mesure)

LiquidCrystal_I2C lcd(0x3F, 16, 2);
SHT31 sht31;

bool capteurOK = false;

bool initCapteur() {
  if (sht31.begin()) {
    Serial.println("SHT31 initialise avec succes.");
    return true;
  }
  Serial.println("ERR,init");
  return false;
}

void afficherErreur(const char* ligne2) {
  lcd.setCursor(0, 0);
  lcd.print("Erreur capteur !");
  lcd.setCursor(0, 1);
  lcd.print(ligne2);
}

void setup() {
  Serial.begin(9600);
  Wire.begin();
  Wire.setClock(50000); // 50kHz pour la stabilité avec les clones

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Init LCD OK !");
  delay(1000);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Init SHT31...");

  capteurOK = initCapteur();
  lcd.setCursor(0, 1);
  lcd.print(capteurOK ? "Capteur OK !    " : "Echec init SHT31");
  delay(1500);
  lcd.clear();
}

void loop() {
  // Capteur absent au démarrage ou perdu : on retente l'initialisation.
  if (!capteurOK) {
    capteurOK = initCapteur();
    if (!capteurOK) {
      afficherErreur("Init impossible ");
      delay(2000);
      return;
    }
    lcd.clear();
  }

  // read() renvoie false si la lecture I2C échoue ; dans ce cas
  // getTemperature()/getHumidity() renverraient l'ancienne valeur.
  if (!sht31.read()) {
    Serial.print("ERR,read,");
    Serial.println(sht31.getError());
    afficherErreur("Lecture echouee ");
    if (!sht31.isConnected()) {
      capteurOK = false;
    }
    delay(2000);
    return;
  }

  float temp = sht31.getTemperature();
  float hum = sht31.getHumidity();

  if (isnan(temp) || isnan(hum)) {
    Serial.println("ERR,nan");
    afficherErreur("Valeur invalide ");
    delay(2000);
    return;
  }

  lcd.setCursor(0, 0);
  lcd.print("T: ");
  lcd.print(temp, 1);
  lcd.print(" C      ");

  lcd.setCursor(0, 1);
  lcd.print("H: ");
  lcd.print(hum, 1);
  lcd.print(" %      ");

  Serial.print("DATA,");
  Serial.print(temp, 1);
  Serial.print(",");
  Serial.println(hum, 1);

  delay(2000);
}
