# KI-Essensplaner Custom Lovelace Cards

Custom dashboard cards for the KI-Essensplaner Home Assistant integration.

## Installation

### 1. Copy Files to Home Assistant

Copy the `www/ki-essensplaner/` directory to your Home Assistant `config/www/` folder:

```bash
# On your Home Assistant system
mkdir -p /config/www/ki-essensplaner
# Copy weekly-plan-card.js and shopping-list-card.js to this folder
```

### 2. Add Resources to Lovelace

Go to **Settings** → **Dashboards** → **Resources** (⋮ menu → **Resources**) and add:

#### Weekly Plan Card
```yaml
url: /local/ki-essensplaner/weekly-plan-card.js
type: module
```

#### Shopping List Card
```yaml
url: /local/ki-essensplaner/shopping-list-card.js
type: module
```

### 3. Add Cards to Dashboard

In your dashboard, click **+ ADD CARD** → **Custom: Weekly Plan Card** or **Custom: Shopping List Card**

## Card Configuration

### Weekly Plan Card

Shows the 7-day meal plan with recipe selection.

**Minimal Configuration:**
```yaml
type: custom:weekly-plan-card
entity: sensor.essensplaner_weekly_plan_status
```

**Features:**
- 7 days × 2 slots (Mittagessen, Abendessen) grid
- Color-coded by prep time (green ≤30min, orange ≤60min, red >60min)
- Dropdown to select alternative recipes (5 options per slot)
- Direct link to original recipe
- "Neu generieren" button
- Badges for new recipes (🆕) and leftovers (♻️)
- Responsive design (stacks on mobile)

**Card Options:**
```yaml
type: custom:weekly-plan-card
entity: sensor.essensplaner_weekly_plan_status
```

### Shopping List Card

Shows the shopping list split by store (Bioland / Rewe).

**Minimal Configuration:**
```yaml
type: custom:shopping-list-card
```

**Full Configuration:**
```yaml
type: custom:shopping-list-card
bioland_entity: sensor.essensplaner_bioland_anzahl
rewe_entity: sensor.essensplaner_rewe_anzahl
total_entity: sensor.essensplaner_einkaufsliste_anzahl
```

**Features:**
- Two tabs: Bioland and Rewe
- Checkboxes to mark items as purchased
- Item count per store
- Progress indicator (X of Y items checked)
- "Markierungen löschen" button to reset checkboxes
- Displays amount, unit, and ingredient name

## Examples

### Complete Dashboard Layout

```yaml
views:
  - title: Essensplaner
    path: essensplaner
    cards:
      - type: custom:weekly-plan-card
        entity: sensor.essensplaner_weekly_plan_status

      - type: custom:shopping-list-card

      - type: entities
        title: Profil & Status
        entities:
          - sensor.essensplaner_api_status
          - sensor.essensplaner_profile_status
          - sensor.essensplaner_household_size

      - type: entities
        title: Nächste Mahlzeit
        entities:
          - sensor.essensplaner_next_meal
```

### Compact View for Mobile

```yaml
- type: custom:weekly-plan-card
  entity: sensor.essensplaner_weekly_plan_status

- type: custom:shopping-list-card
```

The cards automatically adapt to mobile screens with stacked layouts.

## Styling

Cards use Home Assistant's theme variables and automatically adapt to:
- Light/Dark mode
- Custom themes
- Card radius and shadows
- Primary and secondary colors

## Troubleshooting

### Cards don't appear in the "Add Card" menu

1. Clear browser cache (Ctrl+F5)
2. Restart Home Assistant
3. Check browser console (F12) for errors
4. Verify files are in `/config/www/ki-essensplaner/`

### "Custom element doesn't exist"

Make sure you added the resources in **Settings** → **Dashboards** → **Resources**.

### Dropdowns don't work

Check that services are registered:
- `ki_essensplaner.generate_weekly_plan`
- `ki_essensplaner.select_recipe`

### Sensors show "unavailable"

Ensure the integration is properly configured and the API server is running.

## Technical Details

### Weekly Plan Card

**Dependencies:**
- `sensor.essensplaner_weekly_plan_status` (required)
- `sensor.essensplaner_montag_mittagessen` through `sensor.essensplaner_sonntag_abendessen` (14 sensors)

**Services Used:**
- `ki_essensplaner.generate_weekly_plan` - Generate new plan
- `ki_essensplaner.select_recipe` - Select alternative recipe

### Shopping List Card

**Dependencies:**
- `sensor.essensplaner_einkaufsliste_anzahl` (total items)
- `sensor.essensplaner_bioland_anzahl` (Bioland items with attributes)
- `sensor.essensplaner_rewe_anzahl` (Rewe items with attributes)

**State Storage:**
Checked items are stored in the card's local state (not persisted across page reloads).
For persistent todo list functionality, use Home Assistant automations with the todo integration.

## Development

To modify the cards:

1. Edit the `.js` files in `www/ki-essensplaner/`
2. Hard-refresh browser (Ctrl+F5)
3. Check console for errors

### Card Structure

Both cards follow this pattern:
```javascript
class CustomCard extends HTMLElement {
  setConfig(config) { /* Set configuration */ }
  set hass(hass) { /* Update on state changes */ }
  render() { /* Render the card */ }
}
customElements.define('card-name', CustomCard);
```

## License

Same as KI-Essensplaner integration.

## Support

Report issues at: https://github.com/sourcesavant/ki-essensplaner/issues
