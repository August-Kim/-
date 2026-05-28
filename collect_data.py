"""
collect_data.py
글투(글로벌 투자 통합 대시보드) 데이터 수집 스크립트
실행: python scripts/collect_data.py
출력: data/latest.json
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
import yfinance as yf
import requests

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 내부 함수 — NASDAQ 100
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NASDAQ_TICKERS = [
    ("NVDA",  "엔비디아",        "AI반도체",          "SOXX"),
    ("AAPL",  "애플",            "소비자전자",         "XLK"),
    ("MSFT",  "마이크로소프트",   "클라우드/AI",        "IGV"),
    ("AMZN",  "아마존",          "이커머스/클라우드",   "WCLD"),
    ("TSLA",  "테슬라",          "전기차",             "DRIV"),
    ("META",  "메타",            "소셜미디어",          "XLC"),
    ("GOOGL", "알파벳",          "인터넷/검색",         "XLC"),
    ("AVGO",  "브로드컴",        "AI반도체",            "SOXX"),
    ("COST",  "코스트코",        "창고형소매",          "XRT"),
    ("NFLX",  "넷플릭스",        "스트리밍",            "XLC"),
    ("AMD",   "AMD",             "AI반도체",            "SOXX"),
    ("ORCL",  "오라클",          "클라우드DB",          "IGV"),
    ("QCOM",  "퀄컴",            "모바일반도체",         "SOXX"),
    ("MU",    "마이크론",        "메모리반도체",         "SOXX"),
    ("AMAT",  "어플라이드머티리얼즈", "반도체장비",      "SOXX"),
    ("LRCX",  "램리서치",        "반도체장비",          "SOXX"),
    ("KLAC",  "KLA",             "반도체검사",          "SOXX"),
    ("PLTR",  "팔란티어",        "AI분석SW",            "IGV"),
    ("PANW",  "팔로알토네트웍스", "사이버보안",         "CIBR"),
    ("INTU",  "인튜이트",        "세금/회계SW",         "IGV"),
    ("ISRG",  "인튜이티브서지컬", "로봇수술",           "XHE"),
    ("TXN",   "텍사스인스트루먼트","아날로그반도체",     "SOXX"),
    ("CSCO",  "시스코",          "네트워크장비",        "IGV"),
    ("AMGN",  "암젠",            "바이오의약",          "XBI"),
    ("CDNS",  "케이던스",        "EDA소프트",           "IGV"),
]

def _fetch_single_us_stock(ticker, name, sector, benchmark):
    """개별 미국 주식 PER 데이터 수집"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "benchmark": benchmark,
            "per": round(info.get("trailingPE") or 0, 1) or None,
            "fwd_per": round(info.get("forwardPE") or 0, 1) or None,
            "price": round(info.get("currentPrice") or info.get("regularMarketPrice") or 0, 2),
            "market_cap_b": round((info.get("marketCap") or 0) / 1e9, 1),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low": info.get("fiftyTwoWeekLow"),
        }
    except Exception as e:
        print(f"  ⚠ {ticker} 오류: {e}")
        return {
            "ticker": ticker, "name": name, "sector": sector,
            "benchmark": benchmark, "per": None, "fwd_per": None,
            "price": None, "market_cap_b": None,
            "week52_high": None, "week52_low": None,
        }

def _calc_sector_avg_per(stocks):
    """섹터별 평균 PER 계산"""
    sector_map = {}
    for s in stocks:
        sec = s["sector"]
        if sec not in sector_map:
            sector_map[sec] = {"pers": [], "fwd_pers": []}
        if s["per"]:
            sector_map[sec]["pers"].append(s["per"])
        if s["fwd_per"]:
            sector_map[sec]["fwd_pers"].append(s["fwd_per"])
    result = {}
    for sec, vals in sector_map.items():
        result[sec] = {
            "avg_per": round(sum(vals["pers"]) / len(vals["pers"]), 1) if vals["pers"] else None,
            "avg_fwd_per": round(sum(vals["fwd_pers"]) / len(vals["fwd_pers"]), 1) if vals["fwd_pers"] else None,
        }
    return result

