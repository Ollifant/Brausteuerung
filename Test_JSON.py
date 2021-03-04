import json

# Dictionary anlegen
data = {}
data['Brau'] = []

data['csvDataFile'] = 'Messwerte.csv'
data['DatabaseFile'] =  'Brauer.db'
data['timeSleep'] =  1.0
data['Hysterese'] =  0.2
data['ZeitJodprobe'] =  1

data['Brau'].append({
    "Name" : "Einmaischtemperatur",
    "Temperatur" : 45,
    "Dauer" : 1,
    "Jodprobe" : False
    })

data['Brau'].append({
    "Name" : "Eiweißrast",
    "Temperatur" : 55,
    "Dauer" : 1,
    "Jodprobe" : True
    })

with open('Config.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4,sort_keys=False)