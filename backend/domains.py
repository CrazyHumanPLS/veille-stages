"""Domaines de recherche et régions.

Chaque inscrit coche ses domaines et ses régions dans Réglages. Le stock commun, lui, garde toute offre de
stage en France qui touche au moins un de ces domaines.

Le domaine « reseaux » est particulier : ses mots-clés sont ceux de l'onglet Administration (réglages communs
historiques du site). Les autres domaines sont décrits ici.
Pour ajouter un domaine : une entrée de plus dans DOMAINS, avec ses requêtes Adzuna (tous les mots d'une
requête sont obligatoires, et « stage » doit y figurer).
"""
import re
import unicodedata

DOMAINS = {
    "reseaux": {
        "label": "Réseaux, télécoms, cybersécurité, cloud",
        # strong / tech / negative / adzuna : lus dans les réglages communs (scoring.criteria)
    },
    "embarque": {
        "label": "Systèmes embarqués, électronique",
        "strong": ["embarqué", "embarqués", "embarquée", "embedded", "électronique", "electronics", "hardware",
                   "fpga", "vhdl", "verilog", "microcontrôleur", "microcontrôleurs", "microcontroller", "firmware",
                   "temps réel", "real-time", "rtos", "logiciel embarqué", "c embarqué", "bas niveau",
                   "ingénierie système", "ingénieur système", "systems engineer", "test et validation",
                   "validation", "vérification", "microélectronique", "micro-électronique", "asic", "soc design",
                   "cem", "compatibilité électromagnétique", "électronique de puissance", "carte électronique",
                   "banc de test", "instrumentation", "mécatronique", "robotique", "automobile", "avionique",
                   "iot", "objets connectés", "traitement du signal", "radiofréquence", "rf", "hyperfréquence"],
        "tech": ["stm32", "arm", "cortex", "c++", "matlab", "simulink", "labview", "python", "linux embarqué",
                 "yocto", "freertos", "zephyr", "autosar", "can", "spi", "i2c", "uart", "ethernet", "modbus",
                 "pcb", "altium", "kicad", "cadence", "oscilloscope", "xilinx", "vivado", "quartus", "intel fpga",
                 "systemverilog", "uvm", "modelsim", "do-178", "iso 26262", "misra", "jtag", "bootloader",
                 "driver", "drivers", "dsp", "risc-v", "esp32", "arduino", "raspberry", "ltspice", "pspice",
                 "bluetooth", "ble", "lora", "git", "jenkins", "capteurs", "sensors", "adc", "pwm"],
        "negative": ["commercial", "commerciale", "vente", "marketing", "ressources humaines", "comptable",
                     "juridique", "communication", "achats", "immobilier", "assurance", "recrutement",
                     "business developer"],
        "adzuna": ["stage embarqué", "stage électronique", "stage fpga", "stage microcontrôleur",
                   "stage hardware", "stage firmware"],
    },
    "logiciel": {
        "label": "Développement logiciel, web, mobile",
        "strong": ["développeur", "développeuse", "developer", "développement logiciel", "software engineer",
                   "software", "ingénieur logiciel", "backend", "back-end", "frontend", "front-end", "fullstack",
                   "full-stack", "full stack", "web", "mobile", "application", "applications", "api",
                   "qa", "test logiciel", "automatisation des tests", "devops", "jeux vidéo", "game"],
        "tech": ["java", "spring", "python", "django", "fastapi", "javascript", "typescript", "react", "angular",
                 "vue", "node", "php", "symfony", "laravel", "c#", ".net", "c++", "go", "golang", "rust", "kotlin",
                 "swift", "android", "ios", "flutter", "sql", "postgresql", "mysql", "mongodb", "docker",
                 "kubernetes", "git", "gitlab", "ci/cd", "aws", "azure", "rest", "graphql", "agile", "scrum",
                 "selenium", "cypress", "unity", "unreal", "html", "css"],
        "negative": ["commercial", "commerciale", "vente", "ressources humaines", "comptable", "juridique",
                     "immobilier", "assurance", "recrutement", "business developer"],
        "adzuna": ["stage développeur", "stage développement logiciel", "stage fullstack", "stage développeur web",
                   "stage software engineer"],
    },
    "data": {
        "label": "Data, intelligence artificielle",
        "strong": ["data", "données", "data scientist", "data analyst", "data engineer", "machine learning",
                   "deep learning", "intelligence artificielle", "ia", "ai", "nlp", "vision par ordinateur",
                   "computer vision", "statistique", "statistiques", "business intelligence", "bi",
                   "analytics", "big data", "llm", "mlops", "recherche opérationnelle", "optimisation"],
        "tech": ["python", "sql", "pandas", "numpy", "scikit-learn", "pytorch", "tensorflow", "keras", "spark",
                 "hadoop", "airflow", "dbt", "power bi", "tableau", "looker", "excel", "snowflake", "bigquery",
                 "databricks", "kafka", "docker", "aws", "azure", "gcp", "git", "matlab", "langchain",
                 "hugging face", "transformers", "opencv", "sas"],
        "negative": ["commercial", "commerciale", "vente", "ressources humaines", "comptable", "juridique",
                     "immobilier", "recrutement", "business developer"],
        "adzuna": ["stage data scientist", "stage data analyst", "stage data engineer", "stage machine learning",
                   "stage intelligence artificielle"],
    },
    "industrie": {
        "label": "Mécanique, industrie, énergie, aéronautique",
        "strong": ["mécanique", "mechanical", "conception mécanique", "bureau d'études", "industrialisation",
                   "méthodes", "production", "qualité", "amélioration continue", "lean", "maintenance",
                   "automatisme", "automatismes", "automaticien", "génie industriel", "procédés", "process",
                   "énergie", "énergétique", "thermique", "génie civil", "btp", "aéronautique", "spatial",
                   "ferroviaire", "matériaux", "structure", "calcul de structure", "simulation numérique",
                   "supply chain", "logistique", "hse", "qse", "nucléaire", "génie électrique", "électrotechnique"],
        "tech": ["catia", "solidworks", "creo", "autocad", "ansys", "abaqus", "nastran", "matlab", "simulink",
                 "sap", "erp", "gpao", "amdec", "six sigma", "5s", "kaizen", "siemens", "schneider", "tia portal",
                 "automate", "plc", "scada", "cfd", "éléments finis", "excel", "vba", "python", "iso 9001",
                 "revit", "bim", "robot structural", "cao", "dao", "fao", "impression 3d", "usinage"],
        "negative": ["commercial", "commerciale", "vente", "marketing", "ressources humaines", "comptable",
                     "juridique", "immobilier", "assurance", "recrutement", "business developer"],
        "adzuna": ["stage ingénieur mécanique", "stage bureau d'études", "stage méthodes industrialisation",
                   "stage ingénieur qualité", "stage automatisme"],
    },
    "gestion": {
        "label": "Commerce, marketing, finance, RH",
        "strong": ["marketing", "communication", "commercial", "business developer", "vente", "ventes", "sales",
                   "finance", "contrôle de gestion", "audit", "comptabilité", "comptable", "trésorerie",
                   "ressources humaines", "rh", "recrutement", "achats", "acheteur", "chef de produit",
                   "chef de projet", "product manager", "consultant", "conseil", "stratégie", "juridique",
                   "juriste", "droit", "banque", "assurance", "e-commerce", "digital", "événementiel",
                   "relation client", "supply chain", "logistique", "gestion de projet"],
        "tech": ["excel", "powerpoint", "sap", "salesforce", "hubspot", "crm", "google analytics", "seo", "sea",
                 "réseaux sociaux", "linkedin", "canva", "photoshop", "power bi", "vba", "sql", "notion", "jira",
                 "anglais", "sirh", "paie", "ifrs", "consolidation", "m&a", "private equity", "kyc"],
        "negative": [],
        "adzuna": ["stage marketing", "stage finance", "stage contrôle de gestion", "stage ressources humaines",
                   "stage business developer"],
    },
}
DEFAULT_DOMAINS = ["reseaux"]


