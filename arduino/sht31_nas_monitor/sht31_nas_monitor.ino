#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <SHT31.h>

// Protocole série (9600 bauds), une ligne toutes les 2 s :
//   DATA,<temp>,<hum>   mesure valide
//   ERR,<code>          lecture impossible (le NAS ne la compte pas comme une mesure)

LiquidCrystal_I2C lcd(0x3F, 16, 2);
SHT31 sht31;

bool capteurOK = false;

// Un composant I2C (capteur ou LCD) peut rester bloqué au milieu d'un échange, par
// exemple après une coupure brève de l'USB au redémarrage du NAS : il maintient SDA
// à 0 et la carte attend indéfiniment. Ce blocage survit au reset de l'Arduino, car
// le capteur et le LCD restent alimentés ; seul un débranchement le levait.
// Remède : jusqu'à 9 impulsions sur SCL pour que le composant termine son octet et
// relâche SDA, puis une condition STOP.
void libererBusI2C() {
  pinMode(SDA, INPUT_PULLUP);
  pinMode(SCL, INPUT_PULLUP);
  delayMicroseconds(10);
  for (int i = 0; i < 9 && digitalRead(SDA) == LOW; i++) {
    pinMode(SCL, OUTPUT);
    digitalWrite(SCL, LOW);
    delayMicroseconds(10);
    pinMode(SCL, INPUT_PULLUP);
    delayMicroseconds(10);
  }
  // STOP : SDA passe de 0 à 1 pendant que SCL est à 1
  pinMode(SDA, OUTPUT);
  digitalWrite(SDA, LOW);
  delayMicroseconds(10);
  pinMode(SDA, INPUT_PULLUP);
  delayMicroseconds(10);
}

// (Re)démarre le bus I2C et le LCD. lcd.init() appelle Wire.begin(), qui remet
// l'horloge à 100 kHz : la vitesse et le délai maximal se règlent donc après.
void demarrerI2C() {
  libererBusI2C();
  lcd.init();
  lcd.backlight();
  Wire.setClock(50000); // 50kHz pour la stabilité avec les clones
  // Sans délai maximal (désactivé par défaut), un échange I2C bloqué fige la carte
  // pour toujours. Nécessite le cœur Arduino AVR 1.8.3 ou plus récent.
  Wire.setWireTimeout(25000, true);
}

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
  demarrerI2C();

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
    // Le bus est peut-être bloqué : on le libère avant de réessayer.
    Wire.end();
    demarrerI2C();
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
