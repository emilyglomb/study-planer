import pdfplumber
import pandas as pd
import re

path = r'data\data_processing\raw_data\ModulVZ_AngewandteInformatik.pdf'

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
                    })

def safe_int(value, default=None):
    """
    Safely converts a value to integer, handling strings, None, and invalid inputs.

    Args:
        value (any): Input value to convert to int (str, int, float, None, etc.).
        default (int or None, optional): Return value if conversion fails. Defaults to None.

    Returns:
        int or default: Converted integer or default value if conversion fails.

    Examples:
         safe_int('123')
        123
         safe_int('abc', 0)
        0
         safe_int(None)
        None
    """
    try:
        return int(str(value).strip())
    except (ValueError, AttributeError):
        return default

def parse_workload_cell(cell, data):
    """
    Extracts attendance and self-study times from a workload cell string using regex.

    Parses German/English workload descriptions (e.g. "Präsenzzeit: 56h") and stores
    extracted hours as integers in the data dict. Returns True if self-study time found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing workload info.
        data (dict): Mutable dict to store 'attendance_time' and 'selfstudy_time'.

    Returns:
        bool: True if self-study time was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_workload_cell("Präsenzzeit: 56h Selbststudium: 124h", data)
        True
        > data
        {'attendance_time': 56, 'selfstudy_time': 124}
        
        > parse_workload_cell("Attendance time: 40h", data)
        False
        > data['attendance_time']
        40
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(Präsenzzeit|Attendance time)[:\s]+(\d+)', cell_str)
    if match:
        data['attendance_time'] = safe_int(match.group(2))
    match = re.search(r'(Selbststudium|Self-study time)[:\s]+(\d+)', cell_str)
    if match:
        data['selfstudy_time'] = safe_int(match.group(2))
        return True
    return False

def parse_id_cell(cell, data):
    """
    Extracts module id and name from an id cell string using regex.

    Parses German/English id cell (e.g. "Modul B.Inf.1842: Programmieren für Data Scientists: Python") and stores
    extracted id and name as strings in the data dict. Returns True if both is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'id' and 'name'.

    Returns:
        bool: True if id and name was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Modul B.Inf.1842: Programmieren für Data Scientists: Python", data)
        True
        > data
        {'id': 'B.Inf.1842', 'name': 'Programmieren für Data Scientists: Python'}
        
    """
    cell_str = str(cell) if cell else ""
    
    cleaned = re.sub(r'\n\s*', ' ', cell_str)  
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
 
    match = re.search(r'Modul[e]?\s+([^\s:]+)\s*:\s*(.*?)(?=\s*English\s+Title:|$)' , cleaned, re.IGNORECASE)

    
    if match:
        data['id'] = match.group(1).strip()
        data['name'] = match.group(2).strip()
        return True
    return False

def parse_credits_cell(cell, data):
    """
    Extracts credits and wlh/sws from a credit cell string using regex.

    Parses German/English credits cell (e.g. "5 C 3 SWS") and stores
    extracted credits and wlh as ints in the data dict. Returns True if wlh is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'credits' and 'wlh'.

    Returns:
        bool: True if wlh was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("5 C 3 SWS", data)
        True
        > data
        {'credits': 5, 'WLH': 3}
        
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(\d+)\s*C', cell_str)
    if match:
        data['credits'] = safe_int(match.group(1))
    match = re.search(r'(\d+)\s*(SWS|WLH)', cell_str)
    if match:
        data['WLH'] = safe_int(match.group(1))
        return True
    return False

def parse_examination_cell(cell, data):
    """
    Extracts examination type and examination prerequisites from an examination cell string using regex.

    Parses German/English examination cell (e.g. "Prüfung: Projektarbeit und mündliche Prüfung, unbenotet 
    Prüfungsvorleistungen: Lösung von 65% der Programmieraufgaben") and stores
    extracted examination type and examination as strings in the data dict. Returns True if type is found, 
    because prerequisites are optional.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'examination_type' and 'examination_prerequisites'.

    Returns:
        bool: True if examnation type was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Prüfung: Projektarbeit und mündliche Prüfung, unbenotet 
                        Prüfungsvorleistungen: Lösung von 65% der Programmieraufgaben", data)
        True
        > data
        {'examination_type':  'Projektarbeit und mündliche Prüfung, unbenotet', 
        'examination_prerequisites': 'Lösung von 65% der Programmieraufgaben'}
        
    """
    cell_str = str(cell) if cell else ""
    booli = False
    match = re.search(r'(Prüfung|Examination):\s*(.*?)\s*\(', cell_str)
    if match:
        data['examination_type'] = match.group(2).strip()
        booli = True
    match = re.search(r'(Prüfungsvorleistungen|Examination prerequisites):\s+(.*?)(?:\n|$)', cell_str)
    if match:
        data['examination_prerequisites'] = match.group(2).strip()
    return booli

