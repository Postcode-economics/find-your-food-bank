/* Uniform place-card rows (Dean 31 Oct 2026). Display only: never invents a fact the record does not state.
   Same rows, same order, on food banks, shelters, warm spaces, day centres, hostels and foyers.
   Unknown values say Not stated / Heb ei nodi. Wheelchair is yes | partial | no or missing — never inferred
   from Accessible Toilets. Opening lines use the same formatter as the food-bank cards (window.timesFmt). */
(function () {
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const lang = () => { try { return document.documentElement.lang === 'cy' ? 'cy' : 'en'; } catch (e) { return 'en'; } };
  const B = (en, cy) => `<span class="v-en">${en}</span><span class="v-cy" lang="cy">${cy}</span>`;
  const NS = () => B('Not stated', 'Heb ei nodi');
  const MEN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const MCY = ['Ionawr', 'Chwefror', 'Mawrth', 'Ebrill', 'Mai', 'Mehefin', 'Gorffennaf', 'Awst', 'Medi', 'Hydref', 'Tachwedd', 'Rhagfyr'];
  const DAY = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
  const DN = { mon: 'Mon', tue: 'Tue', wed: 'Wed', thu: 'Thu', fri: 'Fri', sat: 'Sat', sun: 'Sun' };
  const DCY = { mon: 'Llun', tue: 'Maw', wed: 'Mer', thu: 'Iau', fri: 'Gwe', sat: 'Sad', sun: 'Sul' };
  const FAC = [
    ['Food Available', 'Food', 'Bwyd'],
    ['Hot Drinks', 'Hot drinks', 'Diodydd poeth'],
    ['Showers', 'Showers', 'Cawodydd'],
    ['Laundry', 'Laundry', 'Golchi dillad'],
    ['Free Wifi', 'Wifi', 'Wifi'],
    ['Charging Facilities', 'Charging', 'Gwefru'],
    ['Accessible Toilets', 'Toilets', 'Toiledau'],
    ['Parking', 'Parking', 'Parcio'],
    ['Computer Access', 'Computers', 'Cyfrifiaduron'],
    ['Other Refreshments', 'Refreshments', 'Lluniaeth'],
    ['Child Friendly', 'Child friendly', 'Croeso i blant'],
    ['Energy Advice', 'Energy advice', 'Cyngor ar ynni'],
    ['Cool Space', 'Cool space', 'Man oer'],
    ['TV', 'TV', 'Teledu']
  ];
  const WHO = {
    'men only': ['Men only', 'Dynion yn unig'],
    'women only': ['Women only', 'Menywod yn unig'],
    'men': ['Men', 'Dynion'],
    'women': ['Women', 'Menywod'],
    'families': ['Families', 'Teuluoedd'],
    'young people': ['Young people', 'Pobl ifanc'],
    'mixed gender': ['Mixed gender', 'Rhyw cymysg'],
    'dogs welcome': ['Dogs welcome', 'Croeso i gŵn'],
    'couples': ['Couples', 'Cyplau']
  };
  function row(en, cy, body) {
    const tag = /<(div|table|ul)\b/.test(body) ? 'div' : 'p';
    const ot = en === 'Opening times' ? ' ot' : '';
    return `<${tag} class="xrow${ot}"><b>${B(esc(en), esc(cy))}:</b> ${body}</${tag}>`;
  }
  function phrase(en, cy) { return B(esc(en), esc(cy || en)); }
  function winter(i) {
    const s = String((i && i.season) || '');
    return /winter|swep|cold weather/i.test(s);
  }
  function typeOf(layer, i) {
    i = i || {};
    if (layer === 'ws') return ['Warm space', 'Man cynnes'];
    if (layer === 'fb') {
      if (i.kind === 'warehouse' || i.kind === 'dropoff') {
        const en = String(i.label_en || 'Food bank').replace(/^📦\s*/, '');
        return [en, String(i.label_cy || 'Banc bwyd')];
      }
      return ['Food bank', 'Banc bwyd'];
    }
    if (i.kind === 'day_centre' || i.service === 'day_centre') return ['Day centre', 'Canolfan ddydd'];
    const name = String(i.name || '');
    const groups = (i.groups || []).join(' ');
    if (i.kind === 'young_people' || /\bfoyers?\b/i.test(name) || (/\bhousing\b/i.test(name) && /16\s*[-–to]{1,3}\s*25/i.test(name + ' ' + groups)))
      return ['Young people’s housing (16–25), referral needed', 'Tai i bobl ifanc (16–25), angen atgyfeiriad'];
    const hostel = /\bhostel\b/i.test(name);
    const referral = i.access_type === 'referral_only' || /\breferral only\b/i.test(String(i.referral || ''));
    if (hostel && referral) return ['Referral hostel', 'Hostel drwy atgyfeiriad'];
    if (hostel) return ['Hostel', 'Hostel'];
    return ['Night shelter', 'Lloches nos'];
  }
  function typeRow(layer, i, opt) {
    const t = typeOf(layer, i);
    const sea = winter(i) ? `<span class="useason">${B('Winter-only', 'Gaeaf yn unig')}</span>` : '';
    const icon = (opt && opt.icon) || '';
    return `<div class="tag utag" role="note">${icon}<span class="utxt">${phrase(t[0], t[1])}${sea}</span></div>`;
  }
  function whoBits(i) {
    const groups = (i.groups || []).map(s => String(s).trim()).filter(Boolean);
    const low = groups.map(g => g.toLowerCase());
    const hasW = low.some(g => /\bwomen\b|\bfemale\b/.test(g));
    const hasM = low.some(g => (/\bmen\b|\bmale\b/.test(g) && !/\bwomen\b|\bfemale\b/.test(g)));
    const bits = groups.map(g => {
      const k = g.toLowerCase();
      if (k === 'men' || k === 'male') return hasW ? WHO.men : WHO['men only'];
      if (k === 'women' || k === 'female') return hasM ? WHO.women : WHO['women only'];
      if (WHO[k]) return WHO[k];
      if (/^couples\b/i.test(g)) return [g.charAt(0).toUpperCase() + g.slice(1), g.charAt(0).toUpperCase() + g.slice(1)];
      return [g.charAt(0).toUpperCase() + g.slice(1), g.charAt(0).toUpperCase() + g.slice(1)];
    });
    const prov = [].concat(i.provided || [], i.facilities || []);
    if (prov.indexOf('Dog Friendly') >= 0 && !bits.some(b => /dog/i.test(b[0]))) bits.push(WHO['dogs welcome']);
    return bits;
  }
  function whoHtml(i) {
    const bits = whoBits(i);
    if (!bits.length) return '';
    return bits.map(b => phrase(b[0], b[1])).join(' · ');
  }
  function accessOf(i, opt) {
    if (opt && opt.access) return opt.access;
    try { if (typeof window.acc === 'function') return window.acc(i); } catch (e) {}
    const A = (typeof window !== 'undefined' && window.FB_ACCESS) || {};
    return A[i.id] || 'unconfirmed';
  }
  function stripHow(ref) {
    return String(ref || '').replace(/^(referral only|referral needed|by referral|self-?referral|open access)\s*[:.–-]?\s*/i, '').replace(/^via\s+/i, '').trim();
  }
  function howPair(layer, i, opt) {
    const ref = String(i.referral || '').trim();
    if (layer === 'fb') {
      const a = accessOf(i, opt);
      if (a === 'voucher') return ['Voucher', 'Taleb'];
      if (a === 'walkin') return ['Walk-in', 'Galw heibio'];
      return null;
    }
    const at = i.access_type;
    if (at === 'self_referral' || /^self-?referral\b/i.test(ref)) {
      const extra = stripHow(ref);
      return extra ? ['Self-referral · ' + extra, 'Hunangyfeirio · ' + extra] : ['Self-referral', 'Hunangyfeirio'];
    }
    if (at === 'open_access' || /^open access\b/i.test(ref) || /\bno referral\b/i.test(ref)) {
      const extra = stripHow(ref);
      return extra ? ['Walk-in · ' + extra, 'Galw heibio · ' + extra] : ['Walk-in', 'Galw heibio'];
    }
    if (at === 'referral_only' || /\breferral\b/i.test(ref)) {
      const via = stripHow(ref);
      if (via) return ['Referral via ' + via, 'Atgyfeiriad drwy ' + via];
      if (i.council) return ['Referral via ' + i.council, 'Atgyfeiriad drwy ' + i.council];
      return ['Referral', 'Atgyfeiriad'];
    }
    if (i.booking === 'Booking needed') return ['Booking needed', 'Rhaid archebu'];
    if (i.booking === 'No booking needed') return ['No booking needed', 'Dim angen archebu'];
    return null;
  }
  function wheelPair(i) {
    const w = i && i.wheelchair;
    if (w === 'yes') return ['Yes', 'Ie'];
    if (w === 'partial') return ['Partly', 'Rhannol'];
    if (w === 'no') return ['No', 'Na'];
    return null;
  }
  function normPc(pc) {
    const s = String(pc || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (s.length < 5 || s.length > 7) return '';
    return s.slice(0, -3) + ' ' + s.slice(-3);
  }
  function addrHtml(i) {
    i = i || {};
    const raw = String(i.address || '').trim();
    const found = raw.match(/[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}/i);
    const pc = normPc(i.postcode || (found && found[0]) || '');
    const re = pc ? new RegExp(pc.replace(/\s+/g, '\\s*'), 'ig') : null;
    const seen = {};
    const out = [];
    raw.split(',').forEach(part => {
      let x = (re ? part.replace(re, ' ') : part).replace(/\s+/g, ' ').trim().replace(/^[,.\s]+|[,.\s]+$/g, '');
      if (!x) return;
      const w = x.split(' ');
      if (w.length % 2 === 0 && w.slice(0, w.length / 2).join(' ').toLowerCase() === w.slice(w.length / 2).join(' ').toLowerCase()) x = w.slice(0, w.length / 2).join(' ');
      const k = x.toLowerCase();
      if (seen[k]) return;
      seen[k] = 1;
      out.push(esc(x));
    });
    const body = out.join(', ');
    return body + (pc ? (body ? ' ' : '') + '<b>' + esc(pc) + '</b>' : '');
  }
  function facHtml(i) {
    const p = [].concat(i.provided || [], i.facilities || []);
    const seen = {};
    const out = [];
    p.forEach(raw => {
      if (raw == null || raw === 'Dog Friendly') return;
      const hit = FAC.find(x => x[0] === raw);
      const en = hit ? hit[1] : String(raw);
      const cy = hit ? hit[2] : String(raw);
      const k = en.toLowerCase();
      if (seen[k]) return;
      seen[k] = 1;
      out.push(`<span class="chip">${phrase(en, cy)}</span>`);
    });
    return out.length ? `<span class="chips">${out.join('')}</span>` : '';
  }
  function nextNote(line) {
    const m = String(line).match(/(\d{2}):(\d{2})[–-](\d{2}):(\d{2})\s*$/);
    if (!m) return line;
    const a = +m[1] * 60 + +m[2], b = +m[3] * 60 + +m[4];
    if (b <= a && !/next day|drannoeth/i.test(line)) return line + (lang() === 'cy' ? ' (drannoeth)' : ' (next day)');
    return line;
  }
  function fmtLines(raw) {
    const arr = (raw || []).map(s => String(s).trim()).filter(Boolean);
    const F = (typeof window !== 'undefined' && window.timesFmt) ? window.timesFmt : null;
    const lines = F ? F.lines(arr) : arr;
    return lines.map(nextNote).map(normClosed).map(dash);
  }
  function hh(v) {
    // A stored 24-hour range is already normalised. Do not run it through the free-text formatter:
    // "17:00 - 10:00" is overnight, and re-reading the 10 as pm would show the wrong time.
    return String(v).trim().replace(/(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})/g, (m, a, b, c, d) => a.padStart(2, '0') + ':' + b + '\u2013' + c.padStart(2, '0') + ':' + d);
  }
  function storedLine(day, value) {
    const v = String(value).trim();
    if (/[ap]m/i.test(v)) return fmtLines([day + ' ' + v]).join(' / ') || (day + ' ' + v);
    if (/closed/i.test(v) && !/\d/.test(v)) return day + ' Closed';
    return nextNote(normClosed(day + ' ' + hh(v)));
  }
  function normClosed(line) {
    return String(line).replace(/\bclosed\b/gi, 'Closed');
  }
  function dash(line) {
    return String(line).replace(/(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})/g, (m, a, b, c, d) => a.padStart(2, '0') + ':' + b + '\u2013' + c.padStart(2, '0') + ':' + d);
  }
  function timesLines(layer, i) {
    if (layer === 'sh' && typeof window !== 'undefined' && window.REFONLY && window.REFONLY(i)) return [];
    if (layer === 'fb') {
      const t = i.opening_times;
      if (!t) return [];
      if (t.status === 'TIMES_FOUND' && (t.structured || t.all_closed)) {
        const closed = t.all_closed ? DAY.slice() : (t.closed || []);
        const lines = [];
        DAY.forEach(d => {
          const slots = (t.structured && t.structured[d]) || [];
          const note = t.notes && t.notes[d] ? ' ' + t.notes[d] : '';
          if (slots.length) lines.push(nextNote(DN[d] + ' ' + slots.map(x => hh(x.join('-'))).join(', ') + note));
          else if (closed.indexOf(d) >= 0) lines.push(DN[d] + ' Closed');
        });
        return lines.map(dash);
      }
      if (t.status === 'TIMES_TEXT_ONLY' && (t.raw || (t.lines && t.lines.length))) {
        const src = (t.lines && t.lines.length) ? t.lines : String(t.raw).split(/\s*\|\s*|\n/);
        return fmtLines(src);
      }
      return [];
    }
    const h = i.hours;
    if (!h) return [];
    if (typeof h === 'string') {
      const s = h.trim();
      if (!s || /^by referral\b|^self-referral\b/i.test(s)) return [];
      return fmtLines(s.split(/\s*\|\s*/));
    }
    if (typeof h === 'object') {
      const order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const lines = [];
      order.forEach(d => { if (d in h && String(h[d]).trim()) lines.push(storedLine(d, h[d])); });
      return lines.map(dash);
    }
    return [];
  }
  function timesHtml(layer, i) {
    const lines = timesLines(layer, i);
    if (!lines.length) return '';
    const listed = {};
    lines.forEach(l => { const m = /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Llun|Maw|Mer|Iau|Gwe|Sad|Sul)\b/.exec(l); if (m) listed[m[1]] = 1; });
    const n = Object.keys(listed).length;
    const rest = n && n < 7 ? `<div class="src">${lang() === 'cy' ? 'Dyddiau eraill heb eu rhestru, ffoniwch cyn mynd' : 'Other days not listed, call before you go'}</div>` : '';
    const t = layer === 'fb' ? i.opening_times : null;
    const src = t && t.source_url ? `<div class="src">${B('From their website', 'O’u gwefan')}${t.checked_date ? ' · ' + phrase(dateEn(t.checked_date), dateCy(t.checked_date)) : ''}. <a href="${esc(t.source_url)}" target="_blank" rel="noopener">${B('source', 'ffynhonnell')}</a></div>` : '';
    return `<div class="ot"><div class="raw">${lines.map(esc).join('<br>')}</div>${rest}${src}</div>`;
  }
  function dateEn(v) { const p = dateParts(v); return p ? p.d + ' ' + MEN[p.mo] + ' ' + p.y : ''; }
  function dateCy(v) { const p = dateParts(v); return p ? p.d + ' ' + MCY[p.mo] + ' ' + p.y : ''; }
  function dateParts(v) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v || ''));
    if (!m) return null;
    return { y: m[1], mo: +m[2] - 1, d: String(+m[3]) };
  }
  function schemeBody(s) {
    const rep = (months, untilWord, opensWord) => String(s).replace(/^Until\s+/i, untilWord + ' ').replace(/^Opens\s+/i, opensWord + ' ').replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, (m, y, mo, d) => (+d) + ' ' + months[+mo - 1] + ' ' + y);
    return phrase(rep(MEN, 'Until', 'Opens'), rep(MCY, 'Tan', 'Yn agor'));
  }
  function checkedHtml(i) {
    const v = i.verified_on || i.checked_on || i.hours_checked || i.last_verified || (i.opening_times && i.opening_times.checked_date) || '';
    const p = dateParts(v);
    const body = p ? phrase(dateEn(v), dateCy(v)) : NS();
    return `<p class="xrow uchk"><b>${B('Last checked', 'Gwiriwyd ddiwethaf')}:</b> ${body}</p>`;
  }
  function block(layer, i, opt) {
    i = i || {}; opt = opt || {};
    const how = howPair(layer, i, opt);
    const wheel = wheelPair(i);
    const who = whoHtml(i);
    const fac = facHtml(i);
    const times = timesHtml(layer, i);
    let extra = '';
    if (opt.phoneHtml) extra += row('Phone', 'Ffôn', opt.phoneHtml);
    if (i.beds) extra += row('Beds', 'Gwelyau', esc(i.beds));
    if (i.offer) extra += row('Offers', 'Yn cynnig', esc(i.offer));
    const sd = i.scheme_dates;
    if (sd && !/^not stated/i.test(String(sd).trim())) extra += row('Scheme dates', 'Dyddiadau’r cynllun', schemeBody(sd));
    return `<div class="ufact">${row('Who it’s for', 'I bwy mae hwn', who || NS())}${row('How to get in', 'Sut i fynd i mewn', how ? phrase(how[0], how[1]) : NS())}${row('Opening times', 'Oriau agor', times || NS())}${row('Wheelchair access', 'Mynediad i gadeiriau olwyn', wheel ? phrase(wheel[0], wheel[1]) : NS())}${row('Facilities', 'Cyfleusterau', fac || NS())}${extra}</div>`;
  }
  const api = { typeOf, typeRow, winter, whoBits, whoHtml, howPair, wheelPair, facHtml, timesLines, timesHtml, block, checked: checkedHtml, addr: addrHtml, normPc, NS };
  if (typeof window !== 'undefined') window.UFacts = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
