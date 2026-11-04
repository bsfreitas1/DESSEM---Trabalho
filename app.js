// -----------------------------------------------------------------------------
// Estado e utilitários
// -----------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

const state = {
  defaults: null,
  values: null,
  rows: null,
  result: null,
  period: 0,
  timer: null,
  running: false,
  pending: false,
  version: 0,
  visible: {},
  chartZoom: null,
  thermalOptions: [],
  selectedThermals: [],
  defaultThermals: [],
  limits: {},
};

const baseControlGroups = [
  {
    title: 'Sistema',
    subtitle: 'Demanda e penalidade de atendimento',
    controls: [
      ['demanda', 'Demanda do SE', 'Escala aplicada a toda a curva de demanda.'],
      ['custo_deficit', 'Custo do déficit', 'Multiplicador da penalidade por energia não atendida.'],
    ],
  },
  {
    title: 'Furnas',
    subtitle: 'Usina hidrelétrica de montante',
    controls: [
      ['afluencia_furnas', 'Afluência natural', 'Vazão natural total da cadeia a montante.'],
    ],
  },
  {
    title: 'Mascarenhas de Moraes',
    subtitle: 'Usina hidrelétrica de jusante',
    controls: [
      ['afluencia_moraes', 'Afluência incremental', 'Vazão incremental própria da usina.'],
    ],
  },
  {
    title: 'Premissas do estudo',
    subtitle: 'Limites globais da otimização',
    controls: [
      ['rampa', 'Fração de rampa', 'Percentual de Pmáx − Pmín por meia hora.'],
      ['custo_vertimento', 'Custo do vertimento', 'Penalidade em R$ por hm³ de água vertida.'],
    ],
  },
];

const chartModes = {
  generation: [
    ['Demanda', (row) => row.demanda, '#17231e'],
    ['Furnas', (row) => row.gh_FURNAS, '#2b8cad'],
    ['Moraes', (row) => row.gh_MORAES, '#70b794'],
  ],
  cmo: [['CMO', (row) => row.cmo, '#194d3b']],
  deficit: [['Déficit', (row) => row.deficit, '#b33a3a']],
  inflow: [
    ['Furnas', (row) => row.afluencia_FURNAS, '#2b8cad'],
    ['Moraes', (row) => row.afluencia_MORAES, '#70b794'],
  ],
  volume: [
    ['Furnas', (row) => row.V_FURNAS, '#2b8cad'],
    ['Moraes', (row) => row.V_MORAES, '#70b794'],
  ],
  flow: [
    ['Furnas', (row) => row.q_FURNAS, '#2b8cad'],
    ['Moraes', (row) => row.q_MORAES, '#70b794'],
  ],
  spill: [
    ['Furnas', (row) => row.s_FURNAS, '#2b8cad'],
    ['Moraes', (row) => row.s_MORAES, '#70b794'],
  ],
};

const thermalColors = ['#dc7040', '#d9aa43'];

function thermalOption(id) {
  return state.thermalOptions.find((option) => option.id === id);
}

function thermalKey(prefix, id) {
  return `${prefix}_${id.toLowerCase()}`;
}

function thermalLabel(id) {
  const option = thermalOption(id);
  return `${option.nome} · UG ${option.unidade}`;
}

function thermalRampSeries() {
  const colors = [
    ['#dc7040', '#f0a178', '#a94b25'],
    ['#2b8cad', '#75bdd2', '#17637c'],
  ];
  return state.selectedThermals.flatMap((id, index) => {
    const label = thermalLabel(id);
    const [generationColor, startupColor, shutdownColor] = colors[index];
    return [
      [`${label} · geração`, (row) => row[`gt_${id}`], generationColor],
      [`${label} · acionamento`, (row) => row[`rampa_partida_${id}`], startupColor],
      [`${label} · desligamento`, (row) => row[`rampa_parada_${id}`], shutdownColor],
    ];
  });
}

