# StudyPlanner

Web app for planning the B.Sc. Applied Computer Science degree: pick a
specialization and modules, and the planner distributes them across semesters.

## Start

**macOS:** double-click **`start.command`**.
**Windows:** double-click **`start.bat`**.

Both do the same thing: the first run creates a virtual environment and installs
the dependencies; every later run starts instantly and opens the browser at
<http://127.0.0.1:5050/home>. Server output is logged to `server.log`.

Requires Python 3.13 (see `.python-version`; anything in the 3.9-3.14 range
should work).

Manual start (macOS/Linux):

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python frontend.py

Manual start (Windows):

    py -3 -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python frontend.py

## Structure

    Study_Planer/
    ├─ appback.py                        backend: Flask app, planning algorithm, requirement checks
    ├─ frontend.py                       frontend: imports appback (unchanged) and adds the UI routes
    ├─ requirements.txt                  Python dependencies (pinned)
    ├─ .python-version                   Python version (3.13)
    ├─ .gitignore                        excludes venv, caches, generated DBs and logs
    ├─ start.command                     one-click launcher (macOS)
    ├─ start.bat                         one-click launcher (Windows)
    ├─ README.md
    ├─ templates/                        Jinja templates
    │  ├─ base.html                      layout: sidebar, topbar, theme loading
    │  ├─ home.html                      dashboard
    │  ├─ overview.html                  full plan with grade entry and module moving
    │  ├─ plan.html                      five-step plan creation form
    │  ├─ statistics.html                charts and metrics
    │  ├─ help.html                      FAQ
    │  └─ profile.html                   name, theme, study progress, reset
    ├─ static/
    │  ├─ css/
    │  │  └─ style.css                   design system, three switchable themes
    │  └─ js/
    │     ├─ app.js                      form steps, progress bars, branch/checkbox logic
    │     ├─ stats.js                    statistics page charts
    │     └─ vendor/
    │        └─ chart.umd.min.js         Chart.js (bundled)
    └─ data/
       ├─ modules.db                     generated: module catalogue
       ├─ module_selection.db            generated: user selection, plan, grades
       └─ data_processing/
          ├─ pdfextractor.py             Modulhandbuch PDF -> module_data.csv
          ├─ studyarea.py                study-area hierarchy from studyareas.pdf
          ├─ cleaning.ipynb              cleaning, feature engineering, k-means clustering
          ├─ database.py                 builds the SQLite databases from the cleaned CSV
          ├─ module_data.csv             intermediate extraction result
          ├─ module_data_final.csv       cleaned module catalogue (final)
          └─ raw_data/                   source PDFs + hand-collected grades.txt

`appback.py` imports `add_modules` from `data/data_processing/database.py` and
points `DB_SELECTION`/`DB_MODULES` at `data/module_selection.db` and
`data/modules.db`. The databases are generated at runtime and are not part of
the repository.

`requirements.txt` has three parts: the core packages needed to run the app
(`flask`, `pandas`), `pdfplumber`, needed only if you rerun the PDF extraction
in `data/data_processing/pdfextractor.py` / `studyarea.py`, and
`numpy`/`scikit-learn`/`matplotlib`, needed to rerun
`data/data_processing/cleaning.ipynb` (the k-means module-difficulty
clustering, PCA visualization and model selection). All versions are pinned
(`package~=major.minor.0`); verify the pinned set actually works by creating a
fresh virtual environment and running `pip install -r requirements.txt` there
before submitting.

## How frontend and backend connect

`frontend.py` imports `appback.py`, so both run in **one** Flask server on port
5050: `appback.py` holds the backend logic (database access, the semester-
planning algorithm, requirement checks) and `frontend.py` adds the UI routes
(`/home`, `/overview`, `/plan`, `/statistics`, `/help`, `/profile`) on top,
calling into `appback.py`'s functions directly rather than through HTTP. The
plan page's step-by-step creation form reads the real study-area hierarchy and modules from the database;
on "Create plan" the selected modules are written to `module_selection` and
`assignin_semesters()` builds the plan. An earlier, unused JSON API in
`appback.py` (a leftover from a previous, non-Jinja frontend) and a ~1000-line
dead Plotly statistics function have since been removed, along with 4
temporary debug routes.

## Contributions

### Emily

Emily built the entire data pipeline that turns the university's documents into structured, queryable data. She wrote the PDF extraction in `data/data_processing/pdfextractor.py`, parsing the 200-plus-page Modulhandbuch (`ModulVZ_AngewandteInformatik.pdf`, which has no machine-readable export) with `pdfplumber`: each module's pages are grouped by their header text, tables are extracted per page, and a dedicated regex parser per field (`parse_id_cell`, `parse_workload_cell`, `parse_credits_cell`, `parse_examination_cell`, `parse_admission_cell`, `parse_rpk_cell`, `parse_frequency_cell`, `parse_duration_cell`, `parse_semester_cell`, `parse_note_cell`) pulls out ID, name, credits, attendance and self-study hours, admission requirements, recommended prior knowledge, frequency, duration, recommended semester, examination type and prerequisites, and notes. Each regex is written to match both the German and English wording the handbook alternates between, with a keyword-routing step so every cell is only checked against parsers that could plausibly match it, producing `module_data.csv`.

