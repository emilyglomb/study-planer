/* StudyPlanner  interactive statistics charts. */

function _themeColors() {
  const s = getComputedStyle(document.documentElement);
  const v = (name) => s.getPropertyValue(name).trim();
  return {
    primary: v('--primary'), primarySoft: v('--primary-soft'),
    accent: v('--accent'), accentSoft: v('--accent-soft'),
    ok: v('--ok'), bad: v('--bad'),
    text: v('--text'), muted: v('--muted'), line: v('--line'),
    surface: v('--surface'),
 
    chart: [v('--chart-1'), v('--chart-2'), v('--chart-3'), v('--chart-4'), v('--chart-5'), v('--chart-6')],
    diffMedium: v('--diff-medium'),
  };
}

let _charts = [];
function _destroyCharts() {
  _charts.forEach(c => c.destroy());
  _charts = [];
}

function _grid(c) {
  return { color: c.line, drawTicks: false };
}
function _ticks(c) {
  return { color: c.muted, font: { family: getComputedStyle(document.body).fontFamily } };
}

function _palette(c, n) {
  const base = c.chart;
  const out = [];
  for (let i = 0; i < n; i++) {
  
    const round = Math.floor(i / base.length);
    const hex = base[i % base.length];
    out.push(round === 0 ? hex : `color-mix(in srgb, ${hex} ${Math.max(35, 85 - round * 25)}%, ${c.surface})`);
  }
  return out;
}

function _showLoadError() {

  document.querySelectorAll('.chart-box').forEach(box => {
    box.innerHTML = '<p class="muted" style="font-size:12.5px;">Charts could not load (chart.umd.min.js missing).</p>';
  });
}

