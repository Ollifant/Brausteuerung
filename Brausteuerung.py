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
# --------------Display Libs ------------
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import sh1106, ssd1306
from PIL import ImageFont, ImageDraw, Image
# ---------------------------------------

# --------------Encoder Lib -------------
# pip3 install encoder (um die Lib zu installieren
import Encoder
# ---------------------------------------

#OLED Display auf I2C Bus initialisieren
serial = i2c(port=1, address=0x3C)
device = sh1106(serial)
oled_font = ImageFont.truetype('FreeSans.ttf', 14)

# GPIO ueber Nummern ansprechen
GPIO.setmode(GPIO.BCM)
# Warnungen ausschalten
GPIO.setwarnings(False)

# Initialize MAX31865 board
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

def Timestamp():
    # Funktion ermittelt die aktuelle Zeit in hh:mm:ss
    x = datetime.datetime.now()
    return x.strftime("%H:%M:%S")
    
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
        #print("Beep on")
        time.sleep(timeOn)
        #print("Beep off")
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
        print("Init {} at Pin {}".format(self.Name, self.Pin))

    def On(self):
        # Wenn Steckdose aus, dann einschalten
        if self.State == False:
            # Steckdose schalten LOW = AN!!!
            GPIO.output(self.Pin, GPIO.LOW)
            self.State = True
            #print("{} {} On".format(Timestamp(), self.Name))
    
    def Off(self):
        # Wenn Steckdose an, dann ausschalten
        if self.State == True:
            # Steckdose schalten High = AUS!!!
            GPIO.output(self.Pin, GPIO.HIGH)
            self.State = False
            #print("{} {} Off".format(Timestamp(), self.Name))
            
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
            print("Datenbank vorhanden")
            # mit Datenbank verbinden
            self.conn = sqlite3.connect('Brauer.db')
            # DB Curor erzeugen
            self.dbcCursor = self.conn.cursor()
            with self.conn:
                # Alte Messwerte löschen, indem Tabelle gedroppt wird
                self.dbcCursor.execute("DROP TABLE Messwerte")
                print("Alte Messerte gelöscht")
        else:
            print("Neue Datenbank anlegen")
            # mit Datenbank verbinden
            self.conn = sqlite3.connect('Brauer.db')
            # DB Curor erzeugen
            self.dbcCursor = self.conn.cursor()
            
        # Tabelle für die neuen Meßwerte anlegen
        self.dbcCursor.execute("CREATE TABLE Messwerte (Counter integer, IstTemp real, SollTemp real)")
        self.conn.commit()

    def importConfig(self):
        try:
            # Json Configurationsdatei einlesen
            with open("config.json") as self.file:
                self.configData = json.load(self.file)
            
            print("CSV Datei:",self.configData["csvDataFile"])
            print("Abtastrate:",self.configData["timeSleep"])
            print("Hysterese:",self.configData["Hysterese"])
            print("Jodprobe [min]:",self.configData["ZeitJodprobe"])
            # For future use
            print("Datenbank:",self.configData["DatabaseFile"])

            for self.item in self.configData['Brau']:
                print(self.item['Name'], "Temperatur:", self.item['Temperatur'], "Dauer:",self.item['Dauer'], "Jodprobe:", self.item['Jodprobe'])#
            
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
        with canvas(device) as draw:
            #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
            draw.text((15, 0), "Ist :", font = oled_font, fill = "white")
            draw.text((50, 0), "{} C".format(istTemperatur), font = oled_font, fill = "white")
            draw.text((15, 20), "Soll:", font = oled_font, fill="white")
            draw.text((50, 20), "{:0.1f} C".format(sollTemperatur), font = oled_font, fill="white")
            draw.text((15, 40), text1, font = oled_font, fill="white")
            draw.text((50, 40), text2, font = oled_font, fill="white")
            
            
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
            self.dbcCursor.execute("""INSERT INTO Messwerte VALUES
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
        print ("{} Solltemperatur {} Dauer {} Minute(n)".format(Timestamp(),Temperature, Duration))
        # Aufheizen, bis Temperatur erreocht
        #print ("{} Aufheizen auf {} Grad".format(Timestamp(), Temperature))
        self.temp = self.ReadTemperature(Temperature)
        while self.temp < Temperature:
            # Schaltet Heizung ein, wenn vorher aus
            self.RedSwitch.On()
            #print('{} Temperature: {:0.3f} C'.format(Timestamp(), self.temp))
            # Temperatur auf Display anzeigen
            self.write_display(self.temp, Temperature, "aufheizen", " ")
            # Dealy 1 second
            time.sleep(1.0)
            # Temperatur neu lesen
            self.temp = self.ReadTemperature(Temperature)
            
        # Hält die Temperatur, bis Zeit abgelaufen ist
        self.StartTime = time.time()
        self.EndTime = self.StartTime + (Duration * 60)
         
        #print("{} Temperatur {} Grad für {} Minute(n) halten".format(Timestamp(), Temperature, Duration))
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
            #print('{} Temperature: {:0.3f} C'.format(Timestamp(), self.temp)
            # Delay 1 Second
            time.sleep(1.0)
        #print("{} Time over".format(Timestamp()))
        
    def makeJodprobe(self, jTemperature, jDuration, jHysteresis):
        # User muss Jodprobe machen
        # Aufmerksamkeitston
        self.beeper.makeBeep(0.5, 0)
        
        #Stellung des Encoders lesen
        self.DrehZahl = self.dreh.read()
        self.AlteZahl = 0
        self.buttonState = False
        self.anzeige = "Ergebnis: Nein"
        self.result = False
        while self.buttonState != True:
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
                time.sleep(0.25)
                #Stellung des Encoders erneut lesen
                self.DrehZahl = self.dreh.read()
        
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
        # Rührwerk einschalten
        self.BlueSwitch.On()
        
        # Temperaturrasten ansteuern
        for self.item in self.configData['Brau']:
            self.HoldTemperature(self.item['Temperatur'], self.item['Dauer'], self.configData["Hysterese"])
            if self.item['Jodprobe'] == True:
                while self.makeJodprobe(self.item['Temperatur'], self.configData["ZeitJodprobe"], self.configData["Hysterese"]) != True:
                    pass
                    
        print("{} Brauvorgang abgeschlossen {} Raste(n)".format(Timestamp(),len(self.configData['Brau'])))
        # Alles ausschalten
        self.RedSwitch.Off()
        self.BlueSwitch.Off()
        # Brauende auf Display anzeigen
        with canvas(device) as draw:
            #draw.rectangle(device.bounding_box, outline = "white", fill = "black")
            draw.text((10, 15), "Brauvorgang", font = oled_font, fill = "white")
            draw.text((10, 40), "abgeschlossen", font = oled_font, fill = "white")
        
        # Daten aus Datenbank in Listen einlesen
        self.readDatabaseIntoLists()
        # CSV Datei schreiben und schließen
        self.WriteCSV()
        # Datenbank schließen
        self.conn.close()
        # Ergebnis plotten
        self.PrintGraph()
        
    def readDatabaseIntoLists(self):
            self.dbcCursor.execute("SELECT * FROM Messwerte ORDER BY rowid ASC")
            #Ersten Datensatz lesen
            self.dbResult = self.dbcCursor.fetchone()
            
            while self.dbResult != None:
                # Daten in Listen übernehmen
                self.xList.append(int(self.dbResult[0]))
                self.TempList.append(float(self.dbResult[1]))
                self.SollList.append(float(self.dbResult[2]))
                #Nächsten Datensatz lesen
                self.dbResult = self.dbcCursor.fetchone()
            
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
    brew.mashing()
    print("Fertig")

    