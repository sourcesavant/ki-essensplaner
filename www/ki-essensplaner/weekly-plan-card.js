/**
 * KI-Essensplaner Weekly Plan Card
 *
 * Custom Lovelace card for displaying the weekly meal plan.
 * Shows 7 days × 2 slots (Mittagessen, Abendessen) with recipe selection.
 */

class WeeklyPlanCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('Please define an entity (sensor.essensplaner_weekly_plan_status)');
    }
    this._config = config;
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 8;
  }

  _callService(service, data = {}) {
    this._hass.callService('ki_essensplaner', service, data);
  }

  _selectRecipe(weekday, slot, recipeIndex) {
    this._callService('select_recipe', {
      weekday: weekday,
      slot: slot,
      recipe_index: recipeIndex
    });
  }

  _generatePlan() {
    this._callService('generate_weekly_plan');
  }

  _getSlotEntity(weekday, slot) {
    const weekdayMap = {
      'Montag': 'montag',
      'Dienstag': 'dienstag',
      'Mittwoch': 'mittwoch',
      'Donnerstag': 'donnerstag',
      'Freitag': 'freitag',
      'Samstag': 'samstag',
      'Sonntag': 'sonntag'
    };
    const slotMap = {
      'Mittagessen': 'mittagessen',
      'Abendessen': 'abendessen'
    };

    const day = weekdayMap[weekday];
    const meal = slotMap[slot];

    return `sensor.essensplaner_${day}_${meal}`;
  }

  _getEffortColor(prepTime) {
    if (!prepTime) return '#808080';
    if (prepTime <= 30) return '#4caf50'; // Green - quick
    if (prepTime <= 60) return '#ff9800'; // Orange - normal
    return '#f44336'; // Red - elaborate
  }

  _renderSlot(weekday, slot) {
    const entityId = this._getSlotEntity(weekday, slot);
    const state = this._hass.states[entityId];

    if (!state) {
      return `
        <div class="slot empty">
          <div class="slot-header">${slot}</div>
          <div class="slot-content">Kein Rezept</div>
        </div>
      `;
    }

    const attributes = state.attributes;
    const recipeTitle = attributes.recipe_title || 'Kein Rezept';
    const recipeUrl = attributes.recipe_url;
    const prepTime = attributes.prep_time_minutes;
    const isNew = attributes.is_new || false;
    const isReuseSlot = attributes.is_reuse_slot || false;
    const alternatives = attributes.alternatives || [];
    const selectedIndex = attributes.selected_index || 0;

    const effortColor = this._getEffortColor(prepTime);
    const newBadge = isNew ? '<span class="badge new">NEU</span>' : '';
    const reuseBadge = isReuseSlot ? '<span class="badge reuse">♻️ Reste</span>' : '';

    const alternativesHtml = alternatives.length > 0 ? `
      <select class="alternatives" onchange="this.getRootNode().host._selectRecipe('${weekday}', '${slot}', this.value)">
        ${alternatives.map((alt, index) => `
          <option value="${index}" ${index === selectedIndex ? 'selected' : ''}>
            ${alt.title}${alt.is_new ? ' 🆕' : ''}
          </option>
        `).join('')}
      </select>
    ` : '';

    return `
      <div class="slot" style="border-left: 4px solid ${effortColor}">
        <div class="slot-header">
          ${slot}
          ${prepTime ? `<span class="prep-time">${prepTime} min</span>` : ''}
        </div>
        <div class="slot-content">
          <div class="recipe-title">
            ${recipeUrl ? `<a href="${recipeUrl}" target="_blank">${recipeTitle}</a>` : recipeTitle}
          </div>
          <div class="badges">
            ${newBadge}
            ${reuseBadge}
          </div>
          ${alternativesHtml}
        </div>
      </div>
    `;
  }

  render() {
    if (!this._hass || !this._config) return;

    const weekdays = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
    const slots = ['Mittagessen', 'Abendessen'];

    const planStatus = this._hass.states[this._config.entity];
    const hasPlan = planStatus && planStatus.state === 'active';

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        .card {
          padding: 16px;
          background: var(--ha-card-background, var(--card-background-color, white));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .card-title {
          font-size: 24px;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .generate-button {
          padding: 8px 16px;
          background: var(--primary-color);
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
        }
        .generate-button:hover {
          opacity: 0.9;
        }
        .week-grid {
          display: grid;
          grid-template-columns: repeat(7, 1fr);
          gap: 8px;
        }
        .day-column {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .day-header {
          font-weight: 600;
          font-size: 14px;
          text-align: center;
          padding: 8px;
          background: var(--secondary-background-color);
          border-radius: 4px;
          color: var(--primary-text-color);
        }
        .slot {
          background: var(--card-background-color, white);
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          padding: 8px;
          min-height: 120px;
        }
        .slot.empty {
          opacity: 0.5;
        }
        .slot-header {
          font-size: 12px;
          font-weight: 500;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
          display: flex;
          justify-content: space-between;
        }
        .prep-time {
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .slot-content {
          font-size: 13px;
        }
        .recipe-title {
          margin-bottom: 4px;
          line-height: 1.3;
        }
        .recipe-title a {
          color: var(--primary-color);
          text-decoration: none;
        }
        .recipe-title a:hover {
          text-decoration: underline;
        }
        .badges {
          display: flex;
          gap: 4px;
          margin-bottom: 8px;
        }
        .badge {
          display: inline-block;
          padding: 2px 6px;
          border-radius: 3px;
          font-size: 10px;
          font-weight: 500;
        }
        .badge.new {
          background: #4caf50;
          color: white;
        }
        .badge.reuse {
          background: #ff9800;
          color: white;
        }
        .alternatives {
          width: 100%;
          padding: 4px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 12px;
        }
        .no-plan {
          text-align: center;
          padding: 40px;
          color: var(--secondary-text-color);
        }
        @media (max-width: 768px) {
          .week-grid {
            grid-template-columns: 1fr;
          }
          .day-column {
            flex-direction: row;
          }
          .day-header {
            min-width: 100px;
          }
        }
      </style>
      <ha-card class="card">
        <div class="card-header">
          <div class="card-title">🍽️ Wochenplan</div>
          <button class="generate-button" onclick="this.getRootNode().host._generatePlan()">
            Neu generieren
          </button>
        </div>
        ${hasPlan ? `
          <div class="week-grid">
            ${weekdays.map(weekday => `
              <div class="day-column">
                <div class="day-header">${weekday}</div>
                ${slots.map(slot => this._renderSlot(weekday, slot)).join('')}
              </div>
            `).join('')}
          </div>
        ` : `
          <div class="no-plan">
            <p>Kein Wochenplan vorhanden</p>
            <button class="generate-button" onclick="this.getRootNode().host._generatePlan()">
              Wochenplan generieren
            </button>
          </div>
        `}
      </ha-card>
    `;
  }
}

customElements.define('weekly-plan-card', WeeklyPlanCard);

// Register the card with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'weekly-plan-card',
  name: 'KI-Essensplaner Wochenplan',
  description: 'Zeigt den wöchentlichen Essensplan mit Rezeptauswahl',
  preview: false,
  documentationURL: 'https://github.com/sourcesavant/ki-essensplaner',
});

console.info(
  '%c KI-ESSENSPLANER-CARD %c Weekly Plan Card loaded ',
  'color: white; background: #4caf50; font-weight: 700;',
  'color: #4caf50; background: white; font-weight: 700;'
);
