import pdfplumber
import pandas as pd
import re

path = r'data\data_processing\raw_data\studyareas.pdf'
df = pd.read_csv('data\data_processing\module_data.csv')
# empty list
df['study_area'] = df['study_area'].apply(lambda x: [] if pd.isna(x) else x)

text = ''
with pdfplumber.open(path) as pdf:
    for page in pdf.pages:
        text += page.extract_text()

lines = text.split('\n')

# Find indices of main sections
idx_1 = lines.index('1. Fachstudium')
idx_2 = lines.index('2. Professionalisierungsbereich')
idx_3 = lines.index('3. Bachelorarbeit')
idx_4 = lines.index('II. Studienschwerpunkt "Bioinformatik"')
idx_5 = lines.index('XIII. Prüfungsformen')

# Extract main sections
fachstudium_1 = lines[idx_1+1:idx_2]
prof_bereich_2 = lines[idx_2+1:idx_3]
bachelor_3 = ('3', lines[idx_3+1:idx_4])
aw_fach_2a = ('2.a', lines[idx_4:idx_5])

# Find indices of subsections within Fachstudium
idx_6 = fachstudium_1.index('a. Studiengebiet "Grundlagen der Informatik"')
idx_7 = fachstudium_1.index('b. Studiengebiet "Mathematische Grundlagen der Informatik"')
idx_8 = fachstudium_1.index('c. Studiengebiet "Kerninformatik"')

# Find indices of subsections within Professionalisierungsbereich
idx_9 = prof_bereich_2.index('b. Schlüsselkompetenzen')
idx_10 = prof_bereich_2.index('cc. Fächerübergreifende Schlüsselkompetenzen (Wahlmodule)')

# Extract subsections with their codes
gdi_1a = ('1.a', fachstudium_1[idx_6+1:idx_7])
mgi_1b = ('1.b', fachstudium_1[idx_7+1:idx_8])
ki_1c = ('1.c', fachstudium_1[idx_8+1:idx_2])
sk_2b = ('2.b', prof_bereich_2[idx_9+1:idx_10])

# Group areas by their processing logic structure
areas1 = [gdi_1a, bachelor_3]  # Simple structure: only modules, no subcategories
areas2 = [ki_1c, sk_2b]  # Structure with one level of subcategories (double letters)
areas3 = [mgi_1b, aw_fach_2a]  # Complex structures with custom naming patterns

# Compile regex patterns once for efficiency
MODULE_ID = re.compile(r'([^\s:]+)\s*:')
DOUBLE_LETTER = re.compile(r'^([a-z])\1\.\s+')
ROMAN_LOWERCASE = re.compile(r'^(i+)\.')
ROMAN_NUMBER = re.compile(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI)\.\s+')
ARABIC_NUMBER = re.compile(r'^(\d+)\.\s+')
SINGLE_LETTER = re.compile(r'^([a-z])\.\s+')


def add_module(module_id, code):
    """
    Add a study area code to a module's studyarea list.
    
    Args:
        module_id (str): The unique identifier of the module to update
        code (str): The study area code to add (e.g., '1.a', '2.b.ii')
    
    Returns:
        None
    
    Description:
        Finds the module by ID in the dataframe and appends the code
        to its studyarea list. Uses vectorized pandas operations.
    """
    df.loc[df['id'] == module_id, 'study_area'] = df.loc[df['id'] == module_id, 'study_area'].apply(
        lambda x: x + [code]
    )


# Process areas1: Simple structure (code + modules, no subcategories)
for area in areas1:
    code = area[0]
    for line in area[1]:
        match = MODULE_ID.search(line)
        if match:
            modul_id = match.group(1).strip()
            add_module(modul_id, code)


# Process areas2: Structure with double-letter subcategories (aa., bb., cc., etc.)
for area in areas2:
    code = None
    for line in area[1]:
        # Check for double-letter pattern (e.g., "aa. ", "bb. ")
        match = DOUBLE_LETTER.search(line.strip())
        if match:
            code = area[0] + '.' + match.group(1) + match.group(1)
            continue
        
        # Extract module ID if code is set
        match = MODULE_ID.search(line)
        if match:
            modul_id = match.group(1).strip()
            add_module(modul_id, code)


# Process mgi_1b: Complex structure with double-letters and roman numerals
# Structure: aa. -> i., ii., iii. -> MODULE_ID
code = None
double_letter_code = None

for line in mgi_1b[1]:
    # Check for double-letter pattern (e.g., "aa. ", "bb. ")
    match = DOUBLE_LETTER.search(line.strip())
    if match:
        double_letter_code = mgi_1b[0] + '.' + match.group(1) + match.group(1)
        code = double_letter_code
        continue
    
    # Check for lowercase roman numeral pattern (e.g., "i. ", "ii. ", "iii. ")
    match = ROMAN_LOWERCASE.search(line.strip())
    if match:
        code = double_letter_code + '.' + match.group(1)
        continue
    
    # Extract module ID if code is set
    match = MODULE_ID.search(line)
    if match:
        modul_id = match.group(1).strip()
        add_module(modul_id, code)



# Process aw_fach_2a: Complex structure with multiple hierarchy levels
# Structure: I., II., III. -> 1., 2., 3. -> a., b., c. -> MODULE_ID
code = None
number_code = None
roman_code = None  # ADD THIS LINE: Track the roman numeral level


for line in aw_fach_2a[1]:
    # Check for uppercase roman numeral pattern (e.g., "I. ", "II. ", "III. ")
    match = ROMAN_NUMBER.search(line.strip())
    if match:
        roman_code = aw_fach_2a[0] + '.' + match.group(1)  # CHANGE: Save to roman_code
        continue
    
    # Check for arabic number pattern (e.g., "1. ", "2. ", "3. ")
    match = ARABIC_NUMBER.search(line.strip())
    if match:
        number_code = roman_code + '.' + match.group(1)  # CHANGE: Build on roman_code
        continue

    # Check for single letter pattern (e.g., "a. ", "b. ", "c. ")
    match = SINGLE_LETTER.search(line.strip())
    if match:
        code = number_code + '.' + match.group(1)
        continue
    
    # Extract module ID if code is set
    match = MODULE_ID.search(line)
    if match:
        modul_id = match.group(1).strip()
        add_module(modul_id, code)
df['study_area'] = df['study_area'].apply(
    lambda lst: ['I.' + code for code in lst])

# Save the updated dataframe with study area assignments
df.to_csv(r'data\data_processing\module_data.csv', index=False)