function controlGroups() {
  const premises = baseControlGroups[baseControlGroups.length - 1];
  const fixed = baseControlGroups.slice(0, -1);
  const thermalGroups = state.selectedThermals.map((id) => ({
    title: thermalLabel(id),
    subtitle: 'Usina termelétrica selecionada',
    controls: [
      [thermalKey('cvu', id), 'Custo', 'Multiplicador do custo variável unitário.'],
      [thermalKey('ton', id), 'Ton', 'Tempo mínimo ligada, em horas.'],
      [thermalKey('toff', id), 'Toff', 'Tempo mínimo desligada, em horas.'],
    ],
  }));
  return [...fixed, ...thermalGroups, premises];
}

function generationSeries() {
  return [
    ['Demanda', (row) => row.demanda, '#17231e'],
    ['Furnas', (row) => row.gh_FURNAS, '#2b8cad'],
    ['Moraes', (row) => row.gh_MORAES, '#70b794'],
    ...state.selectedThermals.map((id, index) => [
      thermalLabel(id), (row) => row[`gt_${id}`], thermalColors[index],
    ]),
  ];
}

function formatNumber(value, digits = 2) {
  return Number(value).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function escapeHtml(value) {
  const replacements = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
  return String(value).replace(/[&<>"']/g, (character) => replacements[character]);
}

function setStatus(title, detail, type = 'ready') {
  $('status-title').textContent = title;
  $('status-text').textContent = detail;
  $('status').className = `status ${type}`;
}

function showToast(message) {
  $('toast').textContent = message;
  $('toast').className = 'show';
  setTimeout(() => {$('toast').className = '';}, 5000);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {cache: 'no-store', ...options});
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || `Erro HTTP ${response.status}`);
    error.code = response.status;
    throw error;
  }
  return body;
}

// -----------------------------------------------------------------------------
// Controles dos parâmetros
// -----------------------------------------------------------------------------
function isTimeControl(key) {
  return key.startsWith('ton_') || key.startsWith('toff_');
}

function displayControlValue(key, value) {
  if (key === 'custo_vertimento') return `R$ ${formatNumber(value, 2)}/hm³`;
  if (isTimeControl(key)) return `${formatNumber(value, 1)} h`;
  if (key.startsWith('cvu_ute_')) {
    const option = thermalOption(key.slice(4).toUpperCase());
    return `R$ ${formatNumber(option.cvu * value, 2)}/MWh`;
  }
  return `${formatNumber(value * 100, 0)}%`;
}

function controlStep(key) {
  if (isTimeControl(key)) return 0.5;
  if (key === 'custo_vertimento' || key === 'rampa') return 0.01;
  return 0.05;
}

function controlHtml(key, label, help, limits) {
  const [minimum, maximum] = limits[key];
  return `
    <div class="control">
      <div class="control-heading">
        <label for="${key}">${label}</label>
        <output id="out-${key}"></output>
      </div>
      <input id="${key}" type="range" min="${minimum}" max="${maximum}" step="${controlStep(key)}">
      <div class="scale">
        <small>${displayControlValue(key, minimum)}</small>
        <small>${displayControlValue(key, maximum)}</small>
      </div>
      <small>${help}</small>
    </div>`;
}

function drawControls(limits) {
  const groups = controlGroups();
  $('controls').innerHTML = groups.map((group, index) => `
    <details class="control-group" ${index === 0 ? 'open' : ''}>
      <summary>
        <span><b>${group.title}</b><small>${group.subtitle}</small></span>
        <i aria-hidden="true">⌄</i>
      </summary>
      <div class="control-group-body">
        ${group.controls.map(([key, label, help]) => controlHtml(key, label, help, limits)).join('')}
      </div>
    </details>`).join('');

  groups.flatMap((group) => group.controls).forEach(([key]) => {
    const input = $(key);
    input.value = state.values[key];
    input.addEventListener('input', () => {
      state.values[key] = Number(input.value);
      updateControl(key);
      state.version += 1;
      scheduleRun();
    });
    updateControl(key);
  });
}

