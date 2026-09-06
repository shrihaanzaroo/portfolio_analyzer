SP500 = {
    "Technology": 31, "Financials": 13, "Health Care": 12, "Consumer Discretionary": 10.5,
    "Communication Services": 9, "Industrials": 8.5, "Consumer Staples": 6, "Energy": 4,
    "Utilities": 2.5, "Real Estate": 2.5, "Materials": 2,
}
NON_EQUITY = {"Bonds", "Gold", "Cash", "Index"}
EQUITY_SECTORS = list(SP500.keys())
SP_TOP = {"NVDA":7.0, "AAPL":6.5, "MSFT":6.3, "AMZN":3.9, "AVGO":2.4, "META":2.7, "GOOGL":3.8,
          "TSLA":1.9, "BRK.B":1.6, "JPM":1.5, "LLY":1.2, "V":0.9, "XOM":1.0, "UNH":0.9, "MA":0.8,
          "COST":0.8, "JNJ":0.8, "PG":0.8, "HD":0.7, "WMT":0.9}
QQQ_TOP = {"NVDA":8.8, "AAPL":8.2, "MSFT":7.8, "AMZN":5.4, "AVGO":5.0, "META":4.4, "GOOGL":4.9,
           "TSLA":2.9, "NFLX":3.0, "COST":2.4, "AMD":1.4, "ADBE":1.0}