def _attach_premium(stocks, sector_avgs):
    """프리미엄율 계산 및 판정 부여"""
    def _judge(prem):
        if prem is None: return "적자"
        if prem >= 50:   return "고평가"
        if prem >= 20:   return "약고평가"
        if prem >= -20:  return "중립"
        if prem >= -50:  return "저평가"
        return "역프"

    for s in stocks:
        avg = sector_avgs.get(s["sector"], {})
        sp  = avg.get("avg_per")
        sfp = avg.get("avg_fwd_per")
        s["sector_per"]     = sp
        s["sector_fwd_per"] = sfp
        s["premium"]     = round(((s["per"] / sp) - 1) * 100, 1) if s["per"] and sp else None
        s["fwd_premium"] = round(((s["fwd_per"] / sfp) - 1) * 100, 1) if s["fwd_per"] and sfp else None
        s["judge"]       = _judge(s["premium"])
        s["fwd_judge"]   = _judge(s["fwd_premium"])
    return stocks

def collect_nasdaq():
    """NASDAQ 100 종목 PER 데이터 수집 — wrapper"""
    print("📡 NASDAQ 100 데이터 수집 중...")
    stocks = []
    for i, (ticker, name, sector, bm) in enumerate(NASDAQ_TICKERS, 1):
        print(f"  [{i}/{len(NASDAQ_TICKERS)}] {ticker}...")
        data = _fetch_single_us_stock(ticker, name, sector, bm)
        stocks.append(data)
        time.sleep(0.3)  # rate limit 방지
    sector_avgs = _calc_sector_avg_per(stocks)
    stocks = _attach_premium(stocks, sector_avgs)
    print(f"  ✅ NASDAQ {len(stocks)}개 수집 완료")
    return stocks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 내부 함수 — KOSPI 500
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KOSPI_TICKERS = [
    ("005930.KS", "005930", "삼성전자",        "메모리/HBM",         "MU",   42.1,  9.6),
    ("000660.KS", "000660", "SK하이닉스",       "메모리/HBM",         "MU",   42.1,  9.6),
    ("402340.KS", "402340", "SK스퀘어",         "AI 반도체",          "NVDA", 32.9, 21.5),
    ("005380.KS", "005380", "현대차",           "자동차/EV",          "TSLA",421.7,201.6),
    ("009150.KS", "009150", "삼성전기",         "전력기기/전력망",    "ETN",  39.4, 28.6),
    ("329180.KS", "329180", "HD현대중공업",     "방산/항공",          "RTX",  33.6, 26.0),
    ("012450.KS", "012450", "한화에로스페이스", "방산/항공",          "RTX",  33.6, 26.0),
    ("000270.KS", "000270", "기아",             "자동차/EV",          "TSLA",421.7,201.6),
    ("012330.KS", "012330", "현대모비스",       "자동차/EV",          "TSLA",421.7,201.6),
    ("105560.KS", "105560", "KB금융",           "은행/금융",          "JPM",  14.7, 13.9),
    ("028260.KS", "028260", "삼성물산",         "산업재/기계",        "CAT",  45.2, 36.0),
    ("207940.KS", "207940", "삼성바이오로직스", "바이오/제약",        "LLY",  37.8, 28.6),
    ("055550.KS", "055550", "신한지주",         "은행/금융",          "JPM",  14.7, 13.9),
    ("068270.KS", "068270", "셀트리온",         "바이오/제약",        "LLY",  37.8, 28.6),
    ("042660.KS", "042660", "한화오션",         "방산/항공",          "RTX",  33.6, 26.0),
    ("267260.KS", "267260", "HD현대일렉트릭",   "전력기기/전력망",    "ETN",  39.4, 28.6),
    ("010120.KS", "010120", "LS ELECTRIC",      "전력기기/전력망",    "ETN",  39.4, 28.6),
    ("066570.KS", "066570", "LG전자",           "소비자 하드웨어",    "AAPL", 37.4, 33.8),
    ("298040.KS", "298040", "효성중공업",       "전력기기/전력망",    "ETN",  39.4, 28.6),
    ("005490.KS", "005490", "POSCO홀딩스",      "철강/소재",          "NUE",  23.8, 15.6),
    ("086790.KS", "086790", "하나금융지주",     "은행/금융",          "JPM",  14.7, 13.9),
    ("009540.KS", "009540", "HD한국조선해양",   "방산/항공",          "RTX",  33.6, 26.0),
    ("035420.KS", "035420", "NAVER",            "인터넷 플랫폼",      "GOOGL",29.7, 31.1),
    ("034020.KS", "034020", "두산에너빌리티",   "발전/에너지 인프라", "GEV",  31.3, 57.9),
    ("034730.KS", "034730", "SK",               "산업재/기계",        "CAT",  45.2, 36.0),
]

