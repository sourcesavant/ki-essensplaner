# PRD.md: KI-Essensplaner (sourcesavant/ki-essensplaner)

**Repo:** https://github.com/sourcesavant/ki-essensplaner  
**Version:** 1.1 (Update: Vorlieben-Ableitung, 30.01.2026)  
**Entwickler:** sourcesavant (Windows 11, PyCharm Community, Python 3.12+)

## Projekt-Ziel
Automatisierter KI-Agent für personalisierte Wochenpläne: Lernt aus OneNote-Wochenplänen Vorlieben (Zutaten, Aufwand pro Tag), scrapt eatsmarter.de + andere Sites für passende Neue, generiert Pläne + Einkaufslisten. HA-integrierbar (MQTT/REST).

## Kern-Features (Priorisiert)
1. **Profil-basiertes Lernen (Content-Based Filtering)**: Analysiert OneNote-Pläne → Vorlieben (Zutaten-Frequenz/Häufigkeit, Aufwand-Klassen: quick/normal/long pro Wochentag/Slot).
2. **Intelligentes Rezept-Scouting**: Sucht auf eatsmarter.de + anderen Sites nach Matches (Score >80% zu Profil: Zutaten-Ähnlichkeit, Aufwand-Passung).
3. **Hybrider Wochenplaner**: 7-Tage-Mix (Favoriten 60% + Neue 40%), Randbedingungen (<30min Werktags).
4. **Einkaufslisten**: Aggregierte Zutaten (Mengen, Kategorien).
5. **Integration**: HA-Dashboard (optional).

## Tech-Stack
- Sprache: Python 3.12 (venv).
- KI: gpt-4o-mini (Scoring/Planung), gpt-4o (Profil-Ableitung).
- Daten: SQLite (data/local/mealplanner.db), JSON (data/raw/all_recipes.json).
- Importer: MS Graph API (OneNote), recipe-scrapers (eatsmarter.de + Multi-Site).
- Tools: PyCharm, GitHub Projects/Issues, plugged.in MCP.
- Phasen: 1=Scrape-Test, 2=OneNote-Merge, 3=DB+Profil (Vorlieben), 4=Planner+Search.

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
