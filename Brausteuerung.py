import RPi.GPIO as GPIO
import time
import datetime
import board
import busio
import digitalio
import adafruit_max31865
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import json
import sqlite3
import os.path
import logging
import traceback
# --------------Display Libs ------------
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106, ssd1306
from PIL import ImageFont, ImageDraw, Image
# ---------------------------------------

# --------------Encoder Lib -------------
# pip3 install encoder (um die Lib zu installieren
# CLK - Clock
# DT  - Direction
# SW  - Push button switch control
# +   - 3.3V
# GND - Ground
import Encoder
# ---------------------------------------

#OLED Display auf I2C Bus initialisieren
# Vcc - 3.3V
# Gnd - Ground
# SCL - I2C SCL
# SDA - I2C SCA
serial = i2c(port=1, address=0x3C)
device = sh1106(serial)
oled_font = ImageFont.truetype('FreeSans.ttf', 14)
logo = Image.open('hop3.png').convert("RGBA")

# GPIO ueber Nummern ansprechen
GPIO.setmode(GPIO.BCM)
# Warnungen ausschalten
GPIO.setwarnings(False)

# Initialize MAX31865 board
# Pi 3V3 to sensor VIN
# Pi GND to sensor GND
# Pi MOSI to sensor SDI
# Pi MISO to sensor SDO
# Pi SCLK to sensor CLK
# Pi GPIO23 to sensor CS (or use any other free GPIO pin)
# The I2C interface is disabled by default so you need to enable it. You can do this within the raspi-config tool on the command line by running :
# sudo raspi-config
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
# Chip select of the MAX31865 board GPIO 23
cs = digitalio.DigitalInOut(board.D23)  
Sensor = adafruit_max31865.MAX31865(spi, cs)

# Rote Steckdose GPIO
redGPIO = 17
# Blaue Steckdose GPIO
blueGPIO = 18
# Beeper GPIO
beepGPIO = 24


# Encoder GPIO 1
encoderDrehGPIO_1 = 14
# Encoder GPIO 2
encoderDrehGPIO_2 = 15
# Encoder Push GPIO
encoderPushGPIO = 25


# Logger erstellen
logger = logging.getLogger('Brew')
logger.setLevel(logging.DEBUG)

# Console handler erstellen und Log-Level setzen
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Formatter erstellen
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
                                datefmt='%H:%M:%S')

# Formatter zu console handler hinzufügen
ch.setFormatter(formatter)

# Console Handler zu Logger hinzufügen
logger.addHandler(ch)

# File Handler erstellen und Log-Level setzen
fh = logging.FileHandler('brewing.log', mode= 'w')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

# def Timestamp():
#     # Funktion ermittelt die aktuelle Zeit in hh:mm:ss
#     x = datetime.datetime.now()
#     return x.strftime("%H:%M:%S")
    
class Beeper:
    def __init__(self, Pin):
        self.Pin = Pin
        # Pin als Output definieren
        GPIO.setup(self.Pin, GPIO.OUT)
        # Beeper ausschalten
        GPIO.output(self.Pin, GPIO.LOW)
        
    def makeBeep(self, timeOn, timeOff):
        # Schaltet den Beeper für eine definierte Zeit ein und danach für eine definierte Zeit aus
        GPIO.output(self.Pin, GPIO.HIGH)
        logger.debug("Beep on")
        time.sleep(timeOn)
        logger.debug("Beep off")
        GPIO.output(self.Pin, GPIO.LOW)
        time.sleep(timeOff)
        
    
