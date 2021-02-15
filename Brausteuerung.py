import RPi.GPIO as GPIO
import time
import datetime
import board
import busio
import digitalio
import adafruit_max31865
import sys
#import tkinter
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
        self.State = False
        self.txt = "Init {} at Pin {}"
        print( self.txt.format(self.Name, self.Pin))

    def On(self):
        # Wenn Steckdose aus, dann einschalten
        if self.State == False:
            # Steckdose schalten LOW = AN!!!
            GPIO.output(self.Pin, GPIO.LOW)
            self.State = True
            self.txt = "{} {} On"
            print (self.txt.format(Timestamp(), self.Name))
    
    def Off(self):
        # Wenn Steckdose an, dann ausschalten
        if self.State == True:
            # Steckdose schalten High = AUS!!!
            GPIO.output(self.Pin, GPIO.HIGH)
            self.State = False
            self.txt = "{} {} Off"
            print (self.txt.format(Timestamp(), self.Name))
        
# Initialize MAX31865 board
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
# Chip select of the MAX31865 board GPIO 23
cs = digitalio.DigitalInOut(board.D23)  
Sensor = adafruit_max31865.MAX31865(spi, cs)

#Leere Listen erzeugen
TempList = []
SollList = []

def ReadTemperature(SollTemp):  
    # Temperatur auslesen
    SensorTemp = float(Sensor.temperature)
    # Temperatur(en) der Liste(n) hinzufügen
    TempList.append(SensorTemp)
    SollList.append(SollTemp)
    # Return Temperature
    return SensorTemp

def HoldTemperature(Temperature, Duration, Hysteresis):
    
    print ("{} Solltemperatur {} Dauer {} Minute(n)".format(Timestamp(),Temperature, Duration))
    
    # Aufheizen, bis Temperatur erreocht
    print ("{} Aufheizen auf {} Grad".format(Timestamp(), Temperature))
    temp = ReadTemperature(Temperature)
    while temp < Temperature:
        # Schaltet Heizung ein, wenn vorher aus
        RedSwitch.On()
        print('{} Temperature: {:0.3f} C'.format(Timestamp(), temp))
        # Dealy 1 second
        time.sleep(1.0)
        # Temperatur neu lesen
        temp = ReadTemperature(Temperature)
        
    # Hält die Temperatur, bis Zeit abgelaufen ist
    StartTime = time.time()
    EndTime = StartTime + (Duration * 60)
     
    print ("{} Temperatur {} Grad für {} Minute(n) halten".format(Timestamp(), Temperature, Duration))
    while EndTime > time.time():
        temp = ReadTemperature(Temperature)
        if temp < (Temperature - Hysteresis):
            # Temperatur ist kleiner Solltemperatur minus Hysterese
            # Heizung einschalten
            RedSwitch.On()
        else:
            # Heizung ausschalten
            RedSwitch.Off()
        print('{} Temperature: {:0.3f} C'.format(Timestamp(), temp))
        # Delay 1 Second
        time.sleep(1.0)
    print ("{} Time over".format(Timestamp()))
    
def PrintGraph():
    matplotlib.use('tkagg')
    #matplotlib.use('Agg')

    # Anzahl der Messpunkte anzeigen
    print("Anzahl Meßpunkte: {}".format(len(TempList)))

    # Style benutzen (überschreibt einige eigene Definitionen)
    #plt.style.use('fivethirtyeight')
    plt.style.use('seaborn-darkgrid')

    # Zeichne Ist-Temperatur
    ypoints1 = np.array(TempList)
    plt.plot(ypoints1, marker = '.', label=r'Ist Temp.')
    # Zeichne Soll-Temperatur
    ypoints2 = np.array(SollList)
    plt.plot(ypoints2, marker = '.', label=r'Soll Temp.')

    # Array mit Anzahl Meßpunkte erzeugen
    x = np.arange(0.,len(TempList),1)
    # Fläche oberhalb blau einfärben und mit Label beschriften
    plt.fill_between(x, ypoints1, ypoints2, where=(ypoints1 > ypoints2), interpolate=True, color='blue', alpha=.1, label='Kühlphase(n)')
    # Fläche oberhalb rot einfärben und mit Label beschriften
    plt.fill_between(x, ypoints1, ypoints2, where=(ypoints1 <= ypoints2), interpolate=True, color='red', alpha=.1, label='Heizphase(n)')

    # Legende einblenden:
    plt.legend(loc='upper left', frameon=False)

    # y-Achse festlegen
    plt.axis( [0, len(TempList), (min(TempList)-5), (max(TempList)+5)])
    
    font1 = {'color':'blue','size':18}
    font2 = {'size':15}
    plt.title("Temperaturverlauf", fontdict = font1)
    plt.xlabel("Zeit [Sek]", fontdict = font2)
    plt.ylabel("Temperatur [Grad C]", fontdict = font2)
    plt.grid(axis = 'y')
    # Nur mit Agg
    #plt.savefig('TempVerlauf.png', bbox_inches='tight')

    # Nur mit Tkgg auf Headless Device
    plt.show()
    plt.savefig(sys.stdout.buffer)
    sys.stdout.flush()

    
Mash = {
    #Hysterese
    "Hyst" : 0.3,
    # Einmaischtemperatur
    "Temp1" : 45,
    "Duration1" : 1,
    # Eiweissrast
    "Temp2" : 50,
    "Duration2" : 1
    }

# Rote Steckdose - Heizung
RedSwitch = Switch(17, "RedSwitch")

# Blaue Steckdos - Rührer
BlueSwitch = Switch(18, "BlueSwitch")

# Main
# Rührwerk einschalten
BlueSwitch.On()

#Hysterese ermitteln
try:
    Hysteresis = Mash["Hyst"]
except:
    Hysteresis = 0.2
text= "{} Grad Hysterese"
print (text.format(Hysteresis))

# Temperaturrasten ansteuern
x = 1
while (True):
    try:
        temp = "Temp" + str(x)
        dur = "Duration" + str(x)
        # Prüfen, ob es einen Eintrag (Temperatur und Dauer) gibt
        if (Mash[temp] > 0) and (Mash[dur] > 0):
            HoldTemperature(Mash[temp], Mash[dur], Hysteresis)
            #Nächster Eintrag
            x = x+1
    except:
        x = x-1
        text = "{} Brauvorgang abgeschlossen {} Raste(n)"
        print(text.format(Timestamp(),x))
        # Alles ausschalten
        RedSwitch.Off()
        
        # Ergebnis plotten
        PrintGraph()
        break
    
    