def _fetch_single_kr_stock(yf_ticker, code, name, sector, us_ref, us_per, us_fwd_per):
    """개별 한국 주식 PER 데이터 수집"""
    try:
        stock = yf.Ticker(yf_ticker)
        info = stock.info
        kr_per = info.get("trailingPE")
        kr_fwd = info.get("forwardPE")
        def _kimpo(kp, up):
            if kp is None or up is None or up == 0: return None
            return round(((kp / up) - 1) * 100, 1)
        def _judge_kimpo(v):
            if v is None: return "적자/무의미"
            if v > 20:  return "김프"
            if v < -20: return "역프"
            return "중립"
        kimpo     = _kimpo(kr_per, us_per)
        fwd_kimpo = _kimpo(kr_fwd, us_fwd_per)
        return {
            "code": code, "name": name, "sector": sector,
            "us_ref": us_ref,
            "kr_per":  round(kr_per, 1) if kr_per else None,
            "us_per":  us_per,
            "kimpo":   kimpo,
            "kr_fwd":  round(kr_fwd, 1) if kr_fwd else None,
            "us_fwd":  us_fwd_per,
            "fwd_kimpo": fwd_kimpo,
            "judge":     _judge_kimpo(kimpo),
            "fwd_judge": _judge_kimpo(fwd_kimpo),
            "price":  info.get("currentPrice") or info.get("regularMarketPrice"),
        }
    except Exception as e:
        print(f"  ⚠ {code} ({name}) 오류: {e}")
        return {
            "code": code, "name": name, "sector": sector, "us_ref": us_ref,
            "kr_per": None, "us_per": us_per, "kimpo": None,
            "kr_fwd": None, "us_fwd": us_fwd_per, "fwd_kimpo": None,
            "judge": "N/A", "fwd_judge": "N/A", "price": None,
        }

def collect_kospi():
    """KOSPI 500 종목 PER·김포율 데이터 수집 — wrapper"""
    print("📡 KOSPI 500 데이터 수집 중...")
    stocks = []
    for i, row in enumerate(KOSPI_TICKERS, 1):
        print(f"  [{i}/{len(KOSPI_TICKERS)}] {row[2]}...")
        data = _fetch_single_kr_stock(*row)
        stocks.append(data)
        time.sleep(0.3)
    print(f"  ✅ KOSPI {len(stocks)}개 수집 완료")
    return stocks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 내부 함수 — 관세청 무역통계 (UNI-PASS API)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CUSTOMS_API_KEY = os.environ.get("CUSTOMS_API_KEY", "")  # GitHub Secret에서 주입

