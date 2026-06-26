# Schmerztagebuch

Kleine lokale Webapp für ein neutrales Schmerztagebuch mit SQLite-Speicherung,
Kalenderübersicht und PDF-Export.

## Lokal starten

```bash
python3 app.py
```

Danach im Browser öffnen:

```text
http://localhost:8080
```

Die SQLite-Datenbank liegt standardmäßig unter `.paintracker-data/paintracker.sqlite3`.

## Mit Docker starten

```bash
docker compose up --build
```

Die App läuft dann ebenfalls unter:

```text
http://localhost:8080
```

Durch das Volume `./.paintracker-data:/data` bleiben die Einträge auch nach einem
Container-Neustart erhalten.

## Export

Der Button `PDF exportieren` erzeugt `schmerztagebuch.pdf`. Der Export ist
neutral gestaltet und enthält kein Fremdbranding.