class Switch:
    def __init__(self, Pin, Name):
        self.Pin = Pin
        self.Name = Name
        # Pin als Output definieren
        GPIO.setup(self.Pin, GPIO.OUT)
        # Steckdose schalten HIGH = AUS!!!
        GPIO.output(self.Pin, GPIO.HIGH)
        # Status der Steckdose ist ausgeschaltet
        self.State = False
        logger.info(f"Init {self.Name} at Pin {self.Pin}")

    def On(self):
        # Wenn Steckdose aus, dann einschalten
        if self.State == False:
            # Steckdose schalten LOW = AN!!!
            GPIO.output(self.Pin, GPIO.LOW)
            self.State = True
            logger.debug(f"{self.Name} On")
    
    def Off(self):
        # Wenn Steckdose an, dann ausschalten
        if self.State == True:
            # Steckdose schalten High = AUS!!!
            GPIO.output(self.Pin, GPIO.HIGH)
            self.State = False
            logger.debug(f"{self.Name} Off")
            
class Brew:
    def __init__(self, heizGPIO, ruehrGPIO, beeperGPIO, dreh1GPIO, dreh2GPIO, pushGPIO):
        #Leere Listen erzeugen
        self.TempList = []
        self.SollList = []
        self.xList = []
        
        # Zähler der Daten in CSV Datei
        self.counterRow = 0
        # Letzter Temperatur-Meßwert
        self.lastTemp = 0
        
        # Rote Steckdose - Heizung
        self.RedSwitch = Switch(heizGPIO, "RedSwitch")
        # Blaue Steckdos - Rührer
        self.BlueSwitch = Switch(ruehrGPIO, "BlueSwitch")
        
        # Beeper
        self.beeper = Beeper(beeperGPIO)
        
        # Encoder
        self.dreh = Encoder.Encoder(dreh1GPIO, dreh2GPIO)
        GPIO.setup(pushGPIO, GPIO.IN)
        GPIO.add_event_detect(pushGPIO, GPIO.FALLING, callback=self.pushButton, bouncetime=30)
        
        #Datenbank initialisieren
        self.initDB()
        
    def initDB(self):
        # Prüfen, ob es die Datenbank gibt
        if os.path.isfile('Brauer.db'):
            logger.info("Datenbank vorhanden")
            # mit Datenbank verbinden
            self.conn = sqlite3.connect('Brauer.db')
            # DB Curor erzeugen
            self.dbCursor = self.conn.cursor()
            with self.conn:
                # Alte Messwerte löschen, indem Tabelle gedroppt wird
                self.dbCursor.execute("DROP TABLE Messwerte")
                logger.info("Alte Messerte gelöscht")
                # Alten Status löschen
                self.dbCursor.execute("DROP TABLE Status")
                logger.info("Alten Status gelöscht")
        else:
            logger.info("Neue Datenbank anlegen")
            # mit Datenbank verbinden
            self.conn = sqlite3.connect('Brauer.db')
            # DB Curor erzeugen
            self.dbCursor = self.conn.cursor()
            # Tabelle für die Rasten anlegen
            self.dbCursor.execute("CREATE TABLE Rasten (Name text, SollTemp real, Dauer real, Jodprobe integer)")
            self.conn.commit()
            
        with self.conn:
            # Tabelle für die neuen Meßwerte anlegen
            self.dbCursor.execute("CREATE TABLE Messwerte (Counter integer, IstTemp real, SollTemp real)")
            
            # Tabelle für die Status anlegen
            self.dbCursor.execute("CREATE TABLE Status (StateName text, State text)")
            # Status setzen
            self.dbCursor.execute("INSERT INTO Status VALUES (:Braustatus, :Status)", {'Braustatus' : "Brewstate", 'Status' : "Wait"})
            # Wenn eine Jodprobe durchgeführt werden muss, dann kann der Status von einem externen Programm über die DB geändert werden
            self.dbCursor.execute("INSERT INTO Status VALUES (:Jodprobe, :Status)", {'Jodprobe' : "Jodprobe", 'Status' : "None"})
            # Der Modus gibt an, ob die Eingabe der Steuerungswerte manuell oder automatisch erfolgen soll - None = unbestimmt
            # Dieser Wert kann von einem externen Programm über die Datenbank geändert werden
            self.dbCursor.execute("INSERT INTO Status VALUES (:Modus, :Status)", {'Modus' : "Modus", 'Status' : "None"})
            

    def checkInputMode(self):
        # Das Ergebnis, ob die Werte manuell oder automatisch eingegeben werden sollen,
        # kann über den Schalter des Encoders oder über die Datenbank eingegeben werden
        
        # Status in DB setzen
        self.dbCursor.execute("UPDATE Status SET State = :Status WHERE StateName = :BState",{'Status' : 'Wait', 'BState' : 'Modus'})
        self.conn.commit()
        
        # Aufmerksamkeitston
        self.beeper.makeBeep(0.5, 0)
        
        self.AlteZahl = 0
        self.buttonState = False
        self.anzeige = "automatisch"
        self.result = True
        
        self.dbCursor.execute("SELECT State FROM Status WHERE StateName = 'Modus'")
        self.jResult = self.dbCursor.fetchone()
        
        logger.info('Modus auswählen')
        
        # Der buttonState wird in der Interupt-Routine geändert
        while (self.buttonState != True) and (self.jResult[0] == "Wait"):
            #Stellung des Encoders lesen
            self.DrehZahl = self.dreh.read()
            if ((self.DrehZahl > (self.AlteZahl + 6)) or (self.DrehZahl < (self.AlteZahl - 6))):
                # Stellung des Encoders hat sich signifikant geändert
                # Anzeige ändern
                if self.anzeige == 'manuell':
                    self.anzeige = "automatisch"
                    self.result = False
                else: 
                    self.anzeige = "manuell"
                    self.result = True
                # Neu Zahl speichern
                self.AlteZahl = self.DrehZahl
            
            try:
                with canvas(device) as draw:
                    #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
                    draw.text((15, 0), "Steuerung", font = oled_font, fill = "white")
                    draw.text((15, 20), "auto/ manuell?", font = oled_font, fill = "white")
                    draw.text((15, 40), self.anzeige, font = oled_font, fill = "white")
            except:
                logging.error(f"Fehler beim Schreiben auf Display: {traceback.format_exc()}")
                
            time.sleep(0.25)
            
            # Status der Abfrage aus DB lesen
            self.dbCursor.execute("SELECT State FROM Status WHERE StateName = 'Modus'")
            self.jResult = self.dbCursor.fetchone()
            
            # Prüfen, ob ein ungültiger Status vorliegt
            if (self.jResult[0] != 'Automatic') and (self.jResult[0] != 'Manual') and (self.jResult[0] != 'Wait'):
                # Status ist ungültig - wird ignoriert
                logger.error("Ungültiger Status: {}".format(str(self.jResult[0])))
                self.jResult = ('Wait', )
                # Status in DB überschreiben
                self.dbCursor.execute("UPDATE Status SET State = :Status WHERE StateName = :BState",
                                      {'Status' : 'Wait', 'BState' : 'Modus'})
                self.conn.commit()
                
            if self.jResult[0] == 'Manual':
                logger.info("Manuelle Eingabe der Werte")
                self.result = True
            elif self.jResult[0] == 'Automatic':
                logger.info("Eingabe der Werte über DB")
                self.result = False

        # Bestätigungston
        self.beeper.makeBeep(0.1, 0)
        
        return self.result
        
        
    def getValue(self, textOne, textTwo, startVal, minVal):
        # aktuelle Stellung des Encoders lesen - Nullpunkt setzen
        self.AlteZahl = self.dreh.read()
        # Status des Push Buttons setzen
        self.buttonState = False
        # Default Wert für die Eingabe
        self.mNum = startVal
        
        # Der buttonState wird in der Interupt-Routine geändert
        while (self.buttonState != True):
            # Stellung des Encoders lesen
            self.DrehZahl = self.dreh.read()
            # Encoder zählt in 4er Schritten
            self.mNum = int(self.mNum + ((self.DrehZahl - self.AlteZahl) / 4))
            # Eingabe soll nichtz kleiner als minVal werden
            if (self.mNum < minVal):
                self.mNum = minVal
                self.beeper.makeBeep(0.1, 0.1)
            # Nur sie Änderungen des Encodes sollen berücksichtigt werden
            self.AlteZahl = self.DrehZahl
            self.anzeige = f"{self.mNum} {textTwo}"
            try:
                with canvas(device) as draw:
                    #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
                    draw.text((15, 0), textOne, font = oled_font, fill = "white")
                    draw.text((15, 20), self.anzeige, font = oled_font, fill = "white")
                    draw.text((15, 40), "Press 4 enter", font = oled_font, fill = "white")
            except:
                logging.error(f"Fehler beim Schreiben auf Display: {traceback.format_exc()}")
                
            time.sleep(1.0)
        
        # Bestätigungston
        self.beeper.makeBeep(0.1, 0)
        
        return self.mNum
        
    def displayHop(self):
        # Zeit überbrücken, bis der Schalter nicht mehr prellt
        self.newPic = Image.new(logo.mode, logo.size, (0,) * 4)
        self.background = Image.new("RGBA", device.size, "black")
        self.posn = ((device.width - logo.width) // 2, 0)
        self.background.paste(logo, self.posn)
        device.display(self.background.convert(device.mode))

        for self.angle in range(0, 360, 15):
            self.rotation = logo.rotate(self.angle, resample=Image.BILINEAR)
            self.img = Image.composite(self.rotation, self.newPic, self.rotation)
            self.background.paste(self.img, self.posn)
            device.display(self.background.convert(device.mode))
                
    def manualInput(self):
        logger.info("Temperatur & Dauer manuell eingeben")
        # Alte Werte löschen
        self.dbCursor.execute("DELETE FROM Rasten")
        # Prellzeit überbrücken
        self.displayHop()
        # Eingabe - Temperatur
        self.mTemp = self.getValue("Temperatur", "Grad", 20, 10)
        # Prellzeit überbrücken
        self.displayHop()
        #Eingabe - Dauer
        self.mDur = self.getValue("Dauer", "Minuten", 2, 1)
        # Prellzeit überbrücken
        self.displayHop()
        
        # Werte in Datenbank/Tabelle für die Meßwerte speichern
        self.dbCursor.execute("""INSERT INTO Rasten VALUES
                                (:Name, :SollTemp, :Dauer, :Jodprobe)""",
                                {'Name' : 'Manuell', 'SollTemp' : self.mTemp, 'Dauer' : self.mDur, 'Jodprobe' : False})
        
        # Status setzen, damit Temperatursteuerung abläuft
        self.dbCursor.execute("UPDATE Status SET State = :Status WHERE StateName = :BState",{'Status' : 'Go', 'BState' : 'Brewstate'})

        self.conn.commit()
        
    def wait4end(self):
        # Brauende auf Display anzeigen
        try:
            with canvas(device) as draw:
                #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
                draw.text((10, 0), "Steuerung", font = oled_font, fill = "white")
                draw.text((10, 20), "beendet", font = oled_font, fill = "white")
                draw.text((10, 40), "Press Button", font = oled_font, fill = "white")
        except:
            logging.error(f"Fehler beim Schreiben auf Display: {traceback.format_exc()}")
            
        # Status des Push Buttons setzen
        self.buttonState = False
        
        # Der buttonState wird in der Interupt-Routine geändert
        while (self.buttonState != True):
            self.beeper.makeBeep(0.5, 2.0)
            
        # Bestätigungston
        self.beeper.makeBeep(0.1, 0)
        
    def wait4go(self):
        # Prüfen, ob Braudatenbank aktualisiert wurde
        logger.info("Warte auf Rasten")
        self.dbCursor.execute("SELECT State FROM Status WHERE StateName = :BState", {'BState' : 'Brewstate'})
        self.Result = self.dbCursor.fetchone()
        if self.Result[0] != 'Go':
            with canvas(device) as draw:
                #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
                draw.text((15, 0), "Warten auf", font = oled_font, fill = "white")
                draw.text((15, 20), "Brauverlauf", font = oled_font, fill = "white")
            time.sleep(1)
            return False
        else:
            # Neuen Status setzen
            self.dbCursor.execute("""UPDATE Status SET State = :State WHERE StateName = :BState""",
                                  {'State' : 'Running', 'BState' : 'Brewstate'})
            self.conn.commit()
            return True
        
    def importConfig(self):
        try:
            # Json Configurationsdatei einlesen
            with open("config.json") as self.file:
                self.configData = json.load(self.file)
                
            logger.info("CSV Datei: {}".format(self.configData["csvDataFile"]))
            logger.info("Abtastrate: {}".format(self.configData["timeSleep"]))
            logger.info("Hysterese: {}".format(self.configData["Hysterese"]))
            logger.info("Jodprobe [min]: {}".format(self.configData["ZeitJodprobe"]))
            logger.info("CSV Ausgabe: {}".format(self.configData["csvAusgabe"]))
            logger.info("Plot Ausgabe: {}".format(self.configData["plotAusgabe"]))
            # For future use
            logger.info("Datenbank: {}".format(self.configData["DatabaseFile"]))

            # return self.userInputJN("Ist die Konfiguration korrekt?")
            return True
        except:
            return False
        
    def userInputJN(self, question):
        # Ja / Nein Frage stellen
        self.userInput = str(input(str("{} j/n: ".format(question))))
        while ((self.userInput != "j") and (self.userInput != "n")):
            # Eingabe wiederholen
            self.userInput = str(input(str("{} j/n: ".format(question))))
        if self.userInput == "n":
            return False
        else:
            return True
        
        
    def write_display(self, istTemperatur, sollTemperatur, text1, text2):
        try:
            with canvas(device) as draw:
                #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
                draw.text((15, 0), "Ist :", font = oled_font, fill = "white")
                draw.text((50, 0), "{} C".format(istTemperatur), font = oled_font, fill = "white")
                draw.text((15, 20), "Soll:", font = oled_font, fill="white")
                draw.text((50, 20), "{:0.1f} C".format(sollTemperatur), font = oled_font, fill="white")
                draw.text((15, 40), text1, font = oled_font, fill="white")
                draw.text((50, 40), text2, font = oled_font, fill="white")
        except:
            logging.error(f"Fehler beim Schreiben auf Display: {traceback.format_exc()}")
                
            
    def clear_display(self):
        try:
            with canvas(device) as draw:
                draw.text((15, 0), " ", font = oled_font, fill = "white")
        except:
            logging.error(f"Fehler beim Schreiben auf Display: {traceback.format_exc()}")
                
    
    def ReadTemperature(self, SollTemp):  
        # Temperatur auslesen und auf eine Nachkommastelle runden
        self.SensorTemp = float(Sensor.temperature)
        self.SensorTemp = round(self.SensorTemp, 1)
        
        if self.SensorTemp > 500:
            while float(self.SensorTemp) > 500:
                # Kein Temperatursensor angeschlossen - Alarm ausgeben
                self.beeper.makeBeep(0.5, 0.5)
                # Temperatur erneut lesen
                self.SensorTemp = float(Sensor.temperature)
                self.SensorTemp = round(self.SensorTemp, 1)
        
        if self.SensorTemp != self.lastTemp:
            #Nur neue Temperaturwerte werden gespeichert           
            # Werte in Datenbank/Tabelle für die Meßwerte speichern
            self.dbCursor.execute("""INSERT INTO Messwerte VALUES
                                    (:Counter, :IstTemp, :SollTemp)""",
                                    {'Counter' : self.counterRow, 'IstTemp' : self.SensorTemp, 'SollTemp' : SollTemp})
            self.conn.commit()
            
            # Aktuelle Temperatur für den nächsten Vergleich speichern
            self.lastTemp = self.SensorTemp
        
        # Zähler für den nächsten Meßpunkt erhöhen
        self.counterRow = self.counterRow +1
        
        # Return Temperature
        return self.SensorTemp
        
    def HoldTemperature(self, Temperature, Duration, Hysteresis):
        logger.info(f"Solltemperatur {Temperature} Dauer {Duration} Minute(n)")
        # Aufheizen, bis Temperatur erreicht
        logger.debug(f"Aufheizen auf {Temperature} Grad")
        self.temp = self.ReadTemperature(Temperature)
        while self.temp < Temperature:
            # Schaltet Heizung ein, wenn vorher aus
            self.RedSwitch.On()
            logger.debug('Temperature: {:0.3f} C'.format(self.temp))
            # Temperatur auf Display anzeigen
            self.write_display(self.temp, Temperature, "aufheizen", " ")
            # Dealy 1 second
            time.sleep(1.0)
            # Temperatur neu lesen
            self.temp = self.ReadTemperature(Temperature)
            
        # Hält die Temperatur, bis Zeit abgelaufen ist
        self.StartTime = time.time()
        self.EndTime = self.StartTime + (Duration * 60)
         
        logger.debug(f"Temperatur {Temperature} Grad für {Duration} Minute(n) halten")
        while self.EndTime > time.time():
            self.temp = self.ReadTemperature(Temperature)
            # Temperaturen & Zeit auf Display anzeigen
            self.write_display(self.temp, Temperature, "Zeit:", "{}".format(self.get_hms(self.EndTime - time.time())))
                
            if self.temp < (Temperature - Hysteresis):
                # Temperatur ist kleiner Solltemperatur minus Hysterese
                # Heizung einschalten
                self.RedSwitch.On()
            else:
                # Heizung ausschalten
                self.RedSwitch.Off()
            logger.debug('Temperature: {:0.3f} C'.format(self.temp))
            # Delay 1 Second
            time.sleep(1.0)
        logger.debug("Time over")
        
    def makeJodprobe(self, jTemperature, jDuration, jHysteresis):
        # User muss Jodprobe machen
        # Das Ergebnis der Jodprobe kann über den Schalter des Encoders oder über die Datenbank eingegeben werden
        
        # Status in DB setzen
        self.dbCursor.execute("UPDATE Status SET State = :Status WHERE StateName = :BState",{'Status' : 'Wait', 'BState' : 'Jodprobe'})
        self.conn.commit()
        
        # Aufmerksamkeitston
        self.beeper.makeBeep(0.5, 0)
        
        #Stellung des Encoders lesen
        self.DrehZahl = self.dreh.read()
        self.AlteZahl = 0
        self.buttonState = False
        self.anzeige = "Ergebnis: Nein"
        self.result = False
        
        self.dbCursor.execute("SELECT State FROM Status WHERE StateName = 'Jodprobe'")
        self.jResult = self.dbCursor.fetchone()
        
        # Der buttonState wird in der Interupt-Routine geändert
        while (self.buttonState != True) and (self.jResult[0] == "Wait"):
            try:
                with canvas(device) as draw:
                    #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
                    draw.text((15, 0), "Jodprobe", font = oled_font, fill = "white")
                    draw.text((15, 20), "erfolgreich?", font = oled_font, fill = "white")
                    if ((self.DrehZahl > (self.AlteZahl + 6)) or (self.DrehZahl < (self.AlteZahl - 6))):
                        # Stellung des Encoders hat sich signifikant geändert
                        # Anzeige ändern
                        if self.anzeige == 'Ergebnis: Ja':
                            self.anzeige = "Ergebnis: Nein"
                            self.result = False
                        else: 
                            self.anzeige = "Ergebnis: Ja"
                            self.result = True
                        # Neu Zahl speichern
                        self.AlteZahl = self.DrehZahl
                
                    draw.text((15, 40), self.anzeige, font = oled_font, fill = "white")
            except:
                logging.error(f"Fehler beim Schreiben auf Display: {traceback.format_exc()}")
                
            time.sleep(0.25)
            # Stellung des Encoders erneut lesen
            self.DrehZahl = self.dreh.read()
            
            # Status der Jodprobe aus DB lesen
            self.dbCursor.execute("SELECT State FROM Status WHERE StateName = 'Jodprobe'")
            self.jResult = self.dbCursor.fetchone()
            
            # Prüfen, ob ein ungültiger Status vorliegt
            if (self.jResult[0] != 'Positive') and (self.jResult[0] != 'Negative') and (self.jResult[0] != 'Wait'):
                # Status ist ungültig - wird ignoriert
                logger.error("Ungültiger Status: {}".format(str(self.jResult[0])))
                self.jResult = ('Wait', )
                # Status in DB überschreiben
                self.dbCursor.execute("UPDATE Status SET State = :Status WHERE StateName = :BState",
                                      {'Status' : 'Wait', 'BState' : 'Jodprobe'})
                self.conn.commit()
                
            if self.jResult[0] == 'Positive':
                logger.info("Jodprobe war erfolgreich")
                self.result = True
            elif self.jResult[0] == 'Negative':
                logger.info("Jodprobe war nicht erfolgreich")
                self.result = False
    
        # Wenn Jodprobe nicht erfolgreich, dann Raste verlängern
        if self.result == False:
            # Zeit auf der Temperaturstufe wird verlängert
            self.HoldTemperature(jTemperature, jDuration, jHysteresis)
            # Jodprobe war nicht erfolgreich und muss ggf. wiederholt werden
            return False
        else:
            # Jodprobe war erfolgreich
            return True
        
    def mashing(self):
        # Warten, dass Rasten definiert sind
        while self.wait4go() == False:
            pass
        
        # Rührwerk einschalten
        self.BlueSwitch.On()
        
        # Temperaturrasten ansteuern
        self.dbCursor.execute("SELECT * FROM Rasten ORDER BY rowid ASC")
        # Rasten auslesen
        self.Rasten = self.dbCursor.fetchall()
        if self.Rasten == []:
            logger.info("Keine Rasten in DB")
        else:
            logger.info(self.Rasten)
        
        for self.Raste in self.Rasten:
            logger.info(self.Raste)
            # Tupel entpacken
            tRaste, tTemperature, tDuration, tJodprobe = self.Raste
            
            self.HoldTemperature(tTemperature, tDuration, self.configData["Hysterese"])
            
            if tJodprobe == True:
                while self.makeJodprobe(tTemperature, self.configData["ZeitJodprobe"], self.configData["Hysterese"]) != True:
                    logger.info("Jodprobe wiederholen")
                    pass
    
                    
        logger.info("Brauvorgang abgeschlossen")
        # Alles ausschalten
        self.RedSwitch.Off()
        self.BlueSwitch.Off()
        
        # Status in Datenbank setzen
        self.dbCursor.execute("""UPDATE Status SET State = :State WHERE StateName = :BState""",
                             {'State' : 'Done', 'BState' : 'Brewstate'})
        self.conn.commit()
        
        # Daten aus Datenbank in Listen einlesen
        self.readDatabaseIntoLists()
        
        if self.configData["csvAusgabe"]:
            # CSV Datei schreiben und schließen
            self.WriteCSV()
            
        if self.configData["plotAusgabe"]:
            # Ergebnis plotten
            self.PrintGraph()
            
        # Datenbank schließen
        self.conn.close()
        
    def readDatabaseIntoLists(self):
        self.dbCursor.execute("SELECT * FROM Messwerte ORDER BY rowid ASC")
        #Ersten Datensatz lesen
        self.dbResult = self.dbCursor.fetchone()
        
        while self.dbResult != None:
            # Daten in Listen übernehmen
            self.xList.append(int(self.dbResult[0]))
            self.TempList.append(float(self.dbResult[1]))
            self.SollList.append(float(self.dbResult[2]))
            #Nächsten Datensatz lesen
            self.dbResult = self.dbCursor.fetchone()
        
    def WriteCSV(self):
        # CSV Datei zum Schreiben öffnen und Werte eintragen
        self.csvFile = open(self.configData["csvDataFile"], "w")
        for self.x in range(0, len(self.xList)):
            self.csvFile.write("{},{},{}\r".format(self.xList[self.x], self.TempList[self.x], self.SollList[self.x]))
        #Datei schließen   
        self.csvFile.close()
        
        
    def PrintGraph(self):
        matplotlib.use('tkagg')
        #matplotlib.use('Agg')

        # Style benutzen (überschreibt einige eigene Definitionen)
        #plt.style.use('fivethirtyeight')
        plt.style.use('seaborn-darkgrid')

        # Zeichne Ist-Temperatur
        self.yPoints1 = np.array(self.TempList)
        plt.plot(self.yPoints1, marker = '.', label=r'Ist Temp.')
        # Zeichne Soll-Temperatur
        self.yPoints2 = np.array(self.SollList)
        plt.plot(self.yPoints2, marker = '.', label=r'Soll Temp.')

        # Array mit Anzahl Meßpunkte erzeugen
        self.xPoints = np.array(self.xList)
        # Fläche oberhalb blau einfärben und mit Label beschriften
        plt.fill_between(self.xPoints, self.yPoints1, self.yPoints2, where=(self.yPoints1 > self.yPoints2), interpolate=True, color='blue', alpha=.1, label='Kühlphase(n)')
        # Fläche oberhalb rot einfärben und mit Label beschriften
        plt.fill_between(self.xPoints, self.yPoints1, self.yPoints2, where=(self.yPoints1 <= self.yPoints2), interpolate=True, color='red', alpha=.1, label='Heizphase(n)')

        # Legende einblenden:
        plt.legend(loc='upper left', frameon=False)

        # y-Achse festlegen
        plt.axis( [0, len(self.TempList), (min(self.TempList)-5), (max(self.TempList)+5)])
        
        self.font1 = {'color':'blue','size':18}
        self.font2 = {'size':15}
        plt.title("Temperaturverlauf", fontdict = self.font1)
        plt.xlabel("Zeit [Sek]", fontdict = self.font2)
        plt.ylabel("Temperatur [Grad C]", fontdict = self.font2)
        plt.grid(axis = 'y')
        # Nur mit Agg
        #plt.savefig('TempVerlauf.png', bbox_inches='tight')

        # Nur mit Tkgg auf Headless Device
        plt.show()
        #plt.savefig(sys.stdout.buffer)
        #sys.stdout.flush()
        
    def pushButton(self, channel):
        # Methode wird aufgerufen, wenn Button des Encoders gedrückt wurde
        self.buttonState = True
        
        
    def get_hms(self, delta):
        # Return hours, minutes and seconds for a given `timedelta`-object.
        h, m = divmod(delta, 3600)
        m, s = divmod(m, 60)
        if h > 0:
            # Zeit größer einer Stunde = Stunde mit ausgeben
            return ("{:0>2d}:{:0>2d}:{:0>2d}".format(int(h), int(m), int(s)))
        else:
            # Zeit kleiner einer Stunde = ohne Stunde ausgeben
            return ("{:0>2d}:{:0>2d}".format(int(m), int(s)))
 

# Main
# Brauprogramm initialisieren
brew = Brew(redGPIO, blueGPIO, beepGPIO, encoderDrehGPIO_1, encoderDrehGPIO_2, encoderPushGPIO)

# Brauprogramm ablaufen lassen
if brew.importConfig() == True:
    # Auswahl zwischen manueller oder externer Eingabe der Steuerungsdaten
    if brew.checkInputMode() == True:
        # Manual Input (Temperature & Duration)
        brew.manualInput()
        
    # Temperatursteuerung
    brew.mashing()
    # User Input: Ende bestätigen
    brew.wait4end()
    # Verabschiedung
    brew.displayHop()
    logger.info("Fertig")
else:
    logger.info("Konfiguration ungültig")

brew.clear_display()
    