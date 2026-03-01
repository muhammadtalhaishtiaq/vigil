/* Backend-driven Vigil dashboard (Phase 1) */

let dashboardState = {
  profile: null,
  intelligence: null,
  scores: null,
  pulse: null,
  sectors: null,
  feed: null,
  conversation: []
};


function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[char]));
}

function statusToClass(status) {
  const lowered = String(status || '').toLowerCase();
  if (lowered.includes('up') || lowered.includes('bull')) return 'up';
  if (lowered.includes('down') || lowered.includes('bear')) return 'dn';
  return 'fl';
}

function scoreColor(score) {
  if (score >= 75) return 'var(--re)';
  if (score >= 65) return 'var(--or)';
  if (score >= 55) return 'var(--ye)';
  return 'var(--g)';
}

function setState(partial) {
  dashboardState = { ...dashboardState, ...partial };
}


async function fetchJson(url, init) {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${url} failed (${res.status})`);
  return res.json();
}

async function initDashboard() {
  try {
    const [profile, intelligence, scores, pulse, sectors, feed, chatHistory] = await Promise.all([
      fetchJson('/api/profile/load'),
      fetchJson('/api/intelligence/analyze'),
      fetchJson('/api/scores/breakdown'),
      fetchJson('/api/market/pulse'),
      fetchJson('/api/sectors/performance'),
      fetchJson('/api/feed/intelligence'),
      fetchJson('/api/chat/history').catch(() => ({ conversation: [] }))
    ]);

    const hasProfile = Boolean((profile?.company_name || '').trim());

    setState({
      profile,
      intelligence,
      scores,
      pulse,
      sectors,
      feed,
      conversation: Array.isArray(chatHistory?.conversation) ? chatHistory.conversation : []
    });
    renderAll();

    if (hasProfile && (dashboardState.conversation || []).length === 0) {
      await triggerInitialBriefing(profile);
    }
  } catch (error) {
    console.error('Dashboard init failed:', error);
  }
}

async function triggerInitialBriefing(profile) {
  try {
    await fetchJson('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: `Run initial risk briefing for ${profile.company_name}. Provide top risks and actions.`,
        intent: 'initial_briefing'
      })
    });

    const chatHistory = await fetchJson('/api/chat/history').catch(() => ({ conversation: [] }));
    if (Array.isArray(chatHistory?.conversation)) {
      setState({ conversation: chatHistory.conversation });
      renderConversation();
    }
  } catch (error) {
    console.error('Initial briefing failed:', error);
  }
}

function renderAll() {
  renderProfile();
  renderIntelligence();
  renderScores();
  renderPulse();
  renderSectors();
  renderFeed();
  renderConversation();
  renderAutoBrief();
}

function renderConversation() {
  const thread = document.getElementById('chatThread');
  const conversation = dashboardState.conversation;
  if (!thread || !Array.isArray(conversation) || conversation.length === 0) return;

  thread.innerHTML = conversation.map((item) => {
    const role = item.role === 'user' ? 'user' : 'sys';
    const label = item.role === 'user'
      ? 'You'
      : (Array.isArray(item.agents_used) && item.agents_used.length > 0 ? item.agents_used.join(' → ') : '⚡ Vigil');
    return `<div class="msg ${role}"><div class="mlbl">${esc(label)}</div><div class="bubble">${esc(item.content || '')}</div></div>`;
  }).join('');

  thread.scrollTop = thread.scrollHeight;
}

function renderProfile() {
  const profile = dashboardState.profile;
  if (!profile) return;

  const hasProfile = Boolean((profile.company_name || '').trim());

  const profPillName = document.querySelector('.prof-pill span:nth-child(2)');
  if (profPillName) profPillName.textContent = hasProfile ? profile.company_name : 'No profile';

  const ccname = document.querySelector('.ccname');
  const ccsub = document.querySelector('.ccsub');
  const cctags = document.querySelector('.cctags');

  if (ccname) ccname.textContent = hasProfile ? profile.company_name : 'No company profile yet';
  if (ccsub) {
    const parts = [profile.location, profile.industry, profile.stage, profile.arb, profile.employees ? `${profile.employees} people` : null].filter(Boolean);
    ccsub.textContent = hasProfile ? parts.join(' · ') : 'Complete profile setup to unlock company intelligence';
  }

  if (cctags) {
    const tags = hasProfile ? [profile.industry, profile.stage, profile.location].filter(Boolean) : [];
    cctags.innerHTML = tags.map((tag) => `<div class="ctag gr">${esc(tag)}</div>`).join('');
  }
}

function renderIntelligence() {
  const intelligence = dashboardState.intelligence;
  if (!intelligence || intelligence.requires_profile) {
    const vscore = document.getElementById('vscore');
    const vtier = document.getElementById('vtier');
    const vdir = document.getElementById('vdir');
    const vtext = document.getElementById('vtext');
    if (vscore) vscore.textContent = '--';
    if (vtier) vtier.textContent = 'PROFILE REQUIRED';
    if (vdir) vdir.textContent = '—';
    if (vtext) vtext.textContent = 'Add company profile first to run intelligence.';

    const drawerRisks = document.getElementById('drawerRisks');
    const drawerActions = document.getElementById('drawerActions');
    if (drawerRisks) drawerRisks.innerHTML = '<div class="drc"><div class="drc-detail">Add company profile to load risk details.</div></div>';
    if (drawerActions) drawerActions.innerHTML = '<div class="dac"><div class="dac-detail">Add company profile to load action plan.</div></div>';
    return;
  }

  const vscore = document.getElementById('vscore');
  const vtier = document.getElementById('vtier');
  const vdir = document.getElementById('vdir');
  const vtext = document.getElementById('vtext');

  if (vscore) vscore.textContent = intelligence.risk_score ?? '--';
  if (vtier) vtier.textContent = intelligence.tier || 'UNKNOWN';
  if (vdir) vdir.textContent = intelligence.direction || '—';
  if (vtext) vtext.textContent = intelligence.summary_text || 'No summary available.';

  const tierClass = String(intelligence.tier || 'neutral').toLowerCase();
  const vbar = document.querySelector('.vbar');
  if (vbar) vbar.className = `vbar tier-${tierClass}`;

  const riskChips = document.querySelectorAll('.rchip');
  const risks = intelligence.risks || [];
  risks.slice(0, 3).forEach((risk, index) => {
    const chip = riskChips[index];
    if (!chip) return;
    const txt = chip.querySelector('.chip-txt');
    const meta = chip.querySelector('.chip-meta');
    if (txt) txt.textContent = risk.name || 'Risk';
    if (meta) meta.textContent = `${risk.probability ?? '--'}%`;
  });

  const actionChips = document.querySelectorAll('.achip');
  const actions = intelligence.actions || [];
  actions.slice(0, 3).forEach((action, index) => {
    const chip = actionChips[index];
    if (!chip) return;
    const txt = chip.querySelector('.chip-txt');
    const meta = chip.querySelector('.chip-meta');
    if (txt) txt.textContent = action.name || 'Action';
    if (meta) meta.textContent = action.deadline || '--';
  });

  const drawerRisks = document.getElementById('drawerRisks');
  if (drawerRisks) {
    drawerRisks.innerHTML = risks.length
      ? risks.map((risk) => `
        <div class="drc">
          <div class="drc-head">
            <div class="drc-name">${esc(risk.name)}</div>
            <div class="drc-prob">${esc(risk.probability)}%</div>
          </div>
          <div class="drc-bar"><div class="drc-bar-fill" style="width:${Math.max(0, Math.min(100, Number(risk.probability) || 0))}%;background:${scoreColor(Number(risk.probability) || 0)}"></div></div>
          <div class="drc-detail">${esc(risk.detail || 'No detail')}</div>
          <div class="drc-tags">
            <div class="drc-tag">Severity: ${esc(risk.severity || 'N/A')}</div>
            <div class="drc-tag">Horizon: ${esc(risk.horizon || 'N/A')}</div>
          </div>
        </div>`).join('')
      : '<div class="drc"><div class="drc-detail">No risk details available.</div></div>';
  }

  const drawerActions = document.getElementById('drawerActions');
  if (drawerActions) {
    drawerActions.innerHTML = actions.length
      ? actions.map((action) => `
        <div class="dac">
          <div class="dac-titlerow"><div class="dac-title">${esc(action.name || 'Action')}</div></div>
          <div class="dac-detail">${esc(action.detail || 'No detail')}</div>
          <div class="dac-tags">
            <div class="datag ow">${esc(action.owner || 'Owner N/A')}</div>
            <div class="datag dl">${esc(action.deadline || 'No deadline')}</div>
            <div class="datag ur">${esc(action.priority || 'N/A')}</div>
          </div>
        </div>`).join('')
      : '<div class="dac"><div class="dac-detail">No action plan available.</div></div>';
  }

  const playbookContent = document.getElementById('playbookContent');
  if (playbookContent) {
    playbookContent.innerHTML = `<strong>VIGIL PLAYBOOK — ${esc(dashboardState.profile?.company_name || 'Company')}</strong><br><br>` +
      actions.slice(0, 6).map((action, idx) => `${idx + 1}. ${esc(action.name || 'Action')} — ${esc(action.deadline || 'No deadline')}`).join('<br>');
  }

  const oracleVerdict = document.getElementById('oracleVerdict');
  const oracleConfidence = document.getElementById('oracleConfidence');
  const oracleCases = document.getElementById('oracleCases');
  if (oracleVerdict) oracleVerdict.textContent = Number(intelligence.risk_score) >= 70 ? 'WAIT ⚠️' : 'MOVE ✅';
  if (oracleConfidence) oracleConfidence.textContent = `Based on live risk score ${esc(intelligence.risk_score)}`;
  if (oracleCases) {
    oracleCases.innerHTML = `
      <div class="doc take"><strong>Live Summary:</strong> ${esc(intelligence.summary_text || 'N/A')}</div>
      <div class="doc hist"><strong>Top Risk:</strong> ${esc(risks[0]?.name || 'N/A')}</div>
      <div class="doc bull"><strong>Top Action:</strong> ${esc(actions[0]?.name || 'N/A')}</div>
    `;
  }
}

function renderScores() {
  const scores = dashboardState.scores;
  if (!scores || scores.requires_profile) {
    const bdrs = document.querySelectorAll('.bdr .bdv');
    bdrs.forEach((v) => { v.textContent = '--'; });
    const formula = document.getElementById('drawerScoresFormula');
    if (formula) formula.textContent = 'Add company profile to compute score breakdown.';
    return;
  }

  const entries = [
    { key: 'macro', label: 'Macro', weight: 0.35 },
    { key: 'market', label: 'Market', weight: 0.25 },
    { key: 'narrative', label: 'Narrative', weight: 0.20 },
    { key: 'competitive', label: 'Competitive', weight: 0.20 }
  ];

  const bdrs = document.querySelectorAll('.bdr');
  entries.forEach((entry, index) => {
    const score = Number(scores[entry.key]?.score || 0);
    const row = bdrs[index];
    if (!row) return;
    const fill = row.querySelector('.bdf');
    const value = row.querySelector('.bdv');
    if (fill) {
      fill.style.width = `${score}%`;
      fill.style.background = scoreColor(score);
    }
    if (value) value.textContent = String(score);
  });

  const drawerRows = document.getElementById('drawerScoresRows');
  if (drawerRows) {
    drawerRows.innerHTML = entries.map((entry) => {
      const score = Number(scores[entry.key]?.score || 0);
      return `<div class="dsc-row"><div class="dsc-lbl">${entry.label}</div><div class="dsc-track"><div class="dsc-fill" style="width:${score}%;background:${scoreColor(score)}"></div></div><div class="dsc-wt">${Math.round(entry.weight * 100)}%</div><div class="dsc-val">${score}</div></div>`;
    }).join('');
  }

  const composite = Math.round(entries.reduce((sum, entry) => sum + Number(scores[entry.key]?.score || 0) * entry.weight, 0));
  const tier = dashboardState.intelligence?.tier || (composite >= 70 ? 'ORANGE' : composite >= 55 ? 'YELLOW' : 'GREEN');

  const formula = document.getElementById('drawerScoresFormula');
  if (formula) formula.textContent = `Formula: Macro×0.35 + Market×0.25 + Narrative×0.20 + Competitive×0.20 = ${composite}`;

  const compositeValue = document.getElementById('drawerCompositeValue');
  const compositeTier = document.getElementById('drawerCompositeTier');
  const coherence = document.getElementById('drawerCoherence');
  const playbookComposite = document.getElementById('playbookComposite');
  const playbookStance = document.getElementById('playbookStance');
  const playbookScores = document.getElementById('playbookScores');

  if (compositeValue) compositeValue.textContent = String(composite);
  if (compositeTier) compositeTier.textContent = `${tier} TIER`;
  if (coherence) coherence.textContent = 'LIVE SIGNALS';
  if (playbookComposite) playbookComposite.textContent = String(composite);
  if (playbookStance) playbookStance.textContent = composite >= 70 ? 'DEFEND / RAISE' : composite >= 55 ? 'CAUTIOUS BUILD' : 'GROW';
  if (playbookScores) {
    playbookScores.innerHTML = entries.map((entry) => {
      const score = Number(scores[entry.key]?.score || 0);
      return `<div class="dpbs-row"><div class="dpbs-lbl2">${entry.label}</div><div class="dpbs-track"><div class="dpbs-fill" style="width:${score}%;background:${scoreColor(score)}"></div></div><div class="dpbs-num">${score}</div></div>`;
    }).join('');
  }
}

function renderPulse() {
  const pulse = dashboardState.pulse;
  if (!pulse) return;

  const keys = ['vix', 'yield_10y', 'sp500_7d', 'gold_7d'];
  const boxes = document.querySelectorAll('.pm');
  boxes.forEach((box, index) => {
    const item = pulse[keys[index]];
    const valueEl = box.querySelector('.pmv');
    if (!valueEl || !item) return;
    valueEl.textContent = item.formatted || item.value || '—';
    valueEl.className = `pmv ${statusToClass(item.status)}`;
  });

  const vix = Number(pulse.vix?.value || 0);
  const regimeValue = document.getElementById('regimeValue');
  const regimeSub = document.getElementById('regimeSub');
  const stanceValue = document.getElementById('stanceValue');

  if (regimeValue) regimeValue.textContent = vix >= 25 ? '⚠ RISK-OFF' : vix >= 18 ? '◐ TRANSITIONAL' : '✅ RISK-ON';
  if (regimeSub) regimeSub.textContent = `VIX ${vix || 'N/A'} from backend feed`;
  if (stanceValue) stanceValue.textContent = vix >= 25 ? 'DEFEND' : 'SELECTIVE DEPLOY';
}

function renderSectors() {
  const sectors = dashboardState.sectors?.sectors;
  if (!Array.isArray(sectors) || sectors.length === 0) {
    const topSectorsList = document.getElementById('topSectorsList');
    if (topSectorsList) {
      topSectorsList.innerHTML = '<div class="sb"><div class="sbn">No live sectors</div><div class="sbp fl">--</div></div>';
    }
    return;
  }

  const sgbs = document.querySelectorAll('.sgb');
  sectors.slice(0, sgbs.length).forEach((sector, index) => {
    const card = sgbs[index];
    if (!card) return;
    const name = card.querySelector('.sgbn');
    const perf = card.querySelector('.sgbp');
    const value = Number(sector.change_7d || 0);
    const cls = statusToClass(sector.status);
    if (name) name.textContent = sector.name || 'SECTOR';
    if (perf) {
      perf.textContent = `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
      perf.className = `sgbp ${cls}`;
    }
    card.className = `sgb ${cls}`;
  });

  const topSectorsList = document.getElementById('topSectorsList');
  if (topSectorsList) {
    const top = [...sectors].sort((a, b) => Number(b.change_7d || 0) - Number(a.change_7d || 0)).slice(0, 4);
    topSectorsList.innerHTML = top.map((sector) => {
      const value = Number(sector.change_7d || 0);
      const cls = statusToClass(sector.status);
      return `<div class="sb ${cls}"><div class="sbn">${esc(sector.name)}</div><div class="sbp ${cls}">${value >= 0 ? '+' : ''}${value.toFixed(1)}%</div></div>`;
    }).join('');
  }
}