function updateControl(key) {
  const input = $(key);
  const ratio = (Number(input.value) - Number(input.min)) / (Number(input.max) - Number(input.min));
  input.style.setProperty('--fill', `${ratio * 100}%`);
  $(`out-${key}`).textContent = displayControlValue(key, Number(input.value));
}

function resetControls() {
  state.selectedThermals = [...state.defaultThermals];
  state.visible.generation = null;
  state.visible['thermal-ramp'] = null;
  $('end-effect').checked = false;
  state.values = {...state.defaults};
  configureThermalControls(false);
  state.version += 1;
  scheduleRun(true);
}

function configureThermalControls(useDeckDefaults = true) {
  const baseKeys = Object.keys(state.defaults).filter((key) =>
    !key.startsWith('cvu_ute_') && !key.startsWith('ton_ute_') && !key.startsWith('toff_ute_'));
  state.values = Object.fromEntries(baseKeys.map((key) => [key, state.values[key] ?? state.defaults[key]]));
  state.limits = Object.fromEntries(baseKeys.map((key) => [key, state.limits[key]]));

  state.selectedThermals.forEach((id) => {
    const option = thermalOption(id);
    const defaults = {cvu: 1, ton: option.ton_h, toff: option.toff_h};
    Object.entries(defaults).forEach(([prefix, defaultValue]) => {
      const key = thermalKey(prefix, id);
      if (useDeckDefaults || state.values[key] === undefined) state.values[key] = defaultValue;
      state.limits[key] = prefix === 'cvu'
        ? [0.5, 1.5]
        : [0, Math.max(336, defaultValue)];
    });
  });
  $('selected-utes').textContent = state.selectedThermals.map(thermalLabel).join(' · ');
  drawControls(state.limits);
}

function populateThermalPicker() {
  const options = state.thermalOptions.map((option) =>
    `<option value="${option.id}">${escapeHtml(option.rotulo)}</option>`).join('');
  $('ute-choice-1').innerHTML = options;
  $('ute-choice-2').innerHTML = options;
}

// -----------------------------------------------------------------------------
// Execução da otimização
// -----------------------------------------------------------------------------
function scheduleRun(immediate = false) {
  if (!$('auto-run').checked && !immediate) {
    setStatus('Alterações pendentes', 'Clique em Executar otimização.', 'pending');
    return;
  }

  clearTimeout(state.timer);
  setStatus('Cenário alterado', 'Aguardando recálculo…', 'pending');
  state.timer = setTimeout(executeDispatch, immediate ? 0 : 850);
}

async function executeDispatch() {
  clearTimeout(state.timer);
  if (state.running) {
    state.pending = true;
    return;
  }

  state.running = true;
  state.pending = false;
  const requestedVersion = state.version;
  const values = {...state.values};
  $('run').disabled = true;
  setStatus('Otimizando cenário', 'MILP e cálculo do CMO em execução…', 'running');

  try {
    const result = await requestJson('/api/dispatch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        ajustes: values,
        termicas: state.selectedThermals,
        efeito_fim_mundo: $('end-effect').checked,
      }),
    });

    if (requestedVersion === state.version) {
      state.result = result;
      state.rows = result.linhas;
      renderAll();
      setStatus(
        `Solução ${result.status}`,
        `Gap ${formatNumber(result.gap * 100, 3)}% · ${formatNumber(result.tempo_s, 2)} s`,
      );
    }
  } catch (error) {
    if (error.code === 409) {
      state.pending = true;
      setStatus('Solver ocupado', 'Nova execução aguardando…', 'pending');
    } else {
      setStatus('Falha na otimização', error.message, 'error');
      showToast(error.message);
    }
  } finally {
    state.running = false;
    $('run').disabled = false;
    if (state.pending || (requestedVersion !== state.version && $('auto-run').checked)) {
      state.pending = false;
      setTimeout(executeDispatch, 1000);
    }
  }
}