def parse_admission_cell(cell, data):
    """
    Extracts Admission Requierments from a cadmission cell string using regex.

    Parses German/English admission cell (e.g. "Zugangsvoraussetzungen: keine") and stores
    extracted ARs as String in the data dict. Returns True if AR is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'AR'.

    Returns:
        bool: True if AR was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Zugangsvoraussetzungen: keine", data)
        True
        > data
        {'AR': 'keine'}

        > data = {}
        > parse_id_cell("Zugangsvoraussetzungen: B.Inf.1101", data)
        True
        > data
        {'AR': 'B.Inf:1101'}
        
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(Zugangsvoraussetzungen|Admission requirements):\s+(.*?)(?:\n|$)', cell_str)
    if match:
        data['AR'] = match.group(2).strip()
        return True
    return False

def parse_rpk_cell(cell, data):
    """
    Extracts Recommended Previous Knowledge from a rpk cell string using regex.

    Parses German/English rpk cell (e.g. "Empfohlene Vorkenntnisse: keine") and stores
    extracted RPKs as String in the data dict. Returns True if RPK is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'RPK'.

    Returns:
        bool: True if RPK was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Empfohlene Vorkenntnisse: keine", data)
        True
        > data
        {'RPK': 'keine'}

        > data = {}
        > parse_id_cell("ZEmpfohlene Vorkenntnisse: B.Inf.1101, B.Inf.1102, B.Inf.1801, B.Inf.1802", data)
        True
        > data
        {'RPK': 'B.Inf.1101, B.Inf.1102, B.Inf.1801, B.Inf.1802'}
        
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(Empfohlene Vorkenntnisse|Recommended previous knowledge):\s+(.*?)(?:\n|$)', cell_str)
    if match:
        data['RPK'] = match.group(2).strip()
        return True
    return False

def parse_frequency_cell(cell, data):
    """
    Extracts frequency from a frequency cell string using regex.

    Parses German/English frequency cell (e.g. "Angebotshäufigkeit: jedes Semester") and stores
    extracted frequency as String in the data dict. Returns True if frequency is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'frequency'.

    Returns:
        bool: True if frequency was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Angebotshäufigkeit: jedes Semester", data)
        True
        > data
        {'frequency': 'jedes Semester'} 
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(Angebotshäufigkeit|Course frequency):\s+(.*?)(?:\n|$)', cell_str)
    if match:
        data['frequency'] = match.group(2).strip()
        return True
    return False

def parse_duration_cell(cell, data):
    """
    Extracts duration from a duration cell string using regex.

    Parses German/English duration cell (e.g. "Dauer:1 Semester") and stores
    extracted integer in the data dict. Returns True if duration is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'duration'.

    Returns:
        bool: True if duration was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Dauer: 1 Semester", data)
        True
        > data
        {'duration': '1'} 
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(Dauer|Duration):\s+(.*?)(?:\n|$)', cell_str)
    if match:
        # Extrahiere nur die Zahl
        duration_str = match.group(2).strip()
        duration_num = safe_int(''.join(filter(str.isdigit, duration_str)))
        if duration_num is not None:
            data['duration'] = duration_num
        return True
    return False

