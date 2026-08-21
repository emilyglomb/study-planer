"""
StudyPlanner — frontend (Flask) wired to the backend in appback.py.
Run:
    python frontend.py
    # open http://127.0.0.1:5050
The JSON API of appback.py stays available on the same server (e.g. /get_plan),
the designed UI lives on /home, /plan, /statistics, /help, /profile.
"""
import os
import re
import ast
import json
import math
import sqlite3
import pandas as pd
from flask import render_template, request, redirect, url_for, jsonify

import appback                      # reuse the backend unchanged
from appback import app            # same Flask app same server, API + UI

# point the existing app at the designed templates / static assets 
BASE = os.path.dirname(os.path.abspath(__file__))
app.template_folder = os.path.join(BASE, "templates")
app.static_folder = os.path.join(BASE, "static")

DB_SELECTION = appback.DB_SELECTION
DB_MODULES = appback.DB_MODULES


# Static UI content (not part of the backend)

THEMES = [
    {"id": "wellness", "name": "Wellness", "sub": "Pink & green", "c1": "#D6749B", "c2": "#7E9B53"},
    {"id": "clean",    "name": "Clean",    "sub": "Modern editorial", "c1": "#4F46E5", "c2": "#F1663E"},
    {"id": "dark",     "name": "Midnight", "sub": "Dark mode", "c1": "#38BDF8", "c2": "#A78BFA"},
]

FAQS = [
    {"q": 'What does "frequency" mean?',
     "a": 'Indicates when a module is offered: <b>W</b> winter only, <b>S</b> summer only, <b>E</b> every semester, <b>N</b> not specified in the module handbook.'},
    {"q": "What are AR prerequisites?",
     "a": "AR (admission requirements) define which modules must be completed <b>beforehand</b>. The planner keeps this order automatically."},
    {"q": "What does RPK mean?",
     "a": "RPK (recommended previous knowledge) is recommended prior knowledge — not a hard requirement like AR, but considered during planning."},
    {"q": "What if a module can't be placed?",
     "a": "Possible reasons: credit limits too tight, unresolved prerequisites, or an offering rhythm that clashes with the available semesters. Try widening your credit range or adding a semester."},
    {"q": "What is the difference between a key area and a study area?",
     "a": "A <b>key area</b> (Schwerpunkt) is the specialization you pick once. A <b>study area</b> groups modules — Compulsory Computer Science, Mathematics, Key Competencies or your specialization — each with its own credit requirement."},
    {"q": "Can I move modules between semesters manually?",
     "a": "Yes. After generating a plan you can reassign any module to another semester. The planner warns you if a move breaks an AR prerequisite or exceeds your credit limits."},
    {"q": "How are credits distributed across semesters?",
     "a": "The algorithm spreads your selected modules to stay within your min/max ECTS per semester while respecting prerequisites and frequency. Target: 30 ECTS per semester."},
    {"q": "How is my average grade estimated?",
     "a": "It is the credit-weighted mean of the historical average grades of your selected modules — an estimate based on past cohorts, not a prediction."},
    {"q": "What does the failure rate tell me?",
     "a": "The share of students who did not pass a module on their first attempt, averaged across your plan. Use it to spot demanding semesters."},
    {"q": "Can I save more than one study plan?",
     "a": "Yes. You can keep several plans and mark one as active. Manage them on the Profile page."},
    {"q": "Can I change my specialization or settings later?",
     "a": "Yes. Go to Edit plan and adjust the program, key area, math track or semester settings at any time — then regenerate the plan."},
    {"q": "How do I change the app's appearance?",
     "a": "Open the Profile page and pick a theme (Wellness, Clean or Midnight). Your choice is remembered on this device."},
]

# study-area buckets: (display name, list of curriculum-code prefixes, nominal ECTS)
def buckets_def(key_code):
    return [
        ("Compulsory Computer Science", ["I.1.a", "I.1.c"], 87),
        ("Mathematics", ["I.1.b"], 18),
        ("Specialization", [key_code or "I.2.a"], 42),
        ("Key Competencies", ["I.2.b"], 9),
        ("Bachelor's Thesis", ["I.3"], 12),
    ]

# Backend data access (read) — direct DB / appback helpers, no API round-trip
def _df(query, db):
    conn = sqlite3.connect(db)
    try:
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()

def selected_df():
    try:
        conn = sqlite3.connect(DB_SELECTION)
        appback.ensure_column(conn, "module_selection", "attempt", "INTEGER DEFAULT 1")
        appback.ensure_column(conn, "module_selection", "retry_semester", "INTEGER")
        conn.commit(); conn.close()
        df = _df("SELECT * FROM module_selection", DB_SELECTION)
    except Exception:
        return pd.DataFrame()
    if "assigned_semester" not in df.columns:
        df["assigned_semester"] = 0
    if "attempt" not in df.columns:
        df["attempt"] = 1
    if "retry_semester" not in df.columns:
        df["retry_semester"] = None
    return df

def all_modules_df():
    try:
        return _df("SELECT * FROM modules", DB_MODULES)
    except Exception:
        return pd.DataFrame()

def plan_exists(df):
    return (not df.empty) and ("assigned_semester" in df.columns) and \
           (pd.to_numeric(df["assigned_semester"], errors="coerce").fillna(0) > 0).any()

def _tag(mid):
    parts = str(mid).split(".")
    return (parts[1][:3] if len(parts) > 1 else str(mid)[:3]).upper()

def _i(x):
    try:
        return int(x)
    except Exception:
        return 0

def _clean_grade(val):
    """Some pre-existing rows in module_selection.db have the literal string
    "nan" stored in `note` (a data artifact from an earlier import/write, not
    a real value) instead of a real NULL. Treat that - and None/empty - as
    "no grade recorded", everywhere `note` is read, so it never leaks into
    the UI as the text "nan" or gets misread as a truthy grade."""
    if val is None:
        return ""
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    return s

def _grade_str(x):
    """German university grades are always truncated to one decimal, never
    rounded (e.g. 1.6666... -> 1,6, not 1,7 - per standard Pruefungsordnung
    rules: only the first decimal is kept, everything after is cut off).
    The tiny epsilon guards against float imprecision (e.g. 1.7 sometimes
    being represented as 1.6999999999) wrongly truncating down a full step."""
    truncated = math.floor(x * 10 + 1e-9) / 10
    return f"{truncated:.1f}".replace(".", ",")