// -----------------------------------------------------------------------------
// Indicadores, período em foco e tabela
// -----------------------------------------------------------------------------
function renderAll() {
  const summary = state.result.resumo;
  $('cost').textContent = formatNumber(state.result.custo);
  $('hydro').textContent = formatNumber(summary.energia_hidraulica, 0);
  $('thermal').textContent = formatNumber(summary.energia_termica, 0);
  $('cmo').textContent = formatNumber(summary.cmo_medio);
  $('period').disabled = false;
  $('download').disabled = false;
  fillChartPeriods();
  renderPeriod();
  renderChart();
  renderTable();
}

function setText(id, value, unit = '', digits = 2) {
  $(id).textContent = `${formatNumber(value, digits)}${unit}`;
}

function renderPeriod() {
  if (!state.rows) return;
  const row = state.rows[state.period];
  $('period').value = state.period + 1;
  $('period').style.setProperty('--fill', `${state.period / (state.rows.length - 1) * 100}%`);
  $('period-label').textContent = `${row.inicio.replace(' ', ' · ')} · Período ${row.t}`;
  setText('furnas-gen', row.gh_FURNAS);
  setText('furnas-q', row.q_FURNAS);
  setText('furnas-v', row.V_FURNAS);
  setText('moraes-gen', row.gh_MORAES);
  setText('moraes-q', row.q_MORAES);
  setText('moraes-v', row.V_MORAES);
  $('period-stats').innerHTML = [
    ...state.selectedThermals.map((id) =>
      `<div>${escapeHtml(thermalLabel(id))}<b>${formatNumber(row[`gt_${id}`])} MW</b></div>`),
    `<div>Demanda<b id="period-demand">—</b></div>`,
    `<div>Déficit<b id="period-deficit">—</b></div>`,
    `<div>CMO<b id="period-cmo">—</b></div>`,
  ].join('');
  setText('period-demand', row.demanda, ' MW');
  setText('period-deficit', row.deficit, ' MW');
  setText('period-cmo', row.cmo, ' R$/MWh');
  $('day').value = String(Math.floor(state.period / 48));
  document.querySelectorAll('#rows tr[data-index]').forEach((rowElement) => {
    rowElement.classList.toggle('active', Number(rowElement.dataset.index) === state.period);
  });
}

function renderTable() {
  if (!state.rows) return;
  const day = Number($('day').value || 0);
  const start = day * 48;
  $('results-head').innerHTML = [
    '<th>Início</th><th>Demanda<br>MW</th><th>Furnas<br>MW</th><th>Moraes<br>MW</th>',
    ...state.selectedThermals.map((id) => `<th>${escapeHtml(thermalLabel(id))}<br>MW</th>`),
    '<th>Déficit<br>MW</th><th>CMO<br>R$/MWh</th>',
  ].join('');
  $('rows').innerHTML = state.rows.slice(start, start + 48).map((row, index) => `
    <tr data-index="${start + index}" class="${start + index === state.period ? 'active' : ''}">
      <td>${escapeHtml(row.inicio.slice(11))}</td>
      <td>${formatNumber(row.demanda)}</td><td>${formatNumber(row.gh_FURNAS)}</td>
      <td>${formatNumber(row.gh_MORAES)}</td>
      ${state.selectedThermals.map((id) => `<td>${formatNumber(row[`gt_${id}`])}</td>`).join('')}
      <td>${formatNumber(row.deficit)}</td>
      <td>${formatNumber(row.cmo)}</td>
    </tr>`).join('');

  document.querySelectorAll('#rows tr[data-index]').forEach((rowElement) => {
    rowElement.onclick = () => {
      state.period = Number(rowElement.dataset.index);
      renderPeriod();
      renderChart();
    };
  });
}

// -----------------------------------------------------------------------------
// Gráfico temporal
// -----------------------------------------------------------------------------
function fillChartPeriods() {
  const firstDate = state.rows[0].inicio.slice(0, 10);
  const lastDate = state.rows[state.rows.length - 1].inicio.slice(0, 10);
  ['chart-start', 'chart-end'].forEach((id) => {
    $(id).min = firstDate;
    $(id).max = lastDate;
  });
  if (!$('chart-start').value) $('chart-start').value = firstDate;
  if (!$('chart-end').value) $('chart-end').value = lastDate;
}