def labels() -> dict[str, str]:
    return {k: d["label"] for k, d in DOMAINS.items()}


def clean(keys) -> list[str]:
    """Liste de domaines valides, sans doublon, dans l'ordre de DOMAINS."""
    wanted = {str(k) for k in keys} if isinstance(keys, (list, tuple, set)) else set()
    return [k for k in DOMAINS if k in wanted]


# =====================================================================================================
# Régions : chaque région est reconnue par ses départements (numéro ou nom) et ses principales villes.
# =====================================================================================================
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


REGIONS = {
    "idf": ("Île-de-France", "75 77 78 91 92 93 94 95",
            ["ile-de-france", "ile de france", "idf", "paris", "la defense", "courbevoie", "nanterre", "puteaux",
             "issy", "boulogne", "massy", "palaiseau", "saclay", "velizy", "guyancourt", "saint-denis", "cergy",
             "montrouge", "levallois", "rueil", "gennevilliers", "elancourt", "chatillon", "meudon", "saint-ouen",
             "montreuil", "vincennes", "noisy", "creteil", "evry", "les ulis", "roissy", "arcueil", "bagneux",
             "malakoff", "clichy", "neuilly", "colombes", "antony", "orsay", "gif-sur-yvette", "versailles",
             "saint-quentin-en-yvelines", "pontoise", "argenteuil", "bezons", "suresnes", "sevres", "saint-cloud",
             "ivry", "villejuif", "rungis", "nozay", "limours", "trappes", "poissy", "les mureaux", "magny",
             "bois-colombes", "asnieres", "aubervilliers", "pantin", "bobigny", "villepinte", "marne-la-vallee",
             "champs-sur-marne", "fontenay", "charenton", "saint-mande", "kremlin", "cachan", "chatenay", "plessis",
             "hauts-de-seine", "yvelines", "essonne", "val-d'oise", "val d'oise", "val-de-marne",
             "seine-saint-denis", "seine-et-marne", "sartrouville", "osny", "eragny", "taverny", "franconville",
             "sarcelles", "gonesse", "garges", "ermont", "herblay", "cormeilles"]),
    "ara": ("Auvergne-Rhône-Alpes", "01 03 07 15 26 38 42 43 63 69 73 74",
            ["auvergne", "rhone-alpes", "lyon", "villeurbanne", "grenoble", "saint-etienne",
             "clermont-ferrand", "annecy", "chambery", "valence", "isere", "savoie", "haute-savoie", "meylan",
             "crolles", "echirolles", "bron", "venissieux", "ecully", "limonest", "bourg-en-bresse", "roanne",
             "vichy", "montlucon", "puy-de-dome", "drome", "ardeche", "saint-priest", "moirans"]),
    "occ": ("Occitanie", "09 11 12 30 31 32 34 46 48 65 66 81 82",
            ["occitanie", "toulouse", "montpellier", "nimes", "perpignan", "blagnac", "colomiers", "labege",
             "ramonville", "tarbes", "albi", "castres", "beziers", "sete", "haute-garonne", "herault", "gard",
             "tarn", "aude", "aveyron", "rodez", "montauban", "cahors", "auch", "foix", "carcassonne", "narbonne",
             "balma", "tournefeuille", "muret", "castelnau"]),
    "naq": ("Nouvelle-Aquitaine", "16 17 19 23 24 33 40 47 64 79 86 87",
            ["nouvelle-aquitaine", "aquitaine", "bordeaux", "merignac", "pessac", "talence", "limoges", "poitiers",
             "la rochelle", "pau", "bayonne", "biarritz", "angouleme", "niort", "gironde", "pyrenees-atlantiques",
             "landes", "dordogne", "charente", "vienne", "correze", "brive", "agen", "perigueux", "mont-de-marsan",
             "chatellerault", "anglet", "le haillan", "cestas"]),
    "paca": ("Provence-Alpes-Côte d'Azur", "04 05 06 13 83 84",
             ["provence", "cote d'azur", "paca", "marseille", "aix-en-provence", "nice", "toulon", "avignon",
              "sophia antipolis", "sophia-antipolis", "valbonne", "antibes", "cannes", "grasse", "biot",
              "bouches-du-rhone", "alpes-maritimes", "var", "vaucluse", "la ciotat", "aubagne", "vitrolles",
              "marignane", "istres", "gardanne", "rousset", "cadarache", "saint-paul-lez-durance", "gap", "hyeres",
              "la seyne", "frejus", "mougins", "carros"]),
    "hdf": ("Hauts-de-France", "02 59 60 62 80",
            ["hauts-de-france", "lille", "villeneuve-d'ascq", "roubaix", "tourcoing", "amiens", "valenciennes",
             "dunkerque", "calais", "lens", "arras", "compiegne", "beauvais", "nord", "pas-de-calais", "somme",
             "aisne", "douai", "maubeuge", "saint-quentin", "boulogne-sur-mer", "marcq-en-baroeul",
             "lesquin", "seclin", "creil", "senlis"]),
    "ges": ("Grand Est", "08 10 51 52 54 55 57 67 68 88",
            ["grand est", "strasbourg", "nancy", "metz", "reims", "mulhouse", "colmar", "troyes", "alsace",
             "lorraine", "champagne", "bas-rhin", "haut-rhin", "moselle", "meurthe-et-moselle", "epinal",
             "illkirch", "schiltigheim", "thionville", "belfort-montbeliard", "charleville", "chalons",
             "saint-louis", "haguenau", "molsheim", "obernai"]),
    "bre": ("Bretagne", "22 29 35 56",
            ["bretagne", "rennes", "brest", "lannion", "vannes", "lorient", "saint-malo", "quimper", "saint-brieuc",
             "cesson-sevigne", "ille-et-vilaine", "finistere", "morbihan", "cotes-d'armor", "bruz", "plouzane",
             "guidel", "ploemeur", "saint-gregoire", "chantepie", "vitre", "fougeres", "morlaix"]),
    "pdl": ("Pays de la Loire", "44 49 53 72 85",
            ["pays de la loire", "nantes", "saint-nazaire", "angers", "le mans", "la roche-sur-yon", "cholet",
             "laval", "saint-herblain", "carquefou", "loire-atlantique", "maine-et-loire", "sarthe", "vendee",
             "mayenne", "bouguenais", "orvault", "reze", "les herbiers", "saumur", "montoir"]),
    "nor": ("Normandie", "14 27 50 61 76",
            ["normandie", "rouen", "caen", "le havre", "cherbourg", "evreux", "seine-maritime", "calvados",
             "alencon", "dieppe", "saint-lo", "herouville", "vernon", "elbeuf", "saint-etienne-du-rouvray",
             "colombelles", "flamanville", "la hague"]),
    "bfc": ("Bourgogne-Franche-Comté", "21 25 39 58 70 71 89 90",
            ["bourgogne", "franche-comte", "dijon", "besancon", "belfort", "montbeliard", "chalon-sur-saone",
             "auxerre", "macon", "nevers", "cote-d'or", "doubs", "jura", "saone-et-loire", "yonne", "sochaux",
             "le creusot", "dole", "vesoul", "lons-le-saunier", "beaune", "sens"]),
    "cvl": ("Centre-Val de Loire", "18 28 36 37 41 45",
            ["centre-val de loire", "val de loire", "orleans", "tours", "bourges", "chartres", "blois",
             "chateauroux", "loiret", "indre-et-loire", "cher", "eure-et-loir", "loir-et-cher", "indre",
             "saint-pierre-des-corps", "joue-les-tours", "montargis", "vierzon", "dreux", "vendome", "saran",
             "olivet", "amboise", "chinon"]),
    "cor": ("Corse", "2A 2B 20",
            ["corse", "ajaccio", "bastia", "corte", "porto-vecchio", "calvi", "haute-corse", "corse-du-sud"]),
}
DEFAULT_REGIONS = ["idf"]