MAGS_TOP = {"AAPL":14, "MSFT":14, "NVDA":15, "AMZN":14, "GOOGL":14, "META":14, "TSLA":14}
VTI_TOP = {k: round(v * 0.86, 2) for k, v in SP_TOP.items()}
FUND_SPEC = {
    "SPY":  {"sector":"Index", "br":50, "mix":SP500, "top":SP_TOP},
    "VOO":  {"sector":"Index", "br":50, "mix":SP500, "top":SP_TOP},
    "VTI":  {"sector":"Index", "br":60, "mix":SP500, "top":VTI_TOP},
    "QQQ":  {"sector":"Technology", "br":25, "top":QQQ_TOP,
             "mix":{"Technology":50, "Communication Services":16, "Consumer Discretionary":14,
                    "Health Care":6, "Consumer Staples":6, "Industrials":5, "Utilities":1.5, "Financials":1.5}},
    "IWM":  {"sector":"Index", "br":100,
             "mix":{"Financials":18, "Industrials":17, "Health Care":15, "Technology":14,
                    "Consumer Discretionary":10, "Energy":7, "Real Estate":6, "Materials":5,
                    "Consumer Staples":4, "Utilities":3, "Communication Services":2}},
    "EFA":  {"sector":"Index", "br":50,
             "mix":{"Financials":20, "Industrials":17, "Health Care":12, "Consumer Discretionary":11,
                    "Technology":10, "Consumer Staples":8, "Materials":7, "Energy":5,
                    "Communication Services":4, "Utilities":3, "Real Estate":3}},
    "VWO":  {"sector":"Index", "br":60,
             "mix":{"Technology":22, "Financials":22, "Consumer Discretionary":13, "Communication Services":10,
                    "Industrials":7, "Materials":7, "Energy":5, "Consumer Staples":5, "Health Care":4,
                    "Utilities":3, "Real Estate":2}},
    "ARKK": {"sector":"Technology", "br":12,
             "mix":{"Technology":60, "Health Care":20, "Communication Services":12, "Consumer Discretionary":8}},
    "VNQ":  {"sector":"Real Estate", "br":30, "mix":{"Real Estate":100}},
    "BND":  {"sector":"Bonds", "br":100},
    "AGG":  {"sector":"Bonds", "br":100},
    "TLT":  {"sector":"Bonds", "br":10},
    "IEF":  {"sector":"Bonds", "br":10},
    "GLD":  {"sector":"Gold"},
    "SLV":  {"sector":"Gold"},
    "GDX":  {"sector":"Gold", "br":20},
    "MAGS": {"sector":"Technology", "br":7, "top":MAGS_TOP,
             "mix":{"Technology":72, "Communication Services":14, "Consumer Discretionary":14}},
    "CASH": {"sector":"Cash"},
}
SECTOR_MAP = {
    "AAPL":"Technology","MSFT":"Technology","NVDA":"Technology","GOOGL":"Technology","META":"Technology",
    "AMD":"Technology","AVGO":"Technology","CRM":"Technology","INTC":"Technology","MU":"Technology",
    "QCOM":"Technology","TXN":"Technology","ORCL":"Technology","ADBE":"Technology","NOW":"Technology",
    "PANW":"Technology","SNOW":"Technology","PLTR":"Technology","SHOP":"Technology","SQ":"Technology",
    "PYPL":"Technology","COIN":"Technology","MSTR":"Technology","MARA":"Technology",
    "NFLX":"Communication Services","DIS":"Communication Services","SPOT":"Communication Services",
    "RBLX":"Communication Services","EA":"Communication Services","T":"Communication Services",
    "VZ":"Communication Services","TMUS":"Communication Services","CMCSA":"Communication Services",
    "TTWO":"Communication Services",
    "AMZN":"Consumer Discretionary","TSLA":"Consumer Discretionary","HD":"Consumer Discretionary",
    "NKE":"Consumer Discretionary","MCD":"Consumer Discretionary","SBUX":"Consumer Discretionary",
    "CMG":"Consumer Discretionary","LULU":"Consumer Discretionary","TGT":"Consumer Discretionary",
    "LOW":"Consumer Discretionary","F":"Consumer Discretionary","GM":"Consumer Discretionary",
    "RIVN":"Consumer Discretionary","ABNB":"Consumer Discretionary","UBER":"Consumer Discretionary",
    "BKNG":"Consumer Discretionary","DKNG":"Consumer Discretionary",
    "JNJ":"Health Care","UNH":"Health Care","PFE":"Health Care","LLY":"Health Care","ABBV":"Health Care",
    "MRK":"Health Care","TMO":"Health Care","ABT":"Health Care","AMGN":"Health Care","GILD":"Health Care",
    "ISRG":"Health Care","CVS":"Health Care","MRNA":"Health Care","DHR":"Health Care","SYK":"Health Care",
    "JPM":"Financials","BAC":"Financials","GS":"Financials","V":"Financials","MA":"Financials",
    "WFC":"Financials","C":"Financials","MS":"Financials","SCHW":"Financials","BLK":"Financials",
    "AXP":"Financials","COF":"Financials","PGR":"Financials","BRK.B":"Financials","HOOD":"Financials",
    "SOFI":"Financials",
    "XOM":"Energy","CVX":"Energy","COP":"Energy","OXY":"Energy","SLB":"Energy","EOG":"Energy",
    "VLO":"Energy","DVN":"Energy",
    "PG":"Consumer Staples","KO":"Consumer Staples","WMT":"Consumer Staples","COST":"Consumer Staples",
    "PEP":"Consumer Staples","MDLZ":"Consumer Staples","CL":"Consumer Staples","GIS":"Consumer Staples",
    "HSY":"Consumer Staples","MNST":"Consumer Staples","KHC":"Consumer Staples",
    "NEE":"Utilities","DUK":"Utilities","SO":"Utilities","D":"Utilities","AEP":"Utilities","ED":"Utilities",
    "BA":"Industrials","CAT":"Industrials","DE":"Industrials","GE":"Industrials","HON":"Industrials",
    "LMT":"Industrials","RTX":"Industrials","UPS":"Industrials","FDX":"Industrials","UNP":"Industrials",
    "DAL":"Industrials","UAL":"Industrials",
    "LIN":"Materials","SHW":"Materials","FCX":"Materials","APD":"Materials","NEM":"Gold",
    "O":"Real Estate","PLD":"Real Estate","AMT":"Real Estate","SPG":"Real Estate",
}

def spec_lookup(ticker):
    if ticker in FUND_SPEC:
        spec = FUND_SPEC[ticker]
        return {"sector": spec["sector"], "br": spec.get("br", 1), "mix": spec.get("mix"), "top": spec.get("top")}
    if ticker in SECTOR_MAP:
        return {"sector": SECTOR_MAP[ticker], "br": 1, "mix": None, "top": None}
    return {"sector": "Other", "br": 1, "mix": None, "top": None}