function selectedChartRows() {
  const start = $('chart-start').value;
  const end = $('chart-end').value;
  const filtered = state.rows.map((row, index) => ({row, index}))
    .filter(({row}) => row.inicio.slice(0, 10) >= start && row.inicio.slice(0, 10) <= end);
  if (!state.chartZoom || filtered.length < 2) return filtered;
  const zoomStart = Math.max(0, Math.min(state.chartZoom.start, filtered.length - 1));
  const zoomEnd = Math.max(zoomStart + 1, Math.min(state.chartZoom.end, filtered.length));
  return filtered.slice(zoomStart, zoomEnd);
}

function resetChartZoom() {
  state.chartZoom = null;
  $('zoom-reset').textContent = '100%';
}

function changeChartZoom(factor, anchorRatio = 0.5) {
  if (!state.rows) return;
  const start = $('chart-start').value;
  const end = $('chart-end').value;
  const total = state.rows.filter((row) => row.inicio.slice(0, 10) >= start && row.inicio.slice(0, 10) <= end).length;
  if (total < 3) return;
  const currentStart = state.chartZoom?.start ?? 0;
  const currentEnd = state.chartZoom?.end ?? total;
  const currentSize = currentEnd - currentStart;
  const newSize = Math.max(2, Math.min(total, Math.round(currentSize * factor)));
  const anchor = currentStart + currentSize * anchorRatio;
  let newStart = Math.round(anchor - newSize * anchorRatio);
  newStart = Math.max(0, Math.min(total - newSize, newStart));
  state.chartZoom = newSize === total ? null : {start: newStart, end: newStart + newSize};
  $('zoom-reset').textContent = state.chartZoom ? `${Math.round(total / newSize * 100)}%` : '100%';
  renderChart();
}

function updateChartDateRange() {
  if (!state.rows) return;
  if ($('chart-start').value > $('chart-end').value) {
    showToast('A data inicial deve ser anterior ou igual à data final.');
    return;
  }
  resetChartZoom();
  renderChart();
}

