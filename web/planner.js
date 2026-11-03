// --- Browser state and shared scenario labels ---
'use strict';
const $ = id => document.getElementById(id);
let sessionId = null, results = [], selectedResult = 0, playing = false;
let minute = 360, lastFrame = 0, selectedGate = null, busy = false;
let summaryFingerprint = '';
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const DATASET_HELP = {
  default: 'Default: the general-purpose synthetic flight schedule.',
  ideal: 'Ideal: a synthetic schedule designed with conflict-free starting gates.',
  realistic: 'Realistic: a congested synthetic schedule with overlapping occupancy.',
};
const VIEW_HELP = {
  optimized_gate: 'After CP-SAT: gate assignments returned by the solver.',
  original_gate: 'Before CP-SAT: original gate assignments, including scheduled conflicts.',
};

// --- Build the fixed 40-gate visualization ---
const gateNodes = [];
for (let number = 1; number <= 40; number++) {
  const node = document.createElement('button');
  node.className = `gate ${number > 10 ? 'standard' : ''}`;
  const label = document.createElement('span');
  label.textContent = String(number).padStart(2, '0');
  const plane = document.createElement('span');
  plane.className = 'plane';
  const count = document.createElement('span');
  count.className = 'count';
  count.textContent = 'EMPTY';
  node.append(label, plane, count);
  node.addEventListener('click', () => {
    selectedGate = `Gate ${number}`;
    render();
  });
  $('gate-grid').append(node);
  gateNodes.push(node);
}

// --- Chat messages, busy state, and accessible field descriptions ---
function addMessage(text, role = 'assistant') {
  const node = document.createElement('div');
  node.className = `message ${role}`;
  node.textContent = text;
  $('chat').append(node);
  $('chat').scrollTop = $('chat').scrollHeight;
}

function setBusy(value, message = 'Planning request in progress…') {
  busy = value;
  for (const node of document.querySelectorAll('#send, #preview, #reset, [data-prompt]')) {
    node.disabled = value;
  }
  $('send').textContent = value ? 'Working…' : 'Send request ↗';
  $('solver-progress').classList.toggle('visible', value);
  $('solver-progress').setAttribute('aria-hidden', String(!value));
  $('solver-progress-label').textContent = message;
}

function updateFieldHelp(fieldId, helpId, text) {
  $(fieldId).dataset.tooltip = text;
  $(helpId).textContent = text;
  $(fieldId).querySelector('select').title = text;
}

function updateHelp() {
  updateFieldHelp('dataset-field', 'dataset-help', DATASET_HELP[$('dataset').value]);
  updateFieldHelp('view-field', 'view-help', VIEW_HELP[$('view').value]);
}