# 관세청 API가 없을 때 사용하는 최근 공개 수치 (매월 수동 업데이트 가능)
TRADE_FALLBACK = {
    "period": "2026.05.1~20",
    "export_total_usd_bn": 52.6,
    "export_yoy_pct": 64.8,
    "semiconductor_usd_bn": 21.9,
    "semiconductor_yoy_pct": 202.1,
    "semiconductor_share_pct": 41.7,
    "trade_balance_usd_bn": 1.7,
    "items": [
        {"name": "반도체",        "yoy": 202.1,  "direction": "up"},
        {"name": "컴퓨터주변기기", "yoy": 305.5,  "direction": "up"},
        {"name": "석유제품",      "yoy": 46.3,   "direction": "up"},
        {"name": "가전제품",      "yoy": -6.3,   "direction": "down"},
        {"name": "승용차",        "yoy": -10.1,  "direction": "down"},
    ],
    "countries": [
        {"name": "대만",  "yoy": 110.4, "direction": "up"},
        {"name": "중국",  "yoy": 96.5,  "direction": "up"},
        {"name": "미국",  "yoy": 79.3,  "direction": "up"},
        {"name": "베트남","yoy": 70.2,  "direction": "up"},
        {"name": "EU",    "yoy": 21.7,  "direction": "up"},
    ],
    "semiconductor_trend": [
        {"label": "'25 1Q", "pct": 19.5},
        {"label": "'25 2Q", "pct": 21.2},
        {"label": "'25 3Q", "pct": 22.8},
        {"label": "'25 4Q", "pct": 24.0},
        {"label": "'26 1Q", "pct": 32.0},
        {"label": "'26 3월","pct": 35.0},
        {"label": "'26 5월","pct": 41.7},
    ],
    "source": "fallback"
}

def _fetch_customs_api(api_key, ym):
    """관세청 UNI-PASS API 호출 (API 키 보유 시)"""
    base = "https://unipass.customs.go.kr:38010/ext/rest/trtImpExpStas/retrieveTrtImpExpStas"
    params = {
        "crkyCn": api_key,
        "strtYymm": ym, "endYymm": ym,
        "hsSgn": "0", "imexTp": "1",  # 1=수출
    }
    resp = requests.get(base, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def _parse_customs_response(raw):
    """관세청 API 응답 파싱 → 표준 형식 변환"""
    # 실제 응답 구조에 맞게 파싱
    items = raw.get("trtImpExpStas", {}).get("item", [])
    return {"period": "API", "items": items, "source": "customs_api"}

def collect_trade():
    """무역통계 수집 — wrapper (API 키 있으면 실시간, 없으면 fallback)"""
    print("📡 무역통계 수집 중...")
    if CUSTOMS_API_KEY:
        try:
            ym = datetime.now().strftime("%Y%m")
            raw = _fetch_customs_api(CUSTOMS_API_KEY, ym)
            data = _parse_customs_response(raw)
            data["source"] = "customs_api"
            print("  ✅ 관세청 API 실시간 데이터 수집 완료")
            return data
        except Exception as e:
            print(f"  ⚠ 관세청 API 오류 ({e}), fallback 사용")
    else:
        print("  ℹ CUSTOMS_API_KEY 없음 → fallback 데이터 사용")
    return TRADE_FALLBACK


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 Wrapper — 전체 수집 후 JSON 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_payload(nasdaq, kospi, trade):
    """수집된 데이터를 최종 JSON 형태로 조합"""
    kst = timezone(timedelta(hours=9))
    return {
        "updated_at": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST"),
        "nasdaq": nasdaq,
        "kospi": kospi,
        "trade": trade,
    }

def _save_json(payload, path="data/latest.json"):
    """JSON 파일 저장"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  💾 저장 완료: {path}")

def run():
    """전체 데이터 수집 실행 — 단일 진입점"""
    print("=" * 50)
    print("  글투 데이터 수집 시작")
    print("=" * 50)
    nasdaq = collect_nasdaq()
    kospi  = collect_kospi()
    trade  = collect_trade()
    payload = _build_payload(nasdaq, kospi, trade)
    _save_json(payload)
    print("=" * 50)
    print(f"  ✅ 완료: {payload['updated_at']}")
    print("=" * 50)


if __name__ == "__main__":
    run()
