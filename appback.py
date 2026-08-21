from typing import Any, Dict, List, Optional, Tuple
import sqlite3
import pandas as pd
from flask import Flask, jsonify, request
from data.data_processing.database import add_modules
import ast
import json
import hashlib
import time
from dataclasses import dataclass



app = Flask(__name__)

# global variabels with information teh student chooses
key_area = None
math_module = None
min_credits = 25
max_credits = 35
semester_nr = 6 # number of semesters one wants to study, Regelstudienzeit of 6 semesters
sem_start = 0 # semester start either winter = 0, the standard, or summer = 1

# Datenbankverbindung

DB_SELECTION = "data/module_selection.db"
DB_MODULES = "data/modules.db"

# Fallback in case the DB isn't reachable yet when this module is imported -
# keeps the app working even if something goes wrong with the requirements
# table, instead of ending up with empty specialization/math dropdowns.
_FALLBACK_KEY_AREAS = {'Bioinformatik' : 'I.2.a.II',
             'Geoinformatik' : 'I.2.a.III',
             'Informatik der Ökosysteme': 'I.2.a.IV',
             'Medizinische Informatik': 'I.2.a.V',
             'Recht der Informatik': 'I.2.a.VI',
             'Wirtschaftsinformatik': 'I.2.a.VII',
             'Wissenschaftliches Rechnen': 'I.2.a.VIII',
             'Neuroinformatik': 'I.2.a.IX',
             'Computational Physics': 'I.2.a.X',
             'Anwendungsorientierte Systementwicklung': 'I.2.a.XI',
             'Berufsfeldorientierte Angewandte Informatik': 'I.2.a.XII'}

_FALLBACK_MATH_MODULES = {'Mathematik für Informationswissenschaften': 'I.1.b.aa.i',
                'Analysis, Analytische Geometrie und Lineare Algebra': 'I.1.b.aa.ii',
                'Mathematik für Studierende der Physik': 'I.1.b.aa.iii'}


def _load_study_area_options(prefix: str, fallback: Dict[str, str]) -> Dict[str, str]:
    """
    Loads {study_area_name: study_area_code} for the direct children of a study
    area prefix (e.g. 'I.2.a' for the specializations, 'I.1.b.aa' for the math
    tracks) straight from the requirements table, instead of hardcoding them
    here in a second place. Falls back to a hardcoded dict if the DB isn't
    reachable yet or the query comes back empty.
    """
    try:
        conn = sqlite3.connect(DB_MODULES)
        rows = conn.execute(
            """
            SELECT DISTINCT study_area, study_area_name
            FROM requirements
            WHERE study_area LIKE ? AND study_area NOT LIKE ?
            ORDER BY study_area
            """,
            (f"{prefix}.%", f"{prefix}.%.%"),
        ).fetchall()
        conn.close()
        options = {name: code for code, name in rows}
        return options if options else fallback
    except Exception:
        return fallback


key_areas = _load_study_area_options("I.2.a", _FALLBACK_KEY_AREAS)
math_modules = _load_study_area_options("I.1.b.aa", _FALLBACK_MATH_MODULES)

def restore_globals():
    """Lädt key_area und math_module aus der settings-DB wieder her."""
    global key_area, math_module
    saved_key_area_key = get_setting("selected_key_area_key")
    saved_math_key = get_setting("selected_math_key")
    if saved_key_area_key and saved_key_area_key in key_areas:
        key_area = (saved_key_area_key, key_areas[saved_key_area_key])
    if saved_math_key and saved_math_key in math_modules:
        math_module = (saved_math_key, math_modules[saved_math_key])


def get_db_connection(db):
    """
    Creates connection to SQLite-Database
    
    Args:
    db: database name 
    returns:
    connection
    """
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn

#Hilfsfunktionen 
def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    """
    Returns a list of column names for a given table.

    Args:
        conn (sqlite3.Connection): Active database connection.
        table (str): Table name to inspect.

    Returns:
        List[str]: Column names of the table.
    """
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]

def ensure_column(conn: sqlite3.Connection, table: str, col: str, col_type: str) -> None:
    """
    Adds a column to a table if it does not already exist.

    Args:
        conn (sqlite3.Connection): Active database connection.
        table (str): Target table name.
        col (str): Column name to add.
        col_type (str): SQLite column type (e.g., 'INTEGER DEFAULT 0').

    Returns:
        None
    """
    cols = table_columns(conn, table)
    if col not in cols:
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        conn.commit()

def parse_literal(value: Any, default: Any) -> Any:
    """
    Safely parses a value into a Python object using ast.literal_eval.

    Args:
        value (Any): Value to parse (str, dict, list, or tuple).
        default (Any): Fallback value if parsing fails or value is empty.

    Returns:
        Any: Parsed Python object or default.
    """
    if value is None:
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return default
        try:
            return ast.literal_eval(s)
        except Exception:
            return default
    return default

def safe_list(val):
    """
    Normalisiert study_area-Felder, die als String wie eine Liste gespeichert sind.
    Beispiele:
      "['I.1.a', 'I.1.b']" -> ['I.1.a', 'I.1.b']
      "I.1.a"              -> ['I.1.a']
      None / ""            -> []
    """
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            x = ast.literal_eval(s)
            if isinstance(x, list):
                return x
            return [x]
        except Exception:
            return [s]
    return [val]