def region_labels() -> dict[str, str]:
    return {k: v[0] for k, v in REGIONS.items()}


def clean_regions(keys) -> list[str]:
    wanted = {str(k) for k in keys} if isinstance(keys, (list, tuple, set)) else set()
    return [k for k in REGIONS if k in wanted]


def _matcher(depts: str, words: list[str]):
    codes = "|".join(re.escape(d.lower()) for d in depts.split())
    # « 31 », « 31000 », « (31) », « 31 - Toulouse » : un numéro de département seul ou suivi de 3 chiffres
    cp = re.compile(rf"(?<![0-9a-z])(?:{codes})(?:\d{{3}})?(?![0-9a-z])")
    names = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(_norm(w)) for w in sorted(words, key=len, reverse=True)) + r")(?![a-z])")
    return lambda p: bool(names.search(p) or cp.search(p))


_MATCH = {k: _matcher(v[1], v[2]) for k, v in REGIONS.items()}
_OTHER_COUNTRY = re.compile(r"(?<![a-z])(usa|united states|etats-unis|uk|united kingdom|royaume-uni|england|london|"
                            r"germany|allemagne|deutschland|berlin|munich|spain|espagne|madrid|barcelona|italy|italie|"
                            r"milan|netherlands|pays-bas|amsterdam|belgium|belgique|bruxelles|brussels|switzerland|"
                            r"suisse|geneve|zurich|lausanne|luxembourg|ireland|irlande|dublin|portugal|lisbon|"
                            r"lisbonne|poland|pologne|romania|roumanie|india|inde|china|chine|japan|japon|singapore|"
                            r"singapour|canada|montreal|toronto|new york|san francisco|israel|tel aviv|dubai|"
                            r"emirates|morocco|maroc|tunisia|tunisie|australia|brazil|bresil|mexico|sweden|suede|"
                            r"stockholm|denmark|danemark|norway|norvege|austria|autriche|vienna)(?![a-z])")