def _attempt_label(n):
    """'Zweitversuch' / 'Drittversuch' / '4. Versuch' ... for n >= 2, empty
    for a first attempt."""
    if n <= 1:
        return ""
    words = {2: "Zweitversuch", 3: "Drittversuch"}
    return words.get(n, f"{n}. Versuch")

def config():
    try:
        appback.init_selection_db()
        return {
            "min_credits": _i(appback.get_setting("min_credits", int)),
            "max_credits": _i(appback.get_setting("max_credits", int)),
            "semester_nr": _i(appback.get_setting("semester_nr", int)),
            "sem_start": _i(appback.get_setting("sem_start", int)),
            "total_credits": _i(appback.get_setting("total_credits", int)) or 180,
            "current_semester": _i(appback.get_setting("current_semester", int)) or 1,
        }
    except Exception:
        return {"min_credits": 25, "max_credits": 35, "semester_nr": 6, "sem_start": 0,
                "total_credits": 180, "current_semester": 1}

def _area_codes(raw):
    return appback.safe_list(raw)

def _strip_roman(name):
    return re.sub(r"\s+(I{1,3}|IV|V)$", "", (name or "").strip()).strip().lower()

def _math_ids_for_package(name):
    """Return exactly the module ids of a math package.

    The math areas' codes are mislabelled in the data, but each math area's
    `description` lists its two module ids. We pick the description whose modules'
    names actually match the chosen package name — so the package name is the
    source of truth, not the (swapped) codes."""
    pkg = (name or "").lower()
    conn = sqlite3.connect(DB_MODULES)
    try:
        best, best_score = [], 0
        for code in appback.math_modules.values():
            row = conn.execute("SELECT description FROM requirements WHERE study_area=?", (code,)).fetchone()
            if not row:
                continue
            ids = re.findall(r"B\.[A-Za-z-]+\.\d+", row[0] or "")
            valid, score = [], 0
            for mid in ids:
                m = conn.execute("SELECT name FROM modules WHERE id=?", (mid,)).fetchone()
                if not m:
                    continue
                valid.append(mid)
                base = _strip_roman(m[0])
                if base and (base in pkg or pkg in base):
                    score += 1
            if score > best_score:
                best_score, best = score, valid
        return best
    finally:
        conn.close()

def bucket_of(codes, key_code):
    for name, prefixes, _ in buckets_def(key_code):
        for c in codes:
            if any(c == p or c.startswith(p) for p in prefixes):
                return name
    return None

