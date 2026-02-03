/**
 * KI-Essensplaner Shopping List Card
 *
 * Custom Lovelace card for displaying the shopping list.
 * Shows items split by store (Bioland / Rewe) with checkboxes.
 */

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
          <div class="card-title">🛒 Einkaufsliste</div>
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
              Markierungen löschen (${this._checkedItems.size})
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

// Register the card with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'shopping-list-card',
  name: 'KI-Essensplaner Einkaufsliste',
  description: 'Zeigt die Einkaufsliste aufgeteilt nach Bioland und Rewe',
  preview: false,
  documentationURL: 'https://github.com/sourcesavant/ki-essensplaner',
});

console.info(
  '%c KI-ESSENSPLANER-CARD %c Shopping List Card loaded ',
  'color: white; background: #ff9800; font-weight: 700;',
  'color: #ff9800; background: white; font-weight: 700;'
);
