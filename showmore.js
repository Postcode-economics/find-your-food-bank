/* Food-bank results: nearest() paints the first page; this file adds the rest.
   Contract: window.SHOW_LIMITS = {first: 5, more: 10} and window.showMoreResults().
   Cards stay in #list as .card elements. A new nearest() call starts again at the first page.
   Show more does not move the page (scroll is restored). The button is a real <button>
   with aria-expanded, so Enter and Space work. Welsh label: Dangos mwy. */
(function () {
  window.SHOW_LIMITS = {first: 5, more: 10};
  var expanded = false;

  function limits() {
    var L = window.SHOW_LIMITS || {};
    var first = +L.first, more = +L.more;
    return {first: first > 0 ? first : 5, more: more > 0 ? more : 10};
  }

  function ranked() {
    if (typeof items === 'undefined' || typeof dists === 'undefined' || typeof vis !== 'function') return [];
    var out = [];
    for (var k = 0; k < items.length; k++) {
      if (!vis(k)) continue;
      var i = items[k];
      if (typeof nc === 'function' && nc(i)) continue;
      var d = dists[k];
      if (typeof d !== 'number' || d !== d) continue;
      out.push({i: i, k: k, d: d});
    }
    out.sort(function (a, b) { return a.d - b.d; });
    return out;
  }

  function listEl() { return document.getElementById('list'); }

  function cardsOf(list) { return list ? list.querySelectorAll(':scope > .card') : []; }

  function makeCard(x) {
    var el = document.createElement('div');
    el.className = 'card';
    el.dataset.k = String(x.k);
    el.innerHTML = card(x.i, x.d);
    try {
      if (window.V3 && (typeof nc !== 'function' || !nc(x.i)) && V3.status('fb', x.i).st === 'closed') el.classList.add('v3closed');
    } catch (e) {}
    var h = el.querySelector('h3');
    if (h) {
      h.style.cursor = 'pointer';
      h.onclick = function () { select(+el.dataset.k, true); };
    }
    return el;
  }

  /* Add up to n cards that are not already in the list. Returns how many were added. */
  function reveal(list, n) {
    if (!list || typeof card !== 'function' || !(n > 0)) return [];
    var all = ranked();
    var have = {};
    Array.prototype.forEach.call(cardsOf(list), function (c) { have[String(c.dataset.k)] = 1; });
    var batch = [];
    for (var i = 0; i < all.length && batch.length < n; i++) {
      if (!have[String(all[i].k)]) batch.push(all[i]);
    }
    if (!batch.length) return [];
    var btn = document.getElementById('showmore');
    var frag = document.createDocumentFragment();
    var added = [];
    batch.forEach(function (it) {
      var el = makeCard(it);
      added.push(el);
      frag.appendChild(el);
    });
    if (btn && list.contains(btn)) list.insertBefore(frag, btn);
    else list.appendChild(frag);
    return added;
  }

  function paintButton(list) {
    if (!list) return;
    var n = cardsOf(list).length;
    var remain = n ? Math.max(0, ranked().length - n) : 0;
    var btn = document.getElementById('showmore');
    if (!n || remain <= 0) {
      if (btn) {
        btn.hidden = true;
        btn.setAttribute('aria-expanded', 'true');
      }
      return;
    }
    if (!btn || !list.contains(btn)) {
      btn = document.createElement('button');
      btn.type = 'button';
      btn.id = 'showmore';
      btn.className = 'showmore';
      btn.setAttribute('aria-controls', 'list');
      btn.innerHTML = '<span class="v-en">Show more</span><span class="v-cy" lang="cy">Dangos mwy</span>';
      btn.addEventListener('click', function () { window.showMoreResults(); });
    }
    btn.hidden = false;
    btn.removeAttribute('tabindex');
    btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    list.appendChild(btn);
  }

  function fitFirst(list) {
    var first = limits().first;
    var cards = cardsOf(list);
    var i;
    if (cards.length > first) {
      for (i = cards.length - 1; i >= first; i--) cards[i].remove();
    } else if (cards.length < first) {
      reveal(list, first - cards.length);
    }
  }

  /* Chromium scrolls a newly focused card into view on a later frame. Put the
     scroll position back, including when that frame arrives. */
  function pinScroll(x, y) {
    var lock = true, busy = false;
    function fix() {
      if (!lock || busy) return;
      if (window.scrollX === x && window.scrollY === y) return;
      busy = true;
      window.scrollTo(x, y);
      busy = false;
    }
    fix();
    window.addEventListener('scroll', fix, true);
    requestAnimationFrame(function () {
      fix();
      requestAnimationFrame(function () {
        fix();
        lock = false;
        window.removeEventListener('scroll', fix, true);
      });
    });
  }

  window.showMoreResults = function () {
    var list = listEl();
    if (!list) return 0;
    var x = window.scrollX, y = window.scrollY;
    var fromBtn = !!(document.activeElement && document.activeElement.id === 'showmore');
    var added = reveal(list, limits().more);
    if (added.length) expanded = true;
    var remain = Math.max(0, ranked().length - cardsOf(list).length);
    if (fromBtn && remain <= 0 && added[0]) {
      var h = added[0].querySelector('h3');
      if (h) { h.tabIndex = -1; h.focus({preventScroll: true}); }
    }
    paintButton(list);
    if (fromBtn && remain > 0) {
      var b = document.getElementById('showmore');
      if (b && !b.hidden) b.focus({preventScroll: true});
    }
    pinScroll(x, y);
    return added.length;
  };

  function install() {
    if (install.done || typeof window.nearest !== 'function') return;
    var orig = window.nearest;
    function wrapped() {
      expanded = false;
      var r = orig.apply(this, arguments);
      try {
        var list = listEl();
        if (list && cardsOf(list).length) {
          fitFirst(list);
          paintButton(list);
        }
      } catch (e) {}
      return r;
    }
    window.nearest = wrapped;
    try { nearest = wrapped; } catch (e) {}
    install.done = true;
    try {
      var list = listEl();
      if (list && cardsOf(list).length) {
        fitFirst(list);
        paintButton(list);
      }
    } catch (e) {}
  }

  var css = document.createElement('style');
  css.setAttribute('data-showmore', '1');
  css.textContent = '#showmore.showmore{display:flex;align-items:center;justify-content:center;width:100%;box-sizing:border-box;min-height:48px;margin:8px 0 18px;padding:10px 16px;background:transparent;color:#F5C518;border:2px solid #F5C518;border-radius:10px;font:inherit;font-weight:800;font-size:18px;cursor:pointer;overflow-anchor:none}#showmore.showmore[hidden]{display:none!important}#showmore.showmore:focus-visible{outline:3px solid #F2F4F8;outline-offset:3px}html.light #showmore.showmore{color:#0A1628;border-color:#8A6A2E;background:#fff}html.light #showmore.showmore:focus-visible{outline-color:#0A1628}';
  document.head.appendChild(css);
  install();
})();
