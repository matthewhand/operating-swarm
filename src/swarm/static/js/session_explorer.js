// Session explorer page logic (loaded via {% static %} from session_explorer.html).
// Feed URL + page limit arrive via data-* on #se-app (not inline JS).
(function(){
  var app = document.getElementById('se-app'); if(!app) return;
  var feed = app.dataset.feed;
  var pageLimit = parseInt(app.dataset.limit || '50', 10) || 50;
  var live = document.getElementById('se-live');
  // Escape for text nodes and double-quoted attributes (data-status/title/class).
  function esc(s){
    return (s==null?'':String(s)).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function dots(ds){ return (ds||[]).map(function(d){return '<span class="dot '+esc(d.status)+'" title="'+esc(d.role)+': '+esc(d.status)+'"></span>';}).join(''); }
  function updateBanner(payload){
    var total = (payload && typeof payload.total === 'number') ? payload.total : null;
    var shown = (payload && typeof payload.shown === 'number') ? payload.shown
              : (payload && payload.sessions ? payload.sessions.length : null);
    var limit = (payload && typeof payload.limit === 'number') ? payload.limit : pageLimit;
    var truncated = payload && typeof payload.truncated === 'boolean'
      ? payload.truncated
      : (total != null && shown != null && total > shown);
    var totalEl = document.getElementById('se-total');
    if(totalEl && total != null) totalEl.textContent = total;
    var banner = document.getElementById('se-trunc-banner');
    if(banner){
      banner.classList.toggle('os-hide', !truncated);
      var shownEl = document.getElementById('se-shown');
      var totBan = document.getElementById('se-total-banner');
      var limEl = document.getElementById('se-limit-label');
      if(shownEl && shown != null) shownEl.textContent = shown;
      if(totBan && total != null) totBan.textContent = total;
      if(limEl) limEl.textContent = limit;
    }
  }
  function render(payload){
    var sessions = (payload && payload.sessions) || [];
    // Hard client-side cap matching page limit (defense in depth if API omits limit).
    if(sessions.length > pageLimit) sessions = sessions.slice(0, pageLimit);
    updateBanner({
      sessions: sessions,
      total: payload && payload.total,
      shown: Math.min(sessions.length, pageLimit),
      limit: (payload && payload.limit) || pageLimit,
      truncated: payload && typeof payload.truncated === 'boolean'
        ? payload.truncated
        : ((payload && payload.total) > pageLimit)
    });
    document.getElementById('se-list').innerHTML = sessions.length ? sessions.map(function(s){
      var st = s.status||'unknown';
      var deleg = (s.delegations&&s.delegations.length) ? '<span class="se-deleg se-meta">⛓ '+dots(s.delegations)+' '+s.delegations.length+' delegation'+(s.delegations.length===1?'':'s')+'</span>' : '';
      return '<div class="se-card" data-status="'+esc(st)+'"><div class="se-row">'
        + '<span class="badge-status st-'+esc(st)+'">'+esc(st)+'</span>'
        + '<a class="se-id" href="/sessions/'+encodeURIComponent(s.id)+'/">'+esc(s.id)+'</a>'
        + '<span class="se-meta">'+esc(s.model||'—')+'</span>'
        + (s.execution_ms?'<span class="se-meta">'+esc(s.execution_ms)+' ms</span>':'')
        + deleg + '</div>'
        + (s.output_preview?'<div class="se-preview">'+esc(s.output_preview)+'</div>':'') + '</div>';
    }).join('') : '<div class="se-empty os-empty" role="status"><div class="os-empty-icon" aria-hidden="true">🧭</div><div>No sessions for your account yet.</div><div class="os-meta mt-2 mb-3">Create one with <code>POST /v1/responses</code> (include API credentials when auth is enabled). This list shows only sessions you own.</div><a href="/teams/launch/" class="btn btn-primary os-launch-btn">Launch a team</a></div>';
  }
  // --- status filtering (click a status chip) ---
  var currentFilter = "";
  function applyFilter(){
    var visible = 0;
    document.querySelectorAll('#se-list .se-card').forEach(function(c){
      var show = (!currentFilter || c.getAttribute('data-status') === currentFilter);
      c.classList.toggle('os-hide', !show);
      if(show) visible++;
    });
    var filterEmpty = document.getElementById('se-filter-empty');
    var hasCards = document.querySelectorAll('#se-list .se-card').length > 0;
    if(filterEmpty){
      filterEmpty.classList.toggle('os-hide', !(hasCards && currentFilter && visible === 0));
    }
  }
  function selectFilter(chip){
    currentFilter = chip.getAttribute('data-filter') || "";
    document.querySelectorAll('.se-filter').forEach(function(c){
      var on = (c === chip);
      c.classList.toggle('active', on);
      c.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    applyFilter();
  }
  document.querySelectorAll('.se-filter').forEach(function(chip){
    chip.addEventListener('click', function(){ selectFilter(chip); });
    chip.addEventListener('keydown', function(e){
      if(e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar'){ e.preventDefault(); selectFilter(chip); }
    });
  });
  var errEl = document.getElementById('se-error');
  var liveDot = document.getElementById('se-live-dot');
  var listEl = document.getElementById('se-list');
  function setLive(state){ if(liveDot) liveDot.className = 'se-live-dot' + (state ? ' '+state : ''); }
  function poll(){
    if(!live.checked){ setLive(''); return; }
    setLive('refreshing'); listEl.setAttribute('aria-busy','true');
    var url = feed + (feed.indexOf('?') >= 0 ? '&' : '?') + 'limit=' + encodeURIComponent(pageLimit);
    fetch(url, {headers:{'Accept':'application/json'}})
      .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
      .then(function(d){
        if(errEl){ errEl.classList.add('os-hide'); } setLive('');
        render(d || {}); applyFilter();
        listEl.setAttribute('aria-busy','false');
      })
      .catch(function(e){
        setLive('stalled'); listEl.setAttribute('aria-busy','false');
        if(errEl){
          errEl.textContent = '⚠ Live refresh failed (' + (e && e.message || 'network error') + ') — showing last data, retrying…';
          errEl.classList.remove('os-hide');
        }
      });
  }
  if(live){ live.addEventListener('change', function(){ if(live.checked){ poll(); } else { setLive(''); if(errEl) errEl.classList.add('os-hide'); } }); }
  applyFilter();
  setInterval(poll, 3000);
})();
