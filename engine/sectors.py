"""
sectors.py
A best-effort sector map for common NSE large/mid-cap stocks, used only to
avoid recommending two picks from the same sector on the same day. Not
exhaustive - unmapped symbols simply fall back to "Unknown" and are still
eligible for recommendation, just without a diversification guarantee.
"""

SECTOR_MAP = {
    # Banking & Financial Services
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking",
    "KOTAKBANK": "Banking", "AXISBANK": "Banking", "INDUSINDBK": "Banking",
    "BANKBARODA": "Banking", "PNB": "Banking", "IDFCFIRSTB": "Banking",
    "BAJFINANCE": "NBFC", "BAJAJFINSV": "NBFC", "TATACAP": "NBFC",
    "SHRIRAMFIN": "NBFC", "CHOLAFIN": "NBFC", "PFC": "NBFC", "RECLTD": "NBFC",
    "SBILIFE": "Insurance", "HDFCLIFE": "Insurance", "ICICIGI": "Insurance",

    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "LTIM": "IT", "MPHASIS": "IT", "PERSISTENT": "IT",
    "COFORGE": "IT",

    # Energy / Oil & Gas / Power
    "RELIANCE": "Energy", "ONGC": "Energy", "IOC": "Energy", "BPCL": "Energy",
    "NTPC": "Power", "POWERGRID": "Power", "TATAPOWER": "Power", "ADANIPOWER": "Power",
    "ADANIGREEN": "Power", "ADANIENSOL": "Power",

    # Metals & Mining
    "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "HINDALCO": "Metals",
    "JSL": "Metals", "VEDL": "Metals", "SAIL": "Metals", "NMDC": "Metals",
    "COALINDIA": "Metals",

    # Auto
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto", "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto", "HEROMOTOCO": "Auto", "APOLLOTYRE": "Auto", "MRF": "Auto",

    # Pharma & Healthcare
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "DIVISLAB": "Pharma", "AUROPHARMA": "Pharma", "LUPIN": "Pharma",
    "APOLLOHOSP": "Healthcare", "MAXHEALTH": "Healthcare",

    # FMCG / Consumer
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "TATACONSUM": "FMCG", "DABUR": "FMCG",
    "MARICO": "FMCG", "GODREJCP": "FMCG", "BERGEPAINT": "Consumer Durables",
    "ASIANPAINT": "Consumer Durables", "TITAN": "Consumer Durables",

    # Cement & Infra
    "ULTRACEMCO": "Cement", "SHREECEM": "Cement", "AMBUJACEM": "Cement",
    "ACC": "Cement", "LT": "Infra", "RITES": "Infra", "RVNL": "Infra",
    "GMRINFRA": "Infra",

    # Telecom
    "BHARTIARTL": "Telecom", "IDEA": "Telecom",

    # Chemicals / Agri
    "UPL": "Chemicals", "PIDILITIND": "Chemicals", "EIDPARRY": "Agri",
    "SRF": "Chemicals", "AAVAS": "NBFC",

    # Diversified / Others seen in earlier scans
    "USHAMART": "Metals", "ARE&M": "Auto Ancillary", "NAM-INDIA": "Financial Services",
    "CUB": "Banking", "IOB": "Banking", "FEDERALBNK": "Banking", "KARURVYSYA": "Banking",
    "SWIGGY": "Consumer Internet", "ZYDUSLIFE": "Pharma", "CAPLIPOINT": "Pharma",
    "MOTHERSON": "Auto Ancillary", "DEVYANI": "Consumer Internet", "TATATECH": "IT",
    "TRAVELFOOD": "Consumer Internet", "NEULANDLAB": "Pharma", "SCI": "Shipping",
    "ENRIN": "Energy", "SAPPHIRE": "Consumer Internet", "CLEAN": "Chemicals",
}


def get_sector(symbol: str) -> str:
    return SECTOR_MAP.get(symbol.upper(), "Unknown")
