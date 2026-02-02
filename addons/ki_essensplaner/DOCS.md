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

### Azure App Registration (für OneNote Import)

Für den OneNote-Import benötigen Sie eine Azure App Registration:

1. Gehen Sie zu https://portal.azure.com
2. Navigieren Sie zu "Azure Active Directory" > "App registrations"
3. Klicken Sie auf "New registration"
4. Name: "KI-Essensplaner"
5. Supported account types: "Personal Microsoft accounts only"
6. Redirect URI: (leer lassen)
7. Klicken Sie auf "Register"

Nach der Registrierung:
- Kopieren Sie die "Application (client) ID" → `AZURE_CLIENT_ID`
- Unter "Authentication" > "Advanced settings": "Allow public client flows" = Yes
- Tragen Sie die Client ID in der Add-on Konfiguration oder `.env` ein

**Wichtig:** Der Tenant ID ist normalerweise "consumers" für persönliche Microsoft-Konten.

## API Endpoints

### Basis

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/api/health` | GET | Nein | Health-Check und Datenstatus |
| `/api/profile` | GET | Ja | Aktuelles Vorlieben-Profil |
| `/api/profile/refresh` | POST | Ja | Profil neu generieren |
| `/api/bioland/products` | GET | Ja | Verfügbare Bioland-Produkte |
| `/api/seasonality/{month}` | GET | Ja | Saisonale Zutaten für Monat (1-12) |

### Onboarding

| Endpoint | Methode | Auth | Beschreibung |
|----------|---------|------|--------------|
| `/api/onboarding/status` | GET | Ja | Gesamtstatus des Onboardings |
| `/api/onboarding/onenote/auth/status` | GET | Ja | OneNote Authentifizierungsstatus |
| `/api/onboarding/onenote/notebooks` | GET | Ja | Verfügbare OneNote Notizbücher |
| `/api/onboarding/import` | POST | Ja | Daten aus Notizbüchern importieren |
| `/api/onboarding/profile/generate` | POST | Ja | Initiales Profil generieren |

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

### Onboarding Status prüfen
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  http://homeassistant.local:8099/api/onboarding/status
```

### OneNote Notizbücher auflisten
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  http://homeassistant.local:8099/api/onboarding/onenote/notebooks
```

### Daten aus Notizbüchern importieren
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"notebook_ids": ["<NOTEBOOK_ID>"]}' \
  http://homeassistant.local:8099/api/onboarding/import
```

### Profil generieren
```bash
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  http://homeassistant.local:8099/api/onboarding/profile/generate
```

## Home Assistant Integration

Nach der Installation können Sie den begleitenden Custom Component "KI-Essensplaner" installieren, der Sensoren und Services für die vollständige Kontrolle bereitstellt.

### Sensoren

**`sensor.essensplaner_api_status`**:
- **State**: `healthy`, `cached`, oder `offline`
- **Attribute**:
  - `database_ok`: Datenbankverbindung OK
  - `profile_age_days`: Alter des Profils in Tagen
  - `bioland_age_days`: Alter der Bioland-Daten in Tagen
  - `cached`: Daten aus Cache (bei API-Ausfall)

**`sensor.essensplaner_profile_status`**:
- **State**: `current`, `outdated`, oder `missing`
- **Attribute**:
  - `profile_age_days`: Alter des Profils in Tagen
  - `needs_update`: Boolean (true wenn >7 Tage alt)

**`sensor.essensplaner_top_ingredients`**:
- **State**: Anzahl der Zutaten im Profil
- **Attribute**:
  - `ingredients`: Liste der Top-10-Zutaten mit Scores

**`sensor.essensplaner_excluded_ingredients`**:
- **State**: Anzahl der ausgeschlossenen Zutaten
- **Attribute**:
  - `ingredients`: Sortierte Liste der ausgeschlossenen Zutaten

### Services

**`ki_essensplaner.rate_recipe`**:
Bewerte ein Rezept von 1-5 Sternen (1=Blacklist, 5=Favorit)
```yaml
service: ki_essensplaner.rate_recipe
data:
  recipe_id: 123
  rating: 5
```

**`ki_essensplaner.exclude_ingredient`**:
Schließe eine Zutat von allen zukünftigen Rezepten aus
```yaml
service: ki_essensplaner.exclude_ingredient
data:
  ingredient_name: "zwiebeln"
```

**`ki_essensplaner.remove_ingredient_exclusion`**:
Entferne eine Zutat von der Ausschlussliste
```yaml
service: ki_essensplaner.remove_ingredient_exclusion
data:
  ingredient_name: "zwiebeln"
```

**`ki_essensplaner.refresh_profile`**:
Aktualisiere das Vorlieben-Profil manuell
```yaml
service: ki_essensplaner.refresh_profile
```

**`ki_essensplaner.generate_weekly_plan`**:
Generiere einen neuen Wochenplan (async, 30-120 Sekunden)
```yaml
service: ki_essensplaner.generate_weekly_plan
```

**`ki_essensplaner.select_recipe`**:
Wähle ein alternatives Rezept für einen Mahlzeiten-Slot
```yaml
service: ki_essensplaner.select_recipe
data:
  weekday: "Montag"
  slot: "Abendessen"
  recipe_index: 2  # Alternative auswählen (0-4)
```

**`ki_essensplaner.delete_weekly_plan`**:
Lösche den aktuellen Wochenplan
```yaml
service: ki_essensplaner.delete_weekly_plan
```

### Wochenplan-Sensoren

**`sensor.essensplaner_weekly_plan_status`**:
- **State**: `active` oder `no_plan`
- **Attribute**:
  - `week_start`: Start-Datum der Woche
  - `generated_at`: Generierungs-Zeitpunkt
  - `favorites_count`: Anzahl Favoriten
  - `new_count`: Anzahl neue Rezepte
  - `total_slots`: Anzahl Slots (14)

**14 Slot-Sensoren** (`sensor.essensplaner_{wochentag}_{mahlzeit}`):
- `sensor.essensplaner_montag_mittagessen`
- `sensor.essensplaner_montag_abendessen`
- ... (und so weiter für alle 7 Tage)

Jeder Slot-Sensor:
- **State**: Rezept-Titel oder "Kein Plan"
- **Attribute**:
  - `recipe_id`: Datenbank-ID
  - `recipe_url`: Link zum Rezept
  - `prep_time_minutes`: Zubereitungszeit
  - `calories`: Kalorien
  - `score`: Scoring-Punkte
  - `is_new`: Neu oder Favorit
  - `alternatives`: Anzahl Alternativen (0-4)
  - `selected_index`: Gewählter Index
  - `ingredients`: Liste der Zutaten

**`sensor.essensplaner_next_meal`**:
- **State**: Titel der nächsten anstehenden Mahlzeit
- **Attribute**:
  - `next_weekday`: Wochentag der nächsten Mahlzeit
  - `next_slot`: Slot der nächsten Mahlzeit
  - `recipe_id`, `recipe_url`, `prep_time_minutes`, `calories`
  - `ingredients`: Liste der Zutaten

Logik für "nächste Mahlzeit":
- Vor 12:00 Uhr → Heutiges Mittagessen
- 12:00-18:00 Uhr → Heutiges Abendessen
- Nach 18:00 Uhr → Morgiges Mittagessen

## Datenspeicherung

Alle Daten werden unter `/share/ki_essensplaner/` gespeichert und bleiben bei Add-on Updates erhalten.

## Support

Bei Problemen erstellen Sie bitte ein Issue auf GitHub:
https://github.com/sourcesavant/ki-essensplaner/issues
