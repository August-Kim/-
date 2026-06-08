"""
collect_data.py
글투(글로벌 투자 통합 대시보드) 데이터 수집 스크립트
실행: python scripts/collect_data.py
출력: data/latest.json
"""

import json
import os
import time
import xml.etree.ElementTree as ET
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


CUSTOMS_API_KEY = os.environ.get("CUSTOMS_API_KEY", "")
CUSTOMS_URL = "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"

# 글투 품목 → HS코드(2~4단위 대표코드) 매핑
ITEM_HS_MAP = [
    ("반도체",         "8542"),
    ("컴퓨터주변기기", "8471"),
    ("석유제품",       "2710"),
    ("가전제품",       "8418"),
    ("승용차",         "8703"),
]

# 주요 수출 상대국 → 관세청 국가코드
# (국가별 수출입실적 API는 별도 — 여기선 품목 중심이라 국가 데이터는 fallback 유지)

# API 실패 시 사용할 기존 수치 (안전망)
TRADE_FALLBACK = {
    "period": "2026.05.1~20",
    "export_total_usd_bn": 52.6, "export_yoy_pct": 64.8,
    "semiconductor_usd_bn": 21.9, "semiconductor_yoy_pct": 202.1,
    "semiconductor_share_pct": 41.7, "trade_balance_usd_bn": 1.7,
    "items": [
        {"name": "반도체", "yoy": 202.1, "direction": "up"},
        {"name": "컴퓨터주변기기", "yoy": 305.5, "direction": "up"},
        {"name": "석유제품", "yoy": 46.3, "direction": "up"},
        {"name": "가전제품", "yoy": -6.3, "direction": "down"},
        {"name": "승용차", "yoy": -10.1, "direction": "down"},
    ],
    "countries": [
        {"name": "대만", "yoy": 110.4, "direction": "up"},
        {"name": "중국", "yoy": 96.5, "direction": "up"},
        {"name": "미국", "yoy": 79.3, "direction": "up"},
        {"name": "베트남", "yoy": 70.2, "direction": "up"},
        {"name": "일본", "yoy": 21.7, "direction": "up"},
    ],
    "semiconductor_trend": [
        {"label": "'25 1Q", "pct": 19.5}, {"label": "'25 2Q", "pct": 21.2},
        {"label": "'25 3Q", "pct": 22.8}, {"label": "'25 4Q", "pct": 24.0},
        {"label": "'26 1Q", "pct": 32.0}, {"label": "'26 3월", "pct": 35.0},
        {"label": "'26 5월", "pct": 41.7},
    ],
    "source": "fallback",
}


