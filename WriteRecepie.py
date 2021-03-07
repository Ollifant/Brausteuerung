import sqlite3

conn = sqlite3.connect('Brauer.db')

dbCursor = conn.cursor()

# Status der Brausteuerung lesen
dbCursor.execute("SELECT State FROM Status WHERE Braustatus = 'Brewstate'")
Result = dbCursor.fetchone()
if Result[0] != "Wait":
    print ("Brausteuerung nicht bereit")
else :
    # Alte Werte löschen
    dbCursor.execute("DELETE FROM Rasten")

    dbCursor.execute("""INSERT INTO Rasten VALUES
                        (:Name, :SollTemp, :Dauer, :Jodprobe)""",
                         {'Name' : 'Eiweißrast', 'SollTemp' : 45.0, 'Dauer' : 1, 'Jodprobe' : False})

    dbCursor.execute("""INSERT INTO Rasten VALUES
                        (:Name, :SollTemp, :Dauer, :Jodprobe)""",
                         {'Name' : 'Maltoserast', 'SollTemp' : 55.0, 'Dauer' : 1, 'Jodprobe' : True})

    conn.commit()

    # Status setzen
    dbCursor.execute("UPDATE Status SET State = :Status WHERE Braustatus = :BState",{'Status' : 'Go', 'BState' : 'Brewstate'})
    conn.commit()

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
