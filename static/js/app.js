/* StudyPlanner frontend interactions */

/*  Theme: persisted across pages via localStorage  */
const THEMES = ['wellness', 'clean', 'dark'];
function applyTheme(t) {
  if (!THEMES.includes(t)) t = 'wellness';
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('sp-theme', t); } catch (e) {}
  document.querySelectorAll('.theme-card').forEach(c =>
    c.classList.toggle('sel', c.dataset.theme === t));
  // let other scripts (e.g. stats.js's Chart.js charts) know the palette
  // changed so they can re-read the CSS variables and redraw in the new colors
  document.dispatchEvent(new CustomEvent('sp-theme-changed', { detail: { theme: t } }));
}
function initTheme() {
  let t = 'wellness';
  try { t = localStorage.getItem('sp-theme') || 'wellness'; } catch (e) {}
  applyTheme(t);
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();

  document.querySelectorAll('.theme-card').forEach(card => {
    card.addEventListener('click', () => applyTheme(card.dataset.theme));
  });

  document.querySelectorAll('.acc-head').forEach(h => {
    h.addEventListener('click', () => h.parentElement.classList.toggle('open'));
  });

  document.querySelectorAll('.toggle').forEach(t => {
    t.addEventListener('click', () => t.classList.toggle('on'));
  });

  /* Full plan: manually move a module to a different semester. The select
     next to each "Move" button is preloaded with the module's current
     semester; validation (frequency fit, credit capacity, prerequisite
     ordering) all happens server-side in appback.move_module_to_semester -
     we just relay whatever error it raises. */
  document.querySelectorAll('.move-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const row = btn.closest('.modrow');
      const select = row.querySelector('.move-sem');
      const targetSem = select.value;
      if (String(select.dataset.current) === String(targetSem)) return;
      btn.disabled = true;
      const body = new URLSearchParams({ module_id: btn.dataset.id, target_semester: targetSem });
      fetch('/move_module', { method: 'POST', body })
        .then(r => r.json().then(data => ({ ok: r.ok, data })))
        .then(({ ok, data }) => {
          if (ok && data.ok) {
            window.location.reload();
          } else {
            alert(data.error || 'Could not move module.');
            btn.disabled = false;
          }
        })
        .catch(() => { alert('Could not move module.'); btn.disabled = false; });
    });
  });

  /* single-select option groups; if data-target is set, write value to a hidden input */
  document.querySelectorAll('[data-select-group]').forEach(group => {
    const targetId = group.dataset.target;
    group.querySelectorAll('.opt:not(.disabled)').forEach(opt => {
      opt.addEventListener('click', () => {
        group.querySelectorAll('.opt').forEach(o => o.classList.remove('sel'));
        opt.classList.add('sel');
        if (targetId) {
          const field = document.getElementById(targetId);
          if (field) field.value = opt.dataset.value || '';
        }
        applyBranchFilter();
        if (targetId === 'f_key_area' && opt.dataset.code)
          chooseBranch('.branch-spec', opt.dataset.code, false);
        if (targetId === 'f_math_track' && opt.dataset.code)
          chooseBranch('.branch-math', opt.dataset.code, true);
      });
    });
  });
  applyBranchFilter();

  /* module checkboxes: keep the .on class in sync + live-update area progress */
  document.querySelectorAll('.check input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => {
      cb.closest('.check').classList.toggle('on', cb.checked);
      updateAreaProgress();
      updateDegreeProgress();
    });
  });
  updateAreaProgress();
  updateDegreeProgress();

  if (document.getElementById('stepper')) initWizard();
});

/* show only the chosen specialization branch and math track */
function _selectedCode(targetId) {
  const grp = document.querySelector('[data-target="' + targetId + '"]');
  if (!grp) return null;
  const sel = grp.querySelector('.opt.sel');
  return sel ? (sel.dataset.code || null) : null;
}
function applyBranchFilter() {
  const k = _selectedCode('f_key_area');
  const m = _selectedCode('f_math_track');
  document.querySelectorAll('.branch-spec').forEach(el => {
    el.style.display = (k && el.dataset.code === k) ? 'block' : 'none';
  });
  document.querySelectorAll('.branch-math').forEach(el => {
    el.style.display = (m && el.dataset.code === m) ? 'block' : 'none';
  });
}

function _setBox(cb, on) {
  cb.checked = on;
  const ch = cb.closest('.check');
  if (ch) ch.classList.toggle('on', on);
}