function renderChart() {
  if (!state.rows) return;

  const mode = $('chart-mode').value;
  const available = mode === 'generation'
    ? generationSeries()
    : mode === 'thermal-ramp' ? thermalRampSeries() : chartModes[mode];
  const selected = state.visible[mode] ?? new Set(available.map(([name]) => name));
  state.visible[mode] = selected;
  const series = available.filter(([name]) => selected.has(name));
  const points = selectedChartRows();
  const rows = points.map(({row}) => row);
  if (!rows.length) return;

  const fullscreen = document.fullscreenElement === $('chart-panel');
  const width = Math.max(640, Math.round($('chart').clientWidth || 940));
  const height = fullscreen ? Math.max(420, window.innerHeight - 185) : 290;
  const independentAxes = mode === 'volume' || mode === 'inflow';
  const left = 55;
  const right = independentAxes && series.length > 1 ? 70 : 15;
  const top = 18;
  const bottom = 35;
  $('chart').style.setProperty('--chart-height', `${height}px`);

  const finiteValues = (valueOf) => rows.map(valueOf).filter(Number.isFinite);
  const values = series.flatMap(([, valueOf]) => finiteValues(valueOf));
  const paddedRange = (rangeValues) => {
    if (!rangeValues.length) return {minimum: 0, maximum: 1};
    const observedMinimum = Math.min(...rangeValues);
    const observedMaximum = Math.max(...rangeValues);
    const padding = Math.max(
      (observedMaximum - observedMinimum) * 0.08,
      Math.max(Math.abs(observedMinimum), Math.abs(observedMaximum)) * 0.01,
      0.01,
    );
    return {
      minimum: observedMinimum >= 0 ? Math.max(0, observedMinimum - padding) : observedMinimum - padding,
      maximum: observedMaximum + padding,
    };
  };
  const overallRange = paddedRange(values);
  const minimum = overallRange.minimum;
  const maximum = overallRange.maximum;
  const span = maximum - minimum;
  const axisRanges = independentAxes
    ? series.map(([, valueOf]) => paddedRange(finiteValues(valueOf)))
    : [];
  const x = (index) => rows.length === 1
    ? left + (width - left - right) / 2
    : left + index * (width - left - right) / (rows.length - 1);
  const y = (value, seriesIndex = 0) => {
    if (!independentAxes) return top + (maximum - value) * (height - top - bottom) / span;
    const range = axisRanges[seriesIndex];
    return top + (range.maximum - value) * (height - top - bottom) / (range.maximum - range.minimum);
  };

  let svg = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" aria-label="Série temporal">`;
  svg += `<rect x="0" y="0" width="${width}" height="${height}" fill="transparent"/>`;

  for (let line = 0; line <= 4; line += 1) {
    const position = height - bottom - line * (height - top - bottom) / 4;
    svg += `<line x1="${left}" y1="${position}" x2="${width - right}" y2="${position}" stroke="#e2e6df"/>`;
    if (independentAxes && axisRanges.length) {
      const leftValue = axisRanges[0].minimum + (axisRanges[0].maximum - axisRanges[0].minimum) * line / 4;
      svg += `<text x="${left - 7}" y="${position + 4}" text-anchor="end" fill="${series[0][2]}" font-size="12">${formatNumber(leftValue, 1)}</text>`;
      if (axisRanges[1]) {
        const rightValue = axisRanges[1].minimum + (axisRanges[1].maximum - axisRanges[1].minimum) * line / 4;
        svg += `<text x="${width - right + 7}" y="${position + 4}" text-anchor="start" fill="${series[1][2]}" font-size="12">${formatNumber(rightValue, 1)}</text>`;
      }
    } else {
      const value = minimum + span * line / 4;
      svg += `<text x="${left - 7}" y="${position + 4}" text-anchor="end" fill="#68746e" font-size="12">${formatNumber(value, 0)}</text>`;
    }
  }

  if (rows.length === 1) {
    svg += `<text x="${x(0)}" y="${height - 9}" text-anchor="middle" fill="#68746e" font-size="12">${escapeHtml(rows[0].inicio.slice(5))}</text>`;
  } else {
    for (let index = 0; index < rows.length; index += 48) {
      svg += `<line x1="${x(index)}" y1="${top}" x2="${x(index)}" y2="${height - bottom}" stroke="#e2e6df"/>`;
      svg += `<text x="${x(index)}" y="${height - 9}" text-anchor="middle" fill="#68746e" font-size="12">${rows[index].inicio.slice(8, 10)}/${rows[index].inicio.slice(5, 7)}</text>`;
    }
  }

  series.forEach(([name, valueOf, color], seriesIndex) => {
    let segment = [];
    const drawSegment = () => {
      if (segment.length > 1) {
        svg += `<polyline points="${segment.join(' ')}" fill="none" stroke="${color}" stroke-width="2.2" vector-effect="non-scaling-stroke"/>`;
      } else if (segment.length === 1) {
        const [cx, cy] = segment[0].split(',');
        svg += `<circle cx="${cx}" cy="${cy}" r="3.5" fill="${color}"/>`;
      }
      segment = [];
    };
    rows.forEach((row, index) => {
      const value = valueOf(row);
      if (Number.isFinite(value)) segment.push(`${x(index).toFixed(1)},${y(value, seriesIndex).toFixed(1)}`);
      else drawSegment();
    });
    drawSegment();
    if (mode === 'volume' && points[points.length - 1].index === state.rows.length - 1) {
      const finalValue = valueOf(rows[rows.length - 1]);
      svg += `<circle cx="${x(rows.length - 1)}" cy="${y(finalValue, seriesIndex)}" r="4" fill="${color}"/>`;
      svg += `<text x="${x(rows.length - 1) - 8}" y="${y(finalValue, seriesIndex) - 7}" text-anchor="end" fill="${color}" font-size="12">${escapeHtml(name)}: ${formatNumber(finalValue)} hm³</text>`;
    }
  });

  const focusedPoint = points.findIndex(({index}) => index === state.period);
  const cursorIndex = focusedPoint >= 0 ? focusedPoint : 0;
  svg += `<line id="cursor" x1="${x(cursorIndex)}" y1="${top}" x2="${x(cursorIndex)}" y2="${height - bottom}" stroke="#17231e" stroke-dasharray="4 4"/>`;
  svg += `<rect id="chart-hit" x="${left}" y="${top}" width="${width - left - right}" height="${height - top - bottom}" fill="transparent"></svg>`;
  $('chart').innerHTML = `${svg}<div class="tooltip" id="tooltip"></div>`;

  const finalRow = state.rows[state.rows.length - 1];
  $('legend').innerHTML = available.map(([name, valueOf, color], index) => `
    <label>
      <input type="checkbox" data-curve="${index}" ${selected.has(name) ? 'checked' : ''}>
      <i style="background:${color}"></i><span>${name}${mode === 'volume'
        ? ` · final: ${formatNumber(valueOf(finalRow))} hm³`
        : ''}</span>
    </label>`).join('');

  document.querySelectorAll('[data-curve]').forEach((input) => {
    input.onchange = () => {
      const name = available[Number(input.dataset.curve)][0];
      input.checked ? selected.add(name) : selected.delete(name);
      renderChart();
    };
  });

  const hitArea = $('chart-hit');
  hitArea.onmousemove = (event) => showChartTooltip(event, points, series, width, x);
  hitArea.onmouseleave = () => {$('tooltip').style.display = 'none';};
  hitArea.onclick = (event) => selectChartPoint(event, points, width);
  hitArea.onwheel = (event) => {
    event.preventDefault();
    const bounds = $('chart').getBoundingClientRect();
    const anchorRatio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    changeChartZoom(event.deltaY < 0 ? 0.7 : 1.4, anchorRatio);
  };
  hitArea.ondblclick = () => { resetChartZoom(); renderChart(); };
}