def parse_semester_cell(cell, data):
    """
    Extracts recommended semester from a semester cell string using regex.

    Parses German/English semester cell (e.g. "Empfohlenes Fachsemester: 1") and stores
    extracted semester as string in the data dict. Returns True if recomended semester is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'RS'.

    Returns:
        bool: True if RS was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Empfohlenes Fachsemester: 1", data)
        True
        > data
        {'RS': '1'} 
        
        > data = {}
        > parse_id_cell("Empfohlenes Fachsemester:1 - 3", data)
        True
        > data
        {'RS': '1-3'} 
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(Empfohlenes Fachsemester|Recommended semester):\s+(.*?)(?:\n|$)', cell_str)
    if match:
        data['RS'] = match.group(2)
        return True
    return False

def parse_note_cell(cell,data):
    """
    Extracts note from a note cell string using regex.

    Parses German/English note cell (e.g. "Bemerkungen: Die Klausuren werden als E-Prüfungen durchgeführt") and stores
    extracted note as string in the data dict. Returns True if recomended note is found.

    Args:
        cell (any): Raw cell content (str, None, etc.) containing id info.
        data (dict): Mutable dict to store 'note'.

    Returns:
        bool: True if note was successfully extracted, False otherwise.

    Examples:
        > data = {}
        > parse_id_cell("Bemerkungen: Die Klausuren werden als E-Prüfungen durchgeführt", data)
        True
        > data
        {'note': 'Die Klausuren werden als E-Prüfungen durchgeführt'} 
 
    """
    cell_str = str(cell) if cell else ""
    match = re.search(r'(Bemerkungen|Additional notes and regulations):\s*(.*)', cell_str)
    if match:
        data['note'] = match.group(2)
        return True
    return False

def parse_page(curr_module):
    """
    Extracts data from a module page using pefore defined function.

    Parses German/English module page and stores extracted data
    as data dict. Returns the dict.

    Args:
        curr_module: module page

    Returns:
        dict: data dict filled

    Examples:
        > parse_id_cell(curr_module)
        True
        > data
        {
                    'id': 'B.Inf.1842',
                    'name': 'Programmieren für Data Scientists: Python',
                    'credits': 5,
                    'WLH': 3, 
                    'attendance_time': 42,
                    'selfstudy_time': 108,
                    'AR': 'keine', 
                    'RPK': 'keine', # recomended previous knowledge
                    'frequency': 'jedes Semester', 
                    'duration': 1,
                    'RS': '1', # recomended Semester 
                    'examination_type': 'Projektarbeit und mündliche Prüfung, unbenotet', 
                    'examination_prerequisites': 'Lösung von 65% der Programmieraufgaben',
                    'note': nan
                    } 
 
    """
    data = {}
    
    # parsing every page as modules can have more than one page
    for mod in curr_module:
        # extractng table from page
        tables = mod.extract_tables()
        if not tables:
            continue
        
        # keywords for data so that not every cell is passes for every data type
        parsers = {
            'id': ('modul', parse_id_cell),
            'workload': ('arbeitsaufwand workload', parse_workload_cell),
            'credits': ('c sws wlh', parse_credits_cell),
            'examination': ('prüfung examination', parse_examination_cell),
            'admission': ('zugang admission', parse_admission_cell),
            'rpk': ('vorkenntnisse knowledge', parse_rpk_cell),
            'frequency': ('häufigkeit frequency', parse_frequency_cell),
            'duration': ('dauer duration', parse_duration_cell),
            'semester': ('fachsemester semester', parse_semester_cell),
            'note': ('bemerkungen notes', parse_note_cell)
        }
        
        flags = list(parsers.keys())
        # bools for each data type
        flag_values = {f: False for f in flags}
        
        found_all = False
        # parsing each table 
        for table in tables:
            # if all data found stop parsing
            if found_all:
                break
            # parsing each row in table
            for row in table:
                # again stop parsing if all were found
                if found_all:
                    break
                # parsing every cell in the row
                for cell in row:
                    # checking if all were found
                    if all(flag_values.values()):
                        found_all = True
                        break
                    
                    cell_lower = str(cell).lower() if cell else ""
                    
                    # parsing for each data type
                    for flag in flags:
                        # if data type has not been found and parser keywords are in cell use 
                        # parser specific function
                        if (not flag_values[flag] 
                            and any(kw in cell_lower for kw in parsers[flag][0].split())):
                            success = parsers[flag][1](cell, data)
                            flag_values[flag] = success
                            # if data has been extraxted move to next cell as no more info can be extrated from
                            # this cell
                            if success:
                                break
    
    return data


# opening module handbook with pdf plumber
with pdfplumber.open(path) as pdf:
    curr_page = pdf.pages[0]
    curr_name = curr_page.extract_text().split('\n')[0] # module name at the top of the page
    curr_module = [curr_page]
    for i in range(1, len(pdf.pages)):
            next_page = pdf.pages[i]
            next_name = next_page.extract_text().split('\n')[0]
            
            if next_name == curr_name: # checking if current and next page contain the same module
                curr_module.append(next_page)
            else:
                df.loc[len(df)] = parse_page(curr_module)
                curr_module = [next_page]
                curr_name = next_name
    df.loc[len(df)] = parse_page(curr_module) # saving last module

# turning dataframe to csv 
df.to_csv(r'data\data_processing\module_data.csv', index = False)