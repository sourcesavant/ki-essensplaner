const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');

function setup(file = 'dist/shopping-list-card.js') {
  let Card;
  const context = {
    HTMLElement: class {
      attachShadow() {
        this.shadowRoot = { querySelector: () => null, querySelectorAll: () => [], innerHTML: '' };
      }
    },
    customElements: { define: (_, cls) => { Card = cls; } },
    window: { scrollY: 0 }, document: {}, console: { info() {} }, CSS: { escape: s => s },
  };
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), context);
  const card = new Card();
  card.setConfig({ bioland_entity: 'bio', rewe_entity: 'rewe', total_entity: 'total' });
  const states = {
    bio: { attributes: { items: [], week_start: 'week1' } },
    rewe: { attributes: { items: [{ ingredient: 'Reis', unit: 'gramm', amount: 200, checked: true }], week_start: 'week1' } },
    total: { state: '1' },
  };
  card.hass = { states, callService: () => Promise.resolve() };
  return { card, states };
}

test('server unchecks and increased quantities propagate', () => {
  const { card, states } = setup();
  assert(card._checkedItems.has('reis_gramm'));
  states.rewe.attributes.items[0] = { ingredient: 'Reis', unit: 'gramm', amount: 400, checked: false };
  card.render();
  assert(!card._checkedItems.has('reis_gramm'));
  assert(card.shadowRoot.innerHTML.includes('400'));
});

test('pending local changes survive stale server state, then accept remote state', async () => {
  const { card, states } = setup();
  let done;
  card._hass.callService = () => new Promise(resolve => { done = resolve; });
  card._toggleItem('reis_gramm');
  card.render();
  assert(!card._checkedItems.has('reis_gramm'));
  states.rewe.attributes.items[0].checked = false;
  done();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(card._pendingChecks.size, 0);
  states.rewe.attributes.items[0].checked = true;
  card.render();
  assert(card._checkedItems.has('reis_gramm'));
});

test('failed changes revert and show an error', async () => {
  const { card } = setup();
  card._hass.callService = () => Promise.reject(new Error('failed'));
  card._toggleItem('reis_gramm');
  await new Promise(resolve => setImmediate(resolve));
  assert(card._checkedItems.has('reis_gramm'));
  assert(card.shadowRoot.innerHTML.includes('nicht gespeichert'));
});

test('missing recipe warnings are escaped and updated', () => {
  const { card, states } = setup();
  states.rewe.attributes.missing_recipes = ['<Test>'];
  card.render();
  assert(card.shadowRoot.innerHTML.includes('&lt;Test&gt;'));
  assert(card.shadowRoot.innerHTML.includes('role="alert"'));
});

test('bundle ships the same shopping implementation and propagates unchecks', () => {
  const body = (file) => fs.readFileSync(file, 'utf8').split('class ShoppingListCard')[1].split("customElements.define('shopping-list-card'")[0];
  assert.equal(body('dist/ki-essensplaner.js'), body('dist/shopping-list-card.js'));
  const { card, states } = setup('dist/ki-essensplaner.js');
  states.rewe.attributes.items[0].checked = false;
  card.render();
  assert(!card._checkedItems.has('reis_gramm'));
});