She also extracted the degree's study-area hierarchy in `data/data_processing/studyarea.py`. Because `studyareas.pdf` has no consistent machine-readable structure and different sections nest one, two or four levels deep with different numbering styles (arabic, roman, single and double letters), she wrote a line-by-line state-machine parser with one branch per structural pattern to assign the correct hierarchical code (e.g. `I.2.a.IX.2.b`) to every module, including modules that legitimately appear under more than one area. Since the university's grade statistics are not exposed through any API or export, she read the pass/fail counts and average grades off the grade website by hand and transcribed them into `data/data_processing/raw_data/grades.txt`, which `cleaning.ipynb`'s `parse_grades()` turns into per-module `avg_grade` and `failure_rates`.

The data cleaning in `data/data_processing/cleaning.ipynb` is hers as well: normalizing the free-text `AR`/`RPK` fields into structured module-ID lists with AND/OR logic for "oder"/"or", collapsing roughly twenty raw frequency strings into `S`/`W`/`E`/`N` codes, mapping about thirty raw examination-type strings onto a consistent vocabulary, and a rule-based `ex_req()` classifier that buckets dozens of different phrasings of the examination prerequisites into a small set of comparable categories. On top of that she did the feature engineering (a recursive RPK-dependency count via `count_all_dependencies()` and an encoded exam-prerequisite difficulty), scaling, a k-means clustering into easy/medium/hard difficulty with model selection via both the elbow method and the silhouette score across k = 2–7, a PCA projection to sanity-check the cluster separation, and a written interpretation of what distinguishes each cluster. The database layer in `data/data_processing/database.py` builds `modules.db` and `module_selection.db` from the cleaned CSV, including the `requirements` table that encodes the actual degree regulations as data (nested minimum-credit and mandatory-module requirements per study area, with conditional variants such as different Professionalisierungsbereich minimums depending on the chosen math track) rather than hardcoding that logic in Python.

On the backend she wrote the requirement-fulfilment checking (`check_all`, `check_requierments`) and the semester-assignment algorithm `assignin_semesters()` in `appback.py`: priority-scored greedy placement weighted by dependency count, credit load and failure rate, frequency constraints for winter- and summer-only modules, a credit-overflow knapsack step, an admission-requirement reordering pass, and RPK-based prerequisite ordering that defers a module to a later semester when its recommended prior knowledge has not been scheduled yet, both across semesters and within a single credit-overflow batch. Finally, she produced the metrics behind the statistics page (`stats_context()` in `frontend.py`, rendered by `templates/statistics.html` and `static/js/stats.js`): credit and workload distribution, grade and failure-rate aggregates, exam-type and study-area breakdowns per semester, the difficulty heatmap, and the module-dependency network derived from the RPK graph.

Emily used an AI assistant (Claude) as a tool for parts of the implementation and for debugging. The overall approach, the parser and cleaning logic, and the data-modelling decisions are her own, and she reviewed and adapted any AI-suggested passages.

### Niklas
Niklas built the frontend and the integration with the backend. The work went through several clearly visible stages. The first user interface was a Streamlit prototype (`front.py`) talking to a JSON API in `appback.py`. That approach was abandoned: Streamlit was too limiting for the layout we wanted, and the HTTP round-trips between two processes made state handling (whose selection is current, when to regenerate the plan) unnecessarily fragile. Niklas replaced it with the current architecture in `frontend.py` a Jinja/Flask UI that imports `appback.py` unchanged and runs in the same process, calling the backend functions directly. What remains is the context-builder layer (`home_context`, `overview_context`, `plan_context`, `stats_context`, `profile_context`) that turns the backend's DataFrames and settings into what the templates render.

The plan creation page took the most iterations. It is a five-step form on `/plan` (specialization, math track, module choice, settings, summary) at whose end the semester plan is generated. The study-area tree on it (`plan_context`, `build_area_tree`) has to reflect the real degree structure

The grade entry on the "Full plan" page (`mark_completed`) was upgradet and a grade above 4.0 must not mark the module as completed and must not count toward the average, but the module should stay visible in the semester where the attempt happened, with an attempt counter and a retry hint that respects the module's offering frequency (retake next semester for modules offered every semester, the semester after next for winter/summer-only ones). Alongside that I built the dashboard (`home_context`), module moving between semesters (`move_module`), the profile page with the editable display name and current-semester setting, and later the "Delete all" reset (`/reset_plan`) that clears selection, plan and grades and re-seeds the compulsory modules — the UI itself went through several simplification passes in which non-functional placeholder elements were removed.

Two integration problems were only found by using the app end to end. `data/data_processing/database.py` originally rebuilt both databases on every import, which wiped the user's selection and plan on every server restart; it now only builds them when the files are missing. And the plan warnings the algorithm produces (over-full semesters, unresolvable orderings) used to disappear silently; they are now persisted via `set_setting("plan_warnings", ...)` and surfaced in the UI. The rest of his work is the visible layer itself the templates, the CSS with the three themes persisted in `localStorage`, the client-side logic in `app.js` (form steps, progress bars, branch/checkbox behaviour) — plus the launchers (`start.command`, `start.bat`) with automatic venv setup, and this README.

Niklas used an AI assistant (Claude) as a tool for parts of the frontend implementation, debugging and small refactorings. The concept, the architecture, all design and product decisions, the integration and the understanding of the code are his own, and he reviewed and adapted any AI-suggested passages.