// --- HTTP request and result-selection helpers ---
async function request(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function showResults(incoming) {
  if (!incoming.length) return;
  results = incoming;
  selectedResult = results.length - 1;
  playing = false;
  $('play').textContent = 'Play';
  $('scenario').replaceChildren();
  results.forEach((result, index) => {
    const option = document.createElement('option');
    option.value = index;
    option.textContent = `${result.dataset} / ${result.aircraft_count} aircraft / ${result.gate_count} gates / ${result.flexible_gates ? 'Flexible' : 'Separate'} / ${result.status}`;
    $('scenario').append(option);
  });
  $('scenario').disabled = false;
  $('scenario').value = selectedResult;
  $('download').disabled = false;
  selectResult();
}

function selectResult() {
  selectedResult = Number($('scenario').value);
  const result = results[selectedResult];
  $('plan-status').textContent = result.status;
  const valid = Array.isArray(result.assignments);
  $('clock').disabled = !valid;
  $('play').disabled = !valid;
  render();
}

// --- Before/after solver metrics and run-status explanations ---
function updateViewSummary(result, key) {
  const values = document.querySelectorAll('.metrics strong');
  const labels = document.querySelectorAll('.metrics span');
  if (!result?.assignments) {
    values.forEach(node => { node.textContent = '—'; });
    $('result-note').textContent = result?.message || 'No assignment is available for this result.';
    summaryFingerprint = 'empty';
    return;
  }

  const optimised = key === 'optimized_gate';
  const conflicts = optimised ? result.optimized_conflicts : result.original_conflicts;
  const moved = optimised ? result.aircraft_moved : 0;
  const removed = optimised
    ? Math.max(0, result.original_conflicts - result.optimized_conflicts)
    : 0;
  const connections = optimised ? result.connections_fulfilled || 0 : 0;
  const fingerprint = [
    selectedResult, key, conflicts, moved, removed, connections, result.status,
  ].join('|');
  if (fingerprint === summaryFingerprint) return;
  summaryFingerprint = fingerprint;

  [conflicts, moved, removed, connections].forEach((value, index) => {
    values[index].textContent = value ?? '—';
  });
  labels[0].textContent = optimised ? 'Conflicts after CP-SAT' : 'Conflicts before CP-SAT';
  labels[1].textContent = 'Aircraft moved';
  labels[2].textContent = 'Conflicts removed';
  labels[3].textContent = optimised ? 'Connections fulfilled' : 'Connections before CP-SAT';

  if (!optimised) {
    $('result-note').textContent = `${result.aircraft_count} aircraft · Original schedule before CP-SAT · ${conflicts ?? '—'} overlapping pairs.`;
    return;
  }

  const quality = result.status === 'OPTIMAL'
    ? 'Proven optimal weighted objective'
    : result.status === 'HEURISTIC'
      ? 'Greedy fallback; no CP-SAT incumbent'
      : result.status === 'SKIPPED'
        ? 'CP-SAT skipped'
        : result.status === 'INFEASIBLE'
          ? 'No compatible gate for part of the fleet'
          : 'Feasible plan; optimality not proven';
  const connectionSummary = `${result.connections_fulfilled || 0}/${result.wing_to_wing_connections_requested || 0} connections fulfilled`;
  $('result-note').textContent = `${result.message ? `${result.message} ` : ''}${result.aircraft_count} aircraft · ${result.gate_count} gates · ${quality} · ${conflicts ?? '—'} overlapping pairs remain · ${connectionSummary}.`;
}

// --- Daily animation, occupancy display, and unresolved-reason hover text ---
function render() {
  const currentMinute = Math.floor(minute);
  $('clock').value = currentMinute;
  $('time').textContent = `${String(Math.floor(currentMinute / 60)).padStart(2, '0')}:${String(currentMinute % 60).padStart(2, '0')}`;
  const result = results[selectedResult];
  const key = $('view').value;
  updateViewSummary(result, key);

  const conflictDetails = key === 'optimized_gate'
    ? (result?.optimized_conflict_details || [])
    : (result?.original_conflict_details || []);
  const reasonsByGate = new Map();
  for (const detail of conflictDetails) {
    const reasons = reasonsByGate.get(detail.gate) || [];
    reasons.push(`Conflict: ${detail.aircraft_ids.join(' / ')} overlap ${detail.overlap_minutes} min — ${detail.reason}`);
    reasonsByGate.set(detail.gate, reasons);
  }
  for (const missing of result?.unresolved_aircraft || []) {
    const flight = result.assignments.find(item => item.aircraft_id === missing.aircraft_id);
    if (!flight) continue;
    const reasons = reasonsByGate.get(flight[key]) || [];
    reasons.push(`${missing.aircraft_id}: ${missing.reason}`);
    reasonsByGate.set(flight[key], reasons);
  }
  for (const connection of result?.unfulfilled_connection_details || []) {
    const pairGates = key === 'optimized_gate'
      ? connection.gates
      : connection.original_gates || connection.gates;
    for (const gate of pairGates) {
      const reasons = reasonsByGate.get(gate) || [];
      reasons.push(`Connection requirement unresolved: ${connection.aircraft_ids.join(' / ')}`);
      reasonsByGate.set(gate, reasons);
    }
  }

  const byGate = new Map();
  for (const flight of result?.assignments || []) {
    if ((currentMinute - flight.arrival_minute + 1440) % 1440 < flight.duration_minutes) {
      const occupants = byGate.get(flight[key]) || [];
      occupants.push(flight);
      byGate.set(flight[key], occupants);
    }
  }

  gateNodes.forEach((node, index) => {
    const gate = `Gate ${index + 1}`;
    const occupants = byGate.get(gate) || [];
    const fingerprint = occupants.map(flight => flight.aircraft_id).join(',');
    if (fingerprint !== node.dataset.occupants) {
      node.classList.remove('entering');
      if (occupants.length > 0 && !reducedMotion) {
        void node.offsetWidth;
        node.classList.add('entering');
      }
    }
    node.dataset.occupants = fingerprint;
    node.classList.toggle('active', occupants.length === 1);
    node.classList.toggle('blocked', occupants.length > 1);
    node.classList.toggle('selected', gate === selectedGate);
    node.querySelector('.plane').textContent = occupants.length ? '✈' : '·';
    node.querySelector('.count').textContent = occupants.length ? `${occupants.length} AIRCRAFT` : 'EMPTY';
    node.setAttribute('aria-label', `${gate}, ${occupants.length} aircraft${occupants.length > 1 ? ', conflict' : ''}`);
    const occupantSummary = occupants.map(flight => `${flight.aircraft_id} (${flight.model})`).join(', ') || 'Empty';
    const hoverReasons = [...(reasonsByGate.get(gate) || [])];
    if (occupants.length && result?.connection_shortfall_reason) {
      hoverReasons.push(`Connection requirement: ${result.connection_shortfall_reason}`);
    }
    node.title = [occupantSummary, ...hoverReasons].join('\n');
  });

  if (selectedGate) {
    const occupants = byGate.get(selectedGate) || [];
    $('flight-detail').textContent = `${selectedGate} at ${$('time').textContent}: ${occupants.map(flight => `${flight.aircraft_id} (${flight.model}, ${flight.original_gate} → ${flight.optimized_gate})`).join('; ') || 'empty'}`;
  }
}

// --- Natural-language chat submission and prompt shortcuts ---
$('chat-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const message = $('message').value.trim();
  if (!message) return;
  addMessage(message, 'user');
  $('message').value = '';
  setBusy(true);
  try {
    const data = await request('/api/chat', {message, session_id: sessionId});
    sessionId = data.session_id;
    addMessage(data.answer);
    showResults(data.results);
  } catch (error) {
    addMessage(error.message, 'error');
  } finally {
    setBusy(false);
  }
});

