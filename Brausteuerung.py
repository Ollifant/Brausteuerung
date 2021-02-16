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

# GPIO ueber Nummern ansprechen
GPIO.setmode(GPIO.BCM)

# Warnungen ausschalten
GPIO.setwarnings(False)

def Timestamp():
    # Funktion ermittelt die aktuelle Zeit in hh:mm:ss
    x = datetime.datetime.now()
    return x.strftime("%H:%M:%S")
    
class Switch:
    def __init__(self, Pin, Name):
        self.Pin = Pin
        self.Name = Name
        #Pin als Output definieren
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
    def __init__(self, heizGPIO, ruehrGPIO):
        #Leere Listen erzeugen
        self.TempList = [float]
        self.SollList = [float]
        # Rote Steckdose - Heizung
        self.RedSwitch = Switch(heizGPIO, "RedSwitch")
        # Blaue Steckdos - Rührer
        self.BlueSwitch = Switch(ruehrGPIO, "BlueSwitch")
        # Rührwerk einschalten
        self.BlueSwitch.On()

    def ReadTemperature(self, SollTemp):  
        # Temperatur auslesen
        self.SensorTemp = float(Sensor.temperature)
        # Temperatur(en) der Liste(n) hinzufügen
        self.TempList.append(self.SensorTemp)
        self.SollList.append(SollTemp)
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
        print("Jodprobe jetzt")
        self.userInput = str(input("Jodprobe erfolgreich? j/n: "))
        while ((self.userInput != "j") and (self.userInput != "n")):
            # Eingabe wiederholen
            self.userInput = str(input("Jodprobe erfolgreich? j/n: "))
        if self.userInput == "n":
            # Zeit auf der Temperaturstufe wird verlängert
            self.HoldTemperature(jTemperature, jDuration, jHysteresis)
            # Jodprobe war nicht erfolgreich und muss ggf. wiederholt werden
            return False
        else:
            # Jodprobe war erfolgreich
            return True
        
    def mashing(self):
        #Hysterese ermitteln
        try:
            self.Hysteresis = Mash["Hyst"]
        except:
            self.Hysteresis = 0.2
        print("{} Grad Hysterese".format(self.Hysteresis))

        # zusätzliche Zeit für Jodprobe ermitteln
        try:
            self.TimeAdd = Mash["TimeAdd"]
        except:
            self.TimeAdd = 10
        print("{} min extra wenn Jodprobe negativ".format(self.TimeAdd))

        # Temperaturrasten ansteuern
        self.x = 1
        while (True):
            try:
                self.tempX = "Temp" + str(self.x)
                self.durX = "Duration" + str(self.x)
                # Prüfen, ob es einen Eintrag (Temperatur und Dauer) gibt
                if (Mash[self.tempX] > 0) and (Mash[self.durX] > 0):
                    self.HoldTemperature(Mash[self.tempX], Mash[self.durX], self.Hysteresis)
                    # Jodprobe erforderlich?
                    try:
                        self.jodProbe = "Jodprobe" + str(self.x)
                        if Mash[self.jodProbe] == True:
                            # Jodprobe so lange durchführen, bis erfolgreich
                            print("Jodprobe machen temp: {} TimeAdd: {} Hysteresis: {}".format(Mash[self.tempX], self.TimeAdd, self.Hysteresis))
                            while (self.makeJodprobe(Mash[self.tempX], self.TimeAdd, self.Hysteresis) != True):
                                pass
                    except:
                        pass
                    #Nächster Eintrag
                    self.x = self.x+1
            except:
                self.x = self.x-1
                print("{} Brauvorgang abgeschlossen {} Raste(n)".format(Timestamp(),self.x))
                # Alles ausschalten
                self.RedSwitch.Off()
                self.BlueSwitch.Off()
                
                # Ergebnis plotten
                #self.PrintGraph()
                break
       
        
    def PrintGraph(self):
        matplotlib.use('tkagg')
        #matplotlib.use('Agg')

        # Anzahl der Messpunkte anzeigen
        print("Anzahl Meßpunkte: {}".format(len(self.TempList)))

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
        self.xPoints = np.arange(0.,len(self.TempList),1)
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

        
# Initialize MAX31865 board
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
# Chip select of the MAX31865 board GPIO 23
cs = digitalio.DigitalInOut(board.D23)  
Sensor = adafruit_max31865.MAX31865(spi, cs)

    
Mash = {
    #Hysterese[Grad C] - optional
    "Hyst" : 0.3,
    # Verlängerung Jodprobe [min] - optional
    "TimeAdd" : 1,
    # Einmaischtemperatur [Grad C]
    "Temp1" : 45,
    "Name1" : "Einmaischen",
    # Dauer [min]
    "Duration1" : 1,
    # Eiweissrast
    "Temp2" : 50,
    "Name2" : "Eiweißrast",
    "Duration2" : 1,
    "Jodprobe2" : True
    }

# Rote Steckdose GPIO
redGPIO = 17
# Blaue Steckdose GPIO
blueGPIO = 18

# Main
# Brauprogramm initialisieren
brew = Brew(redGPIO, blueGPIO)
# Brauprogramm ablaufen lassen
brew.mashing()
    