def regions_of(place: str) -> list[str]:
    """Régions françaises reconnues dans un lieu (souvent une seule)."""
    p = _norm(place)
    if not p or _OTHER_COUNTRY.search(p):
        return []
    return [k for k, m in _MATCH.items() if m(p)]


def in_france(place: str, unknown_ok: bool = True) -> bool:
    """L'offre est-elle en France ? Lieu vide ou non reconnu : on garde (la source ne précise pas toujours)."""
    p = _norm(place)
    if not p:
        return unknown_ok
    if re.search(r"(?<![a-z])france(?![a-z])", p):
        return True
    if _OTHER_COUNTRY.search(p):
        return False
    return bool(regions_of(place)) or bool(re.search(r"(?<!\d)\d{5}(?!\d)", p))


_ANYWHERE = re.compile(r"^(france|teletravail|remote|full remote|a distance|france entiere|toute la france|"
                       r"france \(teletravail\)|remote,? france|france,? remote)?$")


def place_ok(place: str, wanted: list[str]) -> bool:
    """Le lieu convient-il à quelqu'un qui cherche dans ces régions ? Aucune région cochée = toute la France.
    Un lieu vide, ou « France » / « télétravail » sans précision, convient à tout le monde. Une ville française
    que le site ne sait pas rattacher à une région n'est proposée qu'à ceux qui cherchent partout."""
    if not wanted:
        return True
    found = regions_of(place)
    if found:
        return any(r in wanted for r in found)
    return bool(_ANYWHERE.match(_norm(place)))