/* choose one branch of a family (specialization or math package):
   clear every checkbox in the whole family, then tick the mandatory modules of
   the chosen branch  so switching never leaves the old branch's modules selected */
function chooseBranch(family, code, wholeBranchMandatory) {
  document.querySelectorAll(family + ' input[type="checkbox"]').forEach(cb => _setBox(cb, false));
  const el = document.querySelector(family + '[data-code="' + code + '"]');
  if (el) {
    const boxes = [];
    if (wholeBranchMandatory || el.classList.contains('area-mandatory'))
      el.querySelectorAll('input[type="checkbox"]').forEach(b => boxes.push(b));
    el.querySelectorAll('.area-mandatory input[type="checkbox"]').forEach(b => boxes.push(b));
    boxes.forEach(cb => _setBox(cb, true));
  }
  updateAreaProgress();
  updateDegreeProgress();
}

/* live-update the overall degree progress bar (the "I" root, e.g. 180 ECTS
   total) by summing every checked checkbox in the whole form  it has no
   checkboxes nested inside itself (it's a standalone summary, not an
   accordion item), so it can't reuse updateAreaProgress()'s per-item scan. */
function updateDegreeProgress() {
  const box = document.getElementById('degreeProgress');
  if (!box) return;
  const req = parseInt(box.dataset.req, 10) || 0;
  let sel = 0;
  document.querySelectorAll('#planForm input[type="checkbox"]:checked').forEach(cb => {
    sel += parseInt(cb.dataset.cr, 10) || 0;
  });
  const pct = req ? Math.min(100, Math.round(sel / req * 100)) : 0;
  const bar = box.querySelector('.progress.acc > i');
  if (bar) bar.style.width = pct + '%';
  const label = box.querySelector('.area-cr');
  if (label) label.textContent = sel + ' / ' + req + ' ECTS';
  box.classList.toggle('done', req > 0 && sel >= req);
}

/* recompute each study area's selected credits / progress / fulfilment live */
function updateAreaProgress() {
  // #degreeProgress has its own data-req + area-cr but no nested checkboxes
  // (it's a standalone summary, not an accordion item)  updateDegreeProgress()
  // handles it separately, exclude it here so this loop doesn't zero it out.
  document.querySelectorAll('.acc-item[data-req]:not(#degreeProgress)').forEach(item => {
    const req = parseInt(item.dataset.req, 10) || 0;
    let sel = 0;
    item.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
      sel += parseInt(cb.dataset.cr, 10) || 0;
    });
    const pct = req ? Math.min(100, Math.round(sel / req * 100)) : 0;
    const bar = item.querySelector(':scope > .acc-body > .progress.acc > i');
    if (bar) bar.style.width = pct + '%';
    const label = item.querySelector(':scope > .acc-head .area-cr');
    if (label) label.textContent = sel + ' / ' + req + ' ECTS';
    const nowDone = req > 0 && sel >= req;
    item.classList.toggle('done', nowDone);
    // clear the "blocked by last failed create-plan attempt" marker once the
    // area is actually fulfilled again, so it doesn't stay red forever
    if (nowDone) item.classList.remove('area-blocked');
  });
}

/*  Plan creation wizard  */
let wz = 1;
function showStep() {
  document.querySelectorAll('.wstep').forEach(s =>
    s.style.display = (+s.dataset.step === wz) ? 'block' : 'none');
  document.querySelectorAll('#stepper .step').forEach(s => {
    const n = +s.dataset.s;
    s.classList.toggle('done', n < wz);
    s.classList.toggle('cur', n === wz);
  });
  document.getElementById('backBtn').style.visibility = wz === 1 ? 'hidden' : 'visible';
  document.getElementById('wzInfo').textContent = 'Step ' + wz + ' of 5';
  document.getElementById('nextBtn').textContent = wz === 5 ? 'Create plan ✓' : 'Next →';
  window.scrollTo(0, 0);
}
function initWizard() {
  const st = document.getElementById('stepper');
  const start = st ? parseInt(st.dataset.startStep, 10) : NaN;
  wz = Number.isInteger(start) ? start : 1;
  showStep();
}
function wizard(dir) {
  if (wz === 5 && dir > 0) {
    const f = document.getElementById('planForm');
    if (f) { f.submit(); return; }
  }
  wz = Math.min(5, Math.max(1, wz + dir));
  showStep();
}