# Context builders
def home_context():
    df = selected_df()
    cfg = config()
    if not plan_exists(df):
        return {"has_plan": False}
    df = df.copy()
    df["assigned_semester"] = pd.to_numeric(df["assigned_semester"], errors="coerce").fillna(0).astype(int)
    df["credits"] = pd.to_numeric(df["credits"], errors="coerce").fillna(0)
    
    df["semester"] = pd.to_numeric(df["semester"], errors="coerce")
    completed = df[df["semester"].notna()]
    total_credits = int(completed["credits"].sum())

    
    grades = pd.to_numeric(completed["note"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    grade_denom = completed["credits"][grades.notna()].sum()
    wgrade = float((grades * completed["credits"])[grades.notna()].sum() / grade_denom) if grade_denom > 0 else None

    sems = sorted(int(s) for s in df["assigned_semester"].unique() if s > 0)
    cur = cfg["current_semester"]
    cur_df = df[df["assigned_semester"] == cur]
    cur_is_winter = (cur % 2 == 1) if cfg["sem_start"] == 0 else (cur % 2 == 0)
    mods = [{"tag": _tag(r["id"]), "name": r["name"], "id": r["id"],
             "exam": r.get("examination_type") or "—",
             "difficulty": (str(r.get("difficulty") or "—")).capitalize(),
             "cr": _i(r["credits"]), "done": bool(pd.notna(r["semester"])),
             "grade": _clean_grade(r.get("note")) if pd.notna(r["semester"]) else ""} for _, r in cur_df.iterrows()]
    return {
        "has_plan": True,
        "stats": {
            "current_sem": cur, "total_sem": (max(sems) if sems else cfg["semester_nr"]),
            "credits_done": total_credits, "credits_total": cfg["total_credits"],
            "credits_pct": round(total_credits / cfg["total_credits"] * 100) if cfg["total_credits"] else 0,
            "avg_grade": (_grade_str(wgrade) if wgrade is not None else "–"), "modules": len(df),
        },
        "semester": {
            "number": cur, "term": ("Winter term" if cur_is_winter else "Summer term"),
            "credits": int(cur_df["credits"].sum()), "modules": mods,
        },
    }

def _plan_warnings():
    """Compromises assignin_semesters() had to make while building the last
    generated plan (a semester ended up over max_credits because no room
    could be freed, or an AR ordering violation couldn't be resolved) -
    previously these failed completely silently. Re-written fresh on every
    plan generation, so this is always about the CURRENT plan, not stale."""
    try:
        raw = appback.get_setting("plan_warnings", str)
        parsed = json.loads(raw) if raw else []
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []

def overview_context():
    """Full plan across every semester (not just the 'current' one) - task #20.
    home.html keeps showing only the current semester; this feeds a separate
    /overview page that lists all of them plus anything still unassigned."""
    df = selected_df()
    cfg = config()
    if not plan_exists(df):
        return {"has_plan": False}
    df = df.copy()
    df["assigned_semester"] = pd.to_numeric(df["assigned_semester"], errors="coerce").fillna(0).astype(int)
    df["credits"] = pd.to_numeric(df["credits"], errors="coerce").fillna(0)
    df["retry_semester"] = pd.to_numeric(df["retry_semester"], errors="coerce")

    retry_max = df["retry_semester"].max(skipna=True)
    retry_max = int(retry_max) if pd.notna(retry_max) else 0
    total_sem = max(int(df["assigned_semester"].max()), retry_max, cfg["semester_nr"])

    def mod_row(r, view):
        # A module counts as "passed" once `semester` is set (mark_completed
        # only does that for grades <= 4,0); a stored `note` with no
        # `semester` means a failed attempt is on record. Neither -> not
        # graded yet.
        done = pd.notna(r.get("semester"))
        grade = _clean_grade(r.get("note"))
        status = "passed" if (done and grade) else ("failed" if grade else "")
        attempt = _i(r.get("attempt")) or 1
        retry_sem = r.get("retry_semester")
        return {"tag": _tag(r["id"]), "name": r["name"], "id": r["id"],
                "exam": r.get("examination_type") or "—",
                "difficulty": (str(r.get("difficulty") or "—")).capitalize(),
                "cr": _i(r["credits"]), "done": bool(done), "status": status,
                "grade": grade, "view": view,
                "attempt": attempt, "attempt_label": _attempt_label(attempt),
                "retry_semester": (_i(retry_sem) if pd.notna(retry_sem) else None)}

    semesters = []
    for s in range(1, total_sem + 1):
        # A failed module keeps its place in the semester it was actually
        # attempted in (shown red, read-only, credits NOT counted there -
        # it wasn't earned) AND additionally shows up again in the semester
        # the retake becomes possible in (shown with a "Zweitversuch" badge,
        # editable, credits counted there instead - that's where they'll
        # actually be earned).
        sdf = df[df["assigned_semester"] == s].sort_values("id")
        retry_df = df[df["retry_semester"] == s].sort_values("id")
        is_winter = (s % 2 == 1) if cfg["sem_start"] == 0 else (s % 2 == 0)

        rows = []
        credits = 0
        for _, r in sdf.iterrows():
            # Always editable here, even after a failing grade - this is the
            # ONE place a module's grade can be entered/corrected. Making the
            # original semester read-only once failed (as an earlier version
            # did) meant there was no way left to fix a typo'd grade at all.
            row = mod_row(r, "normal")
            rows.append(row)
            if row["status"] != "failed":
                credits += row["cr"]
        for _, r in retry_df.iterrows():
            # Read-only preview of the pending retake in the future semester
            # it becomes possible - the actual grade entry still happens on
            # the "normal" row above, not here (avoids two editable boxes for
            # the same module fighting over which one the server reads).
            row = mod_row(r, "retry_preview")
            rows.append(row)
            credits += row["cr"]

        semesters.append({
            "number": s, "term": ("Winter term" if is_winter else "Summer term"),
            "credits": credits, "modules": rows,
        })

    unassigned_df = df[df["assigned_semester"] <= 0].sort_values("id")
    total_credits = int(df["credits"].sum())
    return {
        "has_plan": True,
        "semesters": semesters,
        "unassigned": [mod_row(r, "normal") for _, r in unassigned_df.iterrows()],
        "total_credits": total_credits,
        "total_target": cfg["total_credits"],
        "total_sem": total_sem,
        "plan_warnings": _plan_warnings(),
    }

def _stats_per_semester(d, sems):
    """Per-semester series for the interactive charts: ECTS, contact/self-study
    hours and average grade (grade only counts modules that actually have a
    clean, passed grade in that semester - _clean_grade() again doing the
    'nan'-string filtering). Kept as its own small function instead of being
    folded into stats_context() - the old calculate_statistics() was one 1000+
    line function that mixed data prep AND chart styling; splitting data prep
    into small, single-purpose functions and leaving all styling/rendering to
    JS+CSS is the actual fix for "the statistics function is too big"."""
    out = []
    for s in sems:
        sd = d[d["assigned_semester"] == s]
        at = pd.to_numeric(sd["attendance_time"], errors="coerce").fillna(0).sum()
        ss = pd.to_numeric(sd["selfstudy_time"], errors="coerce").fillna(0).sum()
        grades = pd.to_numeric(sd["avg_grade"], errors="coerce").dropna()
        out.append({
            "label": f"Sem {s}",
            "credits": int(sd["credits"].sum()),
            "attendance": round(float(at)),
            "selfstudy": round(float(ss)),
            "avg_grade": round(float(grades.mean()), 2) if len(grades) else None,
        })
    return out

def _stats_exam_area_per_sem(d, sems, key_code):
    """Per-semester exam-type and study-area breakdowns (module counts) - the
    same breakdown the old calculate_statistics() built via pd.crosstab for
    its stacked bar charts (fig4/5/7/8), reusing the app's one real
    bucket_of()/_area_codes() grouping instead of that function's separate,
    hardcoded prefix rules."""
    all_et, all_areas = [], []
    per_sem_et, per_sem_area = [], []
    for s in sems:
        sd = d[d["assigned_semester"] == s]
        et_counts = sd["examination_type"].fillna("—").value_counts().to_dict()
        per_sem_et.append(et_counts)
        for et in et_counts:
            if et not in all_et:
                all_et.append(et)
        area_counts = {}
        for _, r in sd.iterrows():
            b = bucket_of(_area_codes(r.get("study_area")), key_code) or "Other"
            area_counts[b] = area_counts.get(b, 0) + 1
        per_sem_area.append(area_counts)
        for b in area_counts:
            if b not in all_areas:
                all_areas.append(b)
    return {
        "exam_labels": all_et,
        "exam_series": [[cnts.get(et, 0) for cnts in per_sem_et] for et in all_et],
        "area_labels": all_areas,
        "area_series": [[cnts.get(b, 0) for cnts in per_sem_area] for b in all_areas],
    }

def _stats_difficulty_heatmap(d, sems):
    """Module-count matrix (difficulty x semester) - fig9 in the old function,
    a Plotly Heatmap there; here just three small integer lists so the
    template can render it as a plain colored grid (no extra chart library
    needed for a 3xN table)."""
    diffs = ["easy", "medium", "hard"]
    dl = d["difficulty"].astype(str).str.strip().str.lower()
    matrix = [[int(((dl == diff) & (d["assigned_semester"] == s)).sum()) for s in sems] for diff in diffs]
    flat_max = max([v for row in matrix for v in row] + [1])
    return {"diff_labels": ["Easy", "Medium", "Hard"], "matrix": matrix, "max": flat_max}

def _stats_scatter(d):
    """Weekly workload (WLH = credits*30/15, same formula as the old
    calculate_statistics()) vs. failure rate, one point per module - fig11."""
    pts = []
    for _, r in d.iterrows():
        diff = str(r.get("difficulty") or "").strip().lower()
        if diff not in ("easy", "medium", "hard"):
            diff = "medium"
        fr = pd.to_numeric(r.get("failure_rates"), errors="coerce")
        pts.append({
            "x": round(float(r["credits"]) * 2, 1),
            "y": round(float(fr) * 100, 1) if pd.notna(fr) else 0,
            "diff": diff,
            "name": str(r.get("name") or r.get("id")),
        })
    return pts

def _stats_network(d, sems, key_code):
    """Module dependency network (fig10 in the old function): modules placed
    on a semester x study-area grid, with an edge drawn from every RPK
    prerequisite to the module that lists it (only if the prerequisite's own
    semester is not later - mirrors the old edge filter). Positions are
    precomputed here in plain numbers so the template can render it as a
    theme-colored inline SVG - Chart.js has no network/graph chart type, and
    this avoids pulling in a second charting library just for one graph."""
    if not sems:
        return None
    bands = ["Compulsory Computer Science", "Mathematics", "Specialization", "Key Competencies", "Bachelor's Thesis"]
    BAND_W, BAND_GAP, ROW_H, PAD_TOP, PAD_L = 130, 26, 62, 30, 16

    id_band, id_sem, id_diff, id_name, id_rpk = {}, {}, {}, {}, {}
    for _, r in d.iterrows():
        mid = r["id"]
        b = bucket_of(_area_codes(r.get("study_area")), key_code)
        id_band[mid] = b if b in bands else "Bachelor's Thesis"
        id_sem[mid] = int(r["assigned_semester"])
        diff = str(r.get("difficulty") or "").strip().lower()
        id_diff[mid] = diff if diff in ("easy", "medium", "hard") else "medium"
        id_name[mid] = str(r.get("name") or mid)
        id_rpk[mid] = appback.safe_list(r.get("RPK"))

    pos = {}
    for s in sems:
        for bi, band in enumerate(bands):
            ids_here = [mid for mid in id_band if id_band[mid] == band and id_sem[mid] == s]
            n = len(ids_here)
            band_start = bi * (BAND_W + BAND_GAP)
            for i, mid in enumerate(ids_here):
                x = band_start + (BAND_W / 2 if n == 1 else i * (BAND_W / (n - 1)))
                y = PAD_TOP + (s - 0.5) * ROW_H
                pos[mid] = (round(x + PAD_L, 1), round(y, 1))

    edges = []
    for mid, rpks in id_rpk.items():
        if mid not in pos:
            continue
        for rp in rpks:
            if rp in pos and id_sem.get(rp, 9999) <= id_sem[mid]:
                x1, y1 = pos[rp]
                x2, y2 = pos[mid]
                edges.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    nodes = [{"id": mid, "name": id_name[mid], "x": x, "y": y, "diff": id_diff[mid]}
              for mid, (x, y) in pos.items()]
    band_defs = [{"label": b, "x0": bi * (BAND_W + BAND_GAP) + PAD_L - BAND_GAP / 2,
                  "x1": bi * (BAND_W + BAND_GAP) + PAD_L + BAND_W + BAND_GAP / 2}
                 for bi, b in enumerate(bands)]
    width = len(bands) * (BAND_W + BAND_GAP) - BAND_GAP + 2 * PAD_L
    height = PAD_TOP + max(sems) * ROW_H + 12
    return {
        "bands": band_defs, "nodes": nodes, "edges": edges,
        "width": round(width, 1), "height": round(height, 1),
        "sem_ticks": [{"y": round(PAD_TOP + (s - 0.5) * ROW_H, 1), "label": f"Sem {s}"} for s in sems],
    }

def stats_context():
    df = selected_df()
    if df.empty:
        return None
    d = df.copy()
    d["assigned_semester"] = pd.to_numeric(d["assigned_semester"], errors="coerce").fillna(0).astype(int)
    d["credits"] = pd.to_numeric(d["credits"], errors="coerce").fillna(0)
    g = pd.to_numeric(d["avg_grade"], errors="coerce")
    fr = pd.to_numeric(d["failure_rates"], errors="coerce") * 100
    diffmap = {"easy": 0, "medium": 1, "hard": 2}
    dnum = d["difficulty"].map(lambda x: diffmap.get(str(x).strip().lower(), 1))

    sems = sorted(int(s) for s in d["assigned_semester"].unique() if s > 0)
    maxc = max([float(d[d["assigned_semester"] == s]["credits"].sum()) for s in sems] + [1.0])
    cps = [{"label": f"Sem {s}", "val": int(d[d["assigned_semester"] == s]["credits"].sum()),
            "pct": round(float(d[d["assigned_semester"] == s]["credits"].sum()) / maxc * 100)} for s in sems]

    et = d["examination_type"].fillna("—").value_counts(normalize=True) * 100
    exam = [{"label": str(k), "pct": round(float(v))} for k, v in et.items()][:6]

    # study area distribution by credits (uses current key area code if set)
    key_code = appback.key_area[1] if appback.key_area else None
    cat_credits = {}
    for _, r in d.iterrows():
        b = bucket_of(_area_codes(r.get("study_area")), key_code) or "Other"
        cat_credits[b] = cat_credits.get(b, 0) + float(r["credits"])
    tot_cat = sum(cat_credits.values()) or 1
    short = {"Compulsory Computer Science": "Computer Sci.", "Key Competencies": "Key comp.",
             "Bachelor's Thesis": "Thesis", "Specialization": "Specialization", "Mathematics": "Mathematics"}
    areas_dist = [{"label": short.get(k, k), "pct": round(v / tot_cat * 100)}
                  for k, v in sorted(cat_credits.items(), key=lambda x: -x[1])][:6]

    at = pd.to_numeric(d["attendance_time"], errors="coerce").fillna(0).sum()
    ss = pd.to_numeric(d["selfstudy_time"], errors="coerce").fillna(0).sum()
    tot = (at + ss) or 1
    per_sem = _stats_per_semester(d, sems)
    exam_area_sem = _stats_exam_area_per_sem(d, sems, key_code)
    heatmap = _stats_difficulty_heatmap(d, sems)
    scatter_pts = _stats_scatter(d)
    network = _stats_network(d, sems, key_code)
    return {
        "credits_total": int(d["credits"].sum()), "modules": len(d),
        "avg_grade": (f"{g.mean():.1f}" if g.notna().any() else "–"),
        "median_grade": (f"{g.median():.1f}" if g.notna().any() else "–"),
        "fail_mean": (f"{fr.mean():.1f}" if fr.notna().any() else "–"),
        "fail_median": (f"{fr.median():.1f}" if fr.notna().any() else "–"),
        "difficulty": f"{dnum.mean():.1f}",
        "credits_per_sem": cps, "exam_types": exam, "areas_dist": areas_dist,
        "contact_pct": round(float(at) / tot * 100), "self_pct": round(float(ss) / tot * 100),
        "ratio": (f"{at/ss:.1f}" if ss else "–"), "avg_ects": f"{d['credits'].mean():.1f}",
        # raw series for the interactive Chart.js charts (chart colors/rendering
        # live entirely in stats.js, which reads the active theme's CSS
        # variables this dict only carries numbers/labels, no presentation)
        "chart_data": {
            "sem_labels": [r["label"] for r in per_sem],
            "credits_series": [r["credits"] for r in per_sem],
            "attendance_series": [r["attendance"] for r in per_sem],
            "selfstudy_series": [r["selfstudy"] for r in per_sem],
            "grade_series": [r["avg_grade"] for r in per_sem],
            "exam_labels": [r["label"] for r in exam],
            "exam_pcts": [r["pct"] for r in exam],
            "areas_labels": [r["label"] for r in areas_dist],
            "areas_pcts": [r["pct"] for r in areas_dist],
            "exam_per_sem_labels": exam_area_sem["exam_labels"],
            "exam_per_sem_series": exam_area_sem["exam_series"],
            "area_per_sem_labels": exam_area_sem["area_labels"],
            "area_per_sem_series": exam_area_sem["area_series"],
            "diff_labels": heatmap["diff_labels"],
            "diff_matrix": heatmap["matrix"],
            "diff_max": heatmap["max"],
            "scatter_points": scatter_pts,
        },
        "network": network,
    }

def build_area_tree(selected_ids, sel_credit, key_code, math_code):
    """Build the study-area hierarchy from the `requirements` table, attach every
    module to the deepest study-area code(s) it belongs to (a module can appear in
    several areas), keep only the chosen specialization / math track, and compute
    selected credits + fulfilment per area."""
    conn = sqlite3.connect(DB_MODULES)
    try:
        area_rows = conn.execute(
            "SELECT study_area, study_area_name, requirement_type, min_value, description "
            "FROM requirements ORDER BY study_area").fetchall()
        mods = pd.read_sql_query(
            "SELECT id, name, credits, frequency, study_area, AR, study_restriction FROM modules", conn)
    except Exception:
        return [], {"name": "", "sel": 0, "req": 0, "pct": 0, "done": False}
    finally:
        conn.close()

    seen, ordered = set(), []
    for sa, sa_name, rt, mv, desc in area_rows:
        if sa in seen:
            continue
        seen.add(sa)
        ordered.append({"code": sa, "name": sa_name, "type": rt, "min": mv, "desc": desc})
    codes = set(seen)
    nodes = {a["code"]: {"code": a["code"], "name": a["name"], "type": a["type"], "min": a["min"],
                         "desc": a["desc"], "children": [], "modules": []} for a in ordered}

    def parent_of(code):
        parts = code.split(".")
        for i in range(len(parts) - 1, 0, -1):
            cand = ".".join(parts[:i])
            if cand in codes:
                return cand
        return None

    def deepest(ac):
        if ac in codes:
            return ac
        parts = ac.split(".")
        for i in range(len(parts) - 1, 0, -1):
            cand = ".".join(parts[:i])
            if cand in codes:
                return cand
        return None

    roots = []
    for a in sorted(ordered, key=lambda x: x["code"].count(".")):
        p = parent_of(a["code"])
        (nodes[p]["children"].append(nodes[a["code"]]) if p else roots.append(nodes[a["code"]]))

    mod_by_id = {str(r["id"]): r for _, r in mods.iterrows()}

    def _prereqs_for(mid):
        """{'requires': [...], 'excludes': [...]} for a module, so the UI can
        show e.g. 'Requires: Datenbanken' (green once selected) and
        'Cannot combine with: X' (red if X IS selected - study_restriction is
        a mutual-exclusion list, the OPPOSITE of an admission requirement -
        e.g. a 'Nebenfach' module and its regular-program equivalent)."""
        r = mod_by_id.get(str(mid))
        if r is None:
            return {"requires": [], "excludes": []}
        try:
            ar = ast.literal_eval(r.get("AR")) if r.get("AR") else {}
        except Exception:
            ar = {}
        try:
            restr = ast.literal_eval(r.get("study_restriction")) if r.get("study_restriction") else []
        except Exception:
            restr = []

        def label(pid, good):
            pr = mod_by_id.get(str(pid))
            return {"id": pid, "name": pr["name"] if pr is not None else pid, "good": good}

        requires = [label(pid, str(pid) in selected_ids) for pid in (ar.get("all") or [])]
        requires += [label(pid, str(pid) in selected_ids) for pid in (ar.get("any") or [])]
        excludes = [label(pid, str(pid) not in selected_ids) for pid in restr]
        return {"requires": requires, "excludes": excludes}

    pairs = set()
    for _, r in mods.iterrows():
        for ac in _area_codes(r.get("study_area")):
            t = deepest(ac)
            if not t or (t, r["id"]) in pairs:
                continue
            pairs.add((t, r["id"]))
            pr = _prereqs_for(r["id"])
            nodes[t]["modules"].append({
                "id": r["id"], "name": r["name"], "cr": _i(r["credits"]),
                "freq": r.get("frequency") or "", "on": str(r["id"]) in selected_ids,
                "requires": pr["requires"], "excludes": pr["excludes"]})


    name_by_code = {c: n for n, c in appback.math_modules.items()}
    math_ids_by_code = {
        code: set(_math_ids_for_package(name_by_code.get(code)))
        for code in appback.math_modules.values()
    }
    all_math_ids = set().union(*math_ids_by_code.values()) if math_ids_by_code else set()

    for node in nodes.values():
        if node["modules"]:
            node["modules"] = [m for m in node["modules"] if m["id"] not in all_math_ids]

    for code, ids in math_ids_by_code.items():
        node = nodes.get(code)
        if not node:
            continue
        ml = []
        for mid in ids:
            r = mod_by_id.get(mid)
            if r is not None:
                pr = _prereqs_for(mid)
                ml.append({"id": mid, "name": r["name"], "cr": _i(r["credits"]),
                           "freq": r.get("frequency") or "", "on": mid in selected_ids,
                           "requires": pr["requires"], "excludes": pr["excludes"]})
        node["modules"] = ml

    for n in nodes.values():
        n["modules"].sort(key=lambda m: m["id"])

    
    root_req = int(roots[0]["min"]) if len(roots) == 1 and roots[0].get("min") else 0
    root_sel = int(round(sum(v for k, v in sel_credit.items() if k in selected_ids)))
    degree_progress = {
        "name": roots[0]["name"] if len(roots) == 1 else "Degree",
        "sel": root_sel, "req": root_req,
        "pct": min(100, round(root_sel / root_req * 100)) if root_req else 0,
        "done": root_req > 0 and root_sel >= root_req,
    }

    # collapse the single synthetic root "I" -> show its children at top level
    top = roots[0]["children"] if len(roots) == 1 and roots[0]["children"] else roots

    spec_set = set(appback.key_areas.values())
    math_set = set(appback.math_modules.values())

    def prune(node):
        kept = []
        for c in node["children"]:
            if key_code and c["code"] in spec_set and c["code"] != key_code:
                continue
            if math_code and c["code"] in math_set and c["code"] != math_code:
                continue
            prune(c)
            kept.append(c)
        node["children"] = kept

    for n in top:
        prune(n)

    # compute selected credits + fulfilment per area (only the chosen
    # specialization / math track remain in the tree after pruning above)
    def enrich(node):
        for c in node["children"]:
            enrich(c)
        ids = {m["id"] for m in node["modules"]}
        for c in node["children"]:
            ids |= c["_ids"]
        node["_ids"] = ids
        sel = sum(sel_credit.get(i, 0) for i in ids if i in selected_ids)
        node["sel"] = int(round(sel))
        node["req"] = int(node["min"]) if node["min"] else 0
        node["pct"] = min(100, round(sel / node["req"] * 100)) if node["req"] else 0
        node["done"] = node["req"] > 0 and sel >= node["req"]

    for n in top:
        enrich(n)
    return top, degree_progress

def _tree_module_ids(nodes):
    """Flatten build_area_tree()'s output into the set of every module id that
    appears as a checkbox somewhere in it (any specialization/math track)."""
    ids = set()
    for n in nodes:
        for m in n.get("modules", []):
            ids.add(str(m["id"]))
        ids |= _tree_module_ids(n.get("children", []))
    return ids


def plan_context(blocked_entries=None):
    """blocked_entries: list of {"code", "label"} dicts from appback.check_all(),
    or None. `code` (only set for study-area failures) is used to red-highlight
    the matching accordion node; `label` is the human-readable banner text -
    also covers AR / study-restriction failures, which have no code."""
    cur_key = appback.key_area[0] if appback.key_area else None
    cur_math = appback.math_module[0] if appback.math_module else None

    key_areas = [{"name": k, "sub": v, "sel": (k == cur_key)} for k, v in appback.key_areas.items()]
    math_tracks = [{"name": k, "sub": v, "sel": (k == cur_math)} for k, v in appback.math_modules.items()]

    sel = selected_df()
    sel_ids = set(sel["id"].astype(str)) if not sel.empty else set()
    sel_credit = {}
    if not sel.empty:
        for _, r in sel.iterrows():
            sel_credit[str(r["id"])] = _i(r["credits"])
    key_code = appback.key_area[1] if appback.key_area else None
    math_code = appback.math_module[1] if appback.math_module else None
    area_tree, degree_progress = build_area_tree(sel_ids, sel_credit, key_code, math_code)

    blocked_entries = blocked_entries or []
    return {"key_areas": key_areas, "math_tracks": math_tracks,
            "area_tree": area_tree, "config": config(), "degree_progress": degree_progress,
            "spec_codes": list(appback.key_areas.values()),
            "math_codes": list(appback.math_modules.values()),
            "blocked_areas": [e["code"] for e in blocked_entries if e.get("code")],
            "blocked_messages": [e["label"] for e in blocked_entries]}

USER = {"first_name": "Student", "name": "Student", "initials": "ST",
        "role": "Student", "program": "B.Sc. Applied CS", "specialization": "—"}

def _user_ctx():
    """USER with the display name pulled from the saved setting (editable on
    the profile page); initials and first name are derived from it."""
    u = dict(USER)
    name = appback.get_setting("user_name")
    if name:
        parts = name.split()
        u["name"] = name
        u["first_name"] = parts[0] if parts else name
        u["initials"] = ("".join(p[0] for p in parts[:2]).upper()) if parts else name[:2].upper()
    return u

def profile_context():
    u = _user_ctx()
    if appback.key_area:
        u["specialization"] = appback.key_area[0]
    return {"user": u, "themes": THEMES, "config": config()}

# Routes (UI)
@app.route("/")
def index():
    return redirect(url_for("home"))

@app.route("/home")
def home():
    ctx = home_context()
    return render_template("home.html", title="Home", active="home", user=_user_ctx(), **ctx)

@app.route("/overview")
def overview():
    ctx = overview_context()
    return render_template("overview.html", title="Full plan", active="overview", **ctx)

@app.route("/mark_completed", methods=["POST"])
def mark_completed():
    """Shared handler for the grade field on Full plan. `rows` lists exactly
    which module ids were rendered on the submitting page - only those get
    touched, so submitting one page never wipes out completion data for
    modules on other pages that simply weren't rendered there."""
    row_ids = request.form.getlist("rows")
    conn = sqlite3.connect(DB_SELECTION)
    appback.ensure_column(conn, "module_selection", "attempt", "INTEGER DEFAULT 1")
    appback.ensure_column(conn, "module_selection", "retry_semester", "INTEGER")
    for mid in row_ids:
        grade_raw = (request.form.get(f"grade_{mid}") or "").strip()

        if not grade_raw:
            conn.execute("UPDATE module_selection SET semester = NULL, note = NULL, retry_semester = NULL WHERE id = ?", (mid,))
            continue

        row = conn.execute(
            "SELECT assigned_semester, frequency, attempt, note FROM module_selection WHERE id=?", (mid,)
        ).fetchone()
        assigned = int(row[0]) if row and row[0] else 0
        freq = (row[1] or "").strip().upper() if row else ""
        attempt = int(row[2]) if row and row[2] else 1
        prev_grade = _clean_grade(row[3]) if row else ""
        base_sem = assigned if assigned > 0 else (_i(appback.get_setting("current_semester", int)) or 1)

        try:
            grade = float(grade_raw.replace(",", "."))
        except ValueError:
            grade = None

        if grade is not None and grade > 4.0:
            # failed: keep the grade on record but leave semester NULL (not
            # completed, not counted in the average). The module stays in
            # its current assigned_semester only a retry hint is recorded.
            # The page always resubmits every row's current value, so if the
            # grade is unchanged from what's already stored this is just a
            # re-save (e.g. the user edited a different module) only bump
            # the attempt counter when a NEW failing grade is actually being
            # entered, otherwise every unrelated save would count as another
            # failed attempt.
            if grade_raw == prev_grade:
                conn.execute("UPDATE module_selection SET semester = NULL WHERE id = ?", (mid,))
            else:
                offset = 1 if freq in ("E", "N") else 2
                retry_sem = base_sem + offset
                conn.execute(
                    "UPDATE module_selection SET semester = NULL, note = ?, attempt = ?, retry_semester = ? "
                    "WHERE id = ?",
                    (grade_raw, attempt + 1, retry_sem, mid)
                )
        else:
            conn.execute("UPDATE module_selection SET semester = ?, note = ?, retry_semester = NULL WHERE id = ?",
                         (base_sem, grade_raw, mid))
    conn.commit(); conn.close()
    dest = request.form.get("return_to") or "home"
    if dest not in ("home", "overview"):
        dest = "home"
    return redirect(url_for(dest))

@app.route("/move_module", methods=["POST"])
def move_module():
    """AJAX endpoint (called from overview.html) for manually dragging a
    module to a different semester. Delegates all the actual validation -
    semester range, frequency fit (a W-only module can't land in a summer
    semester), max_credits capacity, and AR prerequisite ordering - to
    appback.move_module_to_semester(), which raises ValueError with a
    German, user-facing message on any violation. We just translate that
    into a JSON error the frontend JS can show inline instead of crashing."""
    module_id = (request.form.get("module_id") or "").strip()
    try:
        target_sem = int(request.form.get("target_semester"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid semester."}), 400
    if not module_id:
        return jsonify({"ok": False, "error": "Missing module id."}), 400
    try:
        appback.move_module_to_semester(module_id, target_sem)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})

@app.route("/plan", methods=["GET", "POST"])
def plan():
    if request.method == "POST":
        blocked = _apply_plan_form(request.form)
        if blocked:
            return render_template("plan.html", title="Edit plan", active="plan",
                                    **plan_context(blocked_entries=blocked))
        return redirect(url_for("home"))
    return render_template("plan.html", title="Edit plan", active="plan", **plan_context())

@app.route("/statistics")
def statistics():
    s = stats_context()
    return render_template("statistics.html", title="Statistics", active="stats", s=s)

@app.route("/help")
def help_page():
    return render_template("help.html", title="Help", active="help", faqs=FAQS)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        name = request.form.get("display_name")
        if name is not None and name.strip():
            appback.set_setting("user_name", name.strip())
        val = request.form.get("current_semester")
        if val not in (None, ""):
            try:
                appback.set_setting("current_semester", int(val))
            except Exception:
                pass
        return redirect(url_for("profile"))
    return render_template("profile.html", title="Profile", active="profile", **profile_context())

@app.route("/reset_plan", methods=["POST"])
def reset_plan():
    """Danger zone: wipe everything and start from scratch, like a fresh
    install. Removes the entire module selection, the generated plan and all
    grades/completion, and clears the chosen specialization + math track. The
    compulsory modules are re-seeded afterwards so the empty selection still
    has the mandatory baseline, exactly like the first-run database build."""
    from data.data_processing import database as _db
    conn = sqlite3.connect(DB_SELECTION)
    conn.execute("DELETE FROM module_selection")
    conn.execute(
        "DELETE FROM settings WHERE key IN ('selected_key_area_key', 'selected_math_key')"
    )
    conn.commit()
    conn.close()
    # re-seed the compulsory modules (mirrors the first-run seed in database.py)
    try:
        _db.add_modules(_db.COMPULSORY_MODULES)
    except Exception as e:
        print("reset reseed error:", e)
    # drop the in-memory specialization / math selection too
    appback.key_area = None
    appback.math_module = None
    try:
        appback.update_requirements_fulfilled()
    except Exception as e:
        print("reset requirements error:", e)
    return redirect(url_for("profile"))

# Plan form -> backend (write) using appback's own helpers
def _mandatory_ids(code):
    """All module ids that are mandatory ('Every Module') under a study-area code."""
    conn = sqlite3.connect(DB_MODULES)
    try:
        areas = [r[0] for r in conn.execute(
            "SELECT study_area FROM requirements "
            "WHERE requirement_type='ALL_MANDATORY' AND (study_area=? OR study_area LIKE ?)",
            (code, code + ".%"))]
        rows = conn.execute("SELECT id, study_area FROM modules").fetchall()
    finally:
        conn.close()
    ids = []
    for mid, sa in rows:
        codes = appback.safe_list(sa)
        if any(x == a or x.startswith(a + ".") for a in areas for x in codes):
            ids.append(mid)
    return ids

def _add_mandatory(code):
    """Auto-add the mandatory modules of a key area / math track to the selection."""
    ids = _mandatory_ids(code)
    if not ids:
        return
    sel = selected_df()
    have = set(sel["id"].astype(str)) if not sel.empty else set()
    new = [i for i in ids if str(i) not in have]
    if new:
        appback.add_modules(new)

def _ids_under_area(code):
    """Every module id tagged (directly or under a descendant area) with `code` -
    mandatory or elective, unlike _mandatory_ids() which only covers ALL_MANDATORY."""
    conn = sqlite3.connect(DB_MODULES)
    try:
        rows = conn.execute("SELECT id, study_area FROM modules").fetchall()
    finally:
        conn.close()
    ids = []
    for mid, sa in rows:
        codes = appback.safe_list(sa)
        if any(x == code or x.startswith(code + ".") for x in codes):
            ids.append(mid)
    return ids

def _drop_other_branch_modules(all_branch_codes, keep_code):
    """Remove selected modules that belong ONLY to other branches of the same
    family (other specializations / other math tracks) when switching to
    `keep_code`. A module tagged under both the old and the new branch (e.g.
    a legitimate cross-specialization pick) is left alone.

    _select_math() already does the equivalent cleanup inline; specialization
    switches (_select_key_area()) didn't, which let modules from a previously
    chosen specialization linger in module_selection forever - inflating
    every ancestor area's credit total (visible e.g. under 'Studienschwerpunkte'
    showing far more ECTS than the selected specialization actually has)."""
    keep_ids = set(_ids_under_area(keep_code))
    other_ids = set()
    for c in all_branch_codes:
        if c == keep_code:
            continue
        other_ids |= set(_ids_under_area(c))
    stale = other_ids - keep_ids
    if not stale:
        return
    conn = sqlite3.connect(DB_SELECTION)
    conn.executemany("DELETE FROM module_selection WHERE id=?", [(i,) for i in stale])
    conn.commit(); conn.close()

def _select_key_area(name):
    if name in appback.key_areas:
        code = appback.key_areas[name]
        appback.key_area = (name, code)
        appback.set_setting("selected_key_area_key", name)
        conn = appback.get_db_connection(DB_SELECTION)
        conn.execute("DELETE FROM requirements_check WHERE study_area LIKE 'I.2.a.%'")
        conn.commit(); conn.close()
        try:
            appback.add_requierments(code)   # backend has a column-name typo; don't let it block
        except Exception as e:
            print("add_requierments skipped:", e)
        # drop stale modules left over from a previously chosen specialization
        # (mirrors the cleanup _select_math() already does for math tracks)
        _drop_other_branch_modules(list(appback.key_areas.values()), code)
        _add_mandatory(code)          # auto-add the key area's mandatory modules

def _all_math_ids():
    ids = set()
    for nm in appback.math_modules:
        ids |= set(_math_ids_for_package(nm))
    return ids

def _select_math(name):
    if name in appback.math_modules:
        code = appback.math_modules[name]
        appback.math_module = (name, code)
        appback.set_setting("selected_math_key", name)
        conn = appback.get_db_connection(DB_SELECTION)
        conn.execute("DELETE FROM requirements_check WHERE study_area LIKE 'I.1.b.aa.%'")
        conn.commit(); conn.close()
        try:
            appback.add_requierments(code)   # backend has a column-name typo; don't let it block
        except Exception as e:
            print("add_requierments skipped:", e)
        # replace any previously-chosen math modules with exactly this package's two
        chosen = _math_ids_for_package(name)
        all_math = _all_math_ids()
        conn = sqlite3.connect(DB_SELECTION)
        if all_math:
            conn.executemany("DELETE FROM module_selection WHERE id=?", [(i,) for i in all_math])
        conn.commit(); conn.close()
        if chosen:
            appback.add_modules(list(chosen))

def _apply_plan_form(form):
    try:
        appback.init_selection_db()
        if form.get("key_area"):
            _select_key_area(form.get("key_area"))
        if form.get("math_track"):
            _select_math(form.get("math_track"))

        for field, key in [("semesters", "semester_nr"), ("min_credits", "min_credits"),
                           ("max_credits", "max_credits"), ("sem_start", "sem_start")]:
            val = form.get(field)
            if val not in (None, ""):
                try:
                    appback.set_setting(key, int(val))
                except Exception:
                    pass

        # Sync module checkboxes with module_selection: add newly checked ones,
        # AND remove ones that got unchecked. planForm is a single unified form
        # (see templates/plan.html) that always submits every checkbox it renders,
        # so anything that appeared as a checkbox (candidate_ids, from the same
        # area tree the page was rendered with) but isn't in `wanted` was
        # deliberately unchecked. Modules without a study_area tag (compulsory
        # ones) never get a checkbox at all, so they're never touched here.
        # (Previously this only ever added modules deselecting one in the UI
        # never deleted it from the DB, see TODO #32.)
        wanted = set(m.strip() for m in form.getlist("modules") if m.strip())
        sel = selected_df()
        have = set(sel["id"].astype(str)) if not sel.empty else set()
        key_code = appback.key_area[1] if appback.key_area else None
        math_code = appback.math_module[1] if appback.math_module else None
        candidate_tree, _ = build_area_tree(have, {}, key_code, math_code)
        candidate_ids = _tree_module_ids(candidate_tree)

        to_add = [m for m in wanted if m not in have]
        to_remove = (have & candidate_ids) - wanted

        if to_add:
            appback.add_modules(to_add)
        if to_remove:
            conn = sqlite3.connect(DB_SELECTION)
            conn.executemany("DELETE FROM module_selection WHERE id=?", [(i,) for i in to_remove])
            conn.commit(); conn.close()
        if to_add or to_remove:
            appback.update_requirements_fulfilled()

        # generate the plan if a specialization and math module are set but
        # only if every requirement is actually fulfilled (#25). check_all()
        # already existed and was correct, it just was never called anywhere;
        # assignin_semesters() even had the check commented out internally.
        if appback.key_area and appback.math_module:
            appback.update_requirements_fulfilled()
            ok, failed = appback.check_all()
            if ok:
                appback.assignin_semesters()
            else:
                return failed
    except Exception as e:
        print("plan form error:", e)
    return None


if __name__ == "__main__":
    appback.init_selection_db()
    appback.restore_globals()
    # use_reloader=False -> a single, stable process for the double-click launcher
    app.run(debug=True, use_reloader=False, host="127.0.0.1", port=5050)