function formatAgo(timestamp) {
  if (!timestamp) return 'now';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return 'now';
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.max(1, Math.round(diffMs / 60000));
  if (diffMin < 60) return `${diffMin} min ago`;
  const hrs = Math.round(diffMin / 60);
  return `${hrs} hr ago`;
}

function renderFeed() {
  const feed = dashboardState.feed?.feed;
  if (!Array.isArray(feed) || feed.length === 0) {
    const liveFeedList = document.getElementById('liveFeedList');
    const sectorNewsList = document.getElementById('sectorNewsList');
    if (liveFeedList) {
      liveFeedList.innerHTML = '<div class="ni"><div class="ni-src">Vigil</div><div class="ni-hl">No live headlines available.</div><div class="ni-t">now</div></div>';
    }
    if (sectorNewsList) {
      sectorNewsList.innerHTML = '<div class="ptitle" style="position:sticky;top:0;background:var(--sf);z-index:1;">📰 Sector News</div><div class="rni"><div class="rni-src">Vigil</div><div class="rni-hl">No sector news available.</div></div>';
    }
    return;
  }

  const liveFeedList = document.getElementById('liveFeedList');
  if (liveFeedList) {
    liveFeedList.innerHTML = feed.slice(0, 8).map((item) => {
      const sentimentClass = item.sentiment === 'positive' ? 'sdot-p' : item.sentiment === 'negative' ? 'sdot-n' : 'sdot-u';
      return `<div class="ni"><div class="ni-src">${esc(item.source)} <span class="${sentimentClass}">●</span></div><div class="ni-hl">${esc(item.headline)}</div><div class="ni-t">${formatAgo(item.timestamp)}</div></div>`;
    }).join('');
  }

  const sectorNewsList = document.getElementById('sectorNewsList');
  if (sectorNewsList) {
    const title = sectorNewsList.querySelector('.ptitle')?.outerHTML || '<div class="ptitle" style="position:sticky;top:0;background:var(--sf);z-index:1;">📰 Sector News</div>';
    const items = feed.slice(0, 6).map((item) => `<div class="rni"><div class="rni-src">${esc(item.source)}</div><div class="rni-hl">${esc(item.headline)}</div></div>`).join('');
    sectorNewsList.innerHTML = title + items;
  }
}