function chartPointAt(event, pointCount, width) {
  if (pointCount === 1) return 0;
  const bounds = $('chart').getBoundingClientRect();
  const left = 55;
  const mode = $('chart-mode').value;
  const independentAxes = mode === 'volume' || mode === 'inflow';
  const right = independentAxes && (state.visible[mode]?.size ?? 2) > 1 ? 70 : 15;
  return Math.max(0, Math.min(pointCount - 1, Math.round(
    ((event.clientX - bounds.left) / bounds.width * width - left) / (width - left - right) * (pointCount - 1)
  )));
}

function showChartTooltip(event, points, series, width, x) {
  const pointIndex = chartPointAt(event, points.length, width);
  const row = points[pointIndex].row;
  const bounds = $('chart').getBoundingClientRect();
  $('cursor').setAttribute('x1', x(pointIndex));
  $('cursor').setAttribute('x2', x(pointIndex));
  $('tooltip').style.display = 'block';
  $('tooltip').style.left = `${Math.min(bounds.width - 155, event.clientX - bounds.left + 12)}px`;
  $('tooltip').style.top = '13px';
  const values = series.length
    ? series.map(([name, valueOf]) => {
      const value = valueOf(row);
      return `${escapeHtml(name)}: ${Number.isFinite(value) ? formatNumber(value) : '—'}`;
    }).join('<br>')
    : 'Nenhuma curva selecionada';
  $('tooltip').innerHTML = `${escapeHtml(row.inicio)}<br>${values}`;
}

function selectChartPoint(event, points, width) {
  state.period = points[chartPointAt(event, points.length, width)].index;
  renderPeriod();
  renderTable();
  renderChart();
}

