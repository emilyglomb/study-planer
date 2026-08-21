import os
import sqlite3
import pandas as pd

SELECTION_DB_PATH = 'data/module_selection.db'
MODULES_DB_PATH = 'data/modules.db'
MODULE_DATA_CSV = 'data/data_processing/module_data_final.csv'

COMPULSORY_MODULES = ['B.Inf.1101', 'B.Inf.1103', 'B.Inf.1801', 'B.Inf.1802', 'B.Inf.1803', 'B.Inf.1190']


def _build_module_selection_db():
    """Creates module_selection.db from scratch (empty selection + requirements_check table)."""
    conn_selection = sqlite3.connect(SELECTION_DB_PATH)
    df = pd.DataFrame({
                        'id': pd.Series(dtype='str'),
                        'name': pd.Series(dtype='str'),
                        'credits': pd.Series (dtype='int8'),
                        'WLH': pd.Series(dtype='int8'), # workload hours
                        'attendance_time': pd.Series(dtype='int32'),
                        'selfstudy_time': pd.Series(dtype='int32'),
                        'AR': pd.Series(dtype='str'), # admission requierements
                        'RPK': pd.Series(dtype='str'), # recomended previous knowledge
                        'frequency': pd.Series(dtype='str'), # course availability: W for Wintersemester, S for Summmersemester, B for both
                        'duration': pd.Series(dtype='int8'),
                        'RS': pd.Series(dtype='str'), # recomended Semester
                        'examination_type': pd.Series(dtype='str'),
                        'examination_prerequisites': pd.Series(dtype='str'),
                        'note': pd.Series(dtype='str'),
                        'study_area': pd.Series(dtype='str'),
                        'avg_grade': pd.Series(dtype='float'),
                        'failure_rates': pd.Series(dtype='float'),
                        'study_restriction': pd.Series(dtype='str'),
                        'difficulty' :  pd.Series(dtype='str')
                        })

    # creating database from empty df
    df.to_sql('module_selection', conn_selection, if_exists='replace', index=False)

    cursor = conn_selection.cursor()
    # adding one more column
    cursor.execute("""
        ALTER TABLE module_selection
        ADD COLUMN semester INTEGER DEFAULT NULL
        """)

    # creating requierments table in database which contins requierments specific to the student
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requirements_check (
            requirement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_area TEXT NOT NULL,
            study_area_name TEXT,
            requirement_type TEXT NOT NULL,
            min_value INTEGER,
            description TEXT,
            conditional_on TEXT,
            exclude_area TEXT,
            fulfilled INTEGER NOT NULL DEFAULT 0
        )""")

    # mandotary requierments
    requirements_data = [
        ('I', 'Angewandte Informatik (B.Sc.)', 'MIN_CREDITS', 180, None, None, 'At least 180 ECTS'),

        ('I.1', 'Fachstudium', 'MIN_CREDITS', 87, None, None, 'At least 87 ECTS'),
        ('I.1.a', 'Grundlagen der Informatik', 'ALL_MANDATORY', 20, None, None, 'B.Inf.1101 und B.Inf.1103 erforderlich'),

        ('I.1.b', 'Mathematische Grundlagen der Informatik', 'MIN_CREDITS', 27, None, None, 'At least 27 ECTS'),
        ('I.1.b.aa', 'Grundlagen der Mathematik', 'MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.1.b.bb', 'Stochastik', 'MIN_CREDITS', 9, None, None, 'At least 9 ECTS'),

        ('I.1.c', 'Kerninformatik', 'MIN_CREDITS', 40, None, None, 'At least 40 ECTS'),
        ('I.1.c.aa', 'Wahlpflichtmodule', 'MIN_CREDITS', 20, None, None, 'At least 20 ECTS'),
        ('I.1.c.bb', 'Wahlmodule', 'MIN_CREDITS', 0, None, None, 'Any elective modules'),

        ('I.2', 'Professionalisierungsbereich', 'MIN_CREDITS', 78, None, 'I.1.b.aa.iii', 'At least 78 ECTS'),
        ('I.2', 'Professionalisierungsbereich', 'MIN_CREDITS', 72, 'I.1.b.aa.iii', None, 'If Math for physics and not these specializations'),

        ('I.2.a', 'Studienschwerpunkte', 'MIN_CREDITS', 42, None, 'I.1.b.aa.iii', 'At least 42 ECTS'),
        ('I.2.a', 'Studienschwerpunkte', 'MIN_CREDITS', 36, 'I.1.b.aa.iii', 'I.2.a.II, I.2.a.III, I.2.a.IV, I.2.a.V, I.2.a.VI, I.2.a.VII, I.2.a.XI, I.2.a.XII', 'At least 36 ECTS'),

        ('I.2.b', 'Schlüsselkompetenzen', 'MIN_CREDITS', 21, None, None, 'At least 21 ECTS'),
        ('I.2.b.aa', 'Berufsspezifische Schlüsselkompetenzen (Pflichtmodule)', 'ALL_MANDATORY', 16, None, None, 'All modules'),
        ('I.2.b.bb', 'Berufsspezifische Schlüsselkompetenzen (Wahlmodule)', 'MIN_CREDITS', 0, None, None, 'Any elective modules'),

        ('I.2.c', 'Wahlbereich', 'MIN_CREDITS', 0, None, None, 'Any modules from 2.a and 2.b'),

        ('I.3', 'Bachelorarbeit', 'ALL_MANDATORY', 12, None, None, 'Bachelor thesis (12 ECTS)')
    ]

    cursor.executemany("""
        INSERT INTO requirements_check
        (study_area, study_area_name, requirement_type, min_value, conditional_on, exclude_area, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, requirements_data)

    conn_selection.commit()
    conn_selection.close()