def init_selection_db() -> None:
    """
    Initializes the selection database by creating required tables and inserting default settings.

    Creates the 'settings' table if it doesn't exist yet ('requirements_check' is
    created by data/data_processing/database.py, which is the single source of
    truth for its schema).
    Inserts default values for min_credits, max_credits, semester_nr, sem_start, total_credits.

    Returns:
        None
    """
    conn = get_db_connection(DB_SELECTION)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    defaults = {
        "min_credits": "25",
        "max_credits": "35",
        "semester_nr": "6",
        "sem_start": "0",
        "total_credits": "180",
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
    conn.commit()
    conn.close()

def get_setting(key: str, cast_type: type = str) -> Any:
    """
    Retrieves a configuration value from the settings table.

    Args:
        key (str): Setting key to look up.
        cast_type (type): Type to cast the value to (e.g., int, float, str).

    Returns:
        Any: Cast value, or None if key not found.
    """
    init_selection_db()
    conn = get_db_connection(DB_SELECTION)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    val = row[0]
    if cast_type is int:
        return int(float(val))
    if cast_type is float:
        return float(val)
    return val

def set_setting(key: str, value: Any) -> None:
    """
    Inserts or updates a configuration value in the settings table.

    Args:
        key (str): Setting key.
        value (Any): Value to store (stored as string).

    Returns:
        None
    """
    init_selection_db()
    conn = get_db_connection(DB_SELECTION)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()



def add_compulsory():
    """
    Adds all mandatory modules for the selected key area and math module to the module selection.

    Queries DB_MODULES for modules in study areas marked as ALL_MANDATORY
    and adds them to module_selection via add_modules().

    Returns:
        None
    """
    code_area = key_area[1]
    code_math = math_module[1]
    conn = get_db_connection(DB_MODULES)
    cursor = conn.cursor()
    # selecting studyarea which begin with key area and math area code 
    # and where all modules are mandatory
    cursor.execute(f"""SELECT study_area FROM requirements 
                   WHERE study_area LIKE '{code_area}%' 
                   OR study_area LIKE '{code_math}%'
                   AND requirement_type = 'ALL_MANDATORY'
                   """)
    result = cursor.fetchall()
    # if there are stdyareas which fullfill the requierments
    # get the study area ids and choose all module which have this studyarea in their column study_area
    if result:
        ids = [row['study_area'] for row in result]
        placeholder = ','.join(['?' for _ in ids])
        cursor.execute(f"""SELECT id FROM modules WHERE study_area IN ({placeholder})""", ids)
        result = cursor.fetchall()
        conn.close()
        add_modules([id for id in result])

def add_requierments(codearea):
    """
    Populates the requirements_check table with requirements for a given study area code.

    Reads matching rows from the requirements table in DB_MODULES
    and appends them to requirements_check in DB_SELECTION.

    Args:
        code_area (str): Study area code to filter requirements (e.g., 'I.2.a.II').

    Returns:
        None
    """
    conn = get_db_connection(DB_MODULES)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM requirements WHERE study_area LIKE ? OR study_area LIKE ?",
        (f"{codearea}.%", f"{codearea}")
    )
    result = cursor.fetchall()
    conn.close()

    if not result:
        return

    conn_sel = sqlite3.connect(DB_SELECTION)
    
    conn_sel.execute(
        "DELETE FROM requirements_check WHERE study_area LIKE ?",
        (f"{codearea}%",)
    )
    for row in result:
        conn_sel.execute("""
            INSERT INTO requirements_check
            (study_area, study_area_name, requirement_type, min_value, conditional_on, exclude_area, fulfilled)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (
            row["study_area"],
            row["study_area_name"],
            row["requirement_type"],
            row["min_value"],
            row["conditional_on"],
            row["exclude_area"]
        ))
    conn_sel.commit()
    conn_sel.close()
    
def _other_branch_codes():
    """Every specialization (I.2.a.*) / math-track (I.1.b.aa.*) code that is
    NOT the one currently selected. Used so a module cross-tagged into a
    branch the student didn't choose doesn't count toward that branch's
    credit total."""
    other = set(key_areas.values()) | set(math_modules.values())
    if key_area:
        other.discard(key_area[1])
    if math_module:
        other.discard(math_module[1])
    return other


def _tag_in_other_branch(tag, other_codes):
    return any(tag == oc or tag.startswith(oc + ".") for oc in other_codes)


def has_only_study_area(conditional_on, excluded_areas):
    """
    Checks whether the current module selection satisfies a conditional/
    exclusion pair used to pick between two alternate requirement rows for
    the same study area (e.g. Professionalisierungsbereich is 78 ECTS
    normally, but only 72 ECTS if the student is in the "Mathematik für
    Studierende der Physik" track).

    Args:
        conditional_on (str or None): A bare study_area CODE that must be
            present among the selection's study_area tags for this variant
            to be the active one.
        excluded_areas (str or None): Comma-separated bare study_area CODEs;
            if ANY is present among the selection's tags, this variant is
            NOT the active one.

    Returns:
        bool: True if this variant is the currently-active one.

    Note: module_selection.study_area is stored as a stringified LIST per
    module (e.g. "['I.1.a', 'I.2.a.VII']"), never a bare code - comparing it
    directly against a bare code with `=` or `IN` (as this used to do) never
    matches anything. This parses those tags with safe_list() instead.
    """
    has_condition = conditional_on is not None and str(conditional_on).strip() != ""
    exclude = []
    if excluded_areas:
        exclude = [area.strip() for area in str(excluded_areas).split(',') if area.strip()]
    has_exclude = len(exclude) > 0

    if not has_condition and not has_exclude:
        return True

    conn = get_db_connection(DB_SELECTION)
    rows = conn.execute("SELECT study_area FROM module_selection").fetchall()
    conn.close()
    selected_tags = set()
    for row in rows:
        selected_tags.update(safe_list(row[0]))

    a_ok = (conditional_on in selected_tags) if has_condition else True
    b_ok = (not any(e in selected_tags for e in exclude)) if has_exclude else True

    if has_condition and has_exclude:
        return a_ok and b_ok
    return a_ok if has_condition else b_ok


def check_requierments(study_area: str):
    """
    Evaluates and updates the fulfillment status for a single study area requirement.

    Determines the active requirement row using has_only_study_area(), then checks
    MIN_CREDITS or ALL_MANDATORY against the current credit sum in module_selection.

    Args:
        study_area (str): Study area code to validate (e.g., 'I.1.b.aa.iii').

    Returns:
        None: Updates fulfilled column in requirements_check directly.
    """

    conn = get_db_connection(DB_SELECTION)
    cursor = conn.cursor()
    # exact match only
    cursor.execute("""SELECT rowid, requirement_type, min_value, conditional_on, exclude_area
                      FROM requirements_check WHERE study_area = ?""",
        (study_area,))
    result = cursor.fetchall()
    conn.close()

    if not result:
        return

    row_idx = 0
    inactive_rowid = None
    if len(result) > 1:
        # conditional_on/exclude_area are columns 3/4 of the SELECT above
        res1_con, res1_ex = result[0][3], result[0][4]
        res2_con, res2_ex = result[1][3], result[1][4]
        if has_only_study_area(res1_con, res1_ex):
            row_idx = 0
        elif has_only_study_area(res2_con, res2_ex):
            row_idx = 1
        # the row we did NOT pick isn't a real failure, it's just the
        # inapplicable alternate variant. Mark it fulfilled so it never
        # shows up in the "unfulfilled" scan later.
        inactive_rowid = result[1 - row_idx][0]

    active_rowid = result[row_idx][0]
    req_type     = result[row_idx][1]
    min_val      = result[row_idx][2] or 0

    # Credit sum, computed per-tag in Python instead of a raw SQL
    # `LIKE '%study_area%'` (which matches the substring ANYWHERE, e.g.
    # study_area='I.2' would also match a module tagged only 'I.2.a.XI.2.b'
    # by coincidence of both containing "I.2"). Also excludes tags that
    # belong ONLY to a different, currently-unselected specialization/math
    # branch, so a module cross-tagged into two areas doesn't inflate a
    # branch the student didn't choose.
    other_codes = _other_branch_codes()
    conn_selection = get_db_connection(DB_SELECTION)
    rows = conn_selection.execute("SELECT credits, study_area FROM module_selection").fetchall()
    conn_selection.close()

    total_credits = 0.0
    for credits, raw_area in rows:
        tags = safe_list(raw_area)
        matching = [t for t in tags if t == study_area or t.startswith(study_area + ".")]
        if not matching:
            continue
        if any(not _tag_in_other_branch(t, other_codes) for t in matching):
            total_credits += float(credits or 0)

    if req_type == 'MIN_CREDITS':
        fulfilled = total_credits >= min_val  # bool → SQLite speichert als 0/1
    elif req_type == 'ALL_MANDATORY':
        fulfilled = total_credits >= min_val and min_val > 0
    else:
        fulfilled = False

    with get_db_connection(DB_SELECTION) as conn:
        conn.execute(
            "UPDATE requirements_check SET fulfilled = ? WHERE rowid = ?",
            (fulfilled, active_rowid)
        )
        if inactive_rowid is not None:
            conn.execute(
                "UPDATE requirements_check SET fulfilled = 1 WHERE rowid = ?",
                (inactive_rowid,)
            )
        conn.commit()


def update_requirements_fulfilled() -> List[str]:
    """
    Recomputes fulfillment status for all study areas in requirements_check.

    Calls check_requierments() for each distinct study area, then returns
    a list of study areas where fulfilled = 0.

    Returns:
        List[str]: Study area codes that failed their requirement check.
    """
    conn = get_db_connection(DB_SELECTION)
    areas = [row[0] for row in conn.execute("SELECT DISTINCT study_area FROM requirements_check").fetchall()]
    conn.close()

    # "I.2.a.II.a" vor "I.2.a.II" vor "I.2.a" vor "I.2" vor "I"
    areas.sort(key=lambda x: len(x.split(".")), reverse=True)
    
    for area in areas:
        check_requierments(area)
    
    conn = get_db_connection(DB_SELECTION)
    failed = [row[0] for row in conn.execute(
        "SELECT study_area FROM requirements_check WHERE fulfilled = 0"
    ).fetchall()]
    conn.close()
    return failed



def _module_label(mid, modules_cache):
    """Human-readable 'Name (id)' for a module id, checked against the
    current selection first (has the richest data already loaded) and
    falling back to the catalog (modules.db) for modules that aren't
    selected - e.g. a missing AR prerequisite."""
    if mid in modules_cache:
        return modules_cache[mid]
    conn = get_db_connection(DB_SELECTION)
    row = conn.execute("SELECT name FROM module_selection WHERE id=?", (mid,)).fetchone()
    conn.close()
    if row is None:
        conn2 = sqlite3.connect(DB_MODULES)
        row2 = conn2.execute("SELECT name FROM modules WHERE id=?", (mid,)).fetchone()
        conn2.close()
        label = f"{row2[0]} ({mid})" if row2 else mid
    else:
        label = f"{row[0]} ({mid})"
    modules_cache[mid] = label
    return label


def check_all():
    """
    Checks Admission Requirements, study restrictions, and study-area
    requirements are all fulfilled.

    Returns:
        bool: True if the whole selection is valid, else False.
        list[dict]: {"code", "label"} entries describing every problem found.
            `code` is the bare study_area code for area failures (used by the
            frontend to red-highlight the matching tree node) and None for
            AR / study-restriction failures (which don't map to one area).
            `label` is always a human-readable, ready-to-display message.
    """
    clear = True
    entries = []
    modules_cache = {}
    conn = get_db_connection(DB_SELECTION)
    cursor = conn.cursor()

    # AR (admission requirement) checks: modules that must (all) or of which
    # at least one must (any) already be selected.
    cursor.execute('SELECT id, AR FROM module_selection WHERE AR != "{\'all\': [], \'any\': []}"')
    ars = cursor.fetchall()
    if ars:
        for module_id, ar_raw in ars:
            ar_dict = ast.literal_eval(ar_raw)
            if ar_dict.get('all'):
                required = ar_dict['all']
                placeholders = ','.join('?' * len(required))
                cursor.execute(f"SELECT id FROM module_selection WHERE id IN ({placeholders})", required)
                have = {row[0] for row in cursor.fetchall()}
                missing = [m for m in required if m not in have]
                if missing:
                    clear = False
                    missing_labels = ", ".join(_module_label(m, modules_cache) for m in missing)
                    entries.append({
                        "code": None,
                        "label": f"{_module_label(module_id, modules_cache)} requires {missing_labels}, which is/are not selected."
                    })
            elif ar_dict.get('any'):
                required = ar_dict['any']
                placeholders = ','.join('?' * len(required))
                cursor.execute(f"SELECT id FROM module_selection WHERE id IN ({placeholders})", required)
                have = cursor.fetchall()
                if len(have) < 1:
                    clear = False
                    any_labels = ", ".join(_module_label(m, modules_cache) for m in required)
                    entries.append({
                        "code": None,
                        "label": f"{_module_label(module_id, modules_cache)} requires at least one of {any_labels}, none of which is selected."
                    })

    # study_restriction (mutual exclusion) checks, the OPPOSITE of AR: these
    # are modules that must NOT be selected together with this one (e.g. a
    # Nebenfach module and its regular-program equivalent). Fails if any of
    # the listed modules IS present, not if they're missing.
    cursor.execute("""SELECT id, study_restriction FROM module_selection WHERE study_restriction != '[]' """)
    studyRestrictions = cursor.fetchall()
    if studyRestrictions:
        for module_id, restr_raw in studyRestrictions:
            restrictions = ast.literal_eval(restr_raw)
            if not restrictions:
                continue
            placeholders = ','.join('?' * len(restrictions))
            cursor.execute(f"SELECT id FROM module_selection WHERE id IN ({placeholders})", restrictions)
            conflicts = [row[0] for row in cursor.fetchall()]
            if conflicts:
                clear = False
                conflict_labels = ", ".join(_module_label(m, modules_cache) for m in conflicts)
                entries.append({
                    "code": None,
                    "label": f"{_module_label(module_id, modules_cache)} cannot be combined with {conflict_labels}, which is/are also selected."
                })

    # study-area (credit / mandatory) requirements
    cursor.execute("SELECT study_area, study_area_name FROM requirements_check WHERE fulfilled = 0")
    failed_areas = cursor.fetchall()
    conn.close()

    for code, name in failed_areas:
        clear = False
        area_label = f"{name} ({code})" if name else code
        entries.append({"code": code, "label": f"{area_label} requirement not fulfilled yet."})

    return clear, entries

def semester_type(sem: int, sem_start: int) -> str:
    if sem_start == 0:
        return "W" if sem % 2 == 1 else "S"
    return "S" if sem % 2 == 1 else "W"

def allowed_in_semester(freq: str, sem: int, sem_start: int) -> bool:
    if freq in {"E", "N"}:
        return True
    return semester_type(sem, sem_start) == freq


def move_module_to_semester(module_id: str, target_sem: int) -> None:
    """
    Moves a module to a target semester, validating frequency, credit capacity,
    and AR prerequisite ordering.

    Args:
        module_id (str): ID of the module to move.
        target_sem (int): Target semester number (1 to semester_nr).

    Returns:
        None

    Raises:
        ValueError: If semester is out of range, frequency doesn't fit, credits
                    would exceed max, or prerequisite ordering is violated.
    """
    max_credits = int(get_setting("max_credits", int))
    semester_nr = int(get_setting("semester_nr", int))
    sem_start = int(get_setting("sem_start", int))

    if target_sem < 1 or target_sem > semester_nr:
        raise ValueError("target_semester außerhalb des Bereichs")

    conn = get_db_connection(DB_SELECTION)
    ensure_column(conn, "module_selection", "assigned_semester", "INTEGER DEFAULT 0")
    cols = table_columns(conn, "module_selection")
    cur = conn.cursor()
    cur.execute("SELECT * FROM module_selection WHERE id = ?", (module_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Modul {module_id} nicht in Auswahl")

    freq = (row["frequency"] if "frequency" in cols else "N")
    warnings: List[str] = []
    freq_norm = normalize_frequency(freq, warnings, module_id)
    if not allowed_in_semester(freq_norm, target_sem, sem_start):
        conn.close()
        raise ValueError(f"Modul {module_id} hat frequency={freq_norm} und passt nicht in Semester {target_sem}")

    credits = int(row["credits"]) if "credits" in cols else 0
    cur.execute(
        "SELECT COALESCE(SUM(credits), 0) FROM module_selection WHERE assigned_semester = ? AND id != ?",
        (target_sem, module_id),
    )
    sum_target = int(cur.fetchone()[0] or 0)
    if sum_target + credits > max_credits:
        conn.close()
        raise ValueError(f"Semester {target_sem} würde max_credits überschreiten")

    # prerequisite scheduling check (AR)
    cur.execute("SELECT id, AR, assigned_semester FROM module_selection")
    all_rows = cur.fetchall()
    assigned = {str(r[0]): int(r[2] or 0) for r in all_rows}
    deps = {}
    for r in all_rows:
        mid = str(r[0])
        ar = parse_literal(r[1], {"all": [], "any": []})
        if isinstance(ar, dict):
            reqs = [str(x) for x in (ar.get("all", []) or []) + (ar.get("any", []) or [])]
            deps[mid] = [x for x in reqs if x]
    assigned[module_id] = target_sem

    prereqs = deps.get(module_id, [])
    for p in prereqs:
        if p in assigned and assigned[p] >= target_sem:
            conn.close()
            raise ValueError(f"Prereq {p} liegt im gleichen/späteren Semester als {module_id}")
    for other, pre in deps.items():
        if module_id in pre and other in assigned and assigned[other] <= target_sem:
            conn.close()
            raise ValueError(f"{module_id} ist Voraussetzung für {other} (liegt dann zu spät)")

    cur.execute("UPDATE module_selection SET assigned_semester = ? WHERE id = ?", (int(target_sem), module_id))
    conn.commit()
    conn.close()






def get_selected_modules_df() -> pd.DataFrame:
    conn = get_db_connection(DB_SELECTION)
    df = pd.read_sql_query("SELECT * FROM module_selection", conn)
    conn.close()
    return df

def normalize_frequency(freq: Any, warnings: List[str], module_id: Optional[str] = None) -> str:
    if freq is None or (isinstance(freq, float) and pd.isna(freq)):
        warnings.append(f"frequency fehlt{f' bei {module_id}' if module_id else ''} -> setze 'N'")
        return "N"
    s = str(freq).strip().upper()
    if s == "":
        warnings.append(f"frequency leer{f' bei {module_id}' if module_id else ''} -> setze 'N'")
        return "N"
    if s not in {"W", "S", "E", "N"}:
        warnings.append(f"unbekannte frequency '{s}'{f' bei {module_id}' if module_id else ''} -> setze 'N'")
        return "N"
    return s

 
def shift_semester(row):
    """
    Gets a row of a df and shifts the semester if recommended semester does not fit the frequency

    Args:
        row: row of a dataframe

    Returns:
        list: with updated semsters
        
    Examples:
        > check_requierments(row)
        row['RS'] == [1,2,3,4]
        row['frequency'] = 'W'
        semstart= 0, meaning student startet uni in the winter semester
        # returns [1,3,5]
    """
    lst = row['RS']
    freq = row['frequency']
    
    # Bestimme ob ungerade oder gerade Semester verschoben werden
    if (sem_start == 0 and freq == 'S') or (sem_start == 1 and freq == 'W'):
        # Ungerade Semester +1
        return list(dict.fromkeys([x+1 if x % 2 == 1 else x for x in lst]))
    elif (sem_start == 0 and freq == 'W') or (sem_start == 1 and freq == 'S'):
        # Gerade Semester +1
        return list(dict.fromkeys([x+1 if x % 2 == 0 else x for x in lst]))
    else:
        return lst
    
def count_all_dependencies(module_id, df, memo=None):
    """
    Counts ALL modules that directly or indirectly depend on the given module_id.

    Performs recursive dependency counting with memoization to avoid recomputation.
    RPK dependencies count as 1.0, AR dependencies as 1.5 (higher weight). Sums 
    direct dependencies + all transitive dependencies through the dependency graph.

    Args:
        module_id (str): Module ID to start dependency counting from (e.g., 'B.Inf.1101').
        df (pd.DataFrame): Module dataframe with 'RPK' (list-column) and 'AR' (list-column).
        memo (dict, optional): Memoization cache {module_id: total_deps}. Defaults to None.

    Returns:
        float: Total weighted dependency count (direct + indirect).

    Examples:
        > count_all_dependencies('B.Inf.1101', modules_df)
        12.5  # 8 RPK (8.0) + 3 AR (4.5) + transitive
        
        > memo = {}
        > count_all_dependencies('B.Inf.1101', df, memo)
        12.5
        > count_all_dependencies('B.Inf.1102', df, memo)  # Uses cache!
        7.0
    """
    if memo is None:
        memo = {}
    if module_id in memo:
        return memo[module_id]

    # Direct dependencies
    rpk_deps = df[df['RPK'].str.contains(module_id, na=False, regex=False)]['id'].tolist()
    ar_deps = df[df['AR'].str.contains(module_id, na=False, regex=False)]['id'].tolist()
    
    # all direct dependies
    direct_deps = list(set(rpk_deps + ar_deps))

    # Count with weighted dependencies
    total = len(rpk_deps) + len(ar_deps) * 1.5
    
    # counting recursive
    for dep in direct_deps:
        total += count_all_dependencies(dep, df, memo)

    memo[module_id] = total
    return total

def make_space_in_semester(target_sem, needed_credits, df, availableSems):
    """
    Creates free credits in target_semester by relocating E/N Modules, modules available
    in each semester or where semster is not specified.

    Prioritizes modules with fewest prerequisites (lowest RPK_count) for relocation.
    Moves to semesters with matching frequency and sufficient free_credits.
    Updates df['assigned_semester'] and availableSems free_credits balance.

    Args:
        target_sem (int): Target semester needing more free credits.
        needed_credits (int): Minimum free credits required in target_sem.
        df (pd.DataFrame): Module dataframe with 'assigned_semester', 'frequency', 'RPK_count', 'credits'.
        availableSems (pd.DataFrame): Available semesters with 'frequency', 'free_credits'.

    Returns:
        bool: True if enough space created (>= needed_credits), False otherwise.

    Examples:
        > make_space_in_semester(3, 12, modules_df, available_sems)
        True  # Moved modules, now Semester 3 has >=12 free credits
    """
    
    # Select e/n modules in target semester, prioritize low prerequisites
    en_modules = df[(df['assigned_semester'] == target_sem) & (df['frequency'].isin(['E', 'N']))]
    en_modules = en_modules.sort_values('RPK_count')
    
    for move_idx, move_mod in en_modules.iterrows():
        # Try same frequency first 
        target_freq = 'S' if availableSems.loc[target_sem, 'frequency'] == 'W' else 'W'
        target_sems = availableSems[
            (availableSems['frequency'] == target_freq) & 
            (availableSems['free_credits'] >= move_mod['credits'])
        ]
        
        if not target_sems.empty:
            new_sem = target_sems['free_credits'].idxmax()
            df.at[move_idx, 'assigned_semester'] = new_sem
            
            # Update free credits balance
            availableSems.loc[target_sem, 'free_credits'] += move_mod['credits']
            availableSems.loc[new_sem, 'free_credits'] -= move_mod['credits']
            
            if availableSems.loc[target_sem, 'free_credits'] >= needed_credits:
                return True
        else:
            target_freq = 'S' if target_freq == 'W' else 'W'
            target_sems = availableSems[
                (availableSems['frequency'] == target_freq) & 
                (availableSems['free_credits'] >= move_mod['credits'])
            ]
            if not target_sems.empty:
                new_sem = target_sems['free_credits'].idxmax()
                df.at[move_idx, 'assigned_semester'] = new_sem
                
                # Update free credits balance
                availableSems.loc[target_sem, 'free_credits'] += move_mod['credits']
                availableSems.loc[new_sem, 'free_credits'] -= move_mod['credits']
                
                if availableSems.loc[target_sem, 'free_credits'] >= needed_credits:
                    return True
    
    return False

def safe_literal(val):
        try:
            result = ast.literal_eval(str(val))
            return result if isinstance(result, list) else []
        except Exception:
            return []

def _rpk_ready(mod_row, i, id_to_sem, id_to_earliest_rs):
    """True if every RPK (recommended previous knowledge) prerequisite
    this module has - that's actually part of the current selection -
    can plausibly land at or before semester i. A prerequisite counts as
    blocking only if it's ALREADY confirmed scheduled later than i, or
    its own earliest recommended semester is later than i (so it can't
    possibly land here or earlier once it's processed). Prerequisites
    recommended for the SAME semester i are allowed - many intro module
    pairs (e.g. B.Inf.1101/1103) are meant to be taken together, and RPK
    isn't a hard gate like AR, just a strong hint."""
    for rpk_id in mod_row['RPK_list']:
        sem = id_to_sem.get(rpk_id)
        if sem is None:
            continue  # not in the selection - can't block on it
        if sem > 0:
            if sem > i:
                return False
            continue
        earliest_rs = id_to_earliest_rs.get(rpk_id)
        if earliest_rs is not None and earliest_rs > i:
            return False
    return True

def assignin_semesters():
    """
    Creates semester assignment table by distributing modules based on priority scoring.

    Main algorithm for automatic semester planning:
    1. Validates requirements with check_all()
    2. Computes RPK_count (recursive dependency graph)
    3. Assigns modules to semesters using RS recommendations, priority scores 
       (RPK_count + credits + failure_rate + frequency_weight)
    4. Balances credits per semester (respecting max_credits)
    5. Handles remaining modules with make_space_in_semester()
    6. Ensures AR prerequisites precede dependent modules
    7. Updates module_selection table with 'assigned_semester'

    Args:
        None: Uses global modules_selection DB and config (semester_nr, max_credits, sem_start)

    Returns:
        int: 1 if table created successfully, 0 if requirements failed or assignment impossible.

    Raises:
        sqlite3.Error: Database update failures.
        
    Examples:
        > create_table()
        1  # Successfully created semester plan in module_selection.assigned_semester
    """


    # reload the live settings (in case the user changed them via /set_config
    # since the last import) instead of relying on the module-level defaults.
    # global so shift_semester(), which reads sem_start as a global too, sees
    # the same fresh value.
    global sem_start, semester_nr, max_credits
    max_credits = int(get_setting("max_credits", int))
    semester_nr = int(get_setting("semester_nr", int))
    sem_start = int(get_setting("sem_start", int))

    # for later calculation with priority score
    frequency_weight = {
                'E': 1.0,
                'N': 1.0,
                'W': 2.0,  
                'S': 2.0}
    
    # collects human-readable notes about compromises the algorithm had to
    # make (a semester ended up over max_credits because no room could be
    # freed, an AR ordering violation couldn't be resolved, or a module had
    # to be scheduled before its recommended previous knowledge)
    warnings_list: List[str] = []

    conn = get_db_connection(DB_SELECTION)
    ensure_column(conn, "module_selection", "assigned_semester", "INTEGER DEFAULT 0")
    df =  pd.read_sql_query(f"""SELECT id, credits, RPK, AR, "assigned_semester", frequency, failure_rates, RS FROM module_selection""", conn)
    conn.commit()
    conn.close()


    df['RS'] = df['RS'].apply(safe_literal)
    df['RPK_list'] = df['RPK'].apply(safe_literal)
    df['assigned_semester'] = 0 # assigned semester, a new row

    # every module where there is a collision between frequency recommended semester and
    # semstart gets a new rs by moving the not fitting ones forward a semester
    df['RS'] = df.apply(lambda row: shift_semester(row), axis=1)

    # to create an optimal table an rpk_count is being calculatet, which
    # counts how many modules are depended on the module
    df['RPK_count'] = df['id'].apply(lambda x: count_all_dependencies(x, df))

    # based on the RPK count and frequency recommended semesters are calculatet for modules with no rs
    noRS = df[df['RS'].apply(lambda x: x is None or len(x) == 0)]

    if not noRS.empty:
        for freq in ['E', 'N', 'W', 'S']:
            freqModules = noRS[noRS['frequency'] == freq]
            if freqModules.empty:
                continue

            freqModules.sort_values('RPK_count', ascending=False, inplace=True)
            n = len(freqModules)

            # available semester for each frequency, deliberately 1..6 (not
            # semester_nr) to match how the Modulhandbuch itself recommends
            # semesters, regardless of how many semesters this particular
            # plan spans; shorter plans catch the overflow via the leftover
            # mechanism below, longer plans via the final unassigned pass.
            if (freq == 'W' and sem_start == 0) or (freq == 'S' and sem_start == 1):
                available_sems = [1, 3, 5]
            elif (freq == 'W' and sem_start == 1) or (freq == 'S' and sem_start == 0):
                available_sems = [2, 4, 6]
            else:  # E or N
                available_sems = [1, 2, 3, 4, 5, 6]

            # calculating how many modules each semster should get
            num_available = len(available_sems)
            chunk_size = max(n // num_available, 1)

            for idx, (df_idx, mod) in enumerate(freqModules.iterrows()):
                sem_index = min(idx // chunk_size, num_available - 1)
                target_sem = available_sems[sem_index]
                df.at[df_idx, 'RS'] = [target_sem]



    # iterating through each semester
    for i in range (1,semester_nr+1):

        # current sem calculates every module which is recommended for the smester i and has no assigned semester yet
        currentSem = df[(df['RS'].apply(lambda x: i in (x or []))) & (df['assigned_semester'] == 0)].copy()

        if currentSem.empty:
            continue

        # Defer modules whose RPK prerequisites aren't plausibly satisfiable
        # by semester i yet Deferred modules get pushed
        # to a later valid semester using the same frequency-aware step as
        # the credit-overflow leftover mechanism further down.
        id_to_sem = df.set_index('id')['assigned_semester'].to_dict()
        id_to_earliest_rs = {row['id']: (min(row['RS']) if row['RS'] else None) for _, row in df.iterrows()}
        ready_mask = currentSem.apply(lambda r: _rpk_ready(r, i, id_to_sem, id_to_earliest_rs), axis=1)
        not_ready = currentSem[~ready_mask]
        currentSem = currentSem[ready_mask]

        if not not_ready.empty:
            df.loc[df['id'].isin(not_ready['id']), 'RS'] = df[df['id'].isin(not_ready['id'])].apply(
                lambda row: [min(sem + int(frequency_weight[row['frequency']]), semester_nr) for sem in (row['RS'] or [])],
                axis=1
            )
            for _, r in not_ready.iterrows():
                if i >= semester_nr:
                    warnings_list.append(
                        f"{r['id']}: recommended previous knowledge isn't scheduled early enough, but there's no later semester left to move it to."
                    )

        if currentSem.empty:
            continue

        # if the credit summ of current sem fits the max credits every module is added to semester i
        sumcredits =  currentSem['credits'].sum()

        if sumcredits <= max_credits:
            df.loc[df['id'].isin(currentSem['id']), 'assigned_semester'] = i


        elif sumcredits > max_credits:

            # priority count to know which modules should be in this semester.
            # Higher priority = more depended-on (RPK_count), heavier
            # (credits), riskier (failure_rates), and/or harder to reschedule
            # (W/S frequency_weight, since those only recur every other
            # semester). Sorted DESCENDING so these modules get first pick at
            # the greedy knapsack below and stay on schedule - the low-
            # priority modules (few dependents, cheap, flexible E/N
            # frequency) are the ones that should absorb the delay instead.
            currentSem['priority'] = ( currentSem['RPK_count'] +
                                        (currentSem['credits'] / 10) +
                                        (currentSem['failure_rates'] * 2)
                                    ) * currentSem['frequency'].map(frequency_weight)

            # RPK ordering ALSO has to be respected within this single
            # semester's tie-break, not just across semesters. sort prerequisites
            # (within this batch) before their dependents first, priority as
            # the tie-break within that, and skip a module in the greedy
            # pick if a same-batch prerequisite didn't make it in.
            ids_in_batch = set(currentSem['id'])
            rpk_in_batch = {row['id']: [r for r in row['RPK_list'] if r in ids_in_batch and r != row['id']]
                            for _, row in currentSem.iterrows()}
            depth = {mid: 0 for mid in ids_in_batch}
            for _ in range(len(ids_in_batch) + 1):
                changed = False
                for mid, deps in rpk_in_batch.items():
                    if deps:
                        new_depth = max(depth[d] for d in deps) + 1
                        if new_depth > depth[mid]:
                            depth[mid] = new_depth
                            changed = True
                if not changed:
                    break
            currentSem['_rpk_depth'] = currentSem['id'].map(depth)
            currentSem.sort_values(['_rpk_depth', 'priority'], ascending=[True, False], inplace=True)

            important_ids = []
            kept = set()
            credits_moved = 0

            for idx, mod in currentSem.iterrows():
                deps = rpk_in_batch.get(mod['id'], [])
                if any(d not in kept for d in deps):
                    # a same-batch RPK prerequisite didn't make it into this
                    # semester, defer this module along with it instead of
                    # scheduling it ahead of its own prior knowledge.
                    continue
                # if already added credits + credits of next module exeed max_credits try next module
                # this is the classic backpack problem which is NP so we choose a simple greedy algorithm
                # as that is enough for this problem
                if credits_moved + mod['credits'] > max_credits:
                    continue
                important_ids.append(mod['id'])
                kept.add(mod['id'])
                credits_moved += mod['credits']
            df.loc[df['id'].isin(important_ids), 'assigned_semester'] = i

            # Move leftover modules to a later valid semester
            leftover_mask = (df['assigned_semester'] == 0) & (df['RS'].apply(lambda x: i in (x or [])))
            df.loc[leftover_mask, 'RS'] = df[leftover_mask].apply(
                lambda row: [min(sem + int(frequency_weight[row['frequency']]), semester_nr) for sem in (row['RS'] or [])],
                axis=1
            )
            df.loc[leftover_mask, 'RPK_count'] += 2# higher priority score so modules dont get moved to the end


    # modules which havent been assigned yet
    currentSem = df[df['assigned_semester'] == 0].copy()
    if not currentSem.empty:
        currentSem.sort_values('credits', ascending=True, inplace=True)
        # every semester were credits arent filles yet
        assigned_credits = df[df['assigned_semester'] > 0].groupby('assigned_semester')['credits'].sum()
        availableSems = (max_credits - assigned_credits).reindex(
            range(1, semester_nr + 1), fill_value=max_credits
        ).to_frame(name='free_credits')
        availableSems['frequency'] = availableSems.index.map(
            lambda x: 'W' if (x % 2 == 1) == (sem_start == 0) else 'S'
        )


        for type in ('W', 'S'):
            # distribute w or s modules on availabe semester
            if not currentSem[currentSem['frequency'] == type].empty:
                for idx, mod in currentSem[currentSem['frequency'] == type].iterrows():
                    # semester where module fits based on credits
                    wSems = availableSems[(availableSems['frequency'] == type) & (availableSems['free_credits'] > 0)]

                        # two cases: no free w/s smesters or free w/s semesters
                        # case 1: no free w/s semester
                    if wSems.empty:
                        success = False
                        # calculating all available semesters based on frequency
                        sems_to_choose_from = [i for i in range(1, semester_nr + 1) if (i % 2 == 1) == ((type == 'W') == (sem_start == 0))]
                        for sem in sems_to_choose_from:
                            # testing every semester
                            if make_space_in_semester(sem, mod['credits'], df, availableSems):

                                df.at[idx, 'assigned_semester'] = sem
                                availableSems.loc[sem, 'free_credits'] -= mod['credits']
                                success = True
                                break

                        if not success:
                            # no space could be made anywhere, place it in
                            # whichever matching-frequency semester is least
                            # bad (most free_credits, even if <= 0) instead
                            # of crashing on an idxmax() of an empty frame.
                            candidates = availableSems[availableSems['frequency'] == type]
                            best_sem = (candidates['free_credits'].idxmax() if not candidates.empty
                                        else (sems_to_choose_from[0] if sems_to_choose_from else 1))
                            df.at[idx, 'assigned_semester'] = best_sem
                            availableSems.loc[best_sem, 'free_credits'] -= mod['credits']
                            warnings_list.append(
                                f"Semester {best_sem}: no room could be freed for {mod['id']} - max_credits exceeded there."
                            )

                    # case 2: free W/S semesters
                    else:
                        fitting = wSems[wSems['free_credits'] >= mod['credits']]

                        # case 2.1 not enaugh space in free w/s semesters
                        if fitting.empty:
                            # semester with the most space and EN modules are beging moved to S/W semester
                            best_sem = wSems['free_credits'].idxmax()
                            success = make_space_in_semester(best_sem, mod['credits'], df, availableSems)

                            if success:
                                # made space
                                df.at[idx, 'assigned_semester'] = best_sem
                                availableSems.loc[best_sem, 'free_credits'] -= mod['credits']
                                currentSem = currentSem[currentSem['id'] != mod['id']]
                            else:
                                # no space made, credits more than max credits
                                df.at[idx, 'assigned_semester'] = best_sem
                                availableSems.loc[best_sem, 'free_credits'] -= mod['credits']
                                warnings_list.append(
                                    f"Semester {best_sem}: no room could be freed for {mod['id']} - max_credits exceeded there."
                                )

                        # case 2.2: space in free W/S semester
                        else:
                            # best semester: semester with the least space after adding mod
                            best_sem = fitting['free_credits'].idxmin()
                            df.loc[df['id'] == mod['id'], 'assigned_semester'] = best_sem
                            availableSems.loc[best_sem, 'free_credits'] -= mod['credits']

        # again for EN modules
        if not currentSem[currentSem['frequency'].isin(['E', 'N'])].empty:
            for idx, mod in currentSem[currentSem['frequency'].isin(['E', 'N'])].iterrows():
                # working with available sems since all sems can be used
                fitting = availableSems[availableSems['free_credits'] >= mod['credits']]

                # case 2.1: free semesters but not enough space anywhere
                if fitting.empty:
                    # trying to move modules, target the semester with the
                    # most free_credits overall (may still be negative if
                    # everything is already over-booked; that's fine, it's
                    # just the least-bad option and gets a warning below).
                    best_sem = availableSems['free_credits'].idxmax()
                    success = make_space_in_semester(best_sem, mod['credits'], df, availableSems)

                    df.at[idx, 'assigned_semester'] = best_sem
                    availableSems.loc[best_sem, 'free_credits'] -= mod['credits']
                    if not success:
                        warnings_list.append(
                            f"Semester {best_sem}: no room could be freed for {mod['id']} - max_credits exceeded there."
                        )

                # case 2.2: enough space in some semester
                else:
                    # semester with the least space (after adding mod) - keeps
                    # bigger gaps open for later, bigger modules
                    best_sem = fitting['free_credits'].idxmin()
                    df.loc[df['id'] == mod['id'], 'assigned_semester'] = best_sem
                    availableSems.loc[best_sem, 'free_credits'] -= mod['credits']


    # checking if admission requierment modules are before module
    modsWithARs = df[df['AR']!= "{'all': [], 'any': []}"]
    # if there are modules with Ars
    if not modsWithARs.empty:


        
        changes_made = True
        max_iterations = max(10, len(modsWithARs) * 2)
        iterations = 0

        while changes_made and iterations < max_iterations:
            changes_made = False
            iterations += 1

            for idx, row in df[df['AR'] != "{'all': [], 'any': []}"].iterrows():
                # AR to dictionary
                ar_dict = ast.literal_eval(row['AR'])
                required_modules = ar_dict['all'] + ar_dict['any']

                # check every needed module
                for req_mod in required_modules:
                    if req_mod in df['id'].values:
                        req_idx = df[df['id'] == req_mod].index[0]
                        req_sem = df.loc[req_idx, 'assigned_semester']

                        # ar module before module
                        if req_sem >= row['assigned_semester']:
                            new_req_sem = row['assigned_semester']
                            new_own_sem = req_sem
                            req_freq = normalize_frequency(df.loc[req_idx, 'frequency'], warnings_list, req_mod)
                            own_freq = normalize_frequency(row['frequency'], warnings_list, row['id'])
                            if allowed_in_semester(req_freq, new_req_sem, sem_start) and \
                               allowed_in_semester(own_freq, new_own_sem, sem_start):
                                # switch modules
                                df.loc[idx, 'assigned_semester'] = new_own_sem
                                df.loc[req_idx, 'assigned_semester'] = new_req_sem
                                changes_made = True
                                break
                            # swap would break one module's frequency fit -
                            # leave it for now, check the next requirement /
                            # next pass instead of forcing an invalid swap.

        # final check: log anything that's still broken instead of shipping
        # a plan with silent prerequisite violations.
        unresolved = []
        for idx, row in df[df['AR'] != "{'all': [], 'any': []}"].iterrows():
            ar_dict = ast.literal_eval(row['AR'])
            for req_mod in ar_dict['all'] + ar_dict['any']:
                if req_mod in df['id'].values:
                    req_idx = df[df['id'] == req_mod].index[0]
                    if df.loc[req_idx, 'assigned_semester'] >= row['assigned_semester']:
                        unresolved.append(f"{row['id']} is scheduled in/before its prerequisite {req_mod}")
        if unresolved:
            preview = "; ".join(unresolved[:5]) + (f"; +{len(unresolved) - 5} more" if len(unresolved) > 5 else "")
            warnings_list.append(f"{len(unresolved)} prerequisite ordering issue(s) could not be resolved automatically: {preview}")

    conn = sqlite3.connect(DB_SELECTION)
    for _, row in df.iterrows():
        conn.execute(
            'UPDATE module_selection SET assigned_semester = ? WHERE id = ?',
            (int(row['assigned_semester']) if pd.notna(row['assigned_semester']) else 0, row["id"])
        )
    conn.commit()
    conn.close()

    try:
        set_setting("plan_warnings", json.dumps(warnings_list))
    except Exception:
        pass  # warnings are a nice-to-have, never let logging them break plan creation

    return 1

def calculate_grade():
    
    conn = get_db_connection(DB_SELECTION)
    ensure_column(conn, "module_selection", "assigned_semester", "INTEGER DEFAULT 0")
    df =  pd.read_sql_query(f"""SELECT id, credits, RPK, AR, "assigned_semester", frequency, failure_rates, RS FROM module_selection""", conn)
    conn.commit()
    conn.close()