// -----------------------------------------------------------------------------
// Exportação e eventos
// -----------------------------------------------------------------------------
function downloadCsv() {
  if (!state.rows) return;
  const columns = Object.keys(state.rows[0]);
  const lines = [
    columns.join(';'),
    ...state.rows.map((row) => columns.map((column) => String(row[column] ?? '').replace('.', ',')).join(';')),
  ];
  const blob = new Blob([`\ufeff${lines.join('\r\n')}`], {type: 'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'despacho_cenario.csv';
  link.click();
  URL.revokeObjectURL(url);
}

function toggleParameterPanel() {
  const collapsed = $('workspace').classList.toggle('params-collapsed');
  $('collapse-params').setAttribute('aria-expanded', String(!collapsed));
  document.querySelector('.collapse-icon').textContent = collapsed ? '›' : '‹';
  document.querySelector('.collapse-label').textContent = collapsed ? 'Mostrar parâmetros' : 'Recolher parâmetros';
  requestAnimationFrame(renderChart);
}

$('run').onclick = () => scheduleRun(true);
$('reset').onclick = resetControls;
$('collapse-params').onclick = toggleParameterPanel;
$('choose-utes').onclick = () => {
  $('ute-choice-1').value = state.selectedThermals[0];
  $('ute-choice-2').value = state.selectedThermals[1];
  $('ute-dialog').showModal();
};
$('apply-utes').onclick = (event) => {
  event.preventDefault();
  const selected = [$('ute-choice-1').value, $('ute-choice-2').value];
  if (selected[0] === selected[1]) {
    showToast('Selecione duas UTEs diferentes.');
    return;
  }
  state.selectedThermals = selected;
  state.visible.generation = null;
  state.visible['thermal-ramp'] = null;
  configureThermalControls(true);
  state.version += 1;
  $('ute-dialog').close();
  scheduleRun();
};
$('auto-run').onchange = () => $('auto-run').checked
  ? scheduleRun(true)
  : setStatus('Recálculo pausado', 'Use Executar otimização para aplicar ajustes.', 'pending');
$('end-effect').onchange = () => {
  state.version += 1;
  scheduleRun();
};
$('period').oninput = (event) => {
  state.period = Number(event.target.value) - 1;
  renderPeriod();
  renderTable();
  renderChart();
};
$('chart-mode').onchange = renderChart;
$('chart-start').onchange = updateChartDateRange;
$('chart-end').onchange = updateChartDateRange;
$('zoom-in').onclick = () => changeChartZoom(0.7);
$('zoom-out').onclick = () => changeChartZoom(1.4);
$('zoom-reset').onclick = () => { resetChartZoom(); renderChart(); };
$('day').onchange = renderTable;
$('download').onclick = downloadCsv;
$('fullscreen').onclick = async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await $('chart-panel').requestFullscreen();
};

document.addEventListener('fullscreenchange', () => {
  const fullscreen = Boolean(document.fullscreenElement);
  $('fullscreen').textContent = fullscreen ? 'Sair da tela cheia' : 'Tela cheia ↗';
  $('fullscreen').setAttribute('aria-pressed', String(fullscreen));
  requestAnimationFrame(renderChart);
});

window.addEventListener('resize', () => {
  if (state.rows) requestAnimationFrame(renderChart);
});

// -----------------------------------------------------------------------------
// Inicialização
// -----------------------------------------------------------------------------
async function initialize() {
  try {
    const config = await requestJson('/api/config');
    state.defaults = config.ajustes;
    state.values = {...config.ajustes};
    state.limits = {...config.limites};
    state.thermalOptions = config.termicas;
    state.defaultThermals = [...config.termicas_padrao];
    state.selectedThermals = [...config.termicas_padrao];
    populateThermalPicker();
    configureThermalControls(false);
    $('period').max = config.periodos;

    const initialDate = new Date(`${config.inicio}Z`);
    $('day').innerHTML = Array.from({length: config.periodos / 48}, (_, index) => {
      const date = new Date(initialDate.getTime() + index * 86400000);
      const label = date.toLocaleDateString('pt-BR', {day: '2-digit', month: 'short', timeZone: 'UTC'});
      return `<option value="${index}">${label}</option>`;
    }).join('');

    scheduleRun(true);
  } catch (error) {
    setStatus('Servidor indisponível', error.message, 'error');
    showToast('Inicie com python server.py e acesse http://127.0.0.1:8001');
  }
}

initialize();