def _build_modules_db():
    """Creates modules.db from the module catalogue CSV plus the requirements hierarchy."""
    conn_modules = sqlite3.connect(MODULES_DB_PATH)
    cursor = conn_modules.cursor()
    # filling module db with all modules
    df_modules = pd.read_csv(MODULE_DATA_CSV)
    df_modules.to_sql('modules', conn_modules, if_exists='replace', index=False)

    cursor.execute("DROP TABLE IF EXISTS requirements")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requirements (
            requirement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_area TEXT NOT NULL,
            study_area_name TEXT NOT NULL,
            requirement_type TEXT NOT NULL,
            min_value INTEGER,
            description TEXT,
            conditional_on TEXT,
            exclude_area TEXT
        )""")

    # ALL REQUIREMENTS DATA
    requirements_data = [
        ('I', 'Angewandte Informatik (B.Sc.)', 'MIN_CREDITS', 180, None, None, 'At least 180 ECTS'),

        ('I.1', 'Fachstudium', 'MIN_CREDITS', 87, None, None, 'At least 87 ECTS'),
        ('I.1.a', 'Grundlagen der Informatik', 'ALL_MANDATORY', 20, None, None, 'B.Inf.1101 und B.Inf.1103 erforderlich'),

        ('I.1.b', 'Mathematische Grundlagen der Informatik', 'MIN_CREDITS', 27, None, None, 'At least 27 ECTS'),
        ('I.1.b.aa', 'Grundlagen der Mathematik', 'MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.1.b.aa.i', 'Mathematik für Informationswissenschaften', 'ALL_MANDATORY', 18, None, None, 'B.Mat.0011 + B.Mat.0012'),
        ('I.1.b.aa.ii', 'Analysis, Analytische Geometrie und Lineare Algebra','ALL_MANDATORY', 18, None, None, 'B.Mat.0841 + B.Mat.0842'),
        ('I.1.b.aa.iii', 'Mathematik für Studierende der Physik','ALL_MANDATORY', 24, None, None, 'B.Mat.0831 + B.Mat.0832'),
        ('I.1.b.bb', 'Stochastik','MIN_CREDITS', 9, None, None, 'At least 9 ECTS'),

        ('I.1.c', 'Kerninformatik','MIN_CREDITS', 40, None, None, 'At least 40 ECTS'),
        ('I.1.c.aa', 'Wahlpflichtmodule','MIN_CREDITS', 20, None, None, 'At least 20 ECTS'),
        ('I.1.c.bb', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective modules'),

        ('I.2', 'Professionalisierungsbereich','MIN_CREDITS', 78, None, 'I.1.b.aa.iii', 'At least 78 ECTS'),
        ('I.2', 'Professionalisierungsbereich','MIN_CREDITS', 72, 'I.1.b.aa.iii', None, 'If Math for physics and not these specializations'),

        ('I.2.a', 'Studienschwerpunkte','MIN_CREDITS', 42, None, 'I.1.b.aa.iii', 'At least 42 ECTS'),
        ('I.2.a', 'Studienschwerpunkte','MIN_CREDITS', 36, 'I.1.b.aa.iii', 'I.2.a.II, I.2.a.III, I.2.a.IV, I.2.a.V, I.2.a.VI, I.2.a.VII, I.2.a.XI, I.2.a.XII', 'At least 36 ECTS'),

        ('I.2.a.II', 'Bioinformatik','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.II.1', 'Themengebiet "Bioinformatik"','MIN_CREDITS', 21, None, None, 'At least 21 ECTS'),
        ('I.2.a.II.1.a', 'Wahlpflichtmodule I','ALL_MANDATORY', 11, None, None, 'Every Module'),
        ('I.2.a.II.1.b', 'Wahlpflichtmodule II','MIN_CREDITS', 10, None, None, 'At least 10 ECTS'),
        ('I.2.a.II.1.c', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Can be chosen'),
        ('I.2.a.II.2', 'Themengebiet "Biologie"','MIN_CREDITS', 14, None, None, 'At least 14 ECTS'),
        ('I.2.a.II.2.a', 'Wahlpflichtmodule','ALL_MANDATORY', 14, None, None, 'Every Module'),
        ('I.2.a.II.2.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.a.III', 'Geoinformatik','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.III.1', 'Themengebiet "Geoinformatik"','ALL_MANDATORY', 22, None, None, 'Every Module'),
        ('I.2.a.III.2', 'Themengebiet "Geographie"','MIN_CREDITS', 20, None, None, 'At least 20 ECTS'),
        ('I.2.a.III.2.a', 'Wahlpflichtmodule I','ALL_MANDATORY', 13, None, None, 'Every Module'),
        ('I.2.a.III.2.b', 'Wahlpflichtmodule II','MIN_CREDITS', 7, None, None, 'At least 7 ECTS'),

        ('I.2.a.IV', 'Informatik der Ökosysteme','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.IV.1', 'Themengebiet "Informatik der Ökosysteme"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.IV.1.a', 'Wahlpflichtmodule','ALL_MANDATORY', 18, None, None, 'Every Module'),
        ('I.2.a.IV.1.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),
        ('I.2.a.IV.2', 'Themengebiet "Forstwissenschaften/Waldökologie"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.IV.2.a', 'Wahlpflichtmodule','MIN_CREDITS', 12, None, None, 'At least 12 ECTS'),
        ('I.2.a.IV.2.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.a.V', 'Medizinische Informatik','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.V.1', 'Themengebiet "Medizinische Informatik"','MIN_CREDITS', 21, None, None, 'At least 21 ECTS'),
        ('I.2.a.V.1.a', 'Wahlpflichtmodule','ALL_MANDATORY', 21, None, None, 'Every Module'),
        ('I.2.a.V.1.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),
        ('I.2.a.V.2', 'Themengebiet "Gesundheitssystem"','MIN_CREDITS', 16, None, None, 'At least 16 ECTS'),
        ('I.2.a.V.2.a', 'Wahlpflichtmodule','ALL_MANDATORY', 16, None, None, 'Every Module'),
        ('I.2.a.V.2.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.a.VI', 'Recht der Informatik','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.VI.1', 'Themengebiet "Recht der Informatik"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.VI.1.a', 'Wahlpflichtmodule','ALL_MANDATORY', 18, None, None, 'Every Module'),
        ('I.2.a.VI.1.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),
        ('I.2.a.VI.2', 'Themengebiet "Rechtswissenschaftliche Grundlagen"','MIN_CREDITS', 12, None, None, 'At least 12 ECTS'),
        ('I.2.a.VI.2.a', 'Wahlpflichtmodule I','MIN_CREDITS', 8, None, None, 'At least 8 ECTS'),
        ('I.2.a.VI.2.b', 'Wahlpflichtmodule II','MIN_CREDITS', 4, None, None, 'At least 4 ECTS'),
        ('I.2.a.VI.2.c', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.a.VII', 'Wirtschaftsinformatik','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.VII.1', 'Themengebiet "Wirtschaftsinformatik"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.VII.1.a', 'Wahlpflichtmodule','ALL_MANDATORY', 18, None, None, 'Every Module'),
        ('I.2.a.VII.1.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),
        ('I.2.a.VII.2', 'Themengebiet "Betriebswirtschaftslehre"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.VII.2.a', 'Wahlpflichtmodule','ALL_MANDATORY', 18, None, None, 'Every Module'),
        ('I.2.a.VII.2.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.a.VIII', 'Wissenschaftliches Rechnen','MIN_CREDITS', 36, 'I.1.b.aa.iii', None, 'If Math for physics'),
        ('I.2.a.VIII', 'Wissenschaftliches Rechnen','MIN_CREDITS', 42, None, 'I.1.b.aa.iii', 'If not Math for physics: At least 42 ECTS'),
        ('I.2.a.VIII.1', 'Themengebiet "Wissenschaftliches Rechnen"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.VIII.1.a', 'Wahlpflichtmodule','MIN_CREDITS', 6, None, None, 'At least 6 ECTS'),
        ('I.2.a.VIII.1.b', 'Wahlpflichtmodule "Praktikum"','MIN_CREDITS', 3, None, None, 'At least 3 ECTS'),
        ('I.2.a.VIII.1.c', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),
        ('I.2.a.VIII.2.a', 'Themengebiet "Mathematik/Naturwissenschaften"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),

        ('I.2.a.IX', 'Neuroinformatik (Computational Neuroscience)','MIN_CREDITS', 36, 'I.1.b.aa.iii', None, 'If Math for physics'),
        ('I.2.a.IX', 'Neuroinformatik (Computational Neuroscience)','MIN_CREDITS', 42, None, 'I.1.b.aa.iii', 'If not Math for physics: At least 42 ECTS'),
        ('I.2.a.IX.1', 'Themengebiet "Neuroinformatik"','MIN_CREDITS', 20, None, None, 'At least 20 ECTS'),
        ('I.2.a.IX.1.a', 'Wahlpflichtmodule I','ALL_MANDATORY', 7, None, None, 'Every Module'),
        ('I.2.a.IX.1.b', 'Wahlpflichtmodule II','MIN_CREDITS', 0, None, None, 'Any elective module'),
        ('I.2.a.IX.2', 'Themengebiet "Mathematik/Naturwissenschaften"','MIN_CREDITS', 16, None, None, 'At least 16 ECTS'),
        ('I.2.a.IX.2.a', 'Wahlpflichtmodule I','MIN_CREDITS', 6, None, None, 'At least 6 ECTS'),
        ('I.2.a.IX.2.b', 'Wahlpflichtmodule II','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.a.X', 'Computational Physics','MIN_CREDITS', 36, 'I.1.b.aa.iii', None, 'If Math for physics'),
        ('I.2.a.X', 'Computational Physics','MIN_CREDITS', 42, None, 'I.1.b.aa.iii', 'If not Math for physics: At least 42 ECTS'),
        ('I.2.a.X.1', 'Erweiterte Grundlagen der Mathematik','MIN_CREDITS', 6, None, 'I.1.b.aa.iii', 'If not Math for physics: at least 6 ECTS'),
        ('I.2.a.X.1', 'Erweiterte Grundlagen der Mathematik','MIN_CREDITS', 0, 'I.1.b.aa.iii', None, 'Any elective modules'),
        ('I.2.a.X.2', 'Themengebiet "Computational Physics"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.X.2.a', 'Wahlpflichtmodule "Wissenschaftliches Rechnen in der Physik"','ALL_MANDATORY', 12, None, None, 'Every module'),
        ('I.2.a.X.2.b', 'Wahlpflichtmodule "Angewandte Informatik in der Physik"','MIN_CREDITS', 6, None, None, 'At least 6 ECTS'),
        ('I.2.a.X.3', 'Themengebiet "Grundlagen der Physik"','MIN_CREDITS', 18, None, None, 'At least 18 ECTS'),
        ('I.2.a.X.3.a', 'Wahlpflichtmodule "Experimentalphysik"','MIN_CREDITS', 12, None, None, 'At least 12 ECTS'),
        ('I.2.a.X.3.b', 'Wahlpflichtmodule "Theoretische Physik"','ALL_MANDATORY', 6, None, None, 'Every Module'),
        ('I.2.a.X.3.c', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.a.XI', 'Anwendungsorientierte Systementwicklung','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.XI.1', 'Themengebiet "Angewandte Informatik/Anwendungsfach"','MIN_CREDITS', 32, None, None, '32 ECTS from 2.a.II-2.a.X'),
        ('I.2.a.XI.2', 'Themengebiet "Systementwicklung"','MIN_CREDITS', 10, None, None, 'At least 10 ECTS'),
        ('I.2.a.XI.2.a', 'Wahlpflichtmodule I','MIN_CREDITS', 5, None, None, 'At least 5 ECTS'),
        ('I.2.a.XI.2.b', 'Wahlpflichtmodule II','MIN_CREDITS', 5, None, None, 'At least 5 ECTS'),

        ('I.2.a.XII', 'Berufsfeldorientierte Angewandte Informatik','MIN_CREDITS', 42, None, None, 'At least 42 ECTS'),
        ('I.2.a.XII.1', 'Themengebiet "Angewandte Informatik/Anwendungsfach"','MIN_CREDITS', 32, None, None, '32 ECTS from 2.a.II-2.a.X'),
        ('I.2.a.XII.2', 'Themengebiet "Systementwicklung"','MIN_CREDITS', 10, None, None, 'At least 10 ECTS'),
        ('I.2.a.XII.2.a', 'Wahlpflichtmodule','MIN_CREDITS', 5, None, None, 'At least 5 ECTS'),
        ('I.2.a.XII.2.b', 'Wahlmodule','MIN_CREDITS', 0, None, None, 'Any elective module'),

        ('I.2.b', 'Schlüsselkompetenzen','MIN_CREDITS', 21, None, None, 'At least 21 ECTS'),
        ('I.2.b.aa', 'Berufsspezifische Schlüsselkompetenzen (Pflichtmodule)','ALL_MANDATORY', 16, None, None, 'All modules'),
        ('I.2.b.bb', 'Berufsspezifische Schlüsselkompetenzen (Wahlmodule)','MIN_CREDITS', 0, None, None, 'Any elective modules'),

        ('I.2.c', 'Wahlbereich','MIN_CREDITS', 0, None, None, 'Any modules from 2.a and 2.b'),

        ('I.3', 'Bachelorarbeit','ALL_MANDATORY', 12, None, None, 'Bachelor thesis (12 ECTS)')
    ]

    # Insert all data
    cursor.executemany("""
        INSERT INTO requirements
        (study_area, study_area_name, requirement_type, min_value, conditional_on, exclude_area, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, requirements_data)

    conn_modules.commit()
    conn_modules.close()