function renderAutoBrief() {
  if (Array.isArray(dashboardState.conversation) && dashboardState.conversation.length > 0) return;
  const brief = document.getElementById('autoBriefMessage');
  if (!brief) return;
  const company = dashboardState.profile?.company_name || 'your company';
  const score = dashboardState.intelligence?.risk_score ?? '--';
  const tier = dashboardState.intelligence?.tier || 'UNKNOWN';
  brief.innerHTML = `<div class="mlbl">⚡ Vigil · Auto-brief · ${esc(company)} context loaded</div><div class="bubble" style="color:var(--tx2);font-size:11px;">Live backend analysis loaded. Current risk score: <strong>${esc(score)} / 100 · ${esc(tier)}</strong>. Use shortcuts or ask a question to trigger fresh agent synthesis.</div>`;
}

function fc(text) {
  const input = document.getElementById('cin');
  if (!input) return;
  input.value = text;
  input.focus();
}

async function send() {
  const input = document.getElementById('cin');
  const button = document.getElementById('sbtn');
  const thread = document.getElementById('chatThread');
  if (!input || !button || !thread) return;

  const message = input.value.trim();
  if (!message) return;

  const currentConversation = Array.isArray(dashboardState.conversation) ? dashboardState.conversation : [];
  setState({
    conversation: [...currentConversation, {
      role: 'user',
      content: message,
      timestamp: new Date().toISOString()
    }]
  });

  thread.insertAdjacentHTML('beforeend', `<div class="msg user"><div class="mlbl">You</div><div class="bubble">${esc(message)}</div></div>`);
  thread.scrollTop = thread.scrollHeight;

  input.value = '';
  input.disabled = true;
  button.disabled = true;
  button.textContent = 'Routing...';

  const pending = document.createElement('div');
  pending.className = 'msg sys';
  pending.innerHTML = '<div class="mlbl">⚡ Vigil · routing to agents...</div><div class="bubble" style="color:var(--tx3);font-style:italic;">Analysing…</div>';
  thread.appendChild(pending);

  try {
    startOrchestratorPulse();
    const result = await fetchJson('/api/chat/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });

    if (result.status === 'success') {
      pending.innerHTML = `<div class="mlbl">${esc((result.agents_used || []).join(' → ') || 'Vigil')}</div><div class="bubble">${esc(result.message || '')}</div>`;
      const updatedConversation = Array.isArray(dashboardState.conversation) ? dashboardState.conversation : [];
      setState({
        conversation: [...updatedConversation, {
          role: 'assistant',
          content: result.message || '',
          timestamp: new Date().toISOString(),
          agents_used: result.agents_used || []
        }]
      });
      if (Array.isArray(result.agent_trace)) {
        updateAgentFlow(result.agent_trace);
      } else {
        animateAgentsUsed(result.agents_used || []);
      }
    } else {
      pending.innerHTML = '<div class="mlbl">⚠ Error</div><div class="bubble">Backend returned an error.</div>';
    }
  } catch (error) {
    pending.innerHTML = `<div class="mlbl">⚠ Error</div><div class="bubble">${esc(error.message || 'Network error')}</div>`;
  } finally {
    input.disabled = false;
    button.disabled = false;
    button.textContent = '⚡ ANALYZE';
    thread.scrollTop = thread.scrollHeight;
  }
}

function toggleDrawer() {
  const drawer = document.getElementById('idrawer');
  if (drawer) drawer.classList.toggle('open');
}

function closeDrawer() {
  const drawer = document.getElementById('idrawer');
  if (drawer) drawer.classList.remove('open');
}

function switchDTab(tab) {
  const tabs = ['risks', 'actions', 'playbook', 'oracle', 'scores'];
  tabs.forEach((name) => {
    document.getElementById(`dtab-${name}`)?.classList.remove('active');
    document.getElementById(`dpanel-${name}`)?.classList.remove('active');
  });
  document.getElementById(`dtab-${tab}`)?.classList.add('active');
  document.getElementById(`dpanel-${tab}`)?.classList.add('active');
}

function openDrawerTo(event, tab) {
  event.stopPropagation();
  const drawer = document.getElementById('idrawer');
  if (drawer) drawer.classList.add('open');
  switchDTab(tab);
}

function copyPlaybook() {
  const text = document.getElementById('playbookContent')?.innerText || '';
  navigator.clipboard.writeText(text).then(() => {
    const button = document.querySelector('.dpb-copy');
    if (!button) return;
    const old = button.textContent;
    button.textContent = '✓ Copied!';
    setTimeout(() => { button.textContent = old || '📋 Copy playbook'; }, 1500);
  });
}

function updateAgentFlow(agentTrace) {
  const nodes = document.querySelectorAll('.afn');
  nodes.forEach((node, index) => {
    node.className = 'afn';
    if (index < agentTrace.length) {
      const status = String(agentTrace[index].status || '').toLowerCase();
      if (status === 'done') node.classList.add('done');
      else if (status === 'active') node.classList.add('active');
    }
  });
}

function startOrchestratorPulse() {
  const nodes = document.querySelectorAll('.afn');
  nodes.forEach((node) => { node.className = 'afn'; });
  const orchestrator = nodes[0];
  if (orchestrator) orchestrator.classList.add('active');
}

function animateAgentsUsed(agentsUsed) {
  const nodes = document.querySelectorAll('.afn');
  if (!nodes.length) return;

  const normalized = (Array.isArray(agentsUsed) ? agentsUsed : [])
    .map((name) => String(name || '').toLowerCase());

  const nameToIndex = (name) => {
    if (name.includes('orchestrator')) return 0;
    if (name.includes('signal')) return 1;
    if (name.includes('narrative')) return 2;
    if (name.includes('macro')) return 3;
    if (name.includes('competitive')) return 4;
    if (name.includes('synth')) return 5;
    if (name.includes('oracle')) return 6;
    if (name.includes('commander') || name.includes('strategy')) return 7;
    return -1;
  };

  const indices = normalized
    .map(nameToIndex)
    .filter((idx) => idx >= 0 && idx < nodes.length);

  // Always complete orchestrator first.
  nodes[0].classList.remove('active');
  nodes[0].classList.add('done');

  if (indices.length === 0) return;

  indices.forEach((idx, step) => {
    setTimeout(() => {
      nodes[idx].classList.add('active');
    }, step * 350 + 150);
    setTimeout(() => {
      nodes[idx].classList.remove('active');
      nodes[idx].classList.add('done');
    }, step * 350 + 650);
  });
}

let dark = true;
function toggleTheme() {
  dark = !dark;
  const app = document.getElementById('app');
  const button = document.getElementById('tbtn');
  if (!app || !button) return;
  if (dark) {
    app.removeAttribute('data-theme');
    button.textContent = '🌙';
  } else {
    app.setAttribute('data-theme', 'light');
    button.textContent = '☀️';
  }
  sessionStorage.setItem('vt', dark ? 'dark' : 'light');
}

(function hydrateTheme() {
  if (sessionStorage.getItem('vt') === 'light') {
    dark = false;
    const app = document.getElementById('app');
    const button = document.getElementById('tbtn');
    if (app) app.setAttribute('data-theme', 'light');
    if (button) button.textContent = '☀️';
  }
})();

function tick() {
  const clock = document.getElementById('clock');
  if (!clock) return;
  const now = new Date();
  const text = now.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'America/New_York'
  });
  clock.textContent = `${text} EST`;
}

setInterval(tick, 1000);
tick();

document.addEventListener('DOMContentLoaded', async () => {
  await initDashboard();
  setInterval(initDashboard, 5 * 60 * 1000);
});
