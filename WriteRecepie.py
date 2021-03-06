import sqlite3

conn = sqlite3.connect('Brauer.db')

dbCursor = conn.cursor()

# Alte Werte löschen
# dbCursor.execute("DELETE FROM Rasten")
# 
# dbCursor.execute("""INSERT INTO Rasten VALUES
#                     (:Name, :SollTemp, :Dauer, :Jodprobe)""", {'Name' : 'Eiweißrast', 'SollTemp' : 45.0, 'Dauer' : 1, 'Jodprobe' : False})
# 
# dbCursor.execute("""INSERT INTO Rasten VALUES
#                     (:Name, :SollTemp, :Dauer, :Jodprobe)""", {'Name' : 'Maltoserast', 'SollTemp' : 55.0, 'Dauer' : 1, 'Jodprobe' : True})
# 
# conn.commit()

dbCursor.execute("SELECT * FROM Rasten ORDER BY rowid ASC")

Result = dbCursor.fetchall()

for x in Result:
    print(x[0])


# Result = dbCursor.fetchone()
# 
# while Result != None:
#     print(Result[3])
#     Result = dbCursor.fetchone()

# Datenbank schließen
conn.close()
