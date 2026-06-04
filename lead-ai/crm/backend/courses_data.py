"""
Medical Fellowship Programs — exact 68 courses as defined by MedFellow Academy.
These are the ONLY valid course names in the CRM.
"""

FELLOWSHIP_COURSES = [
    # ── Critical Care & Emergency ─────────────────────────────────────────────
    {"course_name": "Fellowship in Emergency Medicine",   "category": "Critical Care & Emergency",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Critical Care",         "category": "Critical Care & Emergency",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Internal Medicine",     "category": "Critical Care & Emergency",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Family Medicine",       "category": "Critical Care & Emergency",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    # ── Cardiology ────────────────────────────────────────────────────────────
    {"course_name": "Fellowship in Clinical Cardiology",   "category": "Cardiology",                  "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Echocardiography",      "category": "Cardiology",                  "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 150000, "currency": "INR"},
    {"course_name": "Fellowship in Interventional Cardiology", "category": "Cardiology",              "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Pediatric Cardiology",  "category": "Cardiology",                  "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Cardiothoracic and Vascular Surgery", "category": "Cardiology",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 600000, "currency": "INR"},
    # ── Obstetrics & Gynecology ───────────────────────────────────────────────
    {"course_name": "Fellowship in Obstetrics & Gynecology",    "category": "Obstetrics & Gynecology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in High Risk Pregnancy",         "category": "Obstetrics & Gynecology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    {"course_name": "Fellowship in Fetal Medicine",              "category": "Obstetrics & Gynecology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Fetal Echocardiography",      "category": "Obstetrics & Gynecology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 200000, "currency": "INR"},
    {"course_name": "Fellowship in Laparoscopy & Hysteroscopy",  "category": "Obstetrics & Gynecology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    {"course_name": "Fellowship in Cosmetic Gynecology",         "category": "Obstetrics & Gynecology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 250000, "currency": "INR"},
    {"course_name": "Fellowship in Gynaecological Oncology",     "category": "Obstetrics & Gynecology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    # ── Reproductive Medicine & IVF ───────────────────────────────────────────
    {"course_name": "Fellowship in Reproductive Medicine", "category": "Reproductive Medicine & IVF", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Embryology",            "category": "Reproductive Medicine & IVF", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    # ── Diabetes & Endocrinology ──────────────────────────────────────────────
    {"course_name": "Fellowship in Diabetology (Diabetes Mellitus)", "category": "Diabetes & Endocrinology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 250000, "currency": "INR"},
    {"course_name": "Fellowship in Endocrinology",         "category": "Diabetes & Endocrinology",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Paediatric Endocrinology", "category": "Diabetes & Endocrinology", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    # ── Gastroenterology ──────────────────────────────────────────────────────
    {"course_name": "Fellowship in Gastroenterology",      "category": "Gastroenterology",            "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in GI Endoscopy",          "category": "Gastroenterology",            "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    # ── Dermatology & Aesthetics ──────────────────────────────────────────────
    {"course_name": "Fellowship in Dermatology",           "category": "Dermatology & Aesthetics",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    {"course_name": "Fellowship in Trichology",            "category": "Dermatology & Aesthetics",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 150000, "currency": "INR"},
    {"course_name": "Fellowship in Cosmetology & Aesthetic Medicine", "category": "Dermatology & Aesthetics", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    # ── Surgery ───────────────────────────────────────────────────────────────
    {"course_name": "Fellowship in General Surgery",       "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Minimal Access Surgery","category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Arthroscopy & Arthroplasty", "category": "Surgery",                "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Orthopedics",           "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Spinal Cord Surgery",   "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Spine Medicine",        "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Neurosurgery",          "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 600000, "currency": "INR"},
    {"course_name": "Fellowship in Plastic Surgery",       "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Microsurgery",          "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Vascular Surgery",      "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Paediatric Surgery",    "category": "Surgery",                     "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    # ── Oncology ──────────────────────────────────────────────────────────────
    {"course_name": "Fellowship in Surgical Oncology",     "category": "Oncology",                    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Medical Oncology",      "category": "Oncology",                    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Head and Neck Oncology","category": "Oncology",                    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Endocrine and Breast Onco Surgery", "category": "Oncology",        "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Oral Oncology",         "category": "Oncology",                    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    # ── Paediatrics ───────────────────────────────────────────────────────────
    {"course_name": "Fellowship in Pediatrics",            "category": "Paediatrics",                 "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Neonatology",           "category": "Paediatrics",                 "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    {"course_name": "Fellowship in Pediatric Neurology",   "category": "Paediatrics",                 "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Paediatric Echocardiography", "category": "Paediatrics",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 150000, "currency": "INR"},
    # ── Neurology ─────────────────────────────────────────────────────────────
    {"course_name": "Fellowship in Neurology",             "category": "Neurology",                   "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    # ── Radiology & Imaging ───────────────────────────────────────────────────
    {"course_name": "Fellowship in Radiology",             "category": "Radiology & Imaging",         "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Neuroradiology",        "category": "Radiology & Imaging",         "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Interventional Radiology", "category": "Radiology & Imaging",      "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Interventional Neuroradiology", "category": "Radiology & Imaging", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 500000, "currency": "INR"},
    {"course_name": "Fellowship in Musculoskeletal Ultrasound", "category": "Radiology & Imaging",    "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 200000, "currency": "INR"},
    {"course_name": "Fellowship in Vascular Ultrasound",   "category": "Radiology & Imaging",         "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 200000, "currency": "INR"},
    {"course_name": "Fellowship in USG",                   "category": "Radiology & Imaging",         "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 150000, "currency": "INR"},
    # ── Pain & Anaesthesia ────────────────────────────────────────────────────
    {"course_name": "Fellowship in Pain Management",       "category": "Pain & Anaesthesia",          "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 250000, "currency": "INR"},
    {"course_name": "Fellowship in Interventional Pain Management & Regional Anaesthesiology", "category": "Pain & Anaesthesia", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 300000, "currency": "INR"},
    {"course_name": "Fellowship in Anesthesiology",        "category": "Pain & Anaesthesia",          "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    # ── Nephrology & Urology ──────────────────────────────────────────────────
    {"course_name": "Fellowship in Nephrology",            "category": "Nephrology & Urology",        "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Urology",               "category": "Nephrology & Urology",        "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Endourology",           "category": "Nephrology & Urology",        "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    # ── Other Specialties ─────────────────────────────────────────────────────
    {"course_name": "Fellowship in Pulmonary Medicine",    "category": "Other Specialties",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Rheumatology",          "category": "Other Specialties",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 400000, "currency": "INR"},
    {"course_name": "Fellowship in Psychiatry",            "category": "Other Specialties",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Ophthalmology",         "category": "Other Specialties",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 350000, "currency": "INR"},
    {"course_name": "Fellowship in Oral Implantology and Laser Dentistry", "category": "Other Specialties", "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 250000, "currency": "INR"},
    {"course_name": "Fellowship in Maxillofacial Surgery", "category": "Other Specialties",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 450000, "currency": "INR"},
    {"course_name": "Fellowship in Epidemiology",          "category": "Other Specialties",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 200000, "currency": "INR"},
    {"course_name": "Fellowship in Sexology",              "category": "Other Specialties",           "duration": "12 Months", "eligibility": "MBBS/MD/MS or Equivalent", "price": 200000, "currency": "INR"},
]

# Flat list of valid course names (used for validation & dropdowns)
VALID_COURSE_NAMES = [c["course_name"] for c in FELLOWSHIP_COURSES]

# Normalisation map: any messy/short name → canonical course name
# Used during CSV import to auto-correct course names
COURSE_NAME_MAP = {
    # Emergency
    'emergency medicine':                          'Fellowship in Emergency Medicine',
    'fellowship in emergency medicine':            'Fellowship in Emergency Medicine',
    'emergency':                                   'Fellowship in Emergency Medicine',
    'emergency medicine fellowship':               'Fellowship in Emergency Medicine',
    # Critical Care
    'critical care medicine':                      'Fellowship in Critical Care',
    'critical care':                               'Fellowship in Critical Care',
    'fellowship in critical care medicine':        'Fellowship in Critical Care',
    'fellowship in critical care':                 'Fellowship in Critical Care',
    # Internal Medicine
    'internal medicine':                           'Fellowship in Internal Medicine',
    'fellowship in internal medicine':             'Fellowship in Internal Medicine',
    # Family Medicine
    'family medicine':                             'Fellowship in Family Medicine',
    'fellowship in family medicine':               'Fellowship in Family Medicine',
    # Cardiology
    'cardiology':                                  'Fellowship in Clinical Cardiology',
    'fellowship in cardiology':                    'Fellowship in Clinical Cardiology',
    'fellowship in clinical cardiology':           'Fellowship in Clinical Cardiology',
    '2d echocardiography':                         'Fellowship in Echocardiography',
    'fellowship in 2d echocardiography':           'Fellowship in Echocardiography',
    'echocardiography':                            'Fellowship in Echocardiography',
    'interventional cardiology':                   'Fellowship in Interventional Cardiology',
    'fellowship in interventional cardiology':     'Fellowship in Interventional Cardiology',
    'cardiothoracic surgery':                      'Fellowship in Cardiothoracic and Vascular Surgery',
    'fellowship in cardiothoracic surgery':        'Fellowship in Cardiothoracic and Vascular Surgery',
    # OBG
    'gynecology & obstetrics':                     'Fellowship in Obstetrics & Gynecology',
    'obs & gyne':                                  'Fellowship in Obstetrics & Gynecology',
    'fellowship in gynecology & obstetrics':       'Fellowship in Obstetrics & Gynecology',
    'high-risk pregnancy':                         'Fellowship in High Risk Pregnancy',
    'high risk pregnancy':                         'Fellowship in High Risk Pregnancy',
    'fellowship in high-risk pregnancy':           'Fellowship in High Risk Pregnancy',
    'fetal medicine':                              'Fellowship in Fetal Medicine',
    'laparoscopy & hysteroscopy':                  'Fellowship in Laparoscopy & Hysteroscopy',
    'laparo_&_hystero_scopy':                      'Fellowship in Laparoscopy & Hysteroscopy',
    'cosmetic gynecology':                         'Fellowship in Cosmetic Gynecology',
    # Reproductive
    'reproductive medicine':                       'Fellowship in Reproductive Medicine',
    'reproductive':                                'Fellowship in Reproductive Medicine',
    'fellowship in reproductive medicine':         'Fellowship in Reproductive Medicine',
    # Diabetes & Endo
    'diabetes mellitus':                           'Fellowship in Diabetology (Diabetes Mellitus)',
    'fellowship in diabetes mellitus':             'Fellowship in Diabetology (Diabetes Mellitus)',
    'diabetology':                                 'Fellowship in Diabetology (Diabetes Mellitus)',
    'fellowship in diabetology':                   'Fellowship in Diabetology (Diabetes Mellitus)',
    'endocrinology':                               'Fellowship in Endocrinology',
    'pediatric endocrinology':                     'Fellowship in Paediatric Endocrinology',
    'paediatric endocrinology':                    'Fellowship in Paediatric Endocrinology',
    'fellowship in pediatric endocrinology':       'Fellowship in Paediatric Endocrinology',
    # Gastro
    'gastroenterology':                            'Fellowship in Gastroenterology',
    'gi endoscopy':                                'Fellowship in GI Endoscopy',
    'fellowship_in_endoscopy':                     'Fellowship in GI Endoscopy',
    # Dermatology
    'dermatology':                                 'Fellowship in Dermatology',
    'cosmetology':                                 'Fellowship in Cosmetology & Aesthetic Medicine',
    'aesthetic medicine':                          'Fellowship in Cosmetology & Aesthetic Medicine',
    'fellowship in cosmetic & aesthetic medicine': 'Fellowship in Cosmetology & Aesthetic Medicine',
    # Surgery
    'arthroscopy & arthroplasty':                  'Fellowship in Arthroscopy & Arthroplasty',
    'arthroscopy':                                 'Fellowship in Arthroscopy & Arthroplasty',
    'arthroplasty':                                'Fellowship in Arthroscopy & Arthroplasty',
    'fellowship in arthroscopy and arthroplasty':  'Fellowship in Arthroscopy & Arthroplasty',
    'orthopedics':                                 'Fellowship in Orthopedics',
    'fellowship in orthopedics':                   'Fellowship in Orthopedics',
    'minimal access surgery':                      'Fellowship in Minimal Access Surgery',
    'fellowship in minimal access & robotic surgery': 'Fellowship in Minimal Access Surgery',
    # Paediatrics
    'pediatrics':                                  'Fellowship in Pediatrics',
    'neonatology':                                 'Fellowship in Neonatology',
    'pediatric neurology':                         'Fellowship in Pediatric Neurology',
    'pediatric echocardiography':                  'Fellowship in Paediatric Echocardiography',
    'paediatric echocardiography':                 'Fellowship in Paediatric Echocardiography',
    # Neurology
    'neurology':                                   'Fellowship in Neurology',
    'clinical neurology':                          'Fellowship in Neurology',
    # Radiology
    'radiology':                                   'Fellowship in Radiology',
    'interventional radiology':                    'Fellowship in Interventional Radiology',
    # Anesthesia
    'anesthesia':                                  'Fellowship in Anesthesiology',
    'fellowship in anesthesia':                    'Fellowship in Anesthesiology',
    'pain management':                             'Fellowship in Pain Management',
    'fellowship in pain medicine':                 'Fellowship in Pain Management',
    # Nephrology / Urology
    'nephrology':                                  'Fellowship in Nephrology',
    'urology':                                     'Fellowship in Urology',
    # Oncology
    'medical oncology':                            'Fellowship in Medical Oncology',
    'surgical oncology':                           'Fellowship in Surgical Oncology',
    'head & neck oncology':                        'Fellowship in Head and Neck Oncology',
    'head and neck oncology':                      'Fellowship in Head and Neck Oncology',
    # Other
    'pulmonary medicine':                          'Fellowship in Pulmonary Medicine',
    'respiratory medicine':                        'Fellowship in Pulmonary Medicine',
    'rheumatology':                                'Fellowship in Rheumatology',
    'psychiatry':                                  'Fellowship in Psychiatry',
    'psychiatric medicine':                        'Fellowship in Psychiatry',
    'fellowship in psychiatric medicine':          'Fellowship in Psychiatry',
    'maxillofacial and oral surgery':              'Fellowship in Maxillofacial Surgery',
    'fellowship in maxillofacial and oral surgery':'Fellowship in Maxillofacial Surgery',
    'ophthalmology':                               'Fellowship in Ophthalmology',
}
