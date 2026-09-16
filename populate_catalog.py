import sqlite3

def get_connection():
    return sqlite3.connect('/opt/varol/database.db')

def init_catalog():
    conn = get_connection()
    c = conn.cursor()
    
    categories = [
        "Weight Management & Metabolic Regulation",
        "Metabolic Activation & Cellular Energy",
        "Muscle Growth & Sports Regeneration",
        "Tissue Regeneration & Injury Recovery",
        "Hormonal Balance & Endocrine Support",
        "Growth Hormone Stimulation",
        "Pigmentation & Melanocortin System Activation",
        "Skin, Cellular Renewal & Anti-Ageing"
    ]
    
    for cat in categories:
        c.execute("INSERT INTO shop_categories (name_ru, name_en, name_lt) VALUES (?, ?, ?)", (cat, cat, cat))
        
    conn.commit()
    
    # Products
    products = [
        (1, "SLIMERIX (Semaglutide)", "GLP-1 receptor agonist for weight control."),
        (1, "ZONJERO (Tirzepatide)", "GLP-1 and GIP receptor agonist."),
        (1, "REVYTAL (Retatrutide)", "Triple GLP-1, GIP and GCGR receptor agonist."),
        (2, "MOTS-C", "Mitochondrial peptide involved in cellular energy."),
        (2, "NAD+", "A key molecule involved in cellular energy."),
        (3, "PEG-MGF", "Pegylated Mechano Growth Factor."),
        (3, "IGF-1 LR3", "Insulin-Like Growth Factor-1 Long R3."),
        (4, "BPC-157 + TB-500", "Peptide Regeneration Complex."),
        (5, "HGH 100 IU", "Human Growth Hormone."),
        (5, "HCG 10 000 IU", "Human Chorionic Gonadotropin."),
        (5, "HMG 75 IU", "FSH and LH analogue."),
        (6, "IPAMORELIN", "Growth hormone secretagogue."),
        (6, "GHRP-2 + CJC-1295 (without DAC)", "Peptide combination for pulsatile growth hormone secretion."),
        (7, "MELANOTAN 2", "Synthetic melanocortin peptide."),
        (8, "GHK-Cu (Copper Peptide)", "Naturally occurring copper-binding tripeptide."),
        (8, "EXOSOMOS", "Wharton’s Jelly Exosomes.")
    ]
    
    for cat_id, name, desc in products:
        c.execute('''
            INSERT INTO shop_products (category_id, name_ru, name_en, name_lt, desc_ru, desc_en, desc_lt, price)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0.0)
        ''', (cat_id, name, name, name, desc, desc, desc))
        
    conn.commit()
    conn.close()
    print("Catalog populated successfully.")

if __name__ == "__main__":
    init_catalog()