def add_modules(module_ids):
    """
     Gets a module_id in a list, extracts it from the modules database and adds it to the module selection database

     Args:
     module_ids(List): List with module ids

     returns: nothing
    """
    conn_modules = sqlite3.connect(MODULES_DB_PATH)
    df_modules = pd.read_sql_query(
        "SELECT * FROM modules WHERE id IN ({})".format(','.join(['?']*len(module_ids))),
        conn_modules,
        params=module_ids
    )
    conn_modules.close()

    conn_selection = sqlite3.connect(SELECTION_DB_PATH)
    df_modules.to_sql('module_selection', conn_selection, if_exists='append', index=False)
    conn_selection.close()


# Only build the databases the first time they're missing. Rebuilding them on
# every import (like this used to) would wipe module_selection.db - i.e. the
# user's saved module selection and generated plan - on every server restart.
# To force a full rebuild (e.g. after editing module_data_final.csv or the
# requirements data above), just delete the corresponding .db file and
# restart the app.
need_selection_db = not os.path.exists(SELECTION_DB_PATH)
need_modules_db = not os.path.exists(MODULES_DB_PATH)

# modules.db has to exist before we can seed the compulsory modules below,
# so build it first.
if need_modules_db:
    _build_modules_db()

if need_selection_db:
    _build_module_selection_db()
    # seed the selection with the compulsory modules, but only on first build
    add_modules(COMPULSORY_MODULES)