function buildStatsCharts(data) {
  if (!window.Chart) { _showLoadError(); return; }
  _destroyCharts();
  const c = _themeColors();
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = c.muted;
  Chart.defaults.responsive = true;
  Chart.defaults.maintainAspectRatio = false;

  const elCredits = document.getElementById('chartCredits');
  if (elCredits) {
    _charts.push(new Chart(elCredits, {
      type: 'bar',
      data: {
        labels: data.sem_labels,
        datasets: [{ label: 'ECTS', data: data.credits_series, backgroundColor: c.accent, borderRadius: 6, maxBarThickness: 34 }],
      },
      options: {
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ctx.parsed.y + ' ECTS' } } },
        scales: { x: { grid: { display: false }, ticks: _ticks(c) }, y: { beginAtZero: true, grid: _grid(c), ticks: _ticks(c) } },
      },
    }));
  }

  const elWorkload = document.getElementById('chartWorkload');
  if (elWorkload) {
    _charts.push(new Chart(elWorkload, {
      type: 'bar',
      data: {
        labels: data.sem_labels,
        datasets: [
          { label: 'Contact hours', data: data.attendance_series, backgroundColor: c.accent, borderRadius: 4, maxBarThickness: 28 },
          { label: 'Self-study hours', data: data.selfstudy_series, backgroundColor: c.primary, borderRadius: 4, maxBarThickness: 28 },
        ],
      },
      options: {
        plugins: { legend: { position: 'bottom', labels: { color: c.text, boxWidth: 12, usePointStyle: true, pointStyle: 'circle' } } },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: _ticks(c) },
          y: { stacked: true, beginAtZero: true, grid: _grid(c), ticks: _ticks(c) },
        },
      },
    }));
  }

  const elExam = document.getElementById('chartExam');
  if (elExam && data.exam_labels.length) {
    _charts.push(new Chart(elExam, {
      type: 'doughnut',
      data: {
        labels: data.exam_labels,
        datasets: [{ data: data.exam_pcts, backgroundColor: _palette(c, data.exam_labels.length), borderColor: c.surface, borderWidth: 2 }],
      },
      options: {
        cutout: '62%',
        plugins: {
          legend: { position: 'bottom', labels: { color: c.text, boxWidth: 12, usePointStyle: true, pointStyle: 'circle' } },
          tooltip: { callbacks: { label: (ctx) => ctx.label + ': ' + ctx.parsed + '%' } },
        },
      },
    }));
  }

  const elAreas = document.getElementById('chartAreas');
  if (elAreas && data.areas_labels.length) {
    _charts.push(new Chart(elAreas, {
      type: 'doughnut',
      data: {
        labels: data.areas_labels,
        datasets: [{ data: data.areas_pcts, backgroundColor: _palette(c, data.areas_labels.length), borderColor: c.surface, borderWidth: 2 }],
      },
      options: {
        cutout: '62%',
        plugins: {
          legend: { position: 'bottom', labels: { color: c.text, boxWidth: 12, usePointStyle: true, pointStyle: 'circle' } },
          tooltip: { callbacks: { label: (ctx) => ctx.label + ': ' + ctx.parsed + '%' } },
        },
      },
    }));
  }

  const elGrade = document.getElementById('chartGrade');
  if (elGrade && data.grade_series.some(g => g !== null)) {
    _charts.push(new Chart(elGrade, {
      type: 'line',
      data: {
        labels: data.sem_labels,
        datasets: [{
          label: 'Avg. grade', data: data.grade_series, spanGaps: true,
          borderColor: c.primary, backgroundColor: c.primarySoft, tension: 0.35,
          pointBackgroundColor: c.primary, pointRadius: 4, fill: true,
        }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: _ticks(c) }, y: { reverse: true, min: 1, max: 5, grid: _grid(c), ticks: _ticks(c) } },
      },
    }));
  }

  // ported from the old calculate_statistics()'s fig4/5 (exam types per
  // semester) and fig7/8 (study areas per semester)  stacked bars, one
  // dataset per category, colors cycling through the theme palette.
  const elExamSem = document.getElementById('chartExamSem');
  if (elExamSem && data.exam_per_sem_labels.length) {
    const colors = _palette(c, data.exam_per_sem_labels.length);
    _charts.push(new Chart(elExamSem, {
      type: 'bar',
      data: {
        labels: data.sem_labels,
        datasets: data.exam_per_sem_labels.map((lbl, i) => ({
          label: lbl, data: data.exam_per_sem_series[i], backgroundColor: colors[i], maxBarThickness: 34,
        })),
      },
      options: {
        plugins: { legend: { position: 'bottom', labels: { color: c.text, boxWidth: 12, usePointStyle: true, pointStyle: 'circle' } } },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: _ticks(c) },
          y: { stacked: true, beginAtZero: true, ticks: { ..._ticks(c), precision: 0 }, grid: _grid(c) },
        },
      },
    }));
  }

  const elAreaSem = document.getElementById('chartAreaSem');
  if (elAreaSem && data.area_per_sem_labels.length) {
    const colors = _palette(c, data.area_per_sem_labels.length);
    _charts.push(new Chart(elAreaSem, {
      type: 'bar',
      data: {
        labels: data.sem_labels,
        datasets: data.area_per_sem_labels.map((lbl, i) => ({
          label: lbl, data: data.area_per_sem_series[i], backgroundColor: colors[i], maxBarThickness: 34,
        })),
      },
      options: {
        plugins: { legend: { position: 'bottom', labels: { color: c.text, boxWidth: 12, usePointStyle: true, pointStyle: 'circle' } } },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: _ticks(c) },
          y: { stacked: true, beginAtZero: true, ticks: { ..._ticks(c), precision: 0 }, grid: _grid(c) },
        },
      },
    }));
  }

  // ported from fig11 (workload vs. failure rate scatter, colored by difficulty)
  const elScatter = document.getElementById('chartScatter');
  if (elScatter && data.scatter_points.length) {
    const diffColor = { easy: c.ok, medium: c.diffMedium, hard: c.bad };
    const diffLabel = { easy: 'Easy', medium: 'Medium', hard: 'Hard' };
    const byDiff = { easy: [], medium: [], hard: [] };
    data.scatter_points.forEach(p => { (byDiff[p.diff] || byDiff.medium).push(p); });
    _charts.push(new Chart(elScatter, {
      type: 'scatter',
      data: {
        datasets: Object.keys(byDiff).filter(k => byDiff[k].length).map(k => ({
          label: diffLabel[k], data: byDiff[k], backgroundColor: diffColor[k], pointRadius: 6, pointHoverRadius: 8,
        })),
      },
      options: {
        plugins: {
          legend: { position: 'bottom', labels: { color: c.text, boxWidth: 12, usePointStyle: true, pointStyle: 'circle' } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.raw.name}: ${ctx.raw.x}h/week, ${ctx.raw.y}% failure` } },
        },
        scales: {
          x: { title: { display: true, text: 'Weekly workload (h)', color: c.muted }, grid: _grid(c), ticks: _ticks(c) },
          y: { title: { display: true, text: 'Failure rate (%)', color: c.muted }, beginAtZero: true, grid: _grid(c), ticks: _ticks(c) },
        },
      },
    }));
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (window.STATS_DATA) buildStatsCharts(window.STATS_DATA);
});
document.addEventListener('sp-theme-changed', () => {
  if (window.STATS_DATA) buildStatsCharts(window.STATS_DATA);
});