document.querySelectorAll('[data-prompt]').forEach(node => node.addEventListener('click', () => {
  $('message').value = node.dataset.prompt;
  $('message').focus();
}));

// --- Direct solver preview using the same scenario variables as chat ---
$('preview').addEventListener('click', async () => {
  if (busy) return;
  const numericFields = ['aircraft-count', 'gate-count', 'lock-percentage', 'connections', 'time-limit'];
  if (!numericFields.every(id => $(id).reportValidity())) return;
  setBusy(true, 'Running CP-SAT solver…');
  try {
    const handlingRate = $('handling-rate').value;
    const data = await request('/api/solve', {
      dataset: $('dataset').value,
      flexible_gates: $('flexible').checked,
      time_limit_seconds: Number($('time-limit').value),
      aircraft_count: Number($('aircraft-count').value),
      gate_count: Number($('gate-count').value),
      lock_percentage: Number($('lock-percentage').value),
      wing_to_wing_connections: Number($('connections').value),
      ground_handling_minutes_per_passenger: handlingRate ? Number(handlingRate) : null,
      ground_handling_overrides: [],
    });
    showResults(data.results);
    const result = data.results[0];
    addMessage(result.assignments
      ? `${result.status} preview: conflicts ${result.original_conflicts} → ${result.optimized_conflicts}; ${result.aircraft_moved} aircraft moved; ${result.connections_fulfilled || 0}/${result.wing_to_wing_connections_requested || 0} connections fulfilled.${result.message ? ` ${result.message}` : ''}`
      : `Solver preview: ${result.message}`);
  } catch (error) {
    addMessage(error.message, 'error');
  } finally {
    setBusy(false);
  }
});

// --- Conversation reset, result controls, playback, and download ---
$('reset').addEventListener('click', () => {
  sessionId = null;
  $('chat').replaceChildren();
  addMessage('New conversation started. What would you like to explore?');
});
$('scenario').addEventListener('change', selectResult);
$('clock').addEventListener('input', () => {
  minute = Number($('clock').value);
  render();
});
$('dataset').addEventListener('change', updateHelp);
$('view').addEventListener('change', () => {
  updateHelp();
  render();
});
$('play').addEventListener('click', () => {
  playing = !playing;
  $('play').textContent = playing ? 'Pause' : 'Play';
});
$('download').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob(
    [JSON.stringify(results[selectedResult], null, 2)],
    {type: 'application/json'},
  ));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'gate-plan.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

// --- Animation frame and backend connection status ---
function frame(time) {
  if (playing && lastFrame) {
    minute = (minute + Math.min(time - lastFrame, 100) * 0.025) % 1440;
    render();
  }
  lastFrame = time;
  requestAnimationFrame(frame);
}

requestAnimationFrame(frame);
updateHelp();
render();
fetch('/api/config').then(response => {
  if (!response.ok) throw new Error();
  return response.json();
}).then(config => {
  $('connection').textContent = config.chat_available
    ? 'OpenAI configured · CP-SAT runs on the server'
    : 'Chat needs OPENAI_API_KEY on the server. Solver preview is available now.';
}).catch(() => {
  $('connection').textContent = 'Backend unavailable. Start the Python server to connect.';
});
