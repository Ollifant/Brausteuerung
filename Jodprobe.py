import sqlite3

conn = sqlite3.connect('Brauer.db')

dbCursor = conn.cursor()

# Status der Brausteuerung lesen
dbCursor.execute("SELECT State FROM Status WHERE StateName = 'Jodprobe'")
Result = dbCursor.fetchone()
print("Result: " + str(Result))
if Result[0] != "Wait":
    print ("Keine Jodprobe aktiv")
else:
    dbCursor.execute("UPDATE Status SET State = :Status WHERE StateName = :BState",{'Status' : 'Positive', 'BState' : 'Jodprobe'})
    conn.commit()
#     dbCursor.execute("SELECT State FROM Status WHERE StateName = 'Jodprobe'")
#     Result = dbCursor.fetchone()
#     print(Result)
    print ("Jodprobe abgeschlossen")