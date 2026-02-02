# KI-Essensplaner Add-on

Dieses Add-on stellt eine REST API für den KI-Essensplaner bereit, der personalisierte Wochenpläne basierend auf Ihren Vorlieben erstellt.

## Funktionen

- **Vorlieben-Profil**: Analysiert Ihre Mahlzeiten-Historie und leitet Präferenzen ab
- **Wochenplan**: Generiert personalisierte Wochenpläne mit 5 Rezept-Empfehlungen pro Slot
- **Einkaufsliste**: Erstellt Einkaufslisten aus Wochenplänen, aufgeteilt nach Bioland/Rewe
- **Rezept-Management**: Bewerten Sie Rezepte und schließen Sie Zutaten aus
- **Bioland-Integration**: Zeigt aktuelle saisonale Produkte vom Bioland-Hof
- **Saisonalität**: Informationen über saisonale Zutaten nach Monat
- **Health-Check**: Status-Endpoint für Home Assistant Integration

## Konfiguration

### API Token

Generieren Sie einen sicheren Token für die API-Authentifizierung:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Tragen Sie diesen Token in der Add-on Konfiguration ein.

### OpenAI API Key (Optional)

Falls Sie die GPT-basierte Zutaten-Normalisierung nutzen möchten, tragen Sie Ihren OpenAI API Key ein.

## API Endpoints

### Basis

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/api/health` | GET | Nein | Health-Check und Datenstatus |
| `/api/profile` | GET | Ja | Aktuelles Vorlieben-Profil |
| `/api/profile/refresh` | POST | Ja | Profil neu generieren |
| `/api/bioland/products` | GET | Ja | Verfügbare Bioland-Produkte |
| `/api/seasonality/{month}` | GET | Ja | Saisonale Zutaten für Monat (1-12) |

### Wochenplan

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/api/weekly-plan` | GET | Ja | Aktuellen Wochenplan abrufen |
| `/api/weekly-plan/generate` | POST | Ja | Neuen Wochenplan generieren (async, ~30-120 Sek.) |
| `/api/weekly-plan/select` | POST | Ja | Rezept für einen Slot auswählen |
| `/api/weekly-plan` | DELETE | Ja | Wochenplan löschen |

### Einkaufsliste

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/api/shopping-list` | GET | Ja | Einkaufsliste aus Wochenplan generieren |
| `/api/shopping-list/split` | GET | Ja | Einkaufsliste nach Bioland/Rewe aufgeteilt |

### Rezept-Management

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/api/recipes/{recipe_id}/rate` | POST | Ja | Rezept bewerten (1-5 Sterne) |
| `/api/recipes/{recipe_id}/rating` | GET | Ja | Bewertung eines Rezepts abrufen |
| `/api/ingredients/exclude` | POST | Ja | Zutat ausschließen |
| `/api/ingredients/exclude/{ingredient}` | DELETE | Ja | Zutat-Ausschluss entfernen |
| `/api/ingredients/excluded` | GET | Ja | Alle ausgeschlossenen Zutaten |

## Authentifizierung

Alle geschützten Endpoints erfordern einen Bearer Token im Authorization Header:

```
Authorization: Bearer <IHR_API_TOKEN>
```

## Beispiel-Aufrufe

### Health Check
```bash
curl http://homeassistant.local:8099/api/health
```

### Profil abrufen
```bash
curl -H "Authorization: Bearer <TOKEN>" http://homeassistant.local:8099/api/profile
```

### Saisonale Zutaten für Februar
```bash
curl -H "Authorization: Bearer <TOKEN>" http://homeassistant.local:8099/api/seasonality/2
```

### Wochenplan generieren
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  http://homeassistant.local:8099/api/weekly-plan/generate
```

### Wochenplan abrufen
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  http://homeassistant.local:8099/api/weekly-plan
```

### Rezept für Slot auswählen
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"weekday":"Montag","slot":"Abendessen","recipe_index":1}' \
  http://homeassistant.local:8099/api/weekly-plan/select
```

### Einkaufsliste nach Store aufgeteilt
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  http://homeassistant.local:8099/api/shopping-list/split
```

### Rezept bewerten
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"rating":5}' \
  http://homeassistant.local:8099/api/recipes/123/rate
```

### Zutat ausschließen
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"ingredient_name":"zwiebeln"}' \
  http://homeassistant.local:8099/api/ingredients/exclude
```

### Ausgeschlossene Zutaten abrufen
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  http://homeassistant.local:8099/api/ingredients/excluded
```

## Home Assistant Integration

Nach der Installation können Sie den begleitenden Custom Component "KI-Essensplaner" installieren, der einen Sensor für den API-Status bereitstellt.

### Sensor

`sensor.essensplaner_api_status`:
- **State**: `healthy`, `cached`, oder `offline`
- **Attribute**:
  - `database_ok`: Datenbankverbindung OK
  - `profile_age_days`: Alter des Profils in Tagen
  - `bioland_age_days`: Alter der Bioland-Daten in Tagen

## Datenspeicherung

Alle Daten werden unter `/share/ki_essensplaner/` gespeichert und bleiben bei Add-on Updates erhalten.

## Support

Bei Problemen erstellen Sie bitte ein Issue auf GitHub:
https://github.com/sourcesavant/ki-essensplaner/issues
