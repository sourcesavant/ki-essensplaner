/**
 * KI-Essensplaner Lovelace Cards Bundle
 *
 * Contains:
 * - weekly-plan-card: Weekly meal plan display
 * - shopping-list-card: Shopping list with store split
 *
 * @version 1.0.0
 */

// ============================================================================
// Weekly Plan Card
// ============================================================================

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
    this._entityPrefix = this._deriveEntityPrefix(config.entity);
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

  _setRecipeUrl(weekday, slot, recipeUrl) {
    const url = (recipeUrl || '').trim();
    if (!url) return;
    this._callService('set_recipe_url', {
      weekday: weekday,
      slot: slot,
      recipe_url: url
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

    return `${this._entityPrefix}${day}_${meal}`;
  }

  _deriveEntityPrefix(entityId) {
    if (!entityId) return 'sensor.essensplaner_';
    if (entityId.endsWith('_weekly_plan_status')) {
      return entityId.slice(0, -'weekly_plan_status'.length);
    }
    return 'sensor.essensplaner_';
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
    const selectedIndex = Number.isInteger(attributes.selected_index) ? attributes.selected_index : 0;

    const effortColor = this._getEffortColor(prepTime);
    const newBadge = isNew ? '<span class="badge new">NEU</span>' : '';
    const reuseBadge = isReuseSlot ? '<span class="badge reuse">Reste</span>' : '';

    const alternativesHtml = !isReuseSlot ? `
      <select class="alternatives" onchange="this.getRootNode().host._selectRecipe('${weekday}', '${slot}', this.value)">
        <option value="-1" ${selectedIndex === -1 ? 'selected' : ''}>Kein Rezept</option>
        ${alternatives.map((alt, index) => `
          <option value="${index}" ${index === selectedIndex ? 'selected' : ''}>
            ${alt.title}${alt.is_new ? ' 🆕' : ''}
          </option>
        `).join('')}
      </select>
      <div class="custom-url">
        <input class="custom-url-input" type="url" placeholder="Rezept-Link einfuegen" />
        <button class="custom-url-button" onclick="this.getRootNode().host._setRecipeUrl('${weekday}', '${slot}', this.previousElementSibling.value); this.previousElementSibling.value = '';">
          Hinzufuegen
        </button>
      </div>
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
          grid-template-columns: repeat(7, minmax(160px, 1fr));
          gap: 8px;
          overflow-x: auto;
          padding-bottom: 4px;
        }
        .day-column {
          display: flex;
          flex-direction: column;
          gap: 8px;
          min-width: 160px;
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
        .custom-url {
          display: flex;
          gap: 6px;
          margin-top: 6px;
        }
        .custom-url-input {
          flex: 1;
          padding: 4px 6px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 12px;
        }
        .custom-url-button {
          padding: 4px 8px;
          border: none;
          border-radius: 4px;
          background: var(--primary-color);
          color: white;
          cursor: pointer;
          font-size: 12px;
        }
        .custom-url-button:hover {
          opacity: 0.9;
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
          <div class="card-title">Wochenplan</div>
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

// ============================================================================
// Shopping List Card
// ============================================================================

class ShoppingListCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._activeTab = 'bioland';
    this._checkedItems = new Set();
  }

  setConfig(config) {
    this._config = {
      bioland_entity: 'sensor.essensplaner_bioland_anzahl',
      rewe_entity: 'sensor.essensplaner_rewe_anzahl',
      total_entity: 'sensor.essensplaner_einkaufsliste_anzahl',
      ...config
    };
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 6;
  }

  _switchTab(tab) {
    this._activeTab = tab;
    this.render();
  }

  _toggleItem(itemKey) {
    if (this._checkedItems.has(itemKey)) {
      this._checkedItems.delete(itemKey);
    } else {
      this._checkedItems.add(itemKey);
    }
    this.render();
  }

  _clearChecked() {
    this._checkedItems.clear();
    this.render();
  }

  _renderItem(item, index, store) {
    const itemKey = `${store}_${index}`;
    const isChecked = this._checkedItems.has(itemKey);
    const amount = item.amount ? `${item.amount}` : '';
    const unit = item.unit || '';
    const ingredient = item.ingredient || '';

    return `
      <div class="item ${isChecked ? 'checked' : ''}">
        <input
          type="checkbox"
          ${isChecked ? 'checked' : ''}
          onchange="this.getRootNode().host._toggleItem('${itemKey}')"
        />
        <span class="item-text">
          ${amount} ${unit} <strong>${ingredient}</strong>
        </span>
      </div>
    `;
  }

  render() {
    if (!this._hass || !this._config) return;

    const biolandState = this._hass.states[this._config.bioland_entity];
    const reweState = this._hass.states[this._config.rewe_entity];
    const totalState = this._hass.states[this._config.total_entity];

    const biolandItems = biolandState?.attributes?.items || [];
    const reweItems = reweState?.attributes?.items || [];
    const biolandCount = biolandItems.length;
    const reweCount = reweItems.length;
    const totalCount = totalState?.state || 0;

    const hasItems = totalCount > 0;

    const biolandChecked = biolandItems.filter((_, i) => this._checkedItems.has(`bioland_${i}`)).length;
    const reweChecked = reweItems.filter((_, i) => this._checkedItems.has(`rewe_${i}`)).length;

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
        .card-stats {
          font-size: 14px;
          color: var(--secondary-text-color);
        }
        .tabs {
          display: flex;
          gap: 8px;
          margin-bottom: 16px;
          border-bottom: 2px solid var(--divider-color);
        }
        .tab {
          padding: 8px 16px;
          cursor: pointer;
          border: none;
          background: transparent;
          color: var(--secondary-text-color);
          font-size: 16px;
          font-weight: 500;
          border-bottom: 2px solid transparent;
          margin-bottom: -2px;
          transition: all 0.2s;
        }
        .tab:hover {
          color: var(--primary-text-color);
        }
        .tab.active {
          color: var(--primary-color);
          border-bottom-color: var(--primary-color);
        }
        .tab-badge {
          display: inline-block;
          margin-left: 8px;
          padding: 2px 8px;
          border-radius: 12px;
          background: var(--secondary-background-color);
          font-size: 12px;
        }
        .tab.active .tab-badge {
          background: var(--primary-color);
          color: white;
        }
        .item-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 400px;
          overflow-y: auto;
        }
        .item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 8px;
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          transition: all 0.2s;
        }
        .item:hover {
          background: var(--secondary-background-color);
        }
        .item.checked {
          opacity: 0.5;
        }
        .item.checked .item-text {
          text-decoration: line-through;
        }
        .item input[type="checkbox"] {
          width: 20px;
          height: 20px;
          cursor: pointer;
        }
        .item-text {
          flex: 1;
          font-size: 14px;
          color: var(--primary-text-color);
        }
        .actions {
          display: flex;
          gap: 8px;
          margin-top: 16px;
        }
        .action-button {
          padding: 8px 16px;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
          transition: all 0.2s;
        }
        .action-button.primary {
          background: var(--primary-color);
          color: white;
        }
        .action-button.secondary {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
        }
        .action-button:hover {
          opacity: 0.9;
        }
        .no-items {
          text-align: center;
          padding: 40px;
          color: var(--secondary-text-color);
        }
        .empty-tab {
          text-align: center;
          padding: 20px;
          color: var(--secondary-text-color);
          font-style: italic;
        }
      </style>
      <ha-card class="card">
        <div class="card-header">
          <div class="card-title">Einkaufsliste</div>
          <div class="card-stats">${totalCount} Artikel</div>
        </div>

        ${hasItems ? `
          <div class="tabs">
            <button
              class="tab ${this._activeTab === 'bioland' ? 'active' : ''}"
              onclick="this.getRootNode().host._switchTab('bioland')"
            >
              Bioland
              <span class="tab-badge">${biolandCount}</span>
            </button>
            <button
              class="tab ${this._activeTab === 'rewe' ? 'active' : ''}"
              onclick="this.getRootNode().host._switchTab('rewe')"
            >
              Rewe
              <span class="tab-badge">${reweCount}</span>
            </button>
          </div>

          <div class="item-list">
            ${this._activeTab === 'bioland' ? (
              biolandItems.length > 0
                ? biolandItems.map((item, i) => this._renderItem(item, i, 'bioland')).join('')
                : '<div class="empty-tab">Keine Bioland-Artikel</div>'
            ) : (
              reweItems.length > 0
                ? reweItems.map((item, i) => this._renderItem(item, i, 'rewe')).join('')
                : '<div class="empty-tab">Keine Rewe-Artikel</div>'
            )}
          </div>

          <div class="actions">
            <button
              class="action-button secondary"
              onclick="this.getRootNode().host._clearChecked()"
              ${this._checkedItems.size === 0 ? 'disabled' : ''}
            >
              Markierungen loeschen (${this._checkedItems.size})
            </button>
          </div>

          <div style="margin-top: 12px; font-size: 12px; color: var(--secondary-text-color);">
            ${this._activeTab === 'bioland'
              ? `${biolandChecked} von ${biolandCount} abgehakt`
              : `${reweChecked} von ${reweCount} abgehakt`
            }
          </div>
        ` : `
          <div class="no-items">
            <p>Keine Einkaufsliste vorhanden</p>
            <p style="font-size: 14px;">Generiere zuerst einen Wochenplan</p>
          </div>
        `}
      </ha-card>
    `;
  }
}

customElements.define('shopping-list-card', ShoppingListCard);

// ============================================================================
// Register Cards with Home Assistant
// ============================================================================

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'weekly-plan-card',
  name: 'KI-Essensplaner Wochenplan',
  description: 'Zeigt den woechentlichen Essensplan mit Rezeptauswahl',
  preview: false,
  documentationURL: 'https://github.com/sourcesavant/ki-essensplaner',
});
window.customCards.push({
  type: 'shopping-list-card',
  name: 'KI-Essensplaner Einkaufsliste',
  description: 'Zeigt die Einkaufsliste aufgeteilt nach Bioland und Rewe',
  preview: false,
  documentationURL: 'https://github.com/sourcesavant/ki-essensplaner',
});

console.info(
  '%c KI-ESSENSPLANER %c v1.0.0 - Cards loaded ',
  'color: white; background: #4caf50; font-weight: 700;',
  'color: #4caf50; background: white; font-weight: 700;'
);