def _fetch_item_total(api_key, hs_sgn, yymm):
    """특정 품목·특정월 수출입 총액 조회 → (수출$, 수입$, 무역수지$) 또는 None"""
    params = {
        "serviceKey": api_key,
        "strtYymm": yymm, "endYymm": yymm,
        "hsSgn": hs_sgn,
    }
    try:
        resp = requests.get(CUSTOMS_URL, params=params, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        if root.findtext(".//resultCode") not in ("00", None):
            return None
        for item in root.findall(".//item"):
            if item.findtext("year") == "총계":
                exp = int(item.findtext("expDlr") or 0)
                imp = int(item.findtext("impDlr") or 0)
                bal = int(item.findtext("balPayments") or 0)
                return (exp, imp, bal)
    except Exception as e:
        print(f"    ⚠ {hs_sgn} {yymm} 조회 오류: {e}")
    return None


def _yoy(cur, prev):
    """전년동월 대비 증감률(%)"""
    if not prev or prev == 0:
        return None
    return round(((cur / prev) - 1) * 100, 1)


def _latest_available_month():
    """관세청 확정치 약 20일 지연 → 2개월 전을 기준월로. (당월YYYYMM, 전년동월YYYYMM)"""
    now = datetime.now()
    month, year = now.month - 2, now.year
    if month <= 0:
        month += 12
        year -= 1
    return f"{year}{month:02d}", f"{year-1}{month:02d}"


def _fetch_grand_total(api_key, yymm):
    """hsSgn 없이 호출 → 전체 수출 총액 조회 (반도체 비중 계산용 분모)"""
    params = {
        "serviceKey": api_key,
        "strtYymm": yymm, "endYymm": yymm,
    }
    try:
        resp = requests.get(CUSTOMS_URL, params=params, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        if root.findtext(".//resultCode") not in ("00", None):
            return None
        # year=총계 행에서 전체 수출액 추출
        for item in root.findall(".//item"):
            if item.findtext("year") == "총계":
                return int(item.findtext("expDlr") or 0)
    except Exception as e:
        print(f"    ⚠ 전체 총액 조회 오류: {e}")
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 국가별 수출입실적 (공공데이터포털) — 국가별 YoY 자동화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COUNTRY_URL = "https://apis.data.go.kr/1220000/nationtrade/getNationtradeList"

# 글투 국가 → 관세청 국가코드(ISO 2자리)
COUNTRY_CD_MAP = [
    ("대만",   "TW"),
    ("중국",   "CN"),
    ("미국",   "US"),
    ("베트남", "VN"),
    ("일본",   "JP"),
]

def _fetch_country_total(api_key, cnty_cd, yymm):
    """특정 국가·특정월 수출액 조회 → 수출$ 또는 None"""
    params = {
        "serviceKey": api_key,
        "strtYymm": yymm, "endYymm": yymm,
        "cntyCd": cnty_cd,
    }
    try:
        resp = requests.get(COUNTRY_URL, params=params, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        if root.findtext(".//resultCode") not in ("00", None):
            return None
        # 단일 국가 조회 → 첫 item에서 수출액 추출
        item = root.find(".//item")
        if item is not None:
            return int(item.findtext("expDlr") or 0)
    except Exception as e:
        print(f"    ⚠ {cnty_cd} {yymm} 조회 오류: {e}")
    return None

def _collect_countries(api_key, cur_ym, prev_ym):
    """국가별 수출 YoY 수집 → 리스트 또는 None(실패 시)"""
    countries = []
    for name, cd in COUNTRY_CD_MAP:
        cur = _fetch_country_total(api_key, cd, cur_ym)
        prev = _fetch_country_total(api_key, cd, prev_ym)
        if cur is None:
            print(f"    ⚠ {name}({cd}) 데이터 없음, 건너뜀")
            continue
        yoy = _yoy(cur, prev)
        countries.append({
            "name": name,
            "yoy": yoy if yoy is not None else 0,
            "direction": "up" if (yoy or 0) >= 0 else "down",
        })
        print(f"    ✅ {name}: 수출 ${cur/1e8:.1f}억 (YoY {yoy}%)")
    return countries if countries else None


def collect_trade():
    """무역통계 수집 — wrapper. API 성공 시 실시간, 실패 시 fallback"""
    print("📡 무역통계 수집 중 (관세청 품목별 API)...")
    if not CUSTOMS_API_KEY:
        print("  ℹ CUSTOMS_API_KEY 없음 → fallback 사용")
        return TRADE_FALLBACK

    cur_ym, prev_ym = _latest_available_month()
    print(f"  기준월: {cur_ym} (전년동월 {prev_ym} 대비)")

    items = []
    semi_exp_cur = None
    total_exp_cur = 0
    total_bal_cur = 0

    for name, hs in ITEM_HS_MAP:
        cur = _fetch_item_total(CUSTOMS_API_KEY, hs, cur_ym)
        prev = _fetch_item_total(CUSTOMS_API_KEY, hs, prev_ym)
        if cur is None:
            print(f"    ⚠ {name} 데이터 없음, 건너뜀")
            continue
        exp_cur, imp_cur, bal_cur = cur
        exp_prev = prev[0] if prev else None
        yoy = _yoy(exp_cur, exp_prev)
        items.append({
            "name": name,
            "yoy": yoy if yoy is not None else 0,
            "direction": "up" if (yoy or 0) >= 0 else "down",
        })
        total_exp_cur += exp_cur
        total_bal_cur += bal_cur
        if name == "반도체":
            semi_exp_cur = exp_cur
            semi_yoy = yoy
        print(f"    ✅ {name}: 수출 ${exp_cur/1e8:.1f}억 (YoY {yoy}%)")

    if not items:
        print("  ⚠ 전 품목 실패 → fallback 사용")
        return TRADE_FALLBACK

    # 전체 수출 총액 조회 (반도체 비중의 정확한 분모)
    grand_total = _fetch_grand_total(CUSTOMS_API_KEY, cur_ym)
    if grand_total and semi_exp_cur:
        semi_share = round((semi_exp_cur / grand_total) * 100, 1)
        print(f"    ℹ 전체 수출 ${grand_total/1e8:.1f}억 기준 반도체 비중 {semi_share}%")
    else:
        semi_share = None

    # 국가별 수출 YoY 자동 수집
    print("  📡 국가별 수출 수집 중...")
    countries = _collect_countries(CUSTOMS_API_KEY, cur_ym, prev_ym)

    result = dict(TRADE_FALLBACK)  # 차트 데이터는 유지
    result["period"] = cur_ym[:4] + "." + cur_ym[4:] + " (확정치)"
    result["items"] = items
    if countries:
        result["countries"] = countries
    result["export_total_usd_bn"] = round(grand_total / 1e8, 1) if grand_total else None
    result["semiconductor_usd_bn"] = round(semi_exp_cur / 1e8, 1) if semi_exp_cur else None
    result["semiconductor_yoy_pct"] = semi_yoy
    result["semiconductor_share_pct"] = semi_share
    result["trade_balance_usd_bn"] = round(total_bal_cur / 1e8, 1)
    result["source"] = "customs_api"
    print(f"  ✅ 관세청 실시간 수집 완료 (반도체 비중 {semi_share}%)")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 Wrapper — 전체 수집 후 JSON 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _update_history(trade, path="data/history.json"):
    """반도체 비중을 월별 history에 누적. 같은 달은 갱신, 새 달은 추가."""
    share = trade.get("semiconductor_share_pct")
    period = trade.get("period", "")  # 예: "2026.04 (확정치)"
    if share is None or not period:
        return trade

    # period에서 'YY MM' 라벨 생성 (예: 2026.04 → '26 4월)
    ym = period.split(" ")[0]  # "2026.04"
    try:
        yy = ym.split(".")[0][2:]
        mm = int(ym.split(".")[1])
        label = f"'{yy} {mm}월"
    except Exception:
        label = ym

    # 기존 history 로드
    history = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    # 같은 라벨 있으면 갱신, 없으면 추가
    found = False
    for h in history:
        if h["label"] == label:
            h["pct"] = share
            found = True
            break
    if not found:
        history.append({"label": label, "pct": share})

    # 최근 12개월만 유지
    history = history[-12:]

    # 저장
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  📈 비중 history 갱신: {label} = {share}% (총 {len(history)}개월)")

    # trade에 history 합치기 (차트용)
    trade["semiconductor_history"] = history
    return trade


def _build_payload(nasdaq, kospi, trade):
    """수집된 데이터를 최종 JSON 형태로 조합"""
    kst = timezone(timedelta(hours=9))
    trade = _update_history(trade)  # 비중 history 누적
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
