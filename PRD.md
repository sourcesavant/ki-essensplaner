# PRD.md: KI-Essensplaner (sourcesavant/ki-essensplaner)

**Repo:** https://github.com/sourcesavant/ki-essensplaner  
**Version:** 1.2 (Update: Phase 3 Details, 31.01.2026)  
**Entwickler:** sourcesavant (Windows 11, PyCharm Community, Python 3.12+)

## Projekt-Ziel
Automatisierter KI-Agent für personalisierte Wochenpläne: Lernt aus OneNote-Wochenplänen Vorlieben (Zutaten, Aufwand pro Tag), scrapt eatsmarter.de + andere Sites für passende Neue, generiert Pläne + Einkaufslisten. HA-integrierbar (MQTT/REST).

## Kern-Features (Priorisiert)
1. **Profil-basiertes Lernen (Content-Based Filtering)**: Analysiert OneNote-Pläne → Vorlieben (Zutaten-Frequenz/Häufigkeit, Aufwand-Klassen: quick/normal/long pro Wochentag/Slot).
2. **Intelligentes Rezept-Scouting**: Sucht auf eatsmarter.de + anderen Sites nach Matches (Score >80% zu Profil: Zutaten-Ähnlichkeit, Aufwand-Passung). Berücksichtigung von Saisonalität, Verfügbarkeit von Produkten auf bevorzugter Einkaufwebseite
3. **Hybrider Wochenplaner**: 7-Tage-Mix (Favoriten 60% + Neue 40%).
4. **Lernfunktion** Aktualisiert wöchentlich das Profil.
5. **Rückmeldung** User kann Rezepte bewerten. User kann Zutaten ausschließen. Rezepte mit dieser Zutat werden trotzdem berücksichtigt, wenn Zutat durch ähnliche Zutat ersetzt werden kann.
6. **Einkaufslisten**: Aggregierte Zutaten (Mengen, Kategorien).
7. **Integration**: HA-Dashboard.

## Tech-Stack
- Sprache: Python 3.12 (venv).
- KI: gpt-4o-mini (Scoring/Planung), gpt-4o (Profil-Ableitung).
- Daten: SQLite (data/local/mealplanner.db), JSON (data/raw/all_recipes.json).
- Importer: MS Graph API (OneNote), recipe-scrapers (eatsmarter.de + Multi-Site).
- Tools: PyCharm, GitHub Projects/Issues, plugged.in MCP.

## Phasen & Issues

### Phase 1: Scrape-Test ✅
- Issue #1: eatsmarter.py Test-Scraper (3 URLs mit recipe-scrapers)

### Phase 2: OneNote-Merge ✅
- Issue #2: OneNote Importer (MS Graph API)

### Phase 3: DB + Profil (Vorlieben) ✅
- Issue #3: Rufe Rezepte von gespeicherten Links ab (Scraping der OneNote-URLs)
- Issue #4: Extrahiere Zutaten und Dauer von Rezepten
- Issue #5: Normalisiere Bezeichnung von Zutaten und Mengen
- Issue #6: Leite Vorlieben-Profil ab (TF-IDF für Zutaten, Aufwand-Klassen pro Wochentag/Slot)

### Phase 4: Planner + Search 🔄
- Verfügbarkeit von saisonalen Produkten auf präferierten Einkaufwebseiten
- Intelligentes Rezept-Scouting (Scoring, Saisonalität, Verfügbarkeit)
- Hybrider Wochenplaner (60% Favoriten + 40% Neue)

### Phase: 5 Lernfunktion + Interaktion
- wöchentliche Aktualisierungsmöglichkeit für das Profil
- Bewertungsmöglichkeit von Rezepten
- Ausschluss von Zutaten; Modifikation von Rezepten durch Ersatz von ungewünschten Zutaten durch ähnliche Zutaten

### Integration in HA-Dashboard
- User Interface

## User Stories
- Als User lade ich OneNote-Pläne hoch → Agent leitet Zutaten-Vorlieben + Aufwand-Profile ab.
- Als User sage "Wochenplan mit favorisierten Zutaten" → Suche + Plan mit Neuen von eatsmarter.de.
- Als HA-User sehe ich Pläne im Dashboard.

## AI-Instructions (für Claude/Cursor)
- Granular: Ein File pro Feature (src/profile/preferences.py).
- Output: Vollständige Python-Dateien + pip-Requirements + Tests.
- Profil: TF-IDF/Cosine für Zutaten, Counts für Aufwand pro Slot.
- Idempotent: UPSERT, Error-Handling.
- Libs: recipe-scrapers, pandas, msal, openai, scikit-learn (Similarity).

## Milestones (GitHub Projects)
- Week 1: Setup + Phase 1-2.
- Week 2: Phase 3 (Profil + Vorlieben-Ableitung).
- Week 3: Phase 4 (Search + Planner).

## Risiken & Constraints
- Azure Permissions (Notes.Read.All).
- Scraping-Limits: sleep(0.5), Multi-Site-Fallback.
- Budget: gpt-4o-mini (~0.15$/1M Tokens).
