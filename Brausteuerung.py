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
            print("{} {} On".format(Timestamp(), self.Name))
    
    def Off(self):
        # Wenn Steckdose an, dann ausschalten
        if self.State == True:
            # Steckdose schalten High = AUS!!!
            GPIO.output(self.Pin, GPIO.HIGH)
            self.State = False
            print("{} {} Off".format(Timestamp(), self.Name))
            
class Brew:
    def __init__(self, heizGPIO, ruehrGPIO, beeperGPIO):
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
        

    def importConfig(self):
        # Json Configurationsdatei einlesen
        with open("config.json") as self.file:
            self.configData = json.load(self.file)
        
        print("CSV Datei:",self.configData["csvDataFile"])
        # For future use
        print("Datenbank:",self.configData["DatabaseFile"])
        print("Abtastrate:",self.configData["timeSleep"])
        print("Hysterese:",self.configData["Hysterese"])
        print("Jodprobe [min]:",self.configData["ZeitJodprobe"])

        for self.item in self.configData['Brau']:
            print(self.item['Name'], "Temperatur:", self.item['Temperatur'], "Dauer:",self.item['Dauer'], "Jodprobe:", self.item['Jodprobe'])#
        
        return self.userInputJN("Ist die Konfiguration korrekt?")
        
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
            self.TempList.append(self.SensorTemp)
            self.SollList.append(SollTemp)
            self.xList.append(self.counterRow )
            
            # Aktuelle Temperatur für den nächsten Vergleich speichern
            self.lastTemp = self.SensorTemp
        
        # Zähler für den nächsten Meßpunkt erhöhen
        self.counterRow = self.counterRow +1
        
        # Return Temperature
        return self.SensorTemp
        
    def HoldTemperature(self, Temperature, Duration, Hysteresis):
        print ("{} Solltemperatur {} Dauer {} Minute(n)".format(Timestamp(),Temperature, Duration))
        # Aufheizen, bis Temperatur erreocht
        print ("{} Aufheizen auf {} Grad".format(Timestamp(), Temperature))
        self.temp = self.ReadTemperature(Temperature)
        while self.temp < Temperature:
            # Schaltet Heizung ein, wenn vorher aus
            self.RedSwitch.On()
            print('{} Temperature: {:0.3f} C'.format(Timestamp(), self.temp))
            # Dealy 1 second
            time.sleep(1.0)
            # Temperatur neu lesen
            self.temp = self.ReadTemperature(Temperature)
            
        # Hält die Temperatur, bis Zeit abgelaufen ist
        self.StartTime = time.time()
        self.EndTime = self.StartTime + (Duration * 60)
         
        print("{} Temperatur {} Grad für {} Minute(n) halten".format(Timestamp(), Temperature, Duration))
        while self.EndTime > time.time():
            self.temp = self.ReadTemperature(Temperature)
            if self.temp < (Temperature - Hysteresis):
                # Temperatur ist kleiner Solltemperatur minus Hysterese
                # Heizung einschalten
                self.RedSwitch.On()
            else:
                # Heizung ausschalten
                self.RedSwitch.Off()
            print('{} Temperature: {:0.3f} C'.format(Timestamp(), self.temp))
            # Delay 1 Second
            time.sleep(1.0)
        print("{} Time over".format(Timestamp()))
        
    def makeJodprobe(self, jTemperature, jDuration, jHysteresis):
        # User muss Jodprobe machen
        # Aufmerksamkeitston
        self.beeper.makeBeep(1, 0)
        # Wenn Jodprobe nicht erfolgreich, dann Raste verlängern
        if self.userInputJN("Jodprobe erfolgreich?") == False:
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
        # CSV Datei schreiben und schließen
        self.WriteCSV()
        # Ergebnis plotten
        self.PrintGraph()
        
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

# Main
# Brauprogramm initialisieren
brew = Brew(redGPIO, blueGPIO, beepGPIO)
# Brauprogramm ablaufen lassen
if brew.importConfig() == True:
    #brew.mashing()
    print("Fertig")

    