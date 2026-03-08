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
    this._lastRenderKey = null;
    this._lastListKey = null;
  }

  setConfig(config) {
    const entityId = config?.entity || config?.total_entity || null;
    const prefix = this._deriveEntityPrefix(entityId);
    this._config = {
      bioland_entity: `${prefix}bioland_anzahl`,
      rewe_entity: `${prefix}rewe_anzahl`,
      total_entity: `${prefix}einkaufsliste_anzahl`,
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

  _deriveEntityPrefix(entityId) {
    if (!entityId) return 'sensor.essensplaner_';
    if (entityId.endsWith('_einkaufsliste_anzahl')) {
      return entityId.slice(0, -'einkaufsliste_anzahl'.length);
    }
    if (entityId.endsWith('_shopping_list_count')) {
      return entityId.slice(0, -'shopping_list_count'.length);
    }
    if (entityId.endsWith('_bioland_anzahl')) {
      return entityId.slice(0, -'bioland_anzahl'.length);
    }
    if (entityId.endsWith('_rewe_anzahl')) {
      return entityId.slice(0, -'rewe_anzahl'.length);
    }
    return 'sensor.essensplaner_';
  }

  _switchTab(tab) {
    this._activeTab = tab;
    this.render();
  }

  _itemKey(item) {
    return `${(item.ingredient || '').toLowerCase()}_${item.unit || ''}`;
  }

  _escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  _toggleItem(itemKey) {
    const newChecked = !this._checkedItems.has(itemKey);
    if (newChecked) {
      this._checkedItems.add(itemKey);
    } else {
      this._checkedItems.delete(itemKey);
    }
    // Optimistic UI update
    const itemEl = this.shadowRoot?.querySelector(`.item[data-item-key="${CSS.escape(itemKey)}"]`);
    if (itemEl) {
      itemEl.classList.toggle('checked', newChecked);
      const checkbox = itemEl.querySelector('input[type="checkbox"]');
      if (checkbox) checkbox.checked = newChecked;
    }
    this._updateCheckedUi();
    // Persist via HA service
    this._hass.callService('ki_essensplaner', 'toggle_shopping_item', {
      item_key: itemKey,
      checked: newChecked,
    });
  }

  _clearChecked() {
    this._checkedItems.clear();
    const itemEls = this.shadowRoot?.querySelectorAll('.item.checked');
    if (itemEls && itemEls.length) {
      itemEls.forEach((el) => {
        el.classList.remove('checked');
        const checkbox = el.querySelector('input[type="checkbox"]');
        if (checkbox) checkbox.checked = false;
      });
    }
    this._updateCheckedUi();
    // Persist via HA service
    this._hass.callService('ki_essensplaner', 'clear_checked_items', {});
  }

  _updateCheckedUi() {
    const biolandState = this._hass?.states?.[this._config.bioland_entity];
    const reweState = this._hass?.states?.[this._config.rewe_entity];
    const biolandItems = biolandState?.attributes?.items || [];
    const reweItems = reweState?.attributes?.items || [];
    const biolandCount = biolandItems.length;
    const reweCount = reweItems.length;
    const biolandChecked = biolandItems.filter((item) => this._checkedItems.has(this._itemKey(item))).length;
    const reweChecked = reweItems.filter((item) => this._checkedItems.has(this._itemKey(item))).length;

    const clearBtn = this.shadowRoot?.querySelector('.action-button.secondary');
    if (clearBtn) {
      clearBtn.disabled = this._checkedItems.size === 0;
      const countEl = clearBtn.querySelector('.clear-count');
      if (countEl) countEl.textContent = `${this._checkedItems.size}`;
    }

    const summary = this.shadowRoot?.querySelector('.checked-summary');
    if (summary) {
      summary.textContent = this._activeTab === 'bioland'
        ? `${biolandChecked} von ${biolandCount} abgehakt`
        : `${reweChecked} von ${reweCount} abgehakt`;
    }
  }

  _renderItem(item) {
    const itemKey = this._itemKey(item);
    const escapedItemKey = this._escapeHtml(itemKey);
    const isChecked = this._checkedItems.has(itemKey);
    const amount = item.amount ? `${item.amount}` : '';
    const unit = item.unit || '';
    const ingredient = item.ingredient || '';

    return `
      <div class="item ${isChecked ? 'checked' : ''}" data-item-key="${escapedItemKey}">
        <input
          class="item-toggle"
          type="checkbox"
          data-item-key="${escapedItemKey}"
          ${isChecked ? 'checked' : ''}
        />
        <span class="item-text">
          ${this._escapeHtml(amount)} ${this._escapeHtml(unit)} <strong>${this._escapeHtml(ingredient)}</strong>
        </span>
      </div>
    `;
  }

  _bindItemListeners() {
    const toggles = this.shadowRoot?.querySelectorAll('.item-toggle') || [];
    toggles.forEach((el) => {
      el.addEventListener('change', (event) => {
        const key = event.currentTarget?.dataset?.itemKey;
        if (!key) return;
        this._toggleItem(key);
      });
    });
  }

  render() {
    if (!this._hass || !this._config) return;

    const prevListEl = this.shadowRoot?.querySelector('.item-list');
    const prevScrollTop = prevListEl ? prevListEl.scrollTop : 0;
    const prevPageScroll = document.scrollingElement
      ? document.scrollingElement.scrollTop
      : window.scrollY;

    const biolandState = this._hass.states[this._config.bioland_entity];
    const reweState = this._hass.states[this._config.rewe_entity];
    const totalState = this._hass.states[this._config.total_entity];
    const missingEntities = [];

    if (!biolandState) missingEntities.push(this._config.bioland_entity);
    if (!reweState) missingEntities.push(this._config.rewe_entity);
    if (!totalState) missingEntities.push(this._config.total_entity);

    const biolandItems = biolandState?.attributes?.items || [];
    const reweItems = reweState?.attributes?.items || [];
    const biolandCount = biolandItems.length;
    const reweCount = reweItems.length;
    const totalFromState = Number(totalState?.state);
    const totalCount = Number.isFinite(totalFromState) && totalFromState >= 0
      ? totalFromState
      : biolandCount + reweCount;

    const hasItems = (biolandCount + reweCount) > 0 || totalCount > 0;

    // Hydration strategy:
    // - compositionKey tracks which items exist (ingredients + units, no checked state).
    // - On composition change (new week / plan edit): full reset from server.
    // - Same composition: one-way merge — add any server-checked items not yet local
    //   (cross-device adds propagate within the poll interval, ~30s).
    //   Local unchecks are never overridden, avoiding the race condition where a fast
    //   double-check loses the second item when the first coordinator refresh arrives.
    const allItems = [...biolandItems, ...reweItems];
    const compositionKey = JSON.stringify(allItems.map((i) => this._itemKey(i)));
    if (compositionKey !== this._lastListKey) {
      // New week or recipe change → full reset from server state
      this._lastListKey = compositionKey;
      this._checkedItems = new Set(
        allItems.filter((i) => i.checked).map((i) => this._itemKey(i))
      );
    } else {
      // Same list → only add server-checked items (cross-device sync for adds)
      for (const item of allItems) {
        if (item.checked) this._checkedItems.add(this._itemKey(item));
      }
    }

    const biolandChecked = biolandItems.filter((item) => this._checkedItems.has(this._itemKey(item))).length;
    const reweChecked = reweItems.filter((item) => this._checkedItems.has(this._itemKey(item))).length;

    const renderKey = JSON.stringify({
      missing: missingEntities,
      active: this._activeTab,
      totalCount,
      biolandItems,
      reweItems,
    });
    if (this._lastRenderKey === renderKey) {
      return;
    }
    this._lastRenderKey = renderKey;

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

        ${missingEntities.length > 0 ? `
          <div class="no-items">
            <p>Fehlende Sensoren für die Einkaufsliste</p>
            <p style="font-size: 14px;">Bitte prüfe die Entity-IDs:</p>
            <div style="font-size: 12px; margin-top: 8px; color: var(--secondary-text-color);">
              ${missingEntities.map(entity => `<div>${entity}</div>`).join('')}
            </div>
          </div>
        ` : hasItems ? `
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
                ? biolandItems.map((item) => this._renderItem(item)).join('')
                : '<div class="empty-tab">Keine Bioland-Artikel</div>'
            ) : (
              reweItems.length > 0
                ? reweItems.map((item) => this._renderItem(item)).join('')
                : '<div class="empty-tab">Keine Rewe-Artikel</div>'
            )}
          </div>

          <div class="actions">
            <button
              class="action-button secondary"
              onclick="this.getRootNode().host._clearChecked()"
              ${this._checkedItems.size === 0 ? 'disabled' : ''}
            >
              Markierungen löschen (<span class="clear-count">${this._checkedItems.size}</span>)
            </button>
          </div>

          <div class="checked-summary" style="margin-top: 12px; font-size: 12px; color: var(--secondary-text-color);">
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
    this._bindItemListeners();

    const newListEl = this.shadowRoot?.querySelector('.item-list');
    if (newListEl) {
      requestAnimationFrame(() => {
        newListEl.scrollTop = prevScrollTop;
      });
    }
    if (document.scrollingElement) {
      requestAnimationFrame(() => {
        document.scrollingElement.scrollTop = prevPageScroll;
      });
    }
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
