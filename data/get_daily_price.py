import os
import yfinance as yf
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
import json

all_nasdaq_100_symbols = [
    "NVDA",
    "MSFT",
    "AAPL",
    "GOOG",
    "GOOGL",
    "AMZN",
    "META",
    "AVGO",
    "TSLA",
    "NFLX",
    "PLTR",
    "COST",
    "ASML",
    "AMD",
    "CSCO",
    "AZN",
    "TMUS",
    "MU",
    "LIN",
    "PEP",
    "SHOP",
    "APP",
    "INTU",
    "AMAT",
    "LRCX",
    "PDD",
    "QCOM",
    "ARM",
    "INTC",
    "BKNG",
    "AMGN",
    "TXN",
    "ISRG",
    "GILD",
    "KLAC",
    "PANW",
    "ADBE",
    "HON",
    "CRWD",
    "CEG",
    "ADI",
    "ADP",
    "DASH",
    "CMCSA",
    "VRTX",
    "MELI",
    "SBUX",
    "CDNS",
    "ORLY",
    "SNPS",
    "MSTR",
    "MDLZ",
    "ABNB",
    "MRVL",
    "CTAS",
    "TRI",
    "MAR",
    "MNST",
    "CSX",
    "ADSK",
    "PYPL",
    "FTNT",
    "AEP",
    "WDAY",
    "REGN",
    "ROP",
    "NXPI",
    "DDOG",
    "AXON",
    "ROST",
    "IDXX",
    "EA",
    "PCAR",
    "FAST",
    "EXC",
    "TTWO",
    "XEL",
    "ZS",
    "PAYX",
    "WBD",
    "BKR",
    "CPRT",
    "CCEP",
    "FANG",
    "TEAM",
    "CHTR",
    "KDP",
    "MCHP",
    "GEHC",
    "VRSK",
    "CTSH",
    "CSGP",
    "KHC",
    "ODFL",
    "DXCM",
    "TTD",
    "ON",
    "BIIB",
    "LULU",
    "CDW",
    "GFS",
]



def get_daily_price(SYMBOL: str, period: str = "1y"):
    """
    使用 yfinance 获取股票日线数据
    
    Parameters:
    SYMBOL (str): 股票代码，如 "QQQ", "AAPL" 等
    period (str): 数据期间，可选 "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"
    """
    try:
        # 创建 ticker 对象
        ticker = yf.Ticker(SYMBOL)
        
        # 获取历史数据
        hist_data = ticker.history(period=period)
        
        if hist_data.empty:
            print(f"Error: 没有找到 {SYMBOL} 的数据")
            return
        
        # 重置索引，将日期变为列
        hist_data.reset_index(inplace=True)
        
        # 转换日期格式
        hist_data['Date'] = hist_data['Date'].dt.strftime('%Y-%m-%d')
        
        # 转换为字典格式，与 Alpha Vantage 类似的结构
        data = {
            "Meta Data": {
                "1. Information": f"Daily Prices for {SYMBOL}",
                "2. Symbol": SYMBOL,
                "3. Last Refreshed": datetime.now().strftime('%Y-%m-%d'),
                "4. Output Size": "Compact",
                "5. Time Zone": "US/Eastern"
            },
            "Time Series (Daily)": {}
        }
        
        # 填充时间序列数据
        for _, row in hist_data.iterrows():
            data["Time Series (Daily)"][row['Date']] = {
                "1. open": str(round(row['Open'], 4)),
                "2. high": str(round(row['High'], 4)),
                "3. low": str(round(row['Low'], 4)),
                "4. close": str(round(row['Close'], 4)),
                "5. volume": str(int(row['Volume']))
            }
        
        # 保存到文件
        with open(f"./daily_prices_{SYMBOL}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
        if SYMBOL == "QQQ":
            with open(f"./Adaily_prices_{SYMBOL}.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
        print(f"成功获取 {SYMBOL} 的数据，共 {len(hist_data)} 个交易日")
        return data
        
    except Exception as e:
        print(f"Error: 获取 {SYMBOL} 数据时发生错误 - {str(e)}")
        return None


if __name__ == "__main__":
    for symbol in all_nasdaq_100_symbols:
        get_daily_price(symbol)

    get_daily_price("QQQ")
