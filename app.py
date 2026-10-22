# ==============================================================================
# GANGJIN AI TRADER PRO — App (17.0 FINAL) — 12-Agent Control Tower & Behavioral Journal Edition
# - ⭐ 실시간 시세 동기화 엔진 탑재 (Nasdaq / Yahoo 1d·5m / Finnhub / CNBC 교차 검증 + 일봉 실시간 병합)
# - ⭐ [16.4] 뉴스 4중 수집 (Finnhub -> Yahoo 공식 RSS -> Google RSS -> Nasdaq News API)
# - ⭐ [16.4] 전 섹터(방산·우주·AI·반도체·바이오·전기차·크립토·금융·SEC공시) 호재·악재 사전 완비
# - ⭐ [16.4] 단어 경계(Regex) 정밀 매칭으로 'mission->miss', 'execute->cut', 'award->war' 오탐 원천 차단
# - ⭐ [16.4] 과거 호재·악재 무조건 선별 패스 (72h 하드 컷오프 + 48h 시그널 컷오프 + 회고성 기사/역행 호재 패스)
# - ⭐ [16.4] 중대 악재 발생 시 RSI 과매도 역발상(PANIC BUY) 자동 차단 (떨어지는 칼날 진입 방지)
# - ⭐ [16.5] 실적발표일 6중 정밀 탐지 엔진 (Nasdaq API -> Finnhub -> CNBC -> Yahoo 다중포맷 -> 뉴스PR 추출 -> KNOWN_EARNINGS + 분기주기 자동추정)
# - ⭐ [16.5-R1] 실시간 봉 병합 로직 안전화 + 뉴스 수집 10분 캐시 분리 + 오탐 방지 문구 정밀화
# - ⭐ [17.0 NEW] 12개 전문 에이전트 멀티팀 통합 (Data·Chart·Macro·Master·News·Policy·Options·Onchain·Supply·Squeeze·Insider·Institutional)
# - ⭐ [17.0 NEW] Chief AI Manager (달리오 레짐 가중치 + 소로스 출구 + 튜더존스 200일선 + 드러켄밀러 변동성 사이징 + 8단계 기관급 Veto 거부권)
# - ⭐ [17.0 NEW] ThreadPoolExecutor 병렬 실행 엔진 탑재 (12개 팀 동시 고속 연산 및 0ms 섹터 사전 매핑으로 체감 지연 제로화)
# - ⭐ [17.0 NEW] Journal Agent 탑재 (매매일지 8대 잘못된 매매 습관/심리 편향 자동 지적 + 대가 기법별·심리별·종목별 승률 리더보드)
# ==============================================================================
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import html
import io
import os
import sqlite3
import logging
import urllib.request
import urllib.parse
import time
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests

# ⭐️ 데이터 이중화를 위한 라이브러리 Import
try:
    import xfinance as xf
    HAS_XFINANCE = True
except ImportError:
    HAS_XFINANCE = False
    xf = None

try:
    import finnhub
    HAS_FINNHUB_LIB = True
except ImportError:
    HAS_FINNHUB_LIB = False
    finnhub = None

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False


# ==============================================================================
# 1) CONFIG (전 섹터 호재·악재 키워드 사전 완비)
# ==============================================================================
CFG = {
    "cache": {
        "live_quote": 20, "history": 60, "indices": 30, "top_bar": 30, "market_cap": 3600,
        "fear_greed": 1800, "macro": 180, "gamma": 1800, "scanner": 120,
        "noise_filter": 60, "short_interest": 3600, "gex": 1800, "earnings": 1800,
        "news_candidates": 600, "policy": 600, "options_flow": 1800, "onchain": 180, "supply": 600, "insider": 3600, "institutional": 3600,
    },
    "ind": {
        "rsi_period": 14, "rsi_panic": 25.0, "rsi_oversold": 35.0, "rsi_overbought": 70.0,
        "rsi_take_profit": 74.0, "atr_period": 14, "box_period": 20,
        "vol_breakout": 1.5, "vol_exit": 1.4,
    },
    "trail": {
        "leverage_etfs": frozenset({
            "SOXL", "TQQQ", "SQQQ", "SOXS", "TSLL", "NVDL", "MSTU", "MSTX",
            "CONL", "BITX", "UPRO", "TMF", "LABU", "FNGU", "BULZ",
        }),
        "tiers": {
            "mega":  {"min": 200e9, "tight": (4.0, 6.5), "core": (6.0, 9.0)},
            "large": {"min": 10e9,  "tight": (5.0, 7.5), "core": (7.0, 10.5)},
            "mid":   {"min": 2e9,   "tight": (6.5, 9.5), "core": (9.0, 13.5)},
            "small": {"min": 0,     "tight": (8.0, 12.0), "core": (11.5, 17.5)},
        },
        "leverage_tier": {"tight": (7.0, 11.0), "core": (10.0, 16.0)},
        "fallback": {
            "high": {"atr_min": 5.5, "tight": (8.0, 12.0), "core": (11.5, 17.0)},
            "mid":  {"atr_min": 3.5, "tight": (6.0, 9.0),  "core": (8.5, 13.0)},
            "low":  {"atr_min": 0,   "tight": (4.5, 7.0),  "core": (6.5, 9.5)},
        },
    },
    "macro": {
        "nq_strong": 1.0, "es_strong": 0.8, "wti_spike_chg": 2.5, "wti_spike_price": 85.0,
        "wti_stable": 75.0, "tnx_spike_price": 4.5, "tnx_spike_chg": 1.5, "tnx_stable": 4.1,
        "vix_crisis": 23.0, "vix_calm": 18.0,
    },
    "news": {
        # ⭐ 1. 확정적 수주·계약·임상승인·인수합병·지수편입 호재 (단독 매칭 시 즉시 호재 인정)
        "contract_strong": (
            # 방산·우주·정부조달·일반 대형 수주
            "contract award", "awarded", "wins contract", "won contract", "secures", "secured",
            "lands", "selected for", "downselect", "sole source", "sole-source", "task order",
            "follow-on", "idiq", "program of record", "full-rate production", "ota agreement",
            "pentagon contract", "dod contract", "navy contract", "air force contract",
            "army contract", "space force", "darpa", "nasa contract", "doe loan", "chips act",
            "definitive agreement", "multiyear", "multi-year", "strategic partnership",
            "strategic alliance", "joint venture", "new contract", "major contract",
            "new deal", "major deal", "signs deal", "signed deal", "signs agreement",
            "inks deal", "contract value rises", "contract modification", "ceiling increase",
            "backlog rises", "record backlog", "successful launch", "faa license", "fcc approval",
            # AI·반도체·데이터센터·네오클라우드·전력
            "hyperscaler", "ai deal", "ai cloud", "gpu cluster", "hpc contract", "colocation deal",
            "hosting agreement", "power purchase agreement", "ppa", "mw expansion", "gw pipeline",
            "energized", "energizes", "design win", "tape-out", "mass production", "sovereign ai",
            "ai factory",
            # 바이오·제약·의료기기 (FDA 승인·임상 성공·기술수출)
            "fda approval", "fda approves", "fda cleared", "fda clearance", "510(k)",
            "de novo", "breakthrough therapy", "fast track", "priority review", "orphan drug",
            "accelerated approval", "positive topline", "met primary endpoint",
            "meets primary endpoint", "statistically significant", "phase 2 success",
            "phase 3 success", "positive phase", "ema approval", "licensing deal",
            "milestone payment", "royalty deal",
            # 전기차·모빌리티·양자·크립토·M&A·지수편입
            "fsd approval", "robotaxi", "quantum advantage", "qubit milestone", "hashrate record",
            "s&p 500 inclusion", "joins s&p 500", "added to s&p", "nasdaq-100 inclusion",
            "added to nasdaq-100", "russell 1000", "russell 2000 inclusion", "bank charter",
            "buyout", "takeover", "tender offer", "all-cash deal", "spin-off", "spinoff",
        ),
        # ⭐ 조건부 계약 단어 (아래 contract_action_verbs 중 하나와 함께 쓰일 때만 호재로 인정)
        "contract_context": (
            "contract", "deal", "partnership", "agreement", "award", "alliance", "expansion", "order", "orders",
        ),
        "contract_action_verbs": (
            "win", "wins", "won", "sign", "signs", "signed", "award", "awards", "awarded",
            "secure", "secures", "secured", "land", "lands", "ink", "inks", "expand", "expands",
            "expanded", "extend", "extends", "extended", "renew", "renews", "renewed",
            "select", "selected", "clinches", "million", "billion",
        ),
        # ⭐ 2. 실적·어닝·가이던스 상향·투자의견 상향·자사주매입·내부자매수 호재
        "earnings_bull": (
            "beat", "beats", "topped", "tops estimates", "beats estimates", "blowout",
            "record revenue", "record earnings", "record profit", "record deliveries",
            "delivery beat", "deliveries beat", "same-store sales beat", "comp sales beat",
            "record bookings", "surge", "surges", "soars", "strong guidance", "raises guidance",
            "raised guidance", "hikes guidance", "boosts guidance", "upbeat guidance",
            "swings to profit", "turns profitable", "margin expansion", "eps beat", "revenue beat",
            "outperform", "overweight", "upgrade", "upgraded", "upgrades", "initiates with buy",
            "strong buy", "top pick", "buyback", "repurchase", "accelerated share repurchase",
            "dividend hike", "raises dividend", "dividend increase", "special dividend",
            "insider buy", "insider buying", "ceo buys", "cfo buys", "director buys",
            "cluster buying", "regains compliance", "credit upgrade", "short squeeze",
        ),
        # ⭐ 3. 중대 악재 (단 1건만 포착되어도 즉시 위험 경보 & RSI 과매도 역발상 매수 차단!)
        "bad_severe": (
            # 계약 해지·중단·취소·분쟁 (방산·우주·정부·수주 산업)
            "halt", "halts", "halted", "halt purchases", "halts purchases", "halts orders",
            "stop work", "stop-work", "work stoppage", "cancel", "cancels", "cancelled",
            "canceled", "cancellation", "terminate", "terminates", "terminated", "termination",
            "terminated for convenience", "terminated for default", "with prejudice",
            "scrap", "scraps", "scrapped", "pause", "pauses", "paused",
            "suspend", "suspends", "suspended", "suspension", "debarment", "debarred",
            "revoke", "revokes", "revoked", "withdraw", "withdraws", "withdrawn", "withdrawal",
            "losing a", "loses contract", "lost contract", "contract loss", "customer cancellation",
            "dispute", "bid protest", "gao protest", "cure notice", "show cause",
            "navy halts", "army halts", "air force halts", "pentagon cuts", "dod cuts", "doge",
            "launch failure", "mission failure", "faa grounding", "grounded", "payload lost",
            # 유상증자·희석·전환사채·내부자 대량매도 (SEC Filings: S-3, Form 144, 424B5, ATM, PIPE)
            "offering", "public offering", "direct offering", "registered direct",
            "shelf registration", "s-3", "form s-3", "424b5", "atm offering", "at-the-market",
            "equity distribution", "equity line", "eloc", "pipe", "private placement",
            "convertible note", "convertible senior", "convertible debt", "warrant exercise",
            "inducement", "dilution", "dilutive", "secondary offering", "block trade",
            "selling shareholders", "reverse split", "reverse stock split",
            "form 144", "insider sale", "insider selling", "ceo sells", "cfo sells", "files to sell",
            # 소송·수사·회계부정·상장폐지·파산·공매도 리포트
            "lawsuit", "class action", "probe", "subpoena", "sec investigation", "sec probe",
            "sec charges", "doj investigation", "doj probe", "grand jury", "wells notice",
            "ftc lawsuit", "antitrust lawsuit", "cfpb lawsuit", "fdic consent order",
            "indictment", "fraud", "accounting irregularities", "whistleblower",
            "restatement", "restates", "non-reliance", "item 4.02", "material weakness",
            "going concern", "auditor resigns", "auditor dismissed", "nt 10-k", "nt 10-q",
            "delayed 10-k", "delayed 10-q", "late filing", "non-compliance", "deficiency notice",
            "nasdaq notice", "nyse notice", "minimum bid price", "delist", "delisting",
            "bankruptcy", "chapter 11", "chapter 7", "insolvency", "default", "debt restructuring",
            "liquidation", "short seller", "short report", "hindenburg", "muddy waters",
            "citron", "culper", "grizzly research", "fuzzy panda", "kerrisdale", "wolfpack",
            "scorpion capital", "bleecker street", "spruce point", "hunterbrook",
            # 바이오·제약 임상실패·FDA 거절
            "complete response letter", "crl", "clinical hold", "partial clinical hold",
            "refusal to file", "fda rejects", "fda rejection", "fda denies", "denies approval", "denies motion to dismiss", "motion to dismiss denied", "fda warning letter", "form 483",
            "boxed warning", "black box warning", "missed primary endpoint", "failed to meet",
            "fails to meet", "did not meet primary endpoint", "trial failure", "phase 2 failure",
            "phase 3 failure", "discontinues trial", "terminates trial", "halted trial",
            "serious adverse", "patient death", "safety signal",
            # 수출통제·해킹·가동중단·주가 폭락·신저가
            "export ban", "chip ban", "entity list", "ransomware", "data breach", "exchange hack",
            "factory shutdown", "production halt", "mass recall", "nhtsa probe",
            "crash", "crashes", "crashed", "plunge", "plunges", "plunged", "plummet", "plummets",
            "52-week low", "all-time low", "record low",
        ),
        # ⭐ 4. 일반 악재 (어닝 미스, 가이던스 하향, 투자의견 하향, 감원, 지연, 리콜 등)
        "bad_strict": (
            "miss", "misses", "missed", "revenue miss", "eps miss", "delivery miss",
            "deliveries fell", "deliveries drop", "comp sales miss", "shortfall",
            "weak guidance", "soft guidance", "lowers guidance", "lowered guidance",
            "slashes guidance", "withdraws guidance", "downbeat guidance",
            "downgrade", "downgrades", "downgraded", "underperform", "underweight", "sell rating",
            "credit downgrade", "junk status", "slash", "slashes", "slashed",
            "delay", "delays", "delayed", "tape-out delay", "rack delay", "datacenter delay",
            "yield issue", "overheating", "design flaw", "lose", "loses", "lost",
            "loss", "losses", "widening loss", "net loss widens", "margin compression",
            "rising delinquencies", "charge-offs", "deposit outflow", "inventory glut",
            "reject", "rejects", "rejected", "fail", "fails", "failed", "failure",
            "warning", "warns", "profit warning", "headwind", "headwinds",
            "slump", "slumps", "tumble", "tumbles", "sink", "sinks", "slide", "slides",
            "recall", "cyberattack", "cloud outage", "service outage",
            "strike", "union strike", "walkout", "boycott", "fine", "penalty",
        ),
        "cut_bullish": (
            "rate cut", "cuts rate", "cut rates", "interest rate cut", "fed cut",
            "price target raised", "raises price target", "hikes price target", "boosts price target",
            "tax cut", "cuts loss", "narrowed loss",
        ),
        "cut_bearish": (
            "guidance cut", "cuts guidance", "cut guidance", "dividend cut", "cuts dividend",
            "dividend suspension", "suspends dividend", "job cut", "job cuts", "layoff", "layoffs",
            "workforce reduction", "headcount reduction", "production cut", "cuts production",
            "capex cut", "price target cut", "cuts price target", "lowered price target",
            "lowers price target", "order cut", "cuts orders", "budget cut", "funding cut",
            "backlog cut", "supply cut",
        ),
        # ⭐ 5. [16.5-R1] 오탐 방지("denies" 단독 매칭을 정밀 구문으로 교체하여 'FDA denies' 오탐 차단)
        "bad_false_positive": (
            "no orders were stopped", "no orders were canceled", "no orders were cancelled",
            "not cancel", "did not cancel",
            "denies report", "denies rumor", "denies rumors", "denies wrongdoing",
            "denies allegations", "denies sec probe", "denies investigation", "denies claims",
            "denies injunction", "denies preliminary injunction", "injunction denied",
            "denies class action", "denies class certification", "denies bid protest",
            "reaffirms", "reaffirmed",
            "continued investment", "continued u.s. navy investment", "resumes work",
            "resumes trading", "lifts halt", "lifts suspension", "lifts clinical hold",
            "dismisses lawsuit", "lawsuit dismissed", "settles lawsuit", "probe closed",
            "investigation closed", "no dilution", "no offering", "non-dilutive",
            "unstoppable", "non-stop", "one-stop", "narrowed loss", "cuts loss", "beats loss",
            "smaller-than-expected loss", "without delay", "zero default",
        ),
        # ⭐ 6. 과거 회고성/클릭베이트 스팸 기사 필터 (오늘 날짜로 재발행되어도 즉시 패스)
        "retrospective_skip": (
            "if you invested", "years ago", "months ago", "last month", "last quarter",
            "last year", "in 2022", "in 2023", "in 2024", "in 2025",
            "why .* dropped last", "what happened last", "here's why .* fell in",
            "looking back at", "how much you would have",
        ),
        # ⭐ 7. 거시·지정학 키워드 ('war'->'award', 'ban'->'bank', 'rate'->'operating' 오탐 방지)
        "geo": (
            "war", "wars", "warfare", "tariff", "tariffs", "sanction", "sanctions",
            "inflation", "stagflation", "fomc", "federal reserve", "powell", "rate hike",
            "interest rate", "cpi", "pce", "missile", "iran", "china", "taiwan",
            "export control", "trade war", "geopolitical", "middle east",
        ),
        # ⭐ 8. 과거 호재·악재 선별 패스 기준 시간(시간)
        "recency_hours": {
            "breaking": 12.0,    # 12시간 이내: 초신선 속보 (가중치 1.15)
            "fresh": 24.0,       # 24시간 이내: 당일 핵심 재료 (가중치 1.00)
            "recent": 48.0,      # 48시간 이내: 유효 단기 재료 (가중치 0.75)
            "stale_pass": 72.0,  # 48~72시간: 과거 재료 → 점수/건수 무조건 패스(0.0), 목록에만 참고 표시
        },
        "bad_recent_threshold": 0.7,
        "recovery_pct_forgive": 3.0,
        "recovery_bonus": 6,
        "recovery_min_age_hours": 24.0,
    },
    "noise": {
        "minor_atr_mult": 1.35, "band_atr_mult": 1.8, "chandelier_atr": 2.8,
        "tight_atr": 2.0, "warn_ratio": 75.0, "confirm_bear": 6.0,
        "confirm_watch": 3.0, "confirm_bull": 5.0,
    },
    "squeeze": {
        "short_pct_high": 20.0, "short_pct_mid": 10.0,
        "dtc_high": 7.0, "dtc_mid": 4.0,
        "squeeze_bonus_max": 10,
    },
    "paths": {"db": "data/portfolio.db", "logs": "data/logs"},
    "usd_krw_fallback": 1380.0,
    # ⭐ [16.5] 야후/외부 API 조회 실패 대비 주요 종목 실적 발표일 수동 보정 사전 (2025~2027 분기별 일정)
    "known_earnings": {
        "IREN":  ["2025-02-12", "2025-05-14", "2025-08-28", "2025-11-06", "2026-02-05", "2026-05-07", "2026-08-26", "2026-11-05", "2027-02-10"],
        "NVDA":  ["2025-02-26", "2025-05-28", "2025-08-27", "2025-11-19", "2026-02-25", "2026-05-27", "2026-08-26", "2026-11-18", "2027-02-24"],
        "TSLA":  ["2025-01-29", "2025-04-22", "2025-07-23", "2025-10-22", "2026-01-28", "2026-04-21", "2026-07-22", "2026-10-21", "2027-01-27"],
        "PLTR":  ["2025-02-03", "2025-05-05", "2025-08-04", "2025-11-03", "2026-02-02", "2026-05-04", "2026-08-03", "2026-11-02", "2027-02-01"],
        "MSTR":  ["2025-02-05", "2025-05-01", "2025-07-31", "2025-10-30", "2026-02-04", "2026-04-30", "2026-08-04", "2026-10-29", "2027-02-03"],
        "IONQ":  ["2025-02-26", "2025-05-07", "2025-08-06", "2025-11-05", "2026-02-25", "2026-05-06", "2026-08-05", "2026-11-04", "2027-02-24"],
        "AAPL":  ["2025-01-30", "2025-05-01", "2025-07-31", "2025-10-30", "2026-01-29", "2026-04-30", "2026-07-30", "2026-10-29", "2027-01-28"],
        "MSFT":  ["2025-01-29", "2025-04-30", "2025-07-29", "2025-10-28", "2026-01-28", "2026-04-29", "2026-07-28", "2026-10-27", "2027-01-27"],
        "AMZN":  ["2025-02-06", "2025-05-01", "2025-08-06", "2025-10-30", "2026-02-05", "2026-04-30", "2026-08-05", "2026-10-29", "2027-02-04"],
        "GOOGL": ["2025-02-04", "2025-04-24", "2025-07-22", "2025-10-28", "2026-02-03", "2026-04-28", "2026-07-28", "2026-10-27", "2027-02-02"],
        "META":  ["2025-01-29", "2025-04-30", "2025-07-30", "2025-10-29", "2026-01-28", "2026-04-29", "2026-07-29", "2026-10-28", "2027-01-27"],
        "AMD":   ["2025-02-04", "2025-05-06", "2025-08-05", "2025-11-04", "2026-02-03", "2026-05-05", "2026-08-04", "2026-11-03", "2027-02-02"],
        "AVGO":  ["2025-03-06", "2025-06-05", "2025-09-04", "2025-12-11", "2026-03-05", "2026-06-10", "2026-09-03", "2026-12-10", "2027-03-04"],
        "SMCI":  ["2025-02-11", "2025-05-06", "2025-08-05", "2025-11-04", "2026-02-10", "2026-05-05", "2026-08-04", "2026-11-03", "2027-02-09"],
        "ARM":   ["2025-02-05", "2025-05-07", "2025-07-30", "2025-11-05", "2026-02-04", "2026-05-06", "2026-07-29", "2026-11-04", "2027-02-03"],
        "TSM":   ["2025-01-16", "2025-04-17", "2025-07-17", "2025-10-16", "2026-01-15", "2026-04-16", "2026-07-16", "2026-10-15", "2027-01-14"],
        "MU":    ["2025-03-20", "2025-06-25", "2025-09-24", "2025-12-17", "2026-03-18", "2026-06-24", "2026-09-23", "2026-12-16", "2027-03-17"],
        "INTC":  ["2025-01-30", "2025-04-24", "2025-07-31", "2025-10-29", "2026-01-29", "2026-04-23", "2026-07-30", "2026-10-29", "2027-01-28"],
        "COIN":  ["2025-02-13", "2025-05-08", "2025-08-07", "2025-11-06", "2026-02-12", "2026-05-07", "2026-08-06", "2026-11-05", "2027-02-11"],
        "MARA":  ["2025-02-26", "2025-05-08", "2025-08-06", "2025-11-05", "2026-02-25", "2026-05-07", "2026-08-05", "2026-11-04", "2027-02-24"],
        "RIOT":  ["2025-02-24", "2025-05-01", "2025-07-31", "2025-10-30", "2026-02-23", "2026-05-04", "2026-08-03", "2026-11-02", "2027-02-22"],
        "CLSK":  ["2025-02-06", "2025-05-08", "2025-08-07", "2025-11-20", "2026-02-05", "2026-05-07", "2026-08-06", "2026-11-19", "2027-02-04"],
        "RKLB":  ["2025-02-27", "2025-05-08", "2025-08-07", "2025-11-10", "2026-02-26", "2026-05-07", "2026-08-06", "2026-11-09", "2027-02-25"],
        "ASTS":  ["2025-03-03", "2025-05-14", "2025-08-14", "2025-11-13", "2026-03-02", "2026-05-13", "2026-08-13", "2026-11-12", "2027-03-01"],
        "LUNR":  ["2025-03-24", "2025-05-13", "2025-08-12", "2025-11-11", "2026-03-19", "2026-05-12", "2026-08-11", "2026-11-10", "2027-03-18"],
        "SOFI":  ["2025-01-27", "2025-04-29", "2025-07-29", "2025-10-28", "2026-01-26", "2026-04-28", "2026-07-28", "2026-10-27", "2027-01-25"],
        "HOOD":  ["2025-02-12", "2025-05-07", "2025-08-06", "2025-11-05", "2026-02-11", "2026-05-06", "2026-08-05", "2026-11-04", "2027-02-10"],
        "NFLX":  ["2025-01-21", "2025-04-17", "2025-07-17", "2025-10-21", "2026-01-20", "2026-04-16", "2026-07-16", "2026-10-20", "2027-01-19"],
        "CRWD":  ["2025-03-04", "2025-06-03", "2025-08-27", "2025-11-25", "2026-03-03", "2026-06-02", "2026-08-26", "2026-11-24", "2027-03-02"],
        "PANW":  ["2025-02-13", "2025-05-20", "2025-08-18", "2025-11-19", "2026-02-17", "2026-05-19", "2026-08-17", "2026-11-18", "2027-02-16"],
        "SNOW":  ["2025-02-26", "2025-05-21", "2025-08-20", "2025-11-19", "2026-02-25", "2026-05-20", "2026-08-26", "2026-11-18", "2027-02-24"],
        "LLY":   ["2025-02-06", "2025-05-01", "2025-08-07", "2025-10-30", "2026-02-05", "2026-04-30", "2026-08-06", "2026-10-29", "2027-02-04"],
        "UNH":   ["2025-01-16", "2025-04-17", "2025-07-15", "2025-10-14", "2026-01-15", "2026-04-16", "2026-07-16", "2026-10-15", "2027-01-14"],
        "ORCL":  ["2025-03-10", "2025-06-11", "2025-09-09", "2025-12-08", "2026-03-09", "2026-06-10", "2026-09-08", "2026-12-07", "2027-03-08"],
        "HIMS":  ["2025-02-24", "2025-05-05", "2025-08-04", "2025-11-03", "2026-02-23", "2026-05-04", "2026-08-03", "2026-11-02", "2027-02-22"],
        "RDDT":  ["2025-02-12", "2025-05-01", "2025-08-05", "2025-10-28", "2026-02-11", "2026-05-05", "2026-08-04", "2026-10-27", "2027-02-10"],
        "APP":   ["2025-02-12", "2025-05-07", "2025-08-06", "2025-11-05", "2026-02-11", "2026-05-06", "2026-08-05", "2026-11-04", "2027-02-10"],
    },
}

Path(CFG["paths"]["logs"]).mkdir(parents=True, exist_ok=True)
Path(CFG["paths"]["db"]).parent.mkdir(parents=True, exist_ok=True)

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "").strip()

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ==============================================================================
# 2) LOGGER
# ==============================================================================
def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("gangjin")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    try:
        fh = RotatingFileHandler(f"{CFG['paths']['logs']}/app.log", maxBytes=5 * 1024 * 1024,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    return logger

LOG = _setup_logger()


# ==============================================================================
# 3) UTILS & CONSTANTS
# ==============================================================================
def render_html(s: str):
    st.markdown("\n".join(l.strip() for l in s.splitlines() if l.strip()), unsafe_allow_html=True)


def safe_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url or "")
        if p.scheme in ("http", "https"):
            return url
    except Exception:
        pass
    return "#"


def safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        if isinstance(val, str):
            val = re.sub(r"[^0-9.-]", "", val)
            if not val or val in ("-", ".", "-."):
                return default
        f = float(val)
        return default if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return default


def _ny_today_str() -> str:
    try:
        return pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def _ny_today_date():
    """미국 동부(뉴욕) 기준 오늘 날짜(date) 반환 — 한국 시간(+9h) 시차로 인한 D-Day 누락 방지."""
    try:
        return pd.Timestamp.now(tz="America/New_York").date()
    except Exception:
        return datetime.utcnow().date()


_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _extract_dates_from_any(val, ref_today=None) -> list:
    """
    다양한 포맷(date, datetime, Timestamp, Unix epoch, list, DataFrame/Series,
    '2026-05-07', '05/07/2026', 'May 7, 2026', 'May 7' 등)에서 datetime.date 리스트 추출.
    """
    if ref_today is None:
        ref_today = _ny_today_date()
    out = []
    if val is None:
        return out
    if isinstance(val, (list, tuple, set)):
        for item in val:
            out.extend(_extract_dates_from_any(item, ref_today))
        return out
    if isinstance(val, (pd.Series, pd.Index, np.ndarray)):
        for item in list(val):
            out.extend(_extract_dates_from_any(item, ref_today))
        return out
    if isinstance(val, pd.DataFrame):
        for col in val.columns:
            out.extend(_extract_dates_from_any(val[col], ref_today))
        for idx_v in val.index:
            out.extend(_extract_dates_from_any(idx_v, ref_today))
        return out
    if isinstance(val, dict):
        for v in val.values():
            out.extend(_extract_dates_from_any(v, ref_today))
        return out
    if isinstance(val, pd.Timestamp):
        if pd.isna(val):
            return out
        try:
            if val.tzinfo is not None:
                return [val.tz_convert("America/New_York").date()]
            return [val.date()]
        except Exception:
            return out
    if isinstance(val, datetime):
        return [val.date()]
    if hasattr(val, "year") and hasattr(val, "month") and hasattr(val, "day") and not isinstance(val, datetime):
        try:
            return [datetime(int(val.year), int(val.month), int(val.day)).date()]
        except Exception:
            return out
    if isinstance(val, (int, float, np.number)):
        fv = float(val)
        if 1e9 <= fv <= 3e9:
            try:
                return [pd.to_datetime(int(fv), unit="s", utc=True).tz_convert("America/New_York").date()]
            except Exception:
                return out
        if 1e12 <= fv <= 3e12:
            try:
                return [pd.to_datetime(int(fv // 1000), unit="s", utc=True).tz_convert("America/New_York").date()]
            except Exception:
                return out
        return out

    s = str(val).strip()
    if not s or s.lower() in ("n/a", "none", "null", "nan", "nat", "-", "tbd", "--"):
        return out

    # 1) YYYY-MM-DD or YYYY/MM/DD
    for m in re.finditer(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b", s):
        try:
            out.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date())
        except Exception:
            pass

    # 2) MM/DD/YYYY
    for m in re.finditer(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/(20\d{2})\b", s):
        try:
            out.append(datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).date())
        except Exception:
            pass

    # 3) Month DD, YYYY (예: May 7, 2026 / Nov. 06, 2025 / February 25 2026)
    for m in re.finditer(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b",
        s,
        flags=re.IGNORECASE,
    ):
        mon_str = m.group(1).lower().rstrip(".")
        mon = _MONTH_MAP.get(mon_str[:3], 0)
        day = int(m.group(2))
        yr_str = m.group(3)
        if mon > 0:
            try:
                if yr_str:
                    out.append(datetime(int(yr_str), mon, day).date())
                else:
                    cand_d = datetime(ref_today.year, mon, day).date()
                    if (cand_d - ref_today).days < -60:
                        cand_d = datetime(ref_today.year + 1, mon, day).date()
                    out.append(cand_d)
            except Exception:
                pass

    return out


def _detect_tod_label(text: str) -> str:
    """실적 발표 시간대(장전 BMO / 장후 AMC) 태그 감지."""
    tl = str(text or "").lower()
    if any(k in tl for k in ("bmo", "before market", "pre-market", "premarket", "before open", "time-pre-market")):
        return " · 장전(BMO)"
    if any(k in tl for k in ("amc", "after market", "after-hours", "after hours", "after close", "time-after-hours")):
        return " · 장후(AMC)"
    return "" 


def _ts_to_ny_date_str(ts_val) -> str:
    try:
        return pd.to_datetime(int(ts_val), unit="s", utc=True).tz_convert("America/New_York").strftime("%Y-%m-%d")
    except Exception:
        return ""


def compute_wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    d = close.diff()
    g = d.where(d > 0, 0.0).ewm(alpha=1.0 / period, adjust=False).mean()
    l = (-d.where(d < 0, 0.0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs = g / l.replace(0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def _hours_since(pub_dt) -> float:
    """뉴스 발행시각으로부터 경과 시간(시간). 파싱 실패 시 9999.0 반환하여 과거 기사로 패스 처리."""
    if pub_dt is None:
        return 9999.0
    try:
        if pub_dt.tzinfo is not None:
            now = datetime.now(pub_dt.tzinfo)
        else:
            now = datetime.now()
        return max(0.0, (now - pub_dt).total_seconds() / 3600.0)
    except Exception:
        return 9999.0


def _recency_weight(pub_dt) -> float:
    """
    ⭐ [16.4] 과거 호재·악재 무조건 선별 패스 가중치:
    - 날짜 미상(None) 또는 48시간 초과: 점수 가중치 0.0 (시그널 산정에서 무조건 패스!)
    - 12시간 이내 속보: 1.15
    - 24시간 이내 당일: 1.00
    - 48시간 이내 최근: 0.75
    """
    hours = _hours_since(pub_dt)
    rcfg = CFG["news"]["recency_hours"]
    if hours <= rcfg["breaking"]:
        return 1.15
    if hours <= rcfg["fresh"]:
        return 1.00
    if hours <= rcfg["recent"]:
        return 0.75
    return 0.0


def _normalize_title(t: str) -> str:
    """중복 기사 판별용 정규화 — 언론사 접미사 제거 후 소문자·숫자 앞 8단어."""
    raw = str(t or "")
    if " - " in raw:
        raw = raw.rsplit(" - ", 1)[0]
    raw = re.sub(r'[^a-z0-9가-힣 ]', ' ', raw.lower())
    return " ".join(raw.split()[:8])


def _kw_match(text_lower: str, kw: str) -> bool:
    """
    ⭐ [16.4] 정밀 경계 매칭:
    - 'miss'가 'mission'/'commission'에 매칭되거나,
    - 'cut'이 'execute'/'executive'에 매칭되거나,
    - 'war'가 'award'/'software'에 매칭되거나,
    - 's-3'가 'class-3'에 매칭되는 오탐을 원천 차단합니다.
    """
    k = kw.lower().strip()
    if not k:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", text_lower))


def _any_kw(text_lower: str, kw_tuple: tuple) -> bool:
    return any(_kw_match(text_lower, k) for k in kw_tuple)


def _parse_relative_or_date(ago_str: str, created_str: str):
    """Nasdaq News 등의 '3 hours ago', '25 mins ago', 'Oct 21, 2026' 문자열을 datetime으로 변환."""
    now = datetime.now()
    s_ago = str(ago_str or "").lower().strip()
    if s_ago:
        m = re.search(r"(\d+)\s*(sec|min|hour|hr|day|wk|week|month|yr|year)", s_ago)
        if m:
            val = int(m.group(1))
            unit = m.group(2)
            if unit.startswith("sec"):
                return now - timedelta(seconds=val)
            if unit.startswith("min"):
                return now - timedelta(minutes=val)
            if unit in ("hour", "hr"):
                return now - timedelta(hours=val)
            if unit == "day":
                return now - timedelta(days=val)
            if unit in ("wk", "week"):
                return now - timedelta(days=val * 7)
            return now - timedelta(days=365)
    s_cr = str(created_str or "").strip()
    if s_cr:
        try:
            return pd.to_datetime(s_cr).to_pydatetime()
        except Exception:
            pass
    return None


SIGNAL_HOLD_LONG   = "🟢 장기 홀딩"
SIGNAL_HOLD_SHORT  = "🟡 단기 대응"
SIGNAL_WATCH       = "🟠 경계 (준비)"
SIGNAL_EXIT        = "🔴 즉시 청산"
SIGNAL_TAKE_PROFIT = "🔵 목표 익절"
SIGNAL_STOP_HIT    = "⚫ 손절선 이탈"

SIGNAL_SEVERITY = {
    SIGNAL_STOP_HIT: 5, SIGNAL_EXIT: 4, SIGNAL_TAKE_PROFIT: 3,
    SIGNAL_WATCH: 2, SIGNAL_HOLD_SHORT: 1, SIGNAL_HOLD_LONG: 0,
}
SIGNAL_BADGE = {
    SIGNAL_STOP_HIT: "badge-red", SIGNAL_EXIT: "badge-red",
    SIGNAL_TAKE_PROFIT: "badge-blue", SIGNAL_WATCH: "badge-yellow",
    SIGNAL_HOLD_SHORT: "badge-indigo", SIGNAL_HOLD_LONG: "badge-green",
}


# ==============================================================================
# 4) PAGE CONFIG & CSS
# ==============================================================================
st.set_page_config(
    page_title="GANGJIN AI TRADER PRO",
    layout="centered",
    page_icon="⚡",
    initial_sidebar_state="collapsed",
)

render_html("""
<meta name="google" content="notranslate">
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Pretendard:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Pretendard', -apple-system, sans-serif; }
.mono { font-family: 'JetBrains Mono', monospace; }
#MainMenu, footer, header {visibility: hidden;}
.block-container { padding-top: 0.8rem; padding-bottom: 2rem; max-width: 800px; }
.stApp { background-color: #080c14; color: #e6edf3; }
div[data-baseweb="input"], div[data-baseweb="textarea"] { background-color: #0f1523 !important; border: 1px solid #1e293b !important; border-radius: 10px !important; color: #ffffff !important; }
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { color: #ffffff !important; font-size: 14px !important; font-weight: 700 !important; }
div[data-baseweb="select"] > div { background-color: #0f1523 !important; border-color: #1e293b !important; color: #ffffff !important; border-radius: 10px !important; }
.glass-card { background: linear-gradient(135deg, rgba(17,24,39,.85), rgba(15,23,42,.65)); border: 1px solid rgba(51,65,85,.5); backdrop-filter: blur(12px); padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(0,0,0,.4); }
.main-hero-card { background: linear-gradient(135deg,#0d1e16,#0a131a 50%,#0c1524); border: 1px solid #1e3a2f; padding: 18px 22px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 8px 32px rgba(16,185,129,.08); }
.verdict-card { background: linear-gradient(135deg,#13221c,#0d1526 55%,#1f1429); border: 2px solid #10b981; padding: 20px 22px; border-radius: 16px; margin-bottom: 16px; box-shadow: 0 8px 35px rgba(16,185,129,.18); }
.master-card { background: linear-gradient(135deg,#2a1b0a,#1a1108); border: 1px solid #f59e0b; padding: 18px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(245,158,11,.25); }
.trailing-card { background: linear-gradient(135deg,#0c192c,#091220); border: 1px solid #38bdf8; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(56,189,248,.15); }
.sentiment-card { background: linear-gradient(135deg,#1e1b4b,#172554); border: 1px solid #6366f1; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(99,102,241,.2); }
.noise-card { background: linear-gradient(135deg,#0f172a,#111827 60%,#0d1f22); border: 1px solid #14b8a6; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(20,184,166,.15); }
.rebal-card { background: linear-gradient(135deg,#1a0f2e,#0f1524 50%,#1a0f2e); border: 1px solid #a855f7; padding: 14px 18px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(168,85,247,.2); }
.journal-card { background: linear-gradient(135deg,#0f2416,#0a131a 50%,#0f2416); border: 1px solid #10b981; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(16,185,129,.15); }
.squeeze-card { background: linear-gradient(135deg,#1a1108,#0d1526 50%,#1a1108); border: 2px solid #f97316; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 25px rgba(249,115,22,.25); }
.signal-card { background: linear-gradient(135deg,#0f172a,#1a1f35 50%,#0f172a); border: 1px solid #6366f1; padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(99,102,241,.2); }
.chief-card { background: linear-gradient(135deg,#0b1528,#141e33 55%,#1a1230); border: 2px solid #38bdf8; padding: 18px 20px; border-radius: 16px; margin-bottom: 16px; box-shadow: 0 8px 30px rgba(56,189,248,.18); }
.index-wrapper { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.index-card { flex: 1 1 100px; background-color: #0d131f; border: 1px solid #1e293b; padding: 10px 8px; border-radius: 10px; text-align: center; }
.index-name { color: #94a3b8; font-size: 10px; font-weight: 600; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.index-price { font-size: 13px; font-weight: 800; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px; }
.index-change { font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
.text-white { color: #fff !important; }
.text-green { color: #10b981 !important; } .text-red { color: #f43f5e !important; }
.text-yellow { color: #f59e0b !important; } .text-blue { color: #3b82f6 !important; }
.text-purple { color: #a855f7 !important; } .text-indigo { color: #818cf8 !important; }
.text-orange { color: #fb923c !important; } .text-teal { color: #2dd4bf !important; }
.badge { padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 4px; letter-spacing: 0.3px; }
.badge-green { background: rgba(16,185,129,.15); color: #34d399; border: 1px solid #10b981; }
.badge-red { background: rgba(244,63,94,.15); color: #fb7185; border: 1px solid #f43f5e; }
.badge-yellow { background: rgba(245,158,11,.15); color: #fbbf24; border: 1px solid #f59e0b; }
.badge-blue { background: rgba(59,130,246,.15); color: #60a5fa; border: 1px solid #3b82f6; }
.badge-purple { background: rgba(168,85,247,.15); color: #c084fc; border: 1px solid #a855f7; }
.badge-indigo { background: rgba(99,102,241,.15); color: #a5b4fc; border: 1px solid #6366f1; }
.badge-teal { background: rgba(20,184,166,.15); color: #5eead4; border: 1px solid #14b8a6; }
.badge-orange { background: rgba(249,115,22,.15); color: #fb923c; border: 1px solid #f97316; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; background-color: #0b111e; padding: 6px; border-radius: 12px; border: 1px solid #1e293b; }
.stTabs [data-baseweb="tab"] { border-radius: 8px; color: #94a3b8; font-weight: 700; padding: 8px 12px; font-size: 12px; }
.stTabs [aria-selected="true"] { background-color: #1e293b !important; color: #fff !important; }
hr { border: none; border-top: 1px solid #1e293b; margin: 14px 0; }
@media (max-width: 768px) {
    .block-container { padding-left: 0.3rem !important; padding-right: 0.3rem !important; max-width: 100% !important; }
    div[style*="grid-template-columns:repeat(4,1fr)"],
    div[style*="grid-template-columns: repeat(4, 1fr)"] { grid-template-columns: repeat(2, 1fr) !important; gap: 6px !important; }
    div[style*="grid-template-columns:repeat(3,1fr)"],
    div[style*="grid-template-columns: repeat(3, 1fr)"] { grid-template-columns: 1fr !important; }
    .index-card { flex: 1 1 45% !important; }
    .stTabs [data-baseweb="tab-list"] { flex-wrap: nowrap !important; overflow-x: auto !important; }
    .stTabs [data-baseweb="tab"] { padding: 6px 8px !important; font-size: 10px !important; white-space: nowrap; }
    .main-hero-card, .verdict-card, .master-card, .trailing-card, .sentiment-card, .noise-card, .rebal-card, .journal-card, .squeeze-card, .signal-card { padding: 12px 14px !important; }
    .main-hero-card > div:nth-child(2) { font-size: 24px !important; }
}
</style>
""")


# ==============================================================================
# 5) LIVE CLOCK HEADER
# ==============================================================================
def render_live_ny_header(btc_price, btc_change, usd_krw):
    btc_color = "#10b981" if btc_change >= 0 else "#f43f5e"
    btc_sign = "▲" if btc_change >= 0 else "▼"
    btc_text = f"{btc_sign} ${btc_price:,.0f}" if btc_price > 0 else "N/A"
    krw_text = f"{usd_krw:,.1f}원" if usd_krw > 0 else "N/A"
    live_clock_html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{margin:0;padding:0;background:transparent;font-family:-apple-system,sans-serif;}}
.header-box{{background:linear-gradient(90deg,#0a0f1d,#111a2e);border:1px solid #1e293b;border-radius:12px;padding:10px 16px;display:flex;justify-content:space-between;align-items:center;gap:10px;box-shadow:0 4px 15px rgba(0,0,0,.3);flex-wrap:wrap;}}
.left-section{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}
.clock-title{{font-weight:800;font-size:13px;color:#f8fafc;display:flex;align-items:center;gap:6px;}}
.pulse-dot{{width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 10px #10b981;}}
.clock-display{{font-family:monospace;font-size:15px;font-weight:800;color:#38bdf8;background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.3);padding:3px 10px;border-radius:6px;}}
.status-badge{{font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;}}
.countdown-text{{font-size:12px;color:#94a3b8;font-weight:600;}}
.right-section{{display:flex;align-items:center;gap:14px;font-family:monospace;font-size:13px;flex-wrap:wrap;}}
</style></head><body>
<div class="header-box">
<div class="left-section">
<div class="clock-title"><span class="pulse-dot" id="pulse-dot"></span><span>NEW YORK (ET)</span></div>
<div class="clock-display" id="ny-live-clock">--:--:-- ET</div>
<div class="status-badge" id="market-status-badge">...</div>
<div class="countdown-text" id="market-countdown">--</div>
</div>
<div class="right-section">
<div><span style="color:#94a3b8;">BTC:</span> <span style="color:{btc_color};font-weight:800;">{btc_text}</span></div>
<div style="border-left:1px solid #334155;padding-left:12px;"><span style="color:#94a3b8;">USD/KRW:</span> <span style="color:#38bdf8;font-weight:800;">{krw_text}</span></div>
</div>
</div>
<script>
function updateNYClock(){{
  try{{
    const now=new Date();
    const tf=new Intl.DateTimeFormat('en-US',{{timeZone:'America/New_York',hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}});
    const tp={{}};tf.formatToParts(now).forEach(p=>tp[p.type]=p.value);
    const h=parseInt(tp.hour,10)%24,m=parseInt(tp.minute,10),tm=h*60+m;
    const wf=new Intl.DateTimeFormat('en-US',{{timeZone:'America/New_York',weekday:'short'}});
    const wd=(wf.formatToParts(now).find(p=>p.type==='weekday')||{{}}).value||'';
    const isWk=(wd==='Sat'||wd==='Sun');
    document.getElementById('ny-live-clock').textContent=`${{String(h).padStart(2,'0')}}:${{tp.minute}}:${{tp.second}} ET`;
    const b=document.getElementById('market-status-badge'),c=document.getElementById('market-countdown'),d=document.getElementById('pulse-dot');
    if(isWk){{b.textContent="WEEKEND CLOSED";b.style.cssText="background:rgba(100,116,139,.2);color:#94a3b8;border:1px solid #475569;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent="월요일 04:00 프리마켓 오픈 대기";d.style.cssText="width:10px;height:10px;border-radius:50%;background:#64748b;";return;}}
    if(tm>=240&&tm<570){{const r=570-tm;b.textContent="⚡ PRE-MARKET";b.style.cssText="background:rgba(245,158,11,.15);color:#fbbf24;border:1px solid #f59e0b;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent=`정규장 개장까지 ${{Math.floor(r/60)}}시간 ${{r%60}}분 전`;d.style.cssText="width:10px;height:10px;border-radius:50%;background:#f59e0b;box-shadow:0 0 10px #f59e0b;";}}
    else if(tm>=570&&tm<960){{const r=960-tm;b.textContent="🟢 REGULAR MARKET (LIVE)";b.style.cssText="background:rgba(16,185,129,.2);color:#34d399;border:1px solid #10b981;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent=`정규장 마감까지 ${{Math.floor(r/60)}}시간 ${{r%60}}분 남음`;d.style.cssText="width:10px;height:10px;border-radius:50%;background:#10b981;box-shadow:0 0 12px #10b981;";}}
    else if(tm>=960&&tm<1200){{const r=1200-tm;b.textContent="🌙 AFTER-HOURS";b.style.cssText="background:rgba(168,85,247,.15);color:#c084fc;border:1px solid #a855f7;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent=`애프터마켓 종료까지 ${{Math.floor(r/60)}}시간 ${{r%60}}분`;d.style.cssText="width:10px;height:10px;border-radius:50%;background:#a855f7;box-shadow:0 0 10px #a855f7;";}}
    else{{b.textContent="🔒 MARKET CLOSED";b.style.cssText="background:rgba(244,63,94,.15);color:#fb7185;border:1px solid #f43f5e;font-size:11px;font-weight:800;padding:4px 10px;border-radius:12px;";c.textContent="프리마켓(04:00 ET) 오픈 대기 중";d.style.cssText="width:10px;height:10px;border-radius:50%;background:#f43f5e;";}}
  }}catch(e){{console.error(e);}}
}}
setInterval(updateNYClock,1000);updateNYClock();
</script></body></html>"""
    st.components.v1.html(live_clock_html, height=80)


# ==============================================================================
# 6) REAL-TIME QUOTE & MULTI-SOURCE DATA ENGINE (전일 종가 지연 방지 + 5중 폴백)
# ==============================================================================
def _detect_ext_session_label(ts_str: str = "") -> str:
    """타임스탬프 문자열 및 현재 뉴욕(ET) 시간대를 기반으로 프리마켓/애프터마켓 라벨을 자동 판정."""
    s = str(ts_str or "").upper().strip()
    if any(k in s for k in ("PRE-MARKET", "PREMARKET", "PRE MARKET", "BEFORE")):
        return "프리마켓"
    if any(k in s for k in ("AFTER-HOURS", "AFTER HOURS", "AFTERHOURS", "POST-MARKET", "POSTMARKET", "AFTER")):
        return "애프터마켓"
    m_tm = re.search(r"\b(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)\b", s)
    if m_tm:
        hh = int(m_tm.group(1)) % 12
        mm = int(m_tm.group(2))
        if m_tm.group(3) == "PM":
            hh += 12
        hm = hh * 60 + mm
        if 240 <= hm < 570:
            return "프리마켓"
        if hm >= 960 or hm < 240:
            return "애프터마켓"
    try:
        ny_now = pd.Timestamp.now(tz="America/New_York")
        hm_now = ny_now.hour * 60 + ny_now.minute
        if 240 <= hm_now < 570:
            return "프리마켓"
    except Exception:
        pass
    return "애프터마켓"


def _period_to_days(period: str) -> int:
    p = (period or "1y").lower().strip()
    if p == "2d": return 5
    if p == "5d": return 10
    if p == "1mo": return 35
    if p == "3mo": return 100
    if p == "6mo": return 190
    if p == "1y": return 370
    if p == "2y": return 740
    if p == "3y": return 1100
    if p == "5y": return 1850
    return 370


def _parse_nasdaq_date(ts_str: str) -> str:
    """'Oct 21, 2026 4:00 PM ET' 또는 '2026-10-21 16:00:00' 등에서 YYYY-MM-DD 추출."""
    if not ts_str:
        return ""
    s = str(ts_str).strip()
    m_iso = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m_iso:
        return m_iso.group(1)
    m_us = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", s)
    if m_us:
        try:
            return pd.to_datetime(m_us.group(1)).strftime("%Y-%m-%d")
        except Exception:
            pass
    m_slash = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", s)
    if m_slash:
        try:
            return pd.to_datetime(m_slash.group(1)).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""


def _clean_company_search_name(raw_name: str, ticker: str) -> str:
    """'AEVEX Corp. Common Stock' -> 'AEVEX' 추출 (뉴스 검색 정밀도 향상용)."""
    if not raw_name:
        return ""
    s = re.sub(
        r"\b(common stock|ordinary shares|american depositary shares|ads|adr|class [a-c]|inc\.?|corp\.?|corporation|ltd\.?|limited|plc|holdings?|group|technologies|technology|company|co\.?)\b",
        " ",
        str(raw_name),
        flags=re.IGNORECASE,
    )
    s = re.sub(r"[^A-Za-z0-9 ]", " ", s).strip()
    words = [w for w in s.split() if len(w) >= 3]
    if not words:
        return ""
    cand = " ".join(words[:2]).strip()
    return "" if cand.upper() == ticker.upper() else cand


def _quote_from_yahoo_v8(ticker: str) -> dict:
    """Yahoo v8 1d/5m + 5d/1d meta.regularMarketPrice 기반 실시간 시세 및 프리/애프터마켓 추출."""
    enc = urllib.parse.quote(ticker.strip().upper())
    cb = int(time.time() // 15)
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            url = f"https://{host}/v8/finance/chart/{enc}?range=1d&interval=5m&includePrePost=true&_={cb}"
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=5)
            if r.status_code != 200:
                continue
            res = ((r.json().get("chart") or {}).get("result") or [None])[0]
            if not res:
                continue
            meta = res.get("meta") or {}
            reg_px = safe_float(meta.get("regularMarketPrice"), 0.0)
            if reg_px <= 0:
                continue
            prev_cl = safe_float(meta.get("previousClose") or meta.get("chartPreviousClose"), 0.0)
            reg_ts = meta.get("regularMarketTime")
            trade_date = _ts_to_ny_date_str(reg_ts) if reg_ts else _ny_today_str()
            day_h = safe_float(meta.get("regularMarketDayHigh"), reg_px)
            day_l = safe_float(meta.get("regularMarketDayLow"), reg_px)
            day_o = safe_float(meta.get("regularMarketOpen"), 0.0)
            day_v = safe_float(meta.get("regularMarketVolume"), 0.0)
            comp_name = _clean_company_search_name(
                meta.get("shortName") or meta.get("longName") or "", ticker
            )

            ts_list = res.get("timestamp") or []
            q = ((res.get("indicators") or {}).get("quote") or [None])[0] or {}
            closes = q.get("close") or []
            opens = q.get("open") or []
            highs = q.get("high") or []
            lows = q.get("low") or []
            vols = q.get("volume") or []

            ext_price, ext_chg, ext_chg_pct, ext_label = 0.0, 0.0, 0.0, ""
            if ts_list and closes:
                idx_ny = pd.to_datetime(ts_list, unit="s", utc=True).tz_convert("America/New_York")
                df_1m = pd.DataFrame({
                    "Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": vols
                }, index=idx_ny).dropna(subset=["Close"])
                if not df_1m.empty:
                    latest_day = df_1m.index[-1].date()
                    day_df = df_1m[df_1m.index.date == latest_day]
                    reg_df = day_df.between_time("09:30", "16:00")
                    if not reg_df.empty:
                        if day_o <= 0:
                            day_o = safe_float(reg_df["Open"].iloc[0], reg_px)
                        day_h = max(day_h, safe_float(reg_df["High"].max(), reg_px))
                        day_l = min(day_l if day_l > 0 else reg_px, safe_float(reg_df["Low"].min(), reg_px))
                        if day_v <= 0:
                            day_v = safe_float(reg_df["Volume"].sum(), 0.0)
                    last_bar_ts = day_df.index[-1]
                    last_bar_px = safe_float(day_df["Close"].iloc[-1], 0.0)
                    last_bar_date = last_bar_ts.strftime("%Y-%m-%d")
                    hm = last_bar_ts.hour * 60 + last_bar_ts.minute
                    if (
                        last_bar_px > 0
                        and reg_px > 0
                        and last_bar_date == trade_date
                        and not any(c in ticker for c in ("^", "=", "-"))
                    ):
                        cand_chg = last_bar_px - reg_px
                        cand_pct = (cand_chg / reg_px) * 100.0
                        # ⭐ 장외 유령 가격 필터링 (정규장 종가 대비 ±15% 이내 정상 틱만 인정)
                        if abs(cand_chg) > 1e-4 and abs(cand_pct) <= 15.0:
                            if hm >= 960:
                                ext_price = last_bar_px
                                ext_chg = cand_chg
                                ext_chg_pct = cand_pct
                                ext_label = "애프터마켓"
                            elif 240 <= hm < 570:
                                ext_price = last_bar_px
                                ext_chg = cand_chg
                                ext_chg_pct = cand_pct
                                ext_label = "프리마켓"

            if prev_cl <= 0 or abs(prev_cl - reg_px) < 1e-6:
                try:
                    u5 = f"https://{host}/v8/finance/chart/{enc}?range=5d&interval=1d&_={cb}"
                    r5 = requests.get(u5, headers=BROWSER_HEADERS, timeout=4)
                    if r5.status_code == 200:
                        res5 = ((r5.json().get("chart") or {}).get("result") or [None])[0] or {}
                        ts5 = res5.get("timestamp") or []
                        cl5 = (((res5.get("indicators") or {}).get("quote") or [None])[0] or {}).get("close") or []
                        valid_pairs = [
                            (_ts_to_ny_date_str(t_), safe_float(c_, 0.0))
                            for t_, c_ in zip(ts5, cl5) if safe_float(c_, 0.0) > 0
                        ]
                        prior = [c_ for d_, c_ in valid_pairs if d_ and d_ < trade_date]
                        if prior:
                            prev_cl = prior[-1]
                except Exception:
                    pass

            if prev_cl <= 0:
                prev_cl = reg_px
            chg = reg_px - prev_cl
            chg_pct = (chg / prev_cl) * 100.0 if prev_cl > 0 else 0.0
            return {
                "price": reg_px, "prev_close": prev_cl, "change": chg, "change_pct": chg_pct,
                "open": day_o if day_o > 0 else prev_cl,
                "high": max(day_h, reg_px), "low": min(day_l if day_l > 0 else reg_px, reg_px),
                "volume": day_v, "trade_date": trade_date,
                "ext_price": ext_price, "ext_change": ext_chg,
                "ext_change_pct": ext_chg_pct, "ext_label": ext_label,
                "company_name": comp_name,
                "source": "Yahoo Real-Time",
            }
        except Exception as e:
            LOG.warning("Yahoo live quote failed (%s) for %s: %s", host, ticker, e)
    return {}


def _quote_from_nasdaq(ticker: str) -> dict:
    """Nasdaq 실시간 Quote API (/api/quote/{symbol}/info + charting latestIntradayData)."""
    t = ticker.strip().upper()
    if any(c in t for c in ("^", "=", "-")):
        return {}
    headers = {
        **BROWSER_HEADERS,
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    for asset in ("stocks", "etf"):
        try:
            url = f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(t)}/info?assetclass={asset}"
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code != 200:
                continue
            data = (r.json() or {}).get("data") or {}
            prim = data.get("primaryData") or {}
            sec = data.get("secondaryData") or {}
            ks = data.get("keyStats") or {}
            px = safe_float(prim.get("lastSalePrice"), 0.0)
            if px <= 0:
                continue
            comp_name = _clean_company_search_name(data.get("companyName") or "", t)
            net_chg = safe_float(prim.get("netChange"), 0.0)
            delta_ind = str(prim.get("deltaIndicator") or "").lower()
            if delta_ind == "down" and net_chg > 0:
                net_chg = -net_chg
            elif delta_ind == "up" and net_chg < 0:
                net_chg = abs(net_chg)
            prev_cl = px - net_chg if (px - net_chg) > 0 else px
            chg_pct = safe_float(prim.get("percentageChange"), 0.0)
            if chg_pct == 0.0 and prev_cl > 0 and net_chg != 0.0:
                chg_pct = (net_chg / prev_cl) * 100.0
            elif net_chg < 0 and chg_pct > 0:
                chg_pct = -chg_pct

            vol = safe_float(prim.get("volume"), 0.0)
            trade_date = _parse_nasdaq_date(prim.get("lastTradeTimestamp") or "")
            if not trade_date:
                trade_date = _ny_today_str()

            day_h, day_l = px, px
            dr_str = str(((ks.get("dayrange") or {}).get("value")) or "")
            nums = [safe_float(x, 0.0) for x in re.findall(r"\d+(?:\.\d+)?", dr_str) if safe_float(x, 0.0) > 0]
            if len(nums) >= 2:
                day_l, day_h = min(nums), max(nums)

            ext_price, ext_chg, ext_chg_pct, ext_label = 0.0, 0.0, 0.0, ""
            if isinstance(sec, dict) and sec.get("lastSalePrice"):
                ep = safe_float(sec.get("lastSalePrice"), 0.0)
                sec_ts = str(sec.get("lastTradeTimestamp") or "")
                sec_date = _parse_nasdaq_date(sec_ts)
                # ⭐ 당일 장외 데이터인지 확인 + 정규장 종가(px) 기준 netChange 직접 재계산 + ±15% 컷오프
                if ep > 0 and px > 0 and abs(ep - px) > 1e-4 and (not sec_date or sec_date == trade_date):
                    ec = ep - px
                    ec_pct = (ec / px) * 100.0
                    if abs(ec_pct) <= 15.0:
                        ext_price = ep
                        ext_chg = ec
                        ext_chg_pct = ec_pct
                        ext_label = _detect_ext_session_label(sec_ts)

            return {
                "price": px, "prev_close": prev_cl, "change": net_chg, "change_pct": chg_pct,
                "open": prev_cl, "high": max(day_h, px), "low": min(day_l, px),
                "volume": vol, "trade_date": trade_date,
                "ext_price": ext_price, "ext_change": ext_chg,
                "ext_change_pct": ext_chg_pct, "ext_label": ext_label,
                "company_name": comp_name,
                "source": "Nasdaq Real-Time",
            }
        except Exception as e:
            LOG.warning("Nasdaq live quote failed (%s) for %s: %s", asset, t, e)
    return {}


def _quote_from_finnhub(ticker: str) -> dict:
    """Finnhub 실시간 Quote (/api/v1/quote)."""
    t = ticker.strip().upper()
    if not FINNHUB_KEY or any(c in t for c in ("^", "=", "-")):
        return {}
    try:
        r = requests.get(
            f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote(t)}&token={FINNHUB_KEY}",
            headers=BROWSER_HEADERS, timeout=4
        )
        if r.status_code == 200:
            j = r.json() or {}
            px = safe_float(j.get("c"), 0.0)
            if px > 0:
                prev_cl = safe_float(j.get("pc"), px)
                chg = safe_float(j.get("d"), px - prev_cl)
                chg_pct = safe_float(j.get("dp"), ((chg / prev_cl) * 100.0) if prev_cl > 0 else 0.0)
                ts_val = j.get("t")
                trade_date = _ts_to_ny_date_str(ts_val) if ts_val else _ny_today_str()
                return {
                    "price": px, "prev_close": prev_cl, "change": chg, "change_pct": chg_pct,
                    "open": safe_float(j.get("o"), prev_cl),
                    "high": max(safe_float(j.get("h"), px), px),
                    "low": min(safe_float(j.get("l"), px) or px, px),
                    "volume": 0.0, "trade_date": trade_date,
                    "ext_price": 0.0, "ext_change": 0.0, "ext_change_pct": 0.0, "ext_label": "",
                    "company_name": "",
                    "source": "Finnhub Real-Time",
                }
    except Exception as e:
        LOG.warning("Finnhub quote failed for %s: %s", t, e)
    return {}


def _quote_from_cnbc(ticker: str) -> dict:
    """CNBC 실시간 Quote JSON 웹서비스 (선물/지수/주식 폴백)."""
    cnbc_map = {
        "^TNX": "US10Y", "ES=F": "@SP.1", "NQ=F": "@ND.1",
        "YM=F": "@DJ.1", "CL=F": "@CL.1", "^VIX": ".VIX", "GC=F": "@GC.1",
        "BTC-USD": "BTC.CM=", "KRW=X": "KRW=",
    }
    t = ticker.strip().upper()
    sym = cnbc_map.get(t, t)
    try:
        url = (
            "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
            f"?symbols={urllib.parse.quote(sym)}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1"
        )
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=5)
        if r.status_code == 200:
            qq = (((r.json() or {}).get("FormattedQuoteResult") or {}).get("FormattedQuote") or [None])[0] or {}
            px = safe_float(qq.get("last"), 0.0)
            if px > 0:
                if t == "^TNX" and px > 20:
                    px = px / 10.0
                chg = safe_float(qq.get("change"), 0.0)
                prev_cl = safe_float(qq.get("previous_day_closing"), px - chg)
                if prev_cl <= 0:
                    prev_cl = px - chg if (px - chg) > 0 else px
                chg_pct = safe_float(qq.get("change_pct"), ((chg / prev_cl) * 100.0) if prev_cl > 0 else 0.0)
                trade_date = _parse_nasdaq_date(qq.get("last_time") or "") or _ny_today_str()
                return {
                    "price": px, "prev_close": prev_cl, "change": chg, "change_pct": chg_pct,
                    "open": safe_float(qq.get("open"), prev_cl),
                    "high": max(safe_float(qq.get("high"), px), px),
                    "low": min(safe_float(qq.get("low"), px) or px, px),
                    "volume": safe_float(qq.get("volume"), 0.0),
                    "trade_date": trade_date,
                    "ext_price": 0.0, "ext_change": 0.0, "ext_change_pct": 0.0, "ext_label": "",
                    "company_name": _clean_company_search_name(qq.get("name") or "", t),
                    "source": "CNBC Real-Time",
                }
    except Exception as e:
        LOG.warning("CNBC quote failed for %s: %s", t, e)
    return {}


@st.cache_data(ttl=CFG["cache"]["live_quote"])
def get_realtime_quote(ticker: str) -> dict:
    """다중 실시간 소스(Nasdaq, Yahoo 1d/5m, Finnhub, CNBC)를 조회해 가장 최신 거래일(trade_date) 시세를 반환."""
    t = ticker.strip().upper()
    if not t:
        return {}
    candidates = []
    if not any(c in t for c in ("^", "=", "-")):
        q_nq = _quote_from_nasdaq(t)
        if q_nq.get("price", 0.0) > 0:
            candidates.append(q_nq)
        q_yh = _quote_from_yahoo_v8(t)
        if q_yh.get("price", 0.0) > 0:
            candidates.append(q_yh)
        if FINNHUB_KEY:
            q_fh = _quote_from_finnhub(t)
            if q_fh.get("price", 0.0) > 0:
                candidates.append(q_fh)
        if not candidates:
            q_cb = _quote_from_cnbc(t)
            if q_cb.get("price", 0.0) > 0:
                candidates.append(q_cb)
    else:
        q_yh = _quote_from_yahoo_v8(t)
        if q_yh.get("price", 0.0) > 0:
            candidates.append(q_yh)
        q_cb = _quote_from_cnbc(t)
        if q_cb.get("price", 0.0) > 0:
            candidates.append(q_cb)

    if not candidates:
        return {}

    candidates.sort(
        key=lambda c: (
            str(c.get("trade_date") or ""),
            1 if c.get("ext_price", 0.0) > 0 else 0,
            1 if c.get("volume", 0.0) > 0 else 0,
        ),
        reverse=True,
    )
    best = dict(candidates[0])
    for c in candidates[1:]:
        if not best.get("company_name") and c.get("company_name"):
            best["company_name"] = c["company_name"]
        if c.get("trade_date") == best.get("trade_date"):
            if best.get("volume", 0.0) <= 0 and c.get("volume", 0.0) > 0:
                best["volume"] = c["volume"]
            if best.get("ext_price", 0.0) <= 0 and c.get("ext_price", 0.0) > 0:
                best["ext_price"] = c["ext_price"]
                best["ext_change"] = c["ext_change"]
                best["ext_change_pct"] = c["ext_change_pct"]
                best["ext_label"] = c["ext_label"]
    return best


# ⭐ [16.5-R1] 실시간 봉 병합 로직 안전화:
# - rt_dt > last_idx (실시간이 새로운 거래일) → 새 봉 추가 및 직전봉 종가(prev_cl) 정합성 보정
# - rt_dt == last_idx (같은 거래일) → 마지막 봉만 갱신 (전일봉 절대 건드리지 않음)
# - rt_dt < last_idx → 아무 동작도 하지 않음 (역방향 구형 데이터 유입 방지)
def _stitch_realtime_quote(df: pd.DataFrame, rt: dict) -> pd.DataFrame:
    """일봉 히스토리(df)가 전일 종가에서 멈춰 있을 때 실시간 당일 봉을 안전하게 추가·갱신."""
    if df is None or df.empty or not rt or safe_float(rt.get("price"), 0.0) <= 0:
        return df
    df = df.copy()
    for _c in ("Open", "High", "Low", "Close", "Volume"):
        if _c in df.columns:
            df[_c] = pd.to_numeric(df[_c], errors="coerce").astype("float64")
    px = safe_float(rt.get("price"), 0.0)
    prev_cl = safe_float(rt.get("prev_close"), 0.0)
    rt_open = safe_float(rt.get("open"), px)
    rt_high = max(safe_float(rt.get("high"), px), px, rt_open)
    rt_low_raw = safe_float(rt.get("low"), px)
    rt_low = min(rt_low_raw if rt_low_raw > 0 else px, px, rt_open)
    rt_vol = safe_float(rt.get("volume"), 0.0)

    last_idx = pd.Timestamp(df.index[-1]).normalize()
    rt_dt = last_idx
    if rt.get("trade_date"):
        try:
            rt_dt = pd.to_datetime(rt["trade_date"]).normalize()
        except Exception:
            rt_dt = last_idx

    if rt_dt > last_idx:
        vol_est = rt_vol if rt_vol > 0 else safe_float(df["Volume"].tail(5).mean(), 0.0)
        new_row = pd.DataFrame(
            [{"Open": rt_open, "High": rt_high, "Low": rt_low, "Close": px, "Volume": vol_est}],
            index=[rt_dt],
        )
        df = pd.concat([df, new_row])
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if prev_cl > 0 and len(df) >= 2:
            df.iloc[-2, df.columns.get_loc("Close")] = prev_cl
    elif rt_dt == last_idx:
        df.iloc[-1, df.columns.get_loc("Close")] = px
        df.iloc[-1, df.columns.get_loc("High")] = max(safe_float(df["High"].iloc[-1], px), rt_high)
        cur_low = safe_float(df["Low"].iloc[-1], px)
        df.iloc[-1, df.columns.get_loc("Low")] = min(cur_low if cur_low > 0 else px, rt_low)
        if rt_vol > safe_float(df["Volume"].iloc[-1], 0.0):
            df.iloc[-1, df.columns.get_loc("Volume")] = rt_vol

    return df


def _fetch_yahoo_v8_direct(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Yahoo v8 Chart JSON 직접 호출 (뉴욕 타임존 정규화 + meta.regularMarketPrice 당일 봉 누락 방지)."""
    enc = urllib.parse.quote(ticker.strip().upper())
    cb = int(time.time() // 30)
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            url = f"https://{host}/v8/finance/chart/{enc}?range={period}&interval=1d&includePrePost=false&_={cb}"
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=6)
            if r.status_code != 200:
                continue
            j = r.json()
            res = (j.get("chart", {}).get("result") or [None])[0]
            if not res:
                continue
            meta = res.get("meta") or {}
            ts_list = res.get("timestamp") or []
            q = ((res.get("indicators", {}).get("quote") or [None])[0]) or {}
            if not ts_list or not q.get("close"):
                continue

            idx_ny = (
                pd.to_datetime(ts_list, unit="s", utc=True)
                .tz_convert("America/New_York")
                .tz_localize(None)
                .normalize()
            )
            df = pd.DataFrame({
                "Open": q.get("open"),
                "High": q.get("high"),
                "Low": q.get("low"),
                "Close": q.get("close"),
                "Volume": q.get("volume"),
            }, index=idx_ny, dtype="float64")

            reg_px = safe_float(meta.get("regularMarketPrice"), 0.0)
            reg_ts = meta.get("regularMarketTime")
            if reg_px > 0 and len(df) >= 1 and pd.isna(df["Close"].iloc[-1]):
                df.iloc[-1, df.columns.get_loc("Close")] = reg_px
                df.iloc[-1, df.columns.get_loc("Open")] = safe_float(meta.get("regularMarketOpen"), reg_px)
                df.iloc[-1, df.columns.get_loc("High")] = safe_float(meta.get("regularMarketDayHigh"), reg_px)
                df.iloc[-1, df.columns.get_loc("Low")] = safe_float(meta.get("regularMarketDayLow"), reg_px)
                df.iloc[-1, df.columns.get_loc("Volume")] = safe_float(meta.get("regularMarketVolume"), 0.0)

            df = df.dropna(subset=["Close"]).copy()
            df = df[~df.index.duplicated(keep="last")].sort_index()
            for col in ("Open", "High", "Low"):
                df[col] = df[col].fillna(df["Close"])
            df["Volume"] = df["Volume"].fillna(0.0)

            if reg_px > 0 and reg_ts and not df.empty:
                reg_dt = (
                    pd.to_datetime(int(reg_ts), unit="s", utc=True)
                    .tz_convert("America/New_York")
                    .tz_localize(None)
                    .normalize()
                )
                if reg_dt > df.index[-1]:
                    new_row = pd.DataFrame([{
                        "Open": safe_float(meta.get("regularMarketOpen"), float(df["Close"].iloc[-1])),
                        "High": max(safe_float(meta.get("regularMarketDayHigh"), reg_px), reg_px),
                        "Low": min(safe_float(meta.get("regularMarketDayLow"), reg_px) or reg_px, reg_px),
                        "Close": reg_px,
                        "Volume": safe_float(meta.get("regularMarketVolume"), float(df["Volume"].tail(5).mean())),
                    }], index=[reg_dt])
                    df = pd.concat([df, new_row])
                elif reg_dt == df.index[-1]:
                    df.iloc[-1, df.columns.get_loc("Close")] = reg_px

            if len(df) >= 2:
                return df
        except Exception as e:
            LOG.warning("Yahoo v8 direct failed (%s) for %s: %s", host, ticker, e)
    return pd.DataFrame()


def _fetch_nasdaq_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Nasdaq Charting API (latestIntradayData 당일 봉 포함) + /api/quote/historical 이중 조회."""
    t = ticker.strip().upper()
    if any(c in t for c in ("^", "=", "-")):
        return pd.DataFrame()
    days = _period_to_days(period)
    to_dt = datetime.now() + timedelta(days=1)
    from_dt = to_dt - timedelta(days=days + 5)

    try:
        c_url = (
            f"https://charting.nasdaq.com/data/charting/historical"
            f"?symbol={urllib.parse.quote(t)}&date={from_dt.strftime('%Y-%m-%d')}~{to_dt.strftime('%Y-%m-%d')}&"
        )
        c_headers = {
            **BROWSER_HEADERS,
            "Referer": "https://charting.nasdaq.com/dynamic/chart.html",
        }
        rc = requests.get(c_url, headers=c_headers, timeout=6)
        if rc.status_code == 200:
            cj = rc.json() or {}
            mdata = cj.get("marketData") or []
            latest_intra = cj.get("latestIntradayData") or {}
            rows_c = []
            for item in mdata:
                cl = safe_float(item.get("Close"), 0.0)
                if cl <= 0:
                    continue
                dt = pd.to_datetime(str(item.get("Date"))[:10]).normalize()
                rows_c.append({
                    "Date": dt,
                    "Open": safe_float(item.get("Open"), cl),
                    "High": safe_float(item.get("High"), cl),
                    "Low": safe_float(item.get("Low"), cl),
                    "Close": cl,
                    "Volume": safe_float(item.get("Volume"), 0.0),
                })
            if latest_intra and safe_float(latest_intra.get("Close"), 0.0) > 0:
                icl = safe_float(latest_intra.get("Close"), 0.0)
                idt = pd.to_datetime(str(latest_intra.get("Date"))[:10]).normalize()
                rows_c.append({
                    "Date": idt,
                    "Open": safe_float(latest_intra.get("Open"), icl),
                    "High": safe_float(latest_intra.get("High"), icl),
                    "Low": safe_float(latest_intra.get("Low"), icl),
                    "Close": icl,
                    "Volume": safe_float(latest_intra.get("Volume"), 0.0),
                })
            if len(rows_c) >= 5:
                dfc = pd.DataFrame(rows_c).set_index("Date").sort_index()
                dfc = dfc[~dfc.index.duplicated(keep="last")]
                return dfc
    except Exception as e:
        LOG.warning("Nasdaq charting historical failed for %s: %s", t, e)

    headers = {
        **BROWSER_HEADERS,
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    for asset in ("stocks", "etf"):
        try:
            url = (
                f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(t)}/historical"
                f"?assetclass={asset}&fromdate={from_dt.strftime('%Y-%m-%d')}"
                f"&limit={max(60, days)}&todate={to_dt.strftime('%Y-%m-%d')}"
            )
            r = requests.get(url, headers=headers, timeout=7)
            if r.status_code != 200:
                continue
            rows = ((r.json().get("data") or {}).get("tradesTable") or {}).get("rows") or []
            if not rows:
                continue
            parsed = []
            for row in rows:
                try:
                    dt = pd.to_datetime(row.get("date")).normalize()
                    cl = safe_float(row.get("close"), 0.0)
                    if cl <= 0:
                        continue
                    op = safe_float(row.get("open"), cl)
                    hi = safe_float(row.get("high"), cl)
                    lo = safe_float(row.get("low"), cl)
                    vl = safe_float(row.get("volume"), 0.0)
                    parsed.append({"Date": dt, "Open": op, "High": hi, "Low": lo, "Close": cl, "Volume": vl})
                except Exception:
                    continue
            if len(parsed) >= 5:
                df = pd.DataFrame(parsed).set_index("Date").sort_index()
                df = df[~df.index.duplicated(keep="last")]
                return df
        except Exception as e:
            LOG.warning("Nasdaq fallback (%s) failed for %s: %s", asset, t, e)
    return pd.DataFrame()


def _fetch_stooq_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Stooq 글로벌 무료 CSV 엔드포인트 폴백."""
    stooq_map = {
        "^TNX": "10usy.b", "ES=F": "spy.us", "NQ=F": "qqq.us",
        "YM=F": "dia.us", "CL=F": "uso.us", "^VIX": "vixy.us", "GC=F": "gld.us",
        "BTC-USD": "btcusd", "KRW=X": "usdkrw",
    }
    sym = stooq_map.get(ticker.upper())
    if not sym:
        if any(c in ticker for c in ("^", "=", "-")):
            return pd.DataFrame()
        sym = f"{ticker.lower()}.us"
    days = _period_to_days(period)
    d2 = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
    d1 = (datetime.now() - timedelta(days=days + 5)).strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={sym}&d1={d1}&d2={d2}&i=d"
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=7)
        if r.status_code == 200 and "Date,Open,High,Low,Close" in r.text:
            df = pd.read_csv(io.StringIO(r.text))
            if not df.empty and "Close" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
                df = df.set_index("Date").sort_index()
                if "Volume" not in df.columns:
                    df["Volume"] = 0.0
                df["Volume"] = df["Volume"].fillna(0.0)
                df = df.dropna(subset=["Close"])
                if len(df) >= 2:
                    return df
    except Exception as e:
        LOG.warning("Stooq fallback failed for %s: %s", ticker, e)
    return pd.DataFrame()


@st.cache_data(ttl=CFG["cache"]["top_bar"])
def get_top_bar_data():
    p, ch, k = 0.0, 0.0, 0.0
    try:
        rb = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=4)
        if rb.status_code == 200:
            jb = rb.json()
            p = safe_float(jb.get("lastPrice"), 0.0)
            ch = safe_float(jb.get("priceChange"), 0.0)
    except Exception:
        pass
    if p <= 0:
        qb = get_realtime_quote("BTC-USD")
        if qb.get("price", 0.0) > 0:
            p = qb["price"]
            ch = qb.get("change", 0.0)
    if p <= 0:
        try:
            rc = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=4)
            if rc.status_code == 200:
                p = safe_float(rc.json().get("data", {}).get("amount"), 0.0)
        except Exception:
            pass

    qk = get_realtime_quote("KRW=X")
    if qk.get("price", 0.0) > 0:
        k = qk["price"]
    if k <= 0:
        try:
            rk = requests.get("https://open.er-api.com/v6/latest/USD", timeout=4)
            if rk.status_code == 200:
                k = safe_float(rk.json().get("rates", {}).get("KRW"), 0.0)
        except Exception:
            pass
    return p, ch, k


@st.cache_data(ttl=CFG["cache"]["indices"])
def get_market_indices():
    tickers = [
        ("10년물 국채", "^TNX"),
        ("S&P500 야간선물", "ES=F"),
        ("나스닥100 야간선물", "NQ=F"),
        ("다우 야간선물", "YM=F"),
        ("WTI 원유", "CL=F"),
        ("VIX 변동성", "^VIX"),
        ("금 (Gold)", "GC=F"),
    ]
    out = []
    for name, t in tickers:
        cur, chg = 0.0, 0.0
        q = get_realtime_quote(t)
        if q.get("price", 0.0) > 0:
            cur = safe_float(q.get("price"), 0.0)
            chg = safe_float(q.get("change_pct"), 0.0)
        if cur <= 0:
            try:
                d = _fetch_yahoo_v8_direct(t, "5d")
                if len(d) >= 2:
                    cur = safe_float(d["Close"].iloc[-1], 0.0)
                    prev = safe_float(d["Close"].iloc[-2], cur)
                    chg = ((cur - prev) / prev) * 100.0 if prev > 0 else 0.0
            except Exception:
                pass
        out.append({"name": name, "price": cur, "change": chg})
    return out


def _clean_tz(df: pd.DataFrame) -> pd.DataFrame:
    if df is not None and not df.empty:
        if getattr(df.index, "tz", None) is not None:
            try:
                df.index = df.index.tz_convert("America/New_York").tz_localize(None).normalize()
            except Exception:
                df.index = df.index.tz_localize(None)
        else:
            try:
                df.index = pd.to_datetime(df.index).normalize()
            except Exception:
                pass
        df = df[~df.index.duplicated(keep="last")].sort_index()
        for _c in ("Open", "High", "Low", "Close", "Volume"):
            if _c in df.columns:
                df[_c] = pd.to_numeric(df[_c], errors="coerce").astype("float64")
    return df


@st.cache_data(ttl=CFG["cache"]["history"])
def get_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    t = ticker.strip().upper()
    if not t:
        return pd.DataFrame()

    df = pd.DataFrame()

    # 1차: Yahoo v8 Direct JSON
    h_v8 = _fetch_yahoo_v8_direct(t, period)
    if not h_v8.empty and len(h_v8) >= 5:
        df = _clean_tz(h_v8)

    # 2차: Nasdaq 공식 Charting / Historical API
    if df.empty:
        h_nq = _fetch_nasdaq_history(t, period)
        if not h_nq.empty and len(h_nq) >= 5:
            LOG.info("Fetched %s from Nasdaq API fallback", t)
            df = _clean_tz(h_nq)

    # 3차: yfinance 라이브러리
    if df.empty:
        try:
            h = yf.Ticker(t).history(period=period)
            if h is not None and not h.empty and "Close" in h.columns and h["Close"].notna().sum() >= 5:
                df = _clean_tz(h)
        except Exception as e:
            LOG.warning("yfinance history failed for %s: %s", t, e)

    # 4차: Stooq 무료 CSV API
    if df.empty:
        h_sq = _fetch_stooq_history(t, period)
        if not h_sq.empty and len(h_sq) >= 5:
            LOG.info("Fetched %s from Stooq CSV fallback", t)
            df = _clean_tz(h_sq)

    # 5차: xfinance 라이브러리 (설치 시)
    if df.empty and HAS_XFINANCE:
        try:
            xh = xf.Ticker(t).history(period=period)
            if xh is not None and not xh.empty:
                df = _clean_tz(xh)
        except Exception as e:
            LOG.error("xfinance fallback failed for %s: %s", t, e)

    if df.empty:
        LOG.error("All 5 history sources failed for %s", t)
        return pd.DataFrame()

    try:
        rt = get_realtime_quote(t)
        if rt and safe_float(rt.get("price"), 0.0) > 0:
            df = _stitch_realtime_quote(df, rt)
    except Exception as e:
        LOG.warning("Realtime stitch skipped for %s: %s", t, e)

    return df


@st.cache_data(ttl=CFG["cache"]["market_cap"])
def get_market_cap(ticker: str):
    if FINNHUB_KEY and HAS_FINNHUB_LIB:
        try:
            client = finnhub.Client(api_key=FINNHUB_KEY)
            prof = client.company_profile2(symbol=ticker.upper()) or {}
            mc_fh = safe_float(prof.get("marketCapitalization", 0.0), 0.0)
            if mc_fh > 0:
                return mc_fh * 1e6
        except Exception:
            pass
    try:
        url = f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(ticker.upper())}/summary?assetclass=stocks"
        r = requests.get(url, headers={**BROWSER_HEADERS, "Referer": "https://www.nasdaq.com/"}, timeout=5)
        if r.status_code == 200:
            sd = ((r.json().get("data") or {}).get("summaryData") or {})
            mc_val = safe_float((sd.get("MarketCap") or {}).get("value"), 0.0)
            if mc_val > 0:
                return mc_val
    except Exception:
        pass
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        mc = fi.get("market_cap") if hasattr(fi, "get") else None
        if not mc and hasattr(fi, "__getitem__"):
            try:
                mc = fi["market_cap"]
            except Exception:
                mc = None
        if mc and float(mc) > 0:
            return float(mc)
    except Exception:
        pass
    return None


@st.cache_data(ttl=CFG["cache"]["fear_greed"])
def get_fear_and_greed_index():
    score, rating = 50.0, "Neutral"
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cnn.com/markets/fear-and-greed'},
            timeout=5)
        if r.status_code == 200:
            d = r.json()
            score = safe_float(d['fear_and_greed']['score'], 50.0)
            rating = str(d['fear_and_greed']['rating']).title()
        else:
            raise ValueError("Fallback to VIX")
    except Exception:
        try:
            vq = get_realtime_quote("^VIX")
            vix = safe_float(vq.get("price"), 18.0) if vq else 18.0
            if vix >= 30:
                score, rating = 18.0, "Extreme Fear"
            elif vix >= 22:
                score, rating = 35.0, "Fear"
            elif vix >= 16:
                score, rating = 52.0, "Neutral"
            elif vix >= 13:
                score, rating = 68.0, "Greed"
            else:
                score, rating = 82.0, "Extreme Greed"
        except Exception:
            score, rating = 50.0, "Neutral"

    if score <= 25:
        kr_label, badge_cls, bar_color = "😱 극단적 공포 (Extreme Fear)", "badge-green", "#10b981"
        advice = "대중의 패닉 셀링 구간입니다. 단, 계약 해지·유상증자 등 개별 악재가 없는 종목에 한해 역발상 매수가 유효합니다."
    elif score <= 45:
        kr_label, badge_cls, bar_color = "😨 공포 (Fear)", "badge-blue", "#38bdf8"
        advice = "시장 경계감이 높은 저점 매집 구간입니다. 지지선 확인 후 분할 매수가 유리합니다."
    elif score <= 55:
        kr_label, badge_cls, bar_color = "😐 중립 (Neutral)", "badge-indigo", "#818cf8"
        advice = "지수 방향성보다 개별 종목의 거래량 돌파 및 정배열 수급이 수익률을 결정하는 종목 장세입니다."
    elif score <= 75:
        kr_label, badge_cls, bar_color = "🤑 탐욕 (Greed)", "badge-yellow", "#f59e0b"
        advice = "강세장 추세가 이어지고 있습니다. 보유 물량은 홀딩하되 1차 익절가 도달 시 미래에셋 트레일링 스탑을 가동하십시오."
    else:
        kr_label, badge_cls, bar_color = "🔥 극단적 탐욕 (Extreme Greed)", "badge-red", "#f43f5e"
        advice = "시장 과열 경보 구간입니다! 신규 추격매수를 자제하고 트레일링 스탑을 단기 타이트폭(①번)으로 조여서 수익을 지키십시오."

    return {
        "score": round(score, 1), "rating": rating, "kr_label": kr_label,
        "badge_cls": badge_cls, "bar_color": bar_color, "advice": advice,
    }


# ==============================================================================
# 7) SHORT INTEREST & GEX
# ==============================================================================
@st.cache_data(ttl=CFG["cache"]["short_interest"])
def get_short_interest_data(ticker: str) -> dict:
    short_pct = 0.0
    short_ratio = 0.0
    shares_short = 0.0
    try:
        info = yf.Ticker(ticker).info or {}
        raw_pct = safe_float(info.get("shortPercentOfFloat", 0.0), 0.0)
        short_pct = raw_pct * 100.0 if 0 < raw_pct <= 1.0 else raw_pct
        short_ratio = safe_float(info.get("shortRatio", 0.0), 0.0)
        shares_short = safe_float(info.get("sharesShort", 0.0), 0.0)
    except Exception as e:
        LOG.info("short_interest skipped/fallback for %s (Yahoo rate limit guard): %s", ticker, e)
    return {"short_pct": round(short_pct, 2), "days_to_cover": round(short_ratio, 2), "shares_short": shares_short}


@st.cache_data(ttl=CFG["cache"]["gex"])
def get_gamma_wall_and_gex_data(ticker: str, current_price: float = 0.0, exp_date=None):
    try:
        stock = yf.Ticker(ticker)
        options = stock.options
        if not options:
            return {"call_wall": None, "put_wall": None, "max_pain": None, "exp_dates": [],
                    "cp_oi_ratio": 1.0, "total_call_oi": 0, "total_put_oi": 0,
                    "gex_status": "옵션 데이터 없음", "is_gamma_squeeze_zone": False}
        target_exp = exp_date if exp_date in options else options[0]
        opt_chain = stock.option_chain(target_exp)
        calls = opt_chain.calls[['strike', 'openInterest']].dropna()
        puts = opt_chain.puts[['strike', 'openInterest']].dropna()
        call_wall = float(calls.loc[calls['openInterest'].idxmax()]['strike']) if not calls.empty and calls['openInterest'].max() > 0 else None
        put_wall = float(puts.loc[puts['openInterest'].idxmax()]['strike']) if not puts.empty and puts['openInterest'].max() > 0 else None
        total_call_oi = int(calls['openInterest'].sum()) if not calls.empty else 0
        total_put_oi = int(puts['openInterest'].sum()) if not puts.empty else 0
        cp_oi_ratio = round(total_call_oi / total_put_oi, 2) if total_put_oi > 0 else (2.0 if total_call_oi > 0 else 1.0)
        all_strikes = np.union1d(calls['strike'], puts['strike'])
        pain_values = []
        for strike in all_strikes:
            call_loss = np.maximum(0, strike - calls['strike']) * calls['openInterest']
            put_loss = np.maximum(0, puts['strike'] - strike) * puts['openInterest']
            pain_values.append(call_loss.sum() + put_loss.sum())
        max_pain = float(all_strikes[np.argmin(pain_values)]) if len(pain_values) > 0 else None
        is_gamma_squeeze = False
        if call_wall and current_price > 0:
            dist_to_call_wall = ((call_wall - current_price) / current_price) * 100.0
            if cp_oi_ratio >= 1.35 and -3.0 <= dist_to_call_wall <= 5.5:
                is_gamma_squeeze = True
        if is_gamma_squeeze:
            gex_status = "🔥 감마스퀴즈 점화 구간 (딜러 델타헤지 매수 유입)"
        elif cp_oi_ratio >= 1.3:
            gex_status = "🟢 콜(Call) 감마 우위 (상방 자석 효과)"
        elif cp_oi_ratio <= 0.75:
            gex_status = "🔴 풋(Put) 감마 우위 (하방 변동성 주의)"
        else:
            gex_status = "⚖️ 중립 감마 (맥스페인 수렴 장세)"
        return {"call_wall": call_wall, "put_wall": put_wall, "max_pain": max_pain,
                "exp_dates": list(options), "cp_oi_ratio": cp_oi_ratio,
                "total_call_oi": total_call_oi, "total_put_oi": total_put_oi,
                "gex_status": gex_status, "is_gamma_squeeze_zone": is_gamma_squeeze,
                "target_exp": target_exp}
    except Exception:
        return {"call_wall": None, "put_wall": None, "max_pain": None, "exp_dates": [],
                "cp_oi_ratio": 1.0, "total_call_oi": 0, "total_put_oi": 0,
                "gex_status": "옵션 조회 제한 (기본 추세 모드)", "is_gamma_squeeze_zone": False}


def evaluate_squeeze_potential(short_data, gex_data, current_price, box_high, vol_ratio):
    scfg = CFG["squeeze"]
    sp = short_data.get("short_pct", 0.0)
    dtc = short_data.get("days_to_cover", 0.0)
    cp_ratio = gex_data.get("cp_oi_ratio", 1.0)
    is_gex_zone = gex_data.get("is_gamma_squeeze_zone", False)
    sq_score = 0
    reasons = []
    if sp >= scfg["short_pct_high"]:
        sq_score += 45
        reasons.append(f"공매도 비중 극단 과열({sp:.1f}% ≥ 20%)")
    elif sp >= scfg["short_pct_mid"]:
        sq_score += 25
        reasons.append(f"공매도 비중 높음({sp:.1f}%)")
    if dtc >= scfg["dtc_high"]:
        sq_score += 20
        reasons.append(f"숏커버 소요일수({dtc:.1f}일) 장기화")
    elif dtc >= scfg["dtc_mid"]:
        sq_score += 10
        reasons.append(f"숏커버 소요일수({dtc:.1f}일)")
    if is_gex_zone:
        sq_score += 25
        reasons.append(f"콜 감마벽 돌파 임박 (Call/Put OI {cp_ratio:.2f}배)")
    elif cp_ratio >= 1.4:
        sq_score += 12
        reasons.append(f"콜 옵션 수급 집중 (C/P {cp_ratio:.2f}배)")
    if current_price >= box_high * 0.98 and vol_ratio >= 1.3:
        sq_score += 15
        reasons.append(f"고점 돌파 + 거래량({vol_ratio:.1f}x) 유입으로 숏커버 강제 트리거")
    sq_score = min(100, sq_score)
    bonus = int(round((sq_score / 100.0) * scfg["squeeze_bonus_max"])) if current_price >= box_high * 0.95 else 0
    if sq_score >= 70:
        grade, badge = "🌋 초강력 더블 스퀴즈 경보 (EXTREME SQUEEZE)", "badge-orange"
        guide = "공매도 숏커버링과 마켓메이커의 콜옵션 델타헤지 매수가 동시에 터지는 폭발 구간입니다! 섣부른 전량 매도를 피하고 트레일링 스탑으로 오버슈팅을 끝까지 발라먹으십시오."
    elif sq_score >= 40:
        grade, badge = "⚡ 스퀴즈 잠재력 우수 (HIGH POTENTIAL)", "badge-yellow"
        guide = "공매도 잔고 또는 콜옵션 감마 에너지가 축적되어 있습니다. 박스 상단 거래량 돌파 시 급격한 숏커버 슈팅이 나올 수 있습니다."
    else:
        grade, badge = "⚖️ 일반 수급 장세 (NORMAL)", "badge-blue"
        guide = "인위적인 숏스퀴즈보다 기업의 펀더멘털(실적·계약)과 6대 대가 정배열 추세에 따라 움직이는 정석 구간입니다."
    return {"sq_score": sq_score, "bonus": bonus, "grade": grade, "badge": badge,
            "reasons": reasons if reasons else ["특이 공매도/옵션 과열 신호 없음"], "guide": guide}


# ==============================================================================
# 8) SQLite
# ==============================================================================
_ACTIVE_DB_PATH = CFG["paths"]["db"]


def _db_conn():
    global _ACTIVE_DB_PATH
    try:
        conn = sqlite3.connect(_ACTIVE_DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=MEMORY;")
        conn.execute("PRAGMA synchronous=OFF;")
        return conn
    except Exception:
        _ACTIVE_DB_PATH = "/tmp/gangjin_portfolio.db"
        conn = sqlite3.connect(_ACTIVE_DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=MEMORY;")
        conn.execute("PRAGMA synchronous=OFF;")
        return conn


def init_db():
    try:
        with _db_conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS holdings (ticker TEXT PRIMARY KEY, buy_price REAL NOT NULL DEFAULT 0.0, qty REAL NOT NULL DEFAULT 0.0, target_roi REAL NOT NULL DEFAULT 15.0, stop_loss_pct REAL NOT NULL DEFAULT 7.0, updated_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS alert_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, signal TEXT, price REAL, message TEXT, created_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS trade_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, trade_date TEXT NOT NULL, ticker TEXT NOT NULL, side TEXT NOT NULL, price REAL NOT NULL DEFAULT 0.0, qty REAL NOT NULL DEFAULT 0.0, realized_pnl REAL NOT NULL DEFAULT 0.0, strategy_tag TEXT, emotion_tag TEXT, memo TEXT, created_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS signal_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL, signal TEXT NOT NULL,
                signal_price REAL NOT NULL, signal_date TEXT NOT NULL,
                horizon_days INTEGER NOT NULL,
                eval_date TEXT, price_at_eval REAL, return_pct REAL, outcome TEXT,
                UNIQUE(ticker, signal, signal_date, horizon_days))""")
            conn.commit()
    except Exception as e:
        LOG.error("init_db error: %s", e)


def db_get_holdings() -> list:
    try:
        with _db_conn() as conn:
            rows = conn.execute("SELECT ticker, buy_price, qty, target_roi, stop_loss_pct, updated_at FROM holdings ORDER BY ticker").fetchall()
        return [{"ticker": r[0], "buy_price": safe_float(r[1]), "qty": safe_float(r[2]),
                 "target_roi": safe_float(r[3], 15.0), "stop_loss_pct": safe_float(r[4], 7.0),
                 "updated_at": r[5] or ""} for r in rows]
    except Exception as e:
        LOG.error("db_get_holdings error: %s", e)
        return []


def db_upsert_holding(ticker, buy_price, qty, target_roi=15.0, stop_loss_pct=7.0):
    t = ticker.strip().upper()
    if not t:
        return
    try:
        with _db_conn() as conn:
            conn.execute("""INSERT INTO holdings (ticker, buy_price, qty, target_roi, stop_loss_pct, updated_at) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET buy_price=excluded.buy_price, qty=excluded.qty, target_roi=excluded.target_roi, stop_loss_pct=excluded.stop_loss_pct, updated_at=excluded.updated_at""",
                (t, float(buy_price), float(qty), float(target_roi), float(stop_loss_pct),
                 datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
    except Exception as e:
        LOG.error("db_upsert_holding error: %s", e)


def db_delete_holding(ticker):
    try:
        with _db_conn() as conn:
            conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker.strip().upper(),))
            conn.commit()
    except Exception as e:
        LOG.error("db_delete_holding error: %s", e)


def db_log_alert(ticker, signal, price, message):
    try:
        with _db_conn() as conn:
            conn.execute("INSERT INTO alert_logs (ticker, signal, price, message, created_at) VALUES (?,?,?,?,?)",
                         (ticker, signal, float(price), message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e:
        LOG.error("db_log_alert error: %s", e)


def db_add_journal_entry(trade_date, ticker, side, price, qty, realized_pnl, strategy_tag, emotion_tag, memo):
    try:
        with _db_conn() as conn:
            conn.execute("""INSERT INTO trade_journal (trade_date, ticker, side, price, qty, realized_pnl, strategy_tag, emotion_tag, memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (trade_date, ticker.strip().upper(), side, float(price), float(qty),
                 float(realized_pnl), strategy_tag, emotion_tag, memo.strip(),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
    except Exception as e:
        LOG.error("db_add_journal_entry error: %s", e)


def db_get_journal_entries(limit=200):
    try:
        with _db_conn() as conn:
            rows = conn.execute("""SELECT id, trade_date, ticker, side, price, qty, realized_pnl, strategy_tag, emotion_tag, memo
                FROM trade_journal ORDER BY trade_date DESC, id DESC LIMIT ?""", (limit,)).fetchall()
        return [{"id": r[0], "일자": r[1], "티커": r[2], "구분": r[3], "단가($)": r[4],
                 "수량": r[5], "실현손익($)": r[6], "적용기법": r[7], "심리상태": r[8], "복기메모": r[9]} for r in rows]
    except Exception as e:
        LOG.error("db_get_journal_entries error: %s", e)
        return []


def db_delete_journal_entry(entry_id):
    try:
        with _db_conn() as conn:
            conn.execute("DELETE FROM trade_journal WHERE id = ?", (int(entry_id),))
            conn.commit()
    except Exception as e:
        LOG.error("db_delete_journal_entry error: %s", e)


def db_register_signal_for_eval(ticker, signal, price, horizons=(5, 10, 20)):
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with _db_conn() as conn:
            for h in horizons:
                conn.execute("""INSERT OR IGNORE INTO signal_outcomes
                    (ticker, signal, signal_price, signal_date, horizon_days)
                    VALUES (?,?,?,?,?)""",
                    (ticker.upper(), signal, float(price), today, h))
            conn.commit()
    except Exception as e:
        LOG.error(f"db_register_signal_for_eval: {e}")


def db_eval_pending_signals():
    try:
        with _db_conn() as conn:
            pending = conn.execute("""SELECT id, ticker, signal_price, signal_date, horizon_days
                FROM signal_outcomes WHERE eval_date IS NULL""").fetchall()
    except Exception:
        return
    today = datetime.now().date()
    for row in pending:
        rid, tk, sig_px, sig_dt, hor = row
        try:
            sig_date = datetime.strptime(sig_dt, "%Y-%m-%d").date()
            if (today - sig_date).days < hor:
                continue
            df = get_history(tk, period="3mo")
            if df.empty:
                continue
            df_dates = [d.date() for d in df.index]
            target_idx = None
            for i, d in enumerate(df_dates):
                if d >= sig_date:
                    target_idx = i
                    break
            if target_idx is None:
                continue
            eval_idx = min(target_idx + hor, len(df) - 1)
            eval_price = float(df['Close'].iloc[eval_idx])
            ret_pct = ((eval_price / sig_px) - 1) * 100
            if ret_pct > 2:
                outcome = "WIN"
            elif ret_pct < -2:
                outcome = "LOSS"
            else:
                outcome = "NEUTRAL"
            with _db_conn() as conn:
                conn.execute("""UPDATE signal_outcomes SET eval_date=?, price_at_eval=?, return_pct=?, outcome=? WHERE id=?""",
                             (today.strftime("%Y-%m-%d"), eval_price, round(ret_pct, 2), outcome, rid))
                conn.commit()
        except Exception as e:
            LOG.warning(f"eval signal {rid}: {e}")


def db_get_signal_stats():
    try:
        with _db_conn() as conn:
            rows = conn.execute("""SELECT signal, horizon_days, COUNT(*) as total,
                SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(return_pct) as avg_ret
                FROM signal_outcomes WHERE outcome IS NOT NULL
                GROUP BY signal, horizon_days""").fetchall()
        out = []
        for r in rows:
            sig, hor, tot, wins, losses, avg_ret = r
            wr = (wins / tot * 100) if tot > 0 else 0
            out.append({"signal": sig, "horizon": hor, "total": tot, "wins": wins,
                        "losses": losses, "win_rate": round(wr, 1),
                        "avg_return": round(avg_ret or 0, 2)})
        return out
    except Exception:
        return []


init_db()


# ==============================================================================
# 9) TELEGRAM & TRAILING
# ==============================================================================
def send_telegram_alert(text, token="", chat_id=""):
    tk = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    cid = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not tk or not cid:
        return False, "텔레그램 봇 토큰 또는 채팅 ID 미설정"
    try:
        url = f"https://api.telegram.org/bot{tk}/sendMessage"
        resp = requests.post(url, json={"chat_id": cid, "text": text, "disable_web_page_preview": True}, timeout=6)
        if resp.status_code == 200:
            return True, "전송 성공!"
        return False, f"전송 실패 (HTTP {resp.status_code})"
    except Exception as e:
        return False, f"오류: {e}"


def get_stock_cap_and_trailing_profile(ticker, mkt_cap, atr_pct):
    t_upper = ticker.upper()
    tr_cfg = CFG["trail"]
    tiers = tr_cfg["tiers"]
    fb = tr_cfg["fallback"]
    if t_upper in tr_cfg["leverage_etfs"]:
        cap_tier, cap_desc, cap_badge = "🚀 2~3X 레버리지 ETF", "초고변동성 레버리지 상품", "badge-purple"
        min_tight, max_tight = tr_cfg["leverage_tier"]["tight"]
        min_core, max_core = tr_cfg["leverage_tier"]["core"]
    elif mkt_cap and mkt_cap >= tiers["mega"]["min"]:
        cap_tier, cap_desc, cap_badge = "👑 메가캡 (초대형주)", f"시총 ${mkt_cap/1e9:,.0f}B", "badge-blue"
        min_tight, max_tight = tiers["mega"]["tight"]
        min_core, max_core = tiers["mega"]["core"]
    elif mkt_cap and mkt_cap >= tiers["large"]["min"]:
        cap_tier, cap_desc, cap_badge = "🐘 대형주 (Large Cap)", f"시총 ${mkt_cap/1e9:,.1f}B", "badge-green"
        min_tight, max_tight = tiers["large"]["tight"]
        min_core, max_core = tiers["large"]["core"]
    elif mkt_cap and mkt_cap >= tiers["mid"]["min"]:
        cap_tier, cap_desc, cap_badge = "🐆 중형 성장주 (Mid Cap)", f"시총 ${mkt_cap/1e9:,.2f}B", "badge-yellow"
        min_tight, max_tight = tiers["mid"]["tight"]
        min_core, max_core = tiers["mid"]["core"]
    elif mkt_cap and mkt_cap > 0:
        cap_tier, cap_desc, cap_badge = "⚡ 소형 급등주 (Small Cap)", f"시총 ${mkt_cap/1e6:,.0f}M", "badge-red"
        min_tight, max_tight = tiers["small"]["tight"]
        min_core, max_core = tiers["small"]["core"]
    else:
        if atr_pct >= fb["high"]["atr_min"]:
            cap_tier, cap_desc, cap_badge = "⚡ 고변동 테마/소형급", "일일 변동폭 상위 종목", "badge-red"
            min_tight, max_tight = fb["high"]["tight"]
            min_core, max_core = fb["high"]["core"]
        elif atr_pct >= fb["mid"]["atr_min"]:
            cap_tier, cap_desc, cap_badge = "🐆 중형 모멘텀급", "중위 변동성 성장주", "badge-yellow"
            min_tight, max_tight = fb["mid"]["tight"]
            min_core, max_core = fb["mid"]["core"]
        else:
            cap_tier, cap_desc, cap_badge = "🐘 대형 안정급", "안정적 대형/지수군", "badge-green"
            min_tight, max_tight = fb["low"]["tight"]
            min_core, max_core = fb["low"]["core"]
    ts_tight_pct = float(np.clip(round(atr_pct * CFG["noise"]["tight_atr"], 1), min_tight, max_tight))
    ts_core_pct = float(np.clip(round(atr_pct * CFG["noise"]["chandelier_atr"], 1), min_core, max_core))
    return {"cap_tier": cap_tier, "cap_desc": cap_desc, "cap_badge": cap_badge,
            "atr_pct": atr_pct, "ts_tight_pct": ts_tight_pct, "ts_core_pct": ts_core_pct}


def normalize_indices_key(indices):
    return tuple((str(item.get("name", "")), round(safe_float(item.get("price", 0.0)), 2),
                  round(safe_float(item.get("change", 0.0)), 2)) for item in (indices or []))


# ==============================================================================
# 9-B) MULTI-SOURCE EARNINGS CALENDAR ENGINE (⭐ [16.5] 실적발표일 6중 정밀 탐지 엔진)
# ==============================================================================
_ETF_NO_EARNINGS = frozenset({
    "SPY", "QQQ", "DIA", "IWM", "VOO", "VTI", "IVV", "SOXX", "SMH", "ARKK",
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB", "XLRE",
    "TLT", "IEF", "SHY", "GLD", "SLV", "USO", "UNG", "IBIT", "FBTC", "BITO",
    "SCHD", "JEPI", "JEPQ", "MSTY", "NVDY", "TSLY", "CONY",
})


def _format_selected_earnings(best_date, ny_today, tod_hint: str = "", is_estimated: bool = False) -> dict:
    """선정된 실적 발표일(best_date)과 미국 동부 오늘 날짜(ny_today)의 D-Day 차이를 계산하여 배지·안내문 생성."""
    dl = (best_date - ny_today).days
    d_str = best_date.strftime("%Y-%m-%d")
    est_tag = " · 예상" if is_estimated else ""
    tod_tag = tod_hint or ""
    if dl == 0:
        return {
            "info": f"🚨 오늘 실적 발표 (D-Day: {d_str}{tod_tag})",
            "imminent": True,
            "badge": "badge-red",
            "days_left": 0,
            "date_str": d_str,
            "is_confirmed": not is_estimated,
        }
    if 1 <= dl <= 7:
        prefix = "⚠️ 실적 시즌 임박" if is_estimated else "⚠️ 실적 임박"
        return {
            "info": f"{prefix} (D-{dl}일: {d_str}{tod_tag}{est_tag})",
            "imminent": True,
            "badge": "badge-yellow",
            "days_left": dl,
            "date_str": d_str,
            "is_confirmed": not is_estimated,
        }
    if dl > 7:
        prefix = "📅 차기 실적(예상)" if is_estimated else "📅 차기 실적"
        return {
            "info": f"{prefix}: {d_str} (D-{dl}일{tod_tag})",
            "imminent": False,
            "badge": "badge-indigo",
            "days_left": dl,
            "date_str": d_str,
            "is_confirmed": not is_estimated,
        }
    # 최근 1~5일 이내 실적 발표 완료 (-5 <= dl < 0)
    return {
        "info": f"📢 최근 실적 발표 완료 (D+{abs(dl)}일: {d_str})",
        "imminent": False,
        "badge": "badge-teal",
        "days_left": dl,
        "date_str": d_str,
        "is_confirmed": True,
    }


@st.cache_data(ttl=CFG["cache"]["earnings"])
def get_earnings_schedule(ticker: str) -> dict:
    """
    ⭐ [16.5] 실적발표일 다중 소스 통합 조회 엔진:
    1차: Nasdaq Analyst Earnings Date API & Quote Notifications/Summary API (야후 차단 무관)
    2차: Finnhub Earnings Calendar API (/api/v1/calendar/earnings, 장전/장후 시간 포함)
    3차: CNBC Quote EventData (next_earnings_date)
    4차: Yahoo Finance 다중 추출 (calendar dict/DataFrame 전 항목 + get_earnings_dates + info timestamps)
    5차: CFG["known_earnings"] 수동 보정 사전 (IREN·NVDA·TSLA 등 주요 종목)
    6차: 직전 분기 실적일 기반 +91일(13주) 차기 분기 주기 자동 추정 폴백
    """
    t = ticker.strip().upper()
    default_res = {
        "info": "실적 일정 미정/통과",
        "imminent": False,
        "badge": "badge-indigo",
        "days_left": None,
        "date_str": "",
        "is_confirmed": False,
    }
    if not t or any(c in t for c in ("^", "=", "-")):
        return default_res
    if t in CFG["trail"]["leverage_etfs"] or t in _ETF_NO_EARNINGS:
        return {
            "info": "📌 ETF 상품 (개별 실적 없음)",
            "imminent": False,
            "badge": "badge-indigo",
            "days_left": None,
            "date_str": "",
            "is_confirmed": True,
        }

    ny_today = _ny_today_date()
    # 후보 리스트: (date_obj, priority, tod_hint) — priority가 낮을수록(1~5) 신뢰도 높음
    candidates = []

    def _add_candidates(raw_val, priority: int, tod_text: str = ""):
        tod = _detect_tod_label(tod_text)
        for d in _extract_dates_from_any(raw_val, ny_today):
            candidates.append((d, priority, tod))

    # ------------------------------------------------------------------
    # [1차] Nasdaq 공식 Analyst Earnings-Date & Quote Notifications API
    # ------------------------------------------------------------------
    nq_headers = {
        **BROWSER_HEADERS,
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    try:
        u_ed = f"https://api.nasdaq.com/api/analyst/{urllib.parse.quote(t)}/earnings-date"
        r_ed = requests.get(u_ed, headers=nq_headers, timeout=4)
        if r_ed.status_code == 200:
            d_ed = (r_ed.json() or {}).get("data") or {}
            ann_txt = str(d_ed.get("announcement") or d_ed.get("earningsDate") or "")
            _add_candidates(ann_txt, priority=1, tod_text=ann_txt)
    except Exception as e:
        LOG.debug("Nasdaq earnings-date failed for %s: %s", t, e)

    try:
        u_inf = f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(t)}/info?assetclass=stocks"
        r_inf = requests.get(u_inf, headers=nq_headers, timeout=4)
        if r_inf.status_code == 200:
            d_inf = (r_inf.json() or {}).get("data") or {}
            notifs = d_inf.get("notifications") or []
            for nf in notifs:
                hl = str(nf.get("headline") or "")
                for ev in (nf.get("eventTypes") or []):
                    msg = str(ev.get("message") or "")
                    ev_name = str(ev.get("eventName") or "")
                    if "earning" in (hl + " " + msg + " " + ev_name).lower():
                        _add_candidates(msg or hl, priority=1, tod_text=msg)
            ks = d_inf.get("keyStats") or {}
            for k_name, k_obj in ks.items():
                if "earning" in str(k_name).lower() and isinstance(k_obj, dict):
                    _add_candidates(k_obj.get("value"), priority=1, tod_text=str(k_obj.get("value") or ""))
    except Exception:
        pass

    try:
        u_sum = f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(t)}/summary?assetclass=stocks"
        r_sum = requests.get(u_sum, headers=nq_headers, timeout=4)
        if r_sum.status_code == 200:
            sd = ((r_sum.json() or {}).get("data") or {}).get("summaryData") or {}
            for k_name in ("EarningsDate", "earningsDate", "NextEarningsDate"):
                if k_name in sd and isinstance(sd[k_name], dict):
                    val_s = sd[k_name].get("value")
                    _add_candidates(val_s, priority=1, tod_text=str(val_s or ""))
    except Exception:
        pass

    # ------------------------------------------------------------------
    # [2차] Finnhub Earnings Calendar API (/api/v1/calendar/earnings)
    # ------------------------------------------------------------------
    if FINNHUB_KEY:
        try:
            f_from = (ny_today - timedelta(days=7)).strftime("%Y-%m-%d")
            f_to = (ny_today + timedelta(days=130)).strftime("%Y-%m-%d")
            u_fh = f"https://finnhub.io/api/v1/calendar/earnings?symbol={urllib.parse.quote(t)}&from={f_from}&to={f_to}&token={FINNHUB_KEY}"
            r_fh = requests.get(u_fh, headers=BROWSER_HEADERS, timeout=4)
            if r_fh.status_code == 200:
                ec_list = (r_fh.json() or {}).get("earningsCalendar") or []
                for item in ec_list:
                    _add_candidates(item.get("date"), priority=1, tod_text=str(item.get("hour") or ""))
        except Exception as e:
            LOG.debug("Finnhub earnings calendar failed for %s: %s", t, e)

    # ------------------------------------------------------------------
    # [3차] CNBC Quote Webservice EventData (next_earnings_date)
    # ------------------------------------------------------------------
    try:
        u_cb = (
            "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
            f"?symbols={urllib.parse.quote(t)}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1"
        )
        r_cb = requests.get(u_cb, headers=BROWSER_HEADERS, timeout=4)
        if r_cb.status_code == 200:
            qq = (((r_cb.json() or {}).get("FormattedQuoteResult") or {}).get("FormattedQuote") or [None])[0] or {}
            ev_data = qq.get("EventData") or {}
            for k_cb in ("next_earnings_date", "earnings_date", "nextEarningsDate"):
                if ev_data.get(k_cb):
                    _add_candidates(ev_data.get(k_cb), priority=2)
                if qq.get(k_cb):
                    _add_candidates(qq.get(k_cb), priority=2)
    except Exception:
        pass

    # ------------------------------------------------------------------
    # [4차] Yahoo Finance (calendar dict/DataFrame + get_earnings_dates + info)
    # ------------------------------------------------------------------
    try:
        yt = yf.Ticker(t)
        try:
            cal = yt.calendar
            if isinstance(cal, dict):
                for k_cal, v_cal in cal.items():
                    if "earning" in str(k_cal).lower():
                        _add_candidates(v_cal, priority=2)
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                for idx_k in cal.index:
                    if "earning" in str(idx_k).lower():
                        _add_candidates(cal.loc[idx_k].values, priority=2)
                for col_k in cal.columns:
                    if "earning" in str(col_k).lower():
                        _add_candidates(cal[col_k].values, priority=2)
        except Exception:
            pass

        # Yahoo calendar가 비어 있을 때 get_earnings_dates(limit=8) 폴백
        if not any(0 <= (d - ny_today).days <= 120 for d, _, _ in candidates):
            try:
                ed_df = yt.get_earnings_dates(limit=8)
                if isinstance(ed_df, pd.DataFrame) and not ed_df.empty:
                    _add_candidates(ed_df.index, priority=2)
            except Exception:
                pass

        # info['earningsTimestamp'] / earningsTimestampStart 폴백
        if not any(0 <= (d - ny_today).days <= 120 for d, _, _ in candidates):
            try:
                inf = yt.info or {}
                for ts_k in ("earningsTimestamp", "earningsTimestampStart", "earningsTimestampEnd"):
                    if inf.get(ts_k):
                        _add_candidates(inf.get(ts_k), priority=2)
            except Exception:
                pass
    except Exception:
        pass

    # ------------------------------------------------------------------
    # [5차] CFG["known_earnings"] 수동 보정 사전 (과거·미래 전체 리스트 중 유효 날짜 선별)
    # ------------------------------------------------------------------
    known_list = (CFG.get("known_earnings") or {}).get(t) or []
    if known_list:
        _add_candidates(known_list, priority=3)

    if not candidates:
        return default_res

    # 날짜별 최고 우선순위 및 장전/장후 태그 병합
    by_date = {}
    for d_obj, prio, tod in candidates:
        if d_obj not in by_date:
            by_date[d_obj] = (prio, tod)
        else:
            old_p, old_tod = by_date[d_obj]
            by_date[d_obj] = (min(old_p, prio), old_tod or tod)

    # 1순위: 오늘(D-Day)부터 향후 125일 이내의 가장 가까운 예정 실적일 (0 <= dl <= 125)
    upcoming = [
        (d_obj, prio, tod)
        for d_obj, (prio, tod) in by_date.items()
        if 0 <= (d_obj - ny_today).days <= 125
    ]
    if upcoming:
        # 가장 가까운 미래 실적일을 우선하되, 불과 1~3일 차이 내에서는 더 높은 신뢰도(낮은 priority) 우선
        upcoming.sort(key=lambda x: ((x[0] - ny_today).days, x[1]))
        best_d, best_p, best_tod = upcoming[0]
        for alt_d, alt_p, alt_tod in upcoming[1:]:
            if abs((alt_d - best_d).days) <= 4 and alt_p < best_p:
                best_d, best_p, best_tod = alt_d, alt_p, (alt_tod or best_tod)
        return _format_selected_earnings(best_d, ny_today, best_tod, is_estimated=False)

    # 2순위: 최근 5일 이내에 막 실적을 발표한 경우 (-5 <= dl < 0)
    recent_past = [
        (d_obj, prio, tod)
        for d_obj, (prio, tod) in by_date.items()
        if -5 <= (d_obj - ny_today).days < 0
    ]
    if recent_past:
        recent_past.sort(key=lambda x: (abs((x[0] - ny_today).days), x[1]))
        best_d, _, best_tod = recent_past[0]
        return _format_selected_earnings(best_d, ny_today, best_tod, is_estimated=False)

    # 3순위: 125일 이후 먼 미래 일정이 존재하는 경우
    far_future = [
        (d_obj, prio, tod)
        for d_obj, (prio, tod) in by_date.items()
        if (d_obj - ny_today).days > 125
    ]
    if far_future:
        far_future.sort(key=lambda x: ((x[0] - ny_today).days, x[1]))
        best_d, _, best_tod = far_future[0]
        return _format_selected_earnings(best_d, ny_today, best_tod, is_estimated=False)

    # 4순위 (6차 폴백): 과거 실적일만 존재할 때 분기 주기(+91일 = 13주)로 차기 실적일 자동 추정
    past_dates = sorted(d_obj for d_obj in by_date.keys() if (d_obj - ny_today).days < -5)
    if past_dates:
        proj_d = past_dates[-1]
        for _ in range(8):
            proj_d = proj_d + timedelta(days=91)
            if (proj_d - ny_today).days >= 0:
                break
        # 주말이면 가장 가까운 평일(목/화)로 보정
        if proj_d.weekday() == 5:
            proj_d -= timedelta(days=1)
        elif proj_d.weekday() == 6:
            proj_d += timedelta(days=1)
        if 0 <= (proj_d - ny_today).days <= 105:
            return _format_selected_earnings(proj_d, ny_today, "", is_estimated=True)

    return default_res


def _refine_earnings_with_news(earn_sched: dict, raw_candidates: list) -> dict:
    """
    ⭐ [16.5] 실시간 수집된 뉴스 헤드라인에서:
    1) 'to report Q3 results on May 7, 2026' 등 실적발표일 공지 PR이 있으면 날짜 자동 추출·보강
    2) 최근 48h 이내 'Reports Q3 Results', 'Q3 Earnings Beat' 등 실제 실적 발표 기사가 있으면 즉시 반영
    """
    if not raw_candidates:
        return earn_sched
    ny_today = _ny_today_date()
    has_confirmed_upcoming = bool(
        earn_sched.get("is_confirmed")
        and earn_sched.get("days_left") is not None
        and 0 <= earn_sched["days_left"] <= 90
    )

    pr_schedule_pat = re.compile(
        r"\b(to report|to announce|schedules|scheduled|sets date|will report|will announce|host[s]? .*?call|release[s]? .*?results)\b.*?"
        r"\b(earnings|financial results|quarterly results|first[- ]quarter|second[- ]quarter|third[- ]quarter|fourth[- ]quarter|q[1-4]|fiscal)\b",
        flags=re.IGNORECASE,
    )
    just_reported_pat = re.compile(
        r"(\b(reports|reported|posts|posted|announces|announced|delivers)\s+(record\s+)?(q[1-4]|first[- ]quarter|second[- ]quarter|third[- ]quarter|fourth[- ]quarter|quarterly|full[- ]year|fy\s*\d{2,4})\b.*?(results|earnings|revenue))"
        r"|(\b(q[1-4]\s+earnings\s+(beat|miss|top|surpass)|eps\s+(beats|misses|tops)\s+estimates|revenue\s+(beats|misses)\s+estimates)\b)",
        flags=re.IGNORECASE,
    )

    # 1) 실적 발표 예정일 공지 PR에서 정확한 날짜 추출
    if not has_confirmed_upcoming:
        for cand in raw_candidates:
            title = str(cand.get("raw_title") or "")
            if pr_schedule_pat.search(title):
                extracted = _extract_dates_from_any(title, ny_today)
                valid_up = [d for d in extracted if -2 <= (d - ny_today).days <= 120]
                if valid_up:
                    valid_up.sort(key=lambda d: abs((d - ny_today).days))
                    tod = _detect_tod_label(title)
                    return _format_selected_earnings(valid_up[0], ny_today, tod, is_estimated=False)

    # 2) 최근 48h 내 실제 실적 발표 기사가 존재할 때 '미정/통과' 상태라면 즉시 '실적 발표 완료'로 전환
    if earn_sched.get("days_left") is None or not earn_sched.get("is_confirmed"):
        for cand in raw_candidates:
            age_h = safe_float(cand.get("age_h"), 9999.0)
            if age_h > 48.0:
                continue
            title = str(cand.get("raw_title") or "")
            if just_reported_pat.search(title) and not pr_schedule_pat.search(title):
                pub_dt = cand.get("pub_dt")
                rep_date = pub_dt.date() if isinstance(pub_dt, datetime) else ny_today
                dl = (rep_date - ny_today).days
                d_str = rep_date.strftime("%Y-%m-%d")
                return {
                    "info": f"📢 최근 실적 발표 완료 ({d_str} · {age_h:.0f}h 전)",
                    "imminent": False,
                    "badge": "badge-teal",
                    "days_left": dl,
                    "date_str": d_str,
                    "is_confirmed": True,
                }

    return earn_sched


# ==============================================================================
# 10) MACRO + NEWS (⭐ [16.5-R1] 뉴스 수집 10분 독립 캐시 + 전 섹터 호악재 판독 + 과거 뉴스 패스)
# ==============================================================================
@st.cache_data(ttl=CFG["cache"]["news_candidates"])
def fetch_raw_news_candidates(ticker: str, company_name: str = "") -> list:
    """
    ⭐ [16.5-R1] 4중 뉴스 수집(Finnhub -> Yahoo RSS -> Google RSS -> Nasdaq News)을
    거시 지수(indices_key) 변동과 분리하여 10분(600초) 단위로 독립 캐싱합니다.
    """
    ncfg = CFG["news"]
    stale_limit_h = ncfg["recency_hours"]["stale_pass"]  # 72h 하드 컷오프
    raw_candidates = []
    seen_titles = set()

    def _collect_candidate(raw_title, raw_link, pub_dt, src_tag):
        if not raw_title or pub_dt is None:
            return
        age_h = _hours_since(pub_dt)
        # ⭐ 72시간(3일) 초과 기사는 과거 뉴스이므로 수집 단계에서 100% 폐기 (무조건 선별 패스)
        if age_h > stale_limit_h:
            return
        tl = raw_title.lower()
        # ⭐ 회고성·클릭베이트("last month", "if you invested" 등) 기사 무조건 패스
        for pat in ncfg["retrospective_skip"]:
            if re.search(pat, tl):
                return
        key = _normalize_title(raw_title)
        if not key or key in seen_titles:
            return
        seen_titles.add(key)
        raw_candidates.append({
            "raw_title": raw_title.strip(),
            "raw_link": raw_link or "#",
            "pub_dt": pub_dt,
            "age_h": age_h,
            "src_tag": src_tag,
        })

    # ⭐ [1차] Finnhub Company News API (최근 3일)
    if FINNHUB_KEY and HAS_FINNHUB_LIB:
        try:
            client = finnhub.Client(api_key=FINNHUB_KEY)
            today = datetime.now()
            from_date = (today - timedelta(days=3)).strftime('%Y-%m-%d')
            to_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
            fh_news = client.company_news(ticker, _from=from_date, to=to_date) or []
            for item in fh_news[:25]:
                ts = item.get('datetime', 0) or 0
                pub_dt = datetime.fromtimestamp(ts) if ts > 0 else None
                _collect_candidate(item.get('headline', ''), item.get('url', '#'), pub_dt, "Finnhub")
        except Exception as e:
            LOG.warning("Finnhub news fetch failed for %s: %s", ticker, e)

    # ⭐ [2차] Yahoo Finance 공식 티커 RSS (Seeking Alpha·Benzinga·BusinessWire 직결 속보)
    try:
        yh_rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={urllib.parse.quote(ticker.upper())}&region=US&lang=en-US"
        r_yh = requests.get(yh_rss_url, headers=BROWSER_HEADERS, timeout=5)
        if r_yh.status_code == 200 and r_yh.content:
            root_yh = ET.fromstring(r_yh.content)
            for item in root_yh.findall('.//item')[:25]:
                t_el = item.find('title')
                l_el = item.find('link')
                p_el = item.find('pubDate')
                pub_dt = None
                if p_el is not None and p_el.text:
                    try:
                        pub_dt = parsedate_to_datetime(p_el.text)
                    except Exception:
                        pub_dt = None
                _collect_candidate(
                    t_el.text if t_el is not None else "",
                    l_el.text if l_el is not None else "#",
                    pub_dt,
                    "Yahoo RSS",
                )
    except Exception as e:
        LOG.warning("Yahoo RSS fetch failed for %s: %s", ticker, e)

    # ⭐ [3차] Google News RSS (티커 + 기업명 병행 검색으로 'Aevex' 같은 기업명 단독 표기 속보 포착)
    try:
        cname = (company_name or "").strip()
        if cname and cname.upper() != ticker.upper():
            q_str = f'("{ticker}" OR "{cname}") stock when:3d'
        else:
            q_str = f'"{ticker}" stock news when:3d'
        g_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q_str)}&hl=en-US&gl=US&ceid=US:en"
        r_gn = requests.get(g_url, headers=BROWSER_HEADERS, timeout=5)
        if r_gn.status_code == 200 and r_gn.content:
            root_gn = ET.fromstring(r_gn.content)
            for item in root_gn.findall('.//item')[:25]:
                t_el = item.find('title')
                l_el = item.find('link')
                p_el = item.find('pubDate')
                pub_dt = None
                if p_el is not None and p_el.text:
                    try:
                        pub_dt = parsedate_to_datetime(p_el.text)
                    except Exception:
                        pub_dt = None
                _collect_candidate(
                    t_el.text if t_el is not None else "",
                    l_el.text if l_el is not None else "#",
                    pub_dt,
                    "Google RSS",
                )
    except Exception as e:
        LOG.warning("Google RSS fetch failed for %s: %s", ticker, e)

    # ⭐ [4차] Nasdaq 공식 종목 뉴스 API (나스닥/뉴욕거래소 공시·프레스릴리즈 보완)
    try:
        nq_news_url = (
            f"https://www.nasdaq.com/api/news/topic/articlebysymbol"
            f"?q={urllib.parse.quote(ticker.upper())}|STOCKS&offset=0&limit=15&fallback=true"
        )
        r_nqn = requests.get(
            nq_news_url,
            headers={**BROWSER_HEADERS, "Referer": "https://www.nasdaq.com/"},
            timeout=5,
        )
        if r_nqn.status_code == 200:
            rows_n = ((r_nqn.json() or {}).get("data") or {}).get("rows") or []
            for rn in rows_n[:15]:
                title_n = str(rn.get("title") or "").strip()
                url_n = str(rn.get("url") or "").strip()
                if url_n.startswith("/"):
                    url_n = f"https://www.nasdaq.com{url_n}"
                pub_dt_n = _parse_relative_or_date(rn.get("ago", ""), rn.get("created", ""))
                _collect_candidate(title_n, url_n, pub_dt_n, "Nasdaq News")
    except Exception as e:
        LOG.warning("Nasdaq news fetch failed for %s: %s", ticker, e)

    raw_candidates.sort(key=lambda x: x["age_h"])
    return raw_candidates


@st.cache_data(ttl=CFG["cache"]["macro"])
def analyze_macro_and_stock_catalysts(ticker, indices_key, company_name: str = "", use_llm: bool = False):
    idx_map = {name: {"price": price, "change": chg} for name, price, chg in indices_key}
    tnx = idx_map.get("10년물 국채", {"price": 4.2, "change": 0.0})
    wti = idx_map.get("WTI 원유", {"price": 72.0, "change": 0.0})
    vix = idx_map.get("VIX 변동성", {"price": 18.0, "change": 0.0})
    gold = idx_map.get("금 (Gold)", {"price": 2700.0, "change": 0.0})
    nq = idx_map.get("나스닥100 야간선물", {"price": 20000.0, "change": 0.0})
    es = idx_map.get("S&P500 야간선물", {"price": 5800.0, "change": 0.0})
    mc = CFG["macro"]
    macro_score = 0
    macro_alerts = []
    if nq["change"] >= mc["nq_strong"] or es["change"] >= mc["es_strong"]:
        macro_score += 12
        macro_alerts.append(f"🌃 미장 야간선물 강세 (나스닥 {nq['change']:+.1f}%, S&P {es['change']:+.1f}%)")
    elif nq["change"] <= -mc["nq_strong"] or es["change"] <= -mc["es_strong"]:
        macro_score -= 12
        macro_alerts.append(f"🌃 미장 야간선물 약세 (나스닥 {nq['change']:+.1f}%, S&P {es['change']:+.1f}%)")
    if wti['change'] >= mc["wti_spike_chg"] or wti['price'] >= mc["wti_spike_price"]:
        macro_score -= 12
        macro_alerts.append(f"🛢️ 유가 급등 (${wti['price']:.1f})")
    elif (wti['change'] <= -1.5 or wti['price'] < mc["wti_stable"]) and wti['price'] > 0:
        macro_score += 5
        macro_alerts.append(f"🛢️ 유가 안정 (${wti['price']:.1f})")
    if tnx['price'] >= mc["tnx_spike_price"] or tnx['change'] >= mc["tnx_spike_chg"]:
        macro_score -= 12
        macro_alerts.append(f"🏦 금리 발작 ({tnx['price']:.2f}%)")
    elif (tnx['change'] <= -1.0 or tnx['price'] < mc["tnx_stable"]) and tnx['price'] > 0:
        macro_score += 8
        macro_alerts.append(f"🏦 금리 안정 ({tnx['price']:.2f}%)")
    if vix['price'] >= mc["vix_crisis"] or (vix['change'] >= 5.0 and gold['change'] >= 1.0):
        macro_score -= 15
        macro_alerts.append(f"💣 지정학 경보 (VIX {vix['price']:.1f})")
    elif 0 < vix['price'] < mc["vix_calm"] and nq['change'] >= 0:
        macro_score += 7
        macro_alerts.append(f"🕊️ 위험선호 양호 (VIX {vix['price']:.1f})")
    if not macro_alerts:
        macro_alerts.append(f"⚖️ 거시 중립 (금리 {tnx['price']:.2f}% | WTI ${wti['price']:.1f} | VIX {vix['price']:.1f})")

    # ⭐ [16.5] 6중 실적 발표일 정밀 탐지 (Nasdaq -> Finnhub -> CNBC -> Yahoo 다중포맷 -> KNOWN_EARNINGS -> 뉴스 PR 보정)
    earn_sched = get_earnings_schedule(ticker)
    earnings_info = earn_sched["info"]
    earnings_imminent = earn_sched["imminent"]
    earnings_badge = earn_sched["badge"]
    earnings_days_left = earn_sched["days_left"]

    ncfg = CFG["news"]
    stale_limit_h = ncfg["recency_hours"]["stale_pass"]  # 72h 하드 컷오프
    active_limit_h = ncfg["recency_hours"]["recent"]     # 48h 시그널 컷오프

    # ⭐ [16.5-R1] 10분 독립 캐시에서 뉴스 후보군 로드 후 현재 시각 기준 경과시간(age_h) 동적 갱신
    cached_candidates = fetch_raw_news_candidates(ticker, company_name=company_name)
    raw_candidates = []
    for c_item in cached_candidates:
        cur_age_h = _hours_since(c_item.get("pub_dt"))
        if cur_age_h <= stale_limit_h:
            item_copy = dict(c_item)
            item_copy["age_h"] = cur_age_h
            raw_candidates.append(item_copy)
    raw_candidates.sort(key=lambda x: x["age_h"])

    news_items = []
    ch_score = ebh_score = bh_score = gh_score = 0.0
    ch_cnt = ebh_cnt = bh_cnt = gh_cnt = 0
    bad_recent_cnt = 0
    severe_bad_cnt = 0
    stale_passed_cnt = 0
    bad_newest_hours = 9999.0
    bull_newest_hours = 9999.0

    for cand in raw_candidates[:20]:
        raw_title = cand["raw_title"]
        raw_link = cand["raw_link"]
        pub_dt = cand["pub_dt"]
        age_h = cand["age_h"]
        src_tag = cand["src_tag"]
        tl = raw_title.lower()

        # 오탐 방지 문구("no orders were stopped", "reaffirms", "lifts clinical hold", "denies [FTC's] injunction" 등) 확인
        is_fp_relief = _any_kw(tl, ncfg["bad_false_positive"]) or bool(
            re.search(
                r"\bdenies\s+(?:[a-z0-9'\-]+\s+){1,2}(?:injunction|class action|class certification|bid protest|gao protest)\b",
                tl,
            )
        )

        severe_court_bad = bool(
            re.search(
                r"\bdenies\s+(?:[a-z0-9'\-]+\s+){0,2}(?:motion to dismiss|approval)\b",
                tl,
            )
        )
        severe_hit = _any_kw(tl, ncfg["bad_severe"]) or severe_court_bad
        strict_hit = _any_kw(tl, ncfg["bad_strict"]) or _any_kw(tl, ncfg["cut_bearish"])
        # 만약 "crashes" / "plunges" / "52-week low" / "halts" / "denies approval" / "denies motion to dismiss"가 명시된 경우 중대 악재 유지
        hard_crash = severe_court_bad or any(
            _kw_match(tl, k)
            for k in (
                "crash", "crashes", "plunge", "plunges", "52-week low",
                "halt purchases", "halts", "denies approval", "fda denies",
                "denies motion to dismiss", "motion to dismiss denied",
            )
        )
        if is_fp_relief and not hard_crash:
            severe_hit = False
            strict_hit = False

        bad_hit = severe_hit or strict_hit

        # 계약/수주 호재 판별: 확정적 수주 구문(contract_strong)이거나,
        # 일반 계약 단어(contract_context) + 수주 동사/규모(contract_action_verbs 또는 $)가 함께 있을 때만 인정
        legal_bull_relief = bool(
            re.search(
                r"\bdenies\s+(?:[a-z0-9'\-]+\s+){0,2}(?:injunction|preliminary injunction|bid protest|gao protest)\b",
                tl,
            )
        )
        c_strong = _any_kw(tl, ncfg["contract_strong"]) or legal_bull_relief
        c_ctx = _any_kw(tl, ncfg["contract_context"]) and (
            _any_kw(tl, ncfg["contract_action_verbs"]) or ("$" in tl)
        )
        c_hit = c_strong or c_ctx
        eb_hit = _any_kw(tl, ncfg["earnings_bull"]) or _any_kw(tl, ncfg["cut_bullish"])
        g_hit = _any_kw(tl, ncfg["geo"])

        # ⭐ 핵심 오분류 방지 규칙:
        # "Navy halts Aevex drone contract", "Pentagon cancels contract", "loses $650M contract" 등
        # 악재 키워드가 동시에 존재하면 계약/실적 호재(c_hit, eb_hit)에서 즉시 제외!
        if bad_hit:
            c_hit = False
            eb_hit = False

        w = _recency_weight(pub_dt)  # 48h 초과 시 w == 0.0 (과거 호재·악재 자동 패스!)
        is_stale_pass = (age_h > active_limit_h) or (w <= 0.0)

        if is_stale_pass:
            if bad_hit or c_hit or eb_hit:
                stale_passed_cnt += 1
        else:
            if c_hit:
                ch_score += 8.0 * w
                ch_cnt += 1
                bull_newest_hours = min(bull_newest_hours, age_h)
            if eb_hit:
                ebh_score += 6.0 * w
                ebh_cnt += 1
                bull_newest_hours = min(bull_newest_hours, age_h)
            if bad_hit:
                # 중대 악재(계약 중단·유증·Form 144·상폐·폭락 등)는 가중 처벌(-18점), 일반 악재는 -12점
                penalty_base = 18.0 if severe_hit else 12.0
                bh_score += penalty_base * w
                bh_cnt += 1
                bad_newest_hours = min(bad_newest_hours, age_h)
                if w >= ncfg["bad_recent_threshold"]:
                    bad_recent_cnt += 1
                    if severe_hit:
                        severe_bad_cnt += 1
            if g_hit:
                gh_score += 4.0 * w
                gh_cnt += 1

        if is_stale_pass and (bad_hit or c_hit or eb_hit):
            sentiment, badge_class = "⏭️ 과거뉴스 패스 (48h+)", "badge-indigo"
        elif severe_hit:
            sentiment, badge_class = "🚨 중대악재/경보", "badge-red"
        elif bad_hit:
            sentiment, badge_class = "🚨 악재/주의", "badge-red"
        elif c_hit:
            sentiment, badge_class = "🤝 계약/수주", "badge-green"
        elif eb_hit:
            sentiment, badge_class = "📈 실적/호재", "badge-green"
        elif g_hit:
            sentiment, badge_class = "🌍 거시 이슈", "badge-yellow"
        else:
            sentiment, badge_class = "📰 일반/중립", "badge-blue"

        age_str = f"{age_h:.0f}h 전" if age_h < 48 else f"{age_h/24.0:.1f}일 전 (패스)"
        date_display = f"{pub_dt.strftime('%m/%d %H:%M')} · {age_str} · {src_tag}"

        news_items.append({
            "title": html.escape(raw_title),
            "link": safe_url(raw_link),
            "date": html.escape(date_display),
            "sentiment": sentiment,
            "badge_class": badge_class,
        })

    # 뉴스 헤드라인 기반 실적발표일 PR / 최근 48h 실적발표 완료 자동 보강
    earn_sched = _refine_earnings_with_news(earn_sched, raw_candidates)
    earnings_info = earn_sched["info"]
    earnings_imminent = earn_sched["imminent"]
    earnings_badge = earn_sched["badge"]
    earnings_days_left = earn_sched["days_left"]

    catalyst_score = ch_score + ebh_score - bh_score - gh_score
    if earnings_imminent:
        catalyst_score -= 5

    llm_insight = ""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if use_llm and api_key and news_items:
        try:
            headlines_txt = "\n".join(f"- {n['title']}" for n in news_items[:5])
            resp = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini",
                      "messages": [{"role": "system", "content": "미국 주식 애널리스트로서 헤드라인을 보고 핵심 호악재를 한국어 1문장(60자 이내)으로 요약하세요."},
                                   {"role": "user", "content": f"종목: {ticker}\n헤드라인:\n{headlines_txt}"}],
                      "max_tokens": 90, "temperature": 0.2},
                timeout=4)
            if resp.status_code == 200:
                llm_insight = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    catalyst_summary = []
    if earnings_imminent:
        catalyst_summary.append(f"{earnings_info} — 어닝 변동성 주의 (선취매 비중 50% 이하 권장)")
    elif earnings_days_left is not None and -5 <= earnings_days_left < 0:
        catalyst_summary.append(f"{earnings_info} — 발표 직후 가이던스 및 기관 수급 방향성 주시")
    if severe_bad_cnt > 0:
        catalyst_summary.append(f"🚨 중대 악재 포착 ({severe_bad_cnt}건 / 계약중단·희석·Form144·급락 등)")
    if bad_recent_cnt > severe_bad_cnt:
        catalyst_summary.append(f"⚠️ 일반 악재 ({bad_recent_cnt - severe_bad_cnt}건 최근 48h 이내)")
    if ch_cnt > 0:
        catalyst_summary.append(f"🤝 최신 계약/수주/승인 ({ch_cnt}건 · 48h 이내)")
    if ebh_cnt > 0:
        catalyst_summary.append(f"📊 최신 실적/어닝/상향 ({ebh_cnt}건 · 48h 이내)")
    if stale_passed_cnt > 0:
        catalyst_summary.append(f"⏭️ 과거 호악재 {stale_passed_cnt}건 자동 선별 패스 (48h 경과)")
    if gh_cnt > 0:
        catalyst_summary.append(f"🌍 거시 변수 ({gh_cnt}건)")
    if llm_insight:
        catalyst_summary.append(f"🤖 LLM: {llm_insight}")
    if not catalyst_summary:
        catalyst_summary.append("최근 48h 내 특이 돌발 호악재 없음 (차트·수급 중심)")

    return {
        "macro_score": macro_score, "macro_alerts": macro_alerts,
        "earnings_info": html.escape(earnings_info), "earnings_imminent": earnings_imminent,
        "earnings_badge": earnings_badge, "earnings_days_left": earnings_days_left,
        "contract_hits": ch_cnt,
        "earnings_bull_hits": ebh_cnt,
        "bull_score": round(ch_score + ebh_score, 2),
        "bull_newest_hours": round(bull_newest_hours, 1),
        "bad_news_hits": bad_recent_cnt,
        "severe_bad_hits": severe_bad_cnt,
        "bad_news_total": bh_cnt,
        "bad_newest_hours": round(bad_newest_hours, 1),
        "geo_hits": gh_cnt,
        "catalyst_score": round(catalyst_score, 2),
        "catalyst_summary": catalyst_summary,
        "news_items": news_items,
        "tnx": tnx, "wti": wti, "vix": vix,
    }


# ==============================================================================
# 11) NOISE FILTER
# ==============================================================================
def evaluate_holding_noise_filter(ticker, hist, buy_price=0.0, qty=0.0, target_roi_pct=15.0, custom_stop_pct=7.0):
    if hist is None or hist.empty or len(hist) < 25:
        return None
    close, high, low, vol = hist['Close'], hist['High'], hist['Low'], hist['Volume']
    curr_price = safe_float(close.iloc[-1], 0.0)
    prev_price = safe_float(close.iloc[-2], curr_price)
    if curr_price <= 0:
        return None
    day_chg_pct = ((curr_price - prev_price) / prev_price) * 100.0 if prev_price > 0 else 0.0
    ema10 = safe_float(close.ewm(span=10, adjust=False).mean().iloc[-1], curr_price)
    ema20 = safe_float(close.ewm(span=20, adjust=False).mean().iloc[-1], curr_price)
    ema50 = safe_float(close.ewm(span=50, adjust=False).mean().iloc[-1], curr_price)
    ema200 = safe_float(close.ewm(span=200, adjust=False).mean().iloc[-1], ema50) if len(hist) >= 200 else ema50
    high_20 = safe_float(high.rolling(CFG["ind"]["box_period"]).max().iloc[-1], curr_price)
    low_20 = safe_float(low.rolling(CFG["ind"]["box_period"]).min().iloc[-1], curr_price)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    atr = safe_float(pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(CFG["ind"]["atr_period"]).mean().iloc[-1], curr_price * 0.03)
    if atr <= 0:
        atr = curr_price * 0.03
    atr_pct = (atr / curr_price) * 100.0
    rsi = safe_float(compute_wilder_rsi(close, CFG["ind"]["rsi_period"]).iloc[-1], 50.0)
    avg_vol = safe_float(vol.rolling(20).mean().iloc[-1], 0.0)
    curr_vol = safe_float(vol.iloc[-1], 0.0)
    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
    mkt_cap = get_market_cap(ticker)
    cap_prof = get_stock_cap_and_trailing_profile(ticker, mkt_cap, atr_pct)
    ts_core_pct = cap_prof['ts_core_pct']
    ts_tight_pct = cap_prof['ts_tight_pct']
    ncfg = CFG["noise"]
    chandelier_stop = high_20 * (1.0 - ts_core_pct / 100.0)
    noise_band_pct = round(min(ts_core_pct * 0.75, atr_pct * ncfg["band_atr_mult"]), 1)
    drawdown_from_high_pct = ((curr_price - high_20) / high_20) * 100.0 if high_20 > 0 else 0.0
    eff_buy = buy_price if buy_price > 0 else curr_price
    roi_pct = ((curr_price - eff_buy) / eff_buy) * 100.0 if eff_buy > 0 else 0.0
    hard_stop_price = max(eff_buy * (1.0 - custom_stop_pct / 100.0), chandelier_stop) if buy_price > 0 else chandelier_stop
    target_price = eff_buy * (1.0 + target_roi_pct / 100.0) if buy_price > 0 else curr_price * 1.12
    noise_used_ratio = min(100.0, max(0.0, (abs(drawdown_from_high_pct) / ts_core_pct) * 100.0)) if ts_core_pct > 0 else 0.0
    is_minor_wave = abs(day_chg_pct) <= (atr_pct * ncfg["minor_atr_mult"]) and curr_price >= chandelier_stop
    bear_confirm = 0.0
    if curr_price < ema20: bear_confirm += 2.5
    if curr_price < ema50: bear_confirm += 3.5
    if vol_ratio >= CFG["ind"]["vol_exit"] and day_chg_pct < -atr_pct: bear_confirm += 2.5
    if noise_used_ratio >= ncfg["warn_ratio"]: bear_confirm += 1.5

    if (buy_price > 0 and curr_price <= eff_buy * (1.0 - custom_stop_pct / 100.0)) or curr_price <= chandelier_stop:
        signal = SIGNAL_STOP_HIT
        wave_status = "🌊 대파도 (추세 손절선 붕괴)"
        headline = f"고점 대비 {drawdown_from_high_pct:.1f}% 하락 — 샹들리에/손절선(${hard_stop_price:,.2f}) 이탈"
        action_guide = "단순 노이즈 범위를 벗어난 구조적 이탈입니다. 원칙 손절/청산으로 계좌를 보호하십시오."
    elif bear_confirm >= ncfg["confirm_bear"]:
        signal = SIGNAL_EXIT
        wave_status = "🌊 대파도 (기관 분배·추세 붕괴 변곡점)"
        headline = f"20일(${ema20:,.2f})·50일선(${ema50:,.2f}) 이탈 (하락컨펌 {bear_confirm:.1f}점)"
        action_guide = "와인스타인 하락 변곡점이 확정되었습니다. 보유 물량의 70~100%를 즉시 현금화하십시오."
    elif (buy_price > 0 and roi_pct >= target_roi_pct) or (rsi >= CFG["ind"]["rsi_take_profit"] and curr_price >= high_20):
        signal = SIGNAL_TAKE_PROFIT
        wave_status = "🌊 상방 변곡점 (슈팅/목표 익절 도달)"
        headline = f"수익률 {roi_pct:+.1f}% | Wilder RSI {rsi:.1f} 과열권 — 분할 익절 타점"
        action_guide = f"1차 물량(30~50%)을 수익 확정하고 잔여 물량은 타이트 트레일링(-{ts_tight_pct:.1f}%)으로 추종하십시오."
    elif bear_confirm >= ncfg["confirm_watch"] or curr_price < ema20:
        signal = SIGNAL_WATCH
        wave_status = "⚠️ 중파도 (생명선 공방 / 노이즈 한계 근접)"
        headline = f"20일선(${ema20:,.2f}) 공방 | 고점 대비 {drawdown_from_high_pct:.1f}% (한계 -{ts_core_pct:.1f}%)"
        action_guide = f"아직 샹들리에 청산선(${chandelier_stop:,.2f})은 방어 중이나 종가상 이탈 시 즉시 매도 준비하십시오."
    elif curr_price >= ema20 and (curr_price < ema10 or atr_pct >= 5.0):
        signal = SIGNAL_HOLD_SHORT
        wave_status = "〰️ 잔파도 (단기 눌림목 노이즈 — 무시)"
        headline = f"10일선 눌림목이나 20일 생명선(${ema20:,.2f}) 위 건전한 소화 과정"
        action_guide = f"일일 ±{noise_band_pct:.1f}% 이내는 정상 호흡입니다. 흔들리지 말고 홀딩하되 단기 스탑(-{ts_tight_pct:.1f}%)을 유지하십시오."
    else:
        signal = SIGNAL_HOLD_LONG
        wave_status = "🌊 잔파도 무시 (완벽 정배열 순항 중)"
        headline = f"10·20·50일선 정배열 + 노이즈 허용폭(-{ts_core_pct:.1f}%) 내 안정적 추세 지속"
        action_guide = f"리버모어·미너비니의 'Sit Tight' 구간입니다. 일일 잔파도(±{atr_pct:.1f}%)에 털리지 말고 대시세를 누리십시오."

    return {"ticker": html.escape(ticker.upper()), "curr_price": curr_price, "day_chg_pct": day_chg_pct,
            "buy_price": eff_buy, "qty": qty, "roi_pct": roi_pct,
            "pnl_usd": (curr_price - eff_buy) * qty if buy_price > 0 and qty > 0 else 0.0,
            "ema10": ema10, "ema20": ema20, "ema50": ema50, "ema200": ema200,
            "high_20": high_20, "low_20": low_20, "atr": atr, "atr_pct": round(atr_pct, 1),
            "rsi": round(rsi, 1), "vol_ratio": round(vol_ratio, 1),
            "ts_core_pct": ts_core_pct, "ts_tight_pct": ts_tight_pct,
            "chandelier_stop": chandelier_stop, "hard_stop_price": hard_stop_price,
            "target_price": target_price, "noise_band_pct": noise_band_pct,
            "drawdown_from_high_pct": round(drawdown_from_high_pct, 1),
            "noise_used_ratio": round(noise_used_ratio, 1), "is_minor_wave": is_minor_wave,
            "signal": signal, "severity": SIGNAL_SEVERITY.get(signal, 0),
            "badge": SIGNAL_BADGE.get(signal, "badge-blue"),
            "wave_status": wave_status, "headline": headline,
            "action_guide": action_guide, "cap_tier": cap_prof['cap_tier']}


@st.cache_data(ttl=CFG["cache"]["noise_filter"])
def evaluate_holding_noise_filter_cached(ticker, buy_price, qty, target_roi_pct, custom_stop_pct):
    h = get_history(ticker)
    return evaluate_holding_noise_filter(ticker, h, buy_price, qty, target_roi_pct, custom_stop_pct)


# ==============================================================================
# 12) SCANNER / BACKTEST / WFA / RISK (야후 차단 시 개별 폴백 지원)
# ==============================================================================
@st.cache_data(ttl=CFG["cache"]["scanner"])
def scan_watchlist(ticker_string):
    tickers = list(dict.fromkeys(t.strip().upper() for t in ticker_string.replace(',', ' ').split() if t.strip()))
    if not tickers:
        return []
    data = None
    try:
        data = yf.download(tickers, period="3mo", group_by='ticker', threads=True, progress=False)
    except Exception:
        data = None
    signals = []
    for t in tickers:
        try:
            df = pd.DataFrame()
            if data is not None and not data.empty:
                try:
                    df = data[t].dropna() if len(tickers) > 1 else data.dropna()
                    df = _clean_tz(df)
                    rt_t = get_realtime_quote(t)
                    if rt_t and safe_float(rt_t.get("price"), 0.0) > 0:
                        df = _stitch_realtime_quote(df, rt_t)
                except Exception:
                    df = pd.DataFrame()
            if df.empty or len(df) < 20:
                df = get_history(t, period="3mo")
            if df.empty or len(df) < 20:
                continue
            close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
            curr_price = safe_float(close.iloc[-1], 0.0)
            prev_price = safe_float(close.iloc[-2], curr_price)
            if curr_price <= 0:
                continue
            change_pct = ((curr_price - prev_price) / prev_price) * 100.0 if prev_price > 0 else 0.0
            ema20 = safe_float(close.ewm(span=20, adjust=False).mean().iloc[-1], curr_price)
            box_high = safe_float(high.rolling(20).max().iloc[-1], curr_price)
            box_low = safe_float(low.rolling(20).min().iloc[-1], curr_price)
            rsi = safe_float(compute_wilder_rsi(close, 14).iloc[-1], 50.0)
            avg_vol = safe_float(vol.rolling(20).mean().iloc[-1], 0.0)
            curr_vol = safe_float(vol.iloc[-1], 0.0)
            vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            atr_val = safe_float(pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1], curr_price * 0.035)
            atr_pct = (atr_val / curr_price) * 100.0 if curr_price > 0 else 3.5
            ts_rec = round(float(np.clip(atr_pct * 2.6, 5.5, 16.5)), 1)
            action, badge = "⏸️ WAIT", "badge-blue"
            if curr_price >= box_high and vol_ratio >= 1.5:
                action, badge = "🔥 STRONG BUY", "badge-green"
            elif curr_price >= box_high:
                action, badge = "📈 BUY", "badge-green"
            elif curr_price < ema20 and rsi <= 25.0:
                # 대량 거래량(-10% 이상 급락 + 거래량 2배 이상) 동반 폭락 시 악재 점검 경고
                if change_pct <= -10.0 and vol_ratio >= 2.0:
                    action, badge = "🚨 악재점검 요망", "badge-red"
                else:
                    action, badge = "🟢 PANIC BUY", "badge-green"
            elif curr_price < ema20:
                action, badge = "⚠️ EXIT", "badge-red"
            elif curr_price > ema20:
                action, badge = "✅ HOLD", "badge-yellow"
            signals.append({"ticker": html.escape(t), "price": curr_price, "change_pct": change_pct,
                            "action": action, "badge": badge, "rsi": rsi, "vol": vol_ratio,
                            "box_high": box_high, "box_low": box_low,
                            "atr_pct": round(atr_pct, 1), "ts_rec": ts_rec, "is_buy": "BUY" in action})
        except Exception:
            pass
    po = {"🔥 STRONG BUY": 0, "🟢 PANIC BUY": 1, "📈 BUY": 2, "✅ HOLD": 3, "⏸️ WAIT": 4, "🚨 악재점검 요망": 5, "⚠️ EXIT": 6}
    signals.sort(key=lambda x: (po.get(x['action'], 99), -x['change_pct']))
    return signals


def _simulate_df(df_in, init_capital=10000.0, box_win=20, atr_mult=2.8):
    df = df_in.copy()
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['Box_High_Prev'] = df['High'].rolling(box_win).max().shift(1)
    df['Vol_MA20'] = df['Volume'].rolling(20).mean()
    df['RSI'] = compute_wilder_rsi(df['Close'], 14)
    tr1 = df['High'] - df['Low']
    tr2 = (df['High'] - df['Close'].shift(1)).abs()
    tr3 = (df['Low'] - df['Close'].shift(1)).abs()
    df['ATR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()
    df = df.dropna().copy()
    if len(df) < 15:
        return {}
    cash = init_capital
    shares = 0.0
    entry_price = 0.0
    entry_date = None
    peak_price = 0.0
    trades = []
    equity_curve = []
    for dt, row in df.iterrows():
        px = float(row['Close'])
        ema20 = float(row['EMA20'])
        ema50 = float(row['EMA50'])
        box_h = float(row['Box_High_Prev'])
        vol_r = float(row['Volume']) / float(row['Vol_MA20']) if row['Vol_MA20'] > 0 else 1.0
        rsi_v = float(row['RSI'])
        atr_v = float(row['ATR']) if row['ATR'] > 0 else px * 0.03
        atr_p = (atr_v / px) * 100.0
        ts_pct = float(np.clip(atr_p * atr_mult, 5.5, 16.0))
        if shares > 0:
            peak_price = max(peak_price, float(row['High']))
            chandelier_exit = peak_price * (1.0 - ts_pct / 100.0)
            hard_stop = entry_price * 0.93
            roi_now = ((px - entry_price) / entry_price) * 100.0
            exit_reason = None
            if px <= max(hard_stop, chandelier_exit):
                exit_reason = f"샹들리에/손절 이탈 (-{ts_pct:.1f}%)"
            elif px < ema50 and px < ema20:
                exit_reason = "20·50일선 추세 붕괴"
            elif rsi_v >= 78.0 and roi_now >= 12.0:
                exit_reason = f"RSI 과열 익절 ({rsi_v:.0f})"
            if exit_reason:
                cash = shares * px
                trades.append({"매수일": entry_date.strftime("%Y-%m-%d"), "매수가($)": round(entry_price, 2),
                               "청산일": dt.strftime("%Y-%m-%d"), "청산가($)": round(px, 2),
                               "수익률(%)": round(roi_now, 2), "청산사유": exit_reason})
                shares = 0.0
                entry_price = 0.0
                peak_price = 0.0
        else:
            breakout_buy = (px >= box_h and vol_r >= 1.25 and px > ema20)
            trend_pullback_buy = (px > ema20 and ema20 > ema50 and 40.0 <= rsi_v <= 62.0)
            panic_buy = (px < ema20 and rsi_v <= 26.0)
            if breakout_buy or trend_pullback_buy or panic_buy:
                shares = cash / px
                cash = 0.0
                entry_price = px
                entry_date = dt
                peak_price = px
        equity_curve.append({"date": dt, "strategy_eq": cash + (shares * px)})
    if shares > 0:
        last_px = float(df['Close'].iloc[-1])
        roi_now = ((last_px - entry_price) / entry_price) * 100.0
        trades.append({"매수일": entry_date.strftime("%Y-%m-%d"), "매수가($)": round(entry_price, 2),
                       "청산일": "보유중", "청산가($)": round(last_px, 2),
                       "수익률(%)": round(roi_now, 2), "청산사유": "보유중"})
    eq_df = pd.DataFrame(equity_curve).set_index("date")
    first_px = float(df['Close'].iloc[0])
    eq_df["bh_eq"] = (df['Close'] / first_px) * init_capital
    strat_ret = ((eq_df["strategy_eq"].iloc[-1] / init_capital) - 1.0) * 100.0
    bh_ret = ((eq_df["bh_eq"].iloc[-1] / init_capital) - 1.0) * 100.0
    strat_peak = eq_df["strategy_eq"].cummax()
    strat_dd = ((eq_df["strategy_eq"] - strat_peak) / strat_peak) * 100.0
    mdd_strat = float(strat_dd.min())
    bh_peak = eq_df["bh_eq"].cummax()
    bh_dd = ((eq_df["bh_eq"] - bh_peak) / bh_peak) * 100.0
    mdd_bh = float(bh_dd.min())
    wins = [t for t in trades if t["수익률(%)"] > 0]
    win_rate = (len(wins) / len(trades)) * 100.0 if trades else 0.0
    return {"eq_df": eq_df, "trades": trades, "strat_ret": round(strat_ret, 2),
            "bh_ret": round(bh_ret, 2), "mdd_strat": round(mdd_strat, 2),
            "mdd_bh": round(mdd_bh, 2), "win_rate": round(win_rate, 1),
            "total_trades": len(trades), "final_equity": round(float(eq_df["strategy_eq"].iloc[-1]), 2)}


def run_strategy_backtest(ticker, period="2y", init_capital=10000.0):
    df = get_history(ticker, period=period)
    if df.empty or len(df) < 40:
        return {}
    return _simulate_df(df, init_capital=init_capital)


def run_walk_forward(ticker, period="3y", n_splits=4, is_ratio=0.7):
    df = get_history(ticker, period=period)
    if df.empty or len(df) < 120:
        return {}
    total_len = len(df)
    fold_size = total_len // n_splits
    if fold_size < 35:
        return {}
    param_grid = [(15, 2.2), (20, 2.8), (25, 3.2)]
    folds = []
    oos_returns = []
    is_returns = []
    for i in range(n_splits):
        start_idx = i * fold_size
        end_idx = total_len if i == n_splits - 1 else (i + 1) * fold_size
        seg = df.iloc[start_idx:end_idx]
        split_pt = int(len(seg) * is_ratio)
        is_df = seg.iloc[:split_pt]
        oos_df = seg.iloc[max(0, split_pt - 25):]
        best_ret = -999.0
        best_params = (20, 2.8)
        for bw, am in param_grid:
            r_is = _simulate_df(is_df, 10000.0, box_win=bw, atr_mult=am)
            if r_is and r_is["strat_ret"] > best_ret:
                best_ret = r_is["strat_ret"]
                best_params = (bw, am)
        r_oos = _simulate_df(oos_df, 10000.0, box_win=best_params[0], atr_mult=best_params[1])
        oos_ret = r_oos.get("strat_ret", 0.0) if r_oos else 0.0
        oos_mdd = r_oos.get("mdd_strat", 0.0) if r_oos else 0.0
        is_ret = best_ret if best_ret > -900 else 0.0
        is_returns.append(is_ret)
        oos_returns.append(oos_ret)
        folds.append({"Fold": f"Fold {i+1}",
                      "IS 구간": f"{is_df.index[0].strftime('%y.%m.%d')}~{is_df.index[-1].strftime('%y.%m.%d')}",
                      "OOS 구간": f"{seg.iloc[split_pt].name.strftime('%y.%m.%d')}~{seg.index[-1].strftime('%y.%m.%d')}",
                      "최적 파라미터": f"Box={best_params[0]}일, ATR×{best_params[1]}",
                      "IS 수익률(%)": round(is_ret, 2),
                      "OOS 수익률(%)": round(oos_ret, 2),
                      "OOS MDD(%)": round(oos_mdd, 2)})
    cum_oos = 1.0
    for r in oos_returns:
        cum_oos *= (1.0 + r / 100.0)
    cum_oos_pct = (cum_oos - 1.0) * 100.0
    avg_is = float(np.mean(is_returns)) if is_returns else 0.0
    avg_oos = float(np.mean(oos_returns)) if oos_returns else 0.0
    wfe = (avg_oos / avg_is) * 100.0 if abs(avg_is) > 0.5 else 100.0
    pos_folds = sum(1 for r in oos_returns if r >= 0)
    consistency = (pos_folds / len(oos_returns)) * 100.0 if oos_returns else 0.0
    if cum_oos_pct > 0 and consistency >= 50.0:
        verdict = "✅ 강건성 통과 (ROBUST)"
    elif cum_oos_pct >= -5.0:
        verdict = "🟡 보통 (MODERATE)"
    else:
        verdict = "🔴 과최적화 주의 (OVERFIT)"
    return {"ticker": ticker, "folds": folds, "cum_oos_pct": round(cum_oos_pct, 2),
            "avg_is_pct": round(avg_is, 2), "avg_oos_pct": round(avg_oos, 2),
            "wfe": round(float(np.clip(wfe, -200.0, 250.0)), 1),
            "consistency": round(consistency, 1), "verdict": verdict}


def build_full_risk_report(holdings, benchmark="SPY"):
    if not holdings:
        return {}
    tickers = [h["ticker"].upper() for h in holdings]
    all_syms = list(dict.fromkeys(tickers + [benchmark]))
    close_dict = {}
    for s in all_syms:
        try:
            df_s = get_history(s, period="6mo")
            if not df_s.empty and len(df_s) >= 20:
                close_dict[s] = df_s["Close"].dropna()
        except Exception:
            pass
    valid_holdings = [h for h in holdings if h["ticker"].upper() in close_dict]
    if not valid_holdings:
        return {}
    prices_df = pd.DataFrame(close_dict).dropna()
    if len(prices_df) < 20:
        return {}
    rets_df = prices_df.pct_change().dropna()
    pos_values = []
    for h in valid_holdings:
        t = h["ticker"].upper()
        curr_px = float(prices_df[t].iloc[-1])
        qty = h["qty"] if h["qty"] > 0 else 10.0
        vol_i = float(rets_df[t].std() * np.sqrt(252) * 100.0)
        pos_values.append({"ticker": t, "value": curr_px * qty, "curr_price": curr_px, "qty": qty, "ann_vol": max(5.0, vol_i)})
    total_val = sum(p["value"] for p in pos_values)
    if total_val <= 0:
        return {}
    weights = np.array([p["value"] / total_val for p in pos_values])
    inv_vols = np.array([1.0 / p["ann_vol"] for p in pos_values])
    rp_weights = inv_vols / inv_vols.sum()
    port_syms = [p["ticker"] for p in pos_values]
    port_rets = (rets_df[port_syms] * weights).sum(axis=1)
    ann_vol = float(port_rets.std() * np.sqrt(252) * 100.0)
    ann_ret = float(port_rets.mean() * 252 * 100.0)
    sharpe = (ann_ret - 4.0) / ann_vol if ann_vol > 0 else 0.0
    var_95_pct = float(np.percentile(port_rets, 5) * 100.0)
    var_99_pct = float(np.percentile(port_rets, 1) * 100.0)
    tail_95 = port_rets[port_rets <= np.percentile(port_rets, 5)]
    cvar_95_pct = float(tail_95.mean() * 100.0) if len(tail_95) > 0 else var_95_pct
    beta = 1.0
    if benchmark in rets_df.columns:
        bm_rets = rets_df[benchmark]
        cov = float(np.cov(port_rets, bm_rets)[0, 1])
        bm_var = float(np.var(bm_rets))
        beta = cov / bm_var if bm_var > 0 else 1.0
    hhi = float(np.sum(weights ** 2) * 100.0)
    corr_matrix = rets_df[port_syms].corr().round(2)
    weights_table = []
    rebal_actions = []
    for p, w, rpw in zip(pos_values, weights, rp_weights):
        cur_w = round(w * 100.0, 1)
        opt_w = round(rpw * 100.0, 1)
        diff_w = round(opt_w - cur_w, 1)
        weights_table.append({"종목": p["ticker"], "평가금액($)": round(p["value"], 1),
                              "현재비중(%)": cur_w, "권장비중(역변동성%)": opt_w, "조정폭(%p)": diff_w})
        if abs(diff_w) >= 5.0:
            act = f"비중 {abs(diff_w):.1f}%p 축소 권장" if diff_w < 0 else f"비중 {abs(diff_w):.1f}%p 확대 여력"
            rebal_actions.append(f"<b>{p['ticker']}</b>: 현재 {cur_w}% → 권장 {opt_w}% ({act})")
    return {"total_val": round(total_val, 2), "ann_vol": round(ann_vol, 2),
            "sharpe": round(sharpe, 2), "beta": round(beta, 2),
            "var_95_pct": round(var_95_pct, 2), "var_95_usd": round(abs(var_95_pct / 100.0) * total_val, 2),
            "var_99_pct": round(var_99_pct, 2), "cvar_95_pct": round(cvar_95_pct, 2),
            "cvar_95_usd": round(abs(cvar_95_pct / 100.0) * total_val, 2),
            "hhi": round(hhi, 1), "corr_matrix": corr_matrix, "weights_table": weights_table,
            "rebal_actions": rebal_actions,
            "stress_5pct_usd": round(total_val * 0.05 * beta, 1),
            "stress_10pct_usd": round(total_val * 0.10 * beta, 1)}


# ==============================================================================
# 13) 12-AGENT MULTI-TEAM ENGINE & CHIEF AI MANAGER & JOURNAL BIAS ANALYZER (⭐ [17.0 NEW])
# ==============================================================================
class AgentReport:
    """개별 전문 에이전트(12개 팀 + 매매일지 팀) 표준 리포트 객체."""
    def __init__(self, name: str, score: float, status: str, summary: str, details: dict = None):
        self.name = name
        self.score = float(score)
        self.status = status
        self.summary = summary
        self.details = details or {}


class ChiefDecision:
    """[Agent 13] Chief AI Manager 최종 통합 의사결정 및 8단계 Veto 리포트 객체."""
    def __init__(
        self,
        ticker: str,
        action: str,
        score: float,
        entry_price: float,
        stop_loss: float,
        target_1: float,
        target_2: float,
        position_size: str,
        briefing: str,
        agent_reports: list,
        meta_action: str,
        meta_badge: str,
        regime: str = "NEUTRAL",
        veto_triggered: bool = False,
        veto_reason: str = "",
        weights_used: dict = None,
    ):
        self.ticker = ticker
        self.action = action
        self.score = float(score)
        self.entry_price = float(entry_price)
        self.stop_loss = float(stop_loss)
        self.target_1 = float(target_1)
        self.target_2 = float(target_2)
        self.position_size = position_size
        self.briefing = briefing
        self.agent_reports = agent_reports or []
        self.meta_action = meta_action
        self.meta_badge = meta_badge
        self.regime = regime
        self.veto_triggered = veto_triggered
        self.veto_reason = veto_reason
        self.weights_used = weights_used or {}


# ⭐ 초고속 섹터 판별 사전 (주요 110+ 종목 0ms 즉시 매핑 -> 미등록 종목만 yfinance 캐시 폴백)
KNOWN_SECTORS = {
    "NVDA": "Technology", "AMD": "Technology", "TSM": "Technology", "AVGO": "Technology",
    "ARM": "Technology", "ASML": "Technology", "QCOM": "Technology", "MU": "Technology",
    "INTC": "Technology", "MRVL": "Technology", "AMAT": "Technology", "LRCX": "Technology",
    "KLAC": "Technology", "ON": "Technology", "NXPI": "Technology", "ADI": "Technology",
    "MPWR": "Technology", "SMCI": "Technology", "AAPL": "Technology", "MSFT": "Technology",
    "ORCL": "Technology", "PLTR": "Technology", "CRWD": "Technology", "PANW": "Technology",
    "SNOW": "Technology", "PATH": "Technology", "AI": "Technology", "IONQ": "Technology",
    "RGTI": "Technology", "QBTS": "Technology", "QUBT": "Technology", "APP": "Technology",
    "MSTR": "Technology", "IREN": "Technology", "MARA": "Financial Services", "RIOT": "Financial Services",
    "CLSK": "Financial Services", "CIFR": "Technology", "HUT": "Financial Services",
    "BITF": "Financial Services", "CORZ": "Technology", "WULF": "Technology", "BTDR": "Technology",
    "COIN": "Financial Services", "HOOD": "Financial Services", "SOFI": "Financial Services",
    "UPST": "Financial Services", "AFRM": "Technology", "SQ": "Technology", "PYPL": "Financial Services",
    "GOOGL": "Communication Services", "GOOG": "Communication Services", "META": "Communication Services",
    "NFLX": "Communication Services", "DIS": "Communication Services", "RDDT": "Communication Services",
    "RBLX": "Communication Services", "BILI": "Communication Services", "BIDU": "Communication Services",
    "ASTS": "Communication Services",
    "AMZN": "Consumer Cyclical", "TSLA": "Consumer Cyclical", "BABA": "Consumer Cyclical",
    "PDD": "Consumer Cyclical", "JD": "Consumer Cyclical", "CPNG": "Consumer Cyclical",
    "SHOP": "Technology", "SE": "Consumer Cyclical", "LCID": "Consumer Cyclical",
    "RIVN": "Consumer Cyclical", "NIO": "Consumer Cyclical", "XPEV": "Consumer Cyclical",
    "LI": "Consumer Cyclical", "F": "Consumer Cyclical", "GM": "Consumer Cyclical",
    "TM": "Consumer Cyclical", "HMC": "Consumer Cyclical", "NKE": "Consumer Cyclical",
    "LULU": "Consumer Cyclical", "SBUX": "Consumer Cyclical", "MCD": "Consumer Cyclical",
    "DKNG": "Consumer Cyclical", "PENN": "Consumer Cyclical", "WYNN": "Consumer Cyclical",
    "LVS": "Consumer Cyclical", "CCL": "Consumer Cyclical", "RCL": "Consumer Cyclical",
    "NCLH": "Consumer Cyclical",
    "KO": "Consumer Defensive", "PEP": "Consumer Defensive", "PG": "Consumer Defensive",
    "WMT": "Consumer Defensive", "COST": "Consumer Defensive",
    "LLY": "Healthcare", "UNH": "Healthcare", "JNJ": "Healthcare", "PFE": "Healthcare",
    "MRK": "Healthcare", "ABBV": "Healthcare", "HIMS": "Healthcare", "NVO": "Healthcare",
    "RKLB": "Industrials", "LUNR": "Industrials", "PL": "Industrials", "BKSY": "Industrials",
    "SPIR": "Industrials", "BA": "Industrials", "RTX": "Industrials", "LMT": "Industrials",
    "GD": "Industrials", "NOC": "Industrials", "UAL": "Industrials", "DAL": "Industrials",
    "AAL": "Industrials", "LUV": "Industrials", "PLUG": "Industrials", "ENPH": "Technology",
    "SEDG": "Technology", "FCEL": "Industrials", "CHPT": "Consumer Cyclical", "BLNK": "Consumer Cyclical",
    "QS": "Consumer Cyclical",
    "XOM": "Energy", "CVX": "Energy", "OXY": "Energy", "SLB": "Energy", "HAL": "Energy", "COP": "Energy",
    "OPEN": "Real Estate",
}

CRYPTO_TICKERS = frozenset({
    "MSTR", "COIN", "MARA", "RIOT", "CLSK", "IREN", "HUT", "BITF", "CORZ",
    "WULF", "BTDR", "CIFR", "BITO", "IBIT", "FBTC", "HOOD", "CONL", "MSTU", "MSTX", "BITX",
})

SUPPLY_MAP = {
    "Technology": ["TSM", "ASML", "AMAT", "LRCX", "KLAC"],
    "Industrials": ["RTX", "LMT", "NOC", "GD", "BA"],
    "Energy": ["XLE", "CVX", "XOM", "SLB", "COP"],
    "Consumer Cyclical": ["TSLA", "GM", "F", "STLA", "HMC"],
    "Healthcare": ["JNJ", "PFE", "MRK", "LLY", "ABBV"],
    "Communication Services": ["META", "GOOGL", "NFLX", "DIS", "TMUS"],
    "Financial Services": ["JPM", "GS", "MS", "BAC", "V"],
}

POLICY_CFG = {
    "bull": (
        "deregulation", "tax cut", "tax credit", "subsidy", "stimulus", "infrastructure bill",
        "chips act", "inflation reduction act", "green energy bill", "defense budget increase",
        "defense spending", "tariff exemption", "trade deal", "rate cut", "fed cut", "dovish",
        "approved by congress", "bipartisan support", "funding bill passed", "ai regulation relaxed",
        "crypto regulation clear", "bank charter approved", "space force funding", "solar tax credit",
        "ev subsidy", "nuclear funding", "drug pricing reform eased", "doe loan",
    ),
    "bear": (
        "antitrust", "monopoly", "doj lawsuit", "ftc investigation", "strict regulation",
        "tariff", "trade war", "export ban", "sanctions", "china restriction", "entity list",
        "drug pricing cap", "medicare negotiation", "price gouging", "windfall tax", "wealth tax",
        "capital gains tax hike", "corporate tax hike", "rate hike", "hawkish", "fed hike",
        "government shutdown", "debt ceiling", "recession risk", "defense budget cut", "pentagon cut",
        "ai safety regulation strict", "crypto crackdown", "sec regulation", "section 230",
        "tiktok ban", "media regulation", "student loan", "environmental regulation", "epa rule",
    ),
    "election": (
        "presidential election", "trump", "biden", "harris", "vance", "midterm",
        "republican win", "democrat win", "swing state", "electoral vote", "primary election",
        "polling", "approval rating", "campaign", "debate",
    ),
    "sector": {
        "Technology":             (("ai regulation relaxed", "chips act", "ai act", "sovereign ai"), ("antitrust", "section 230", "tariff", "export ban", "chip ban", "entity list")),
        "Communication Services": (("media deregulation", "fcc approval"), ("section 230", "tiktok ban", "antitrust", "media regulation")),
        "Healthcare":             (("fda reform", "drug pricing reform eased", "breakthrough therapy"), ("medicare negotiation", "drug pricing cap", "price gouging", "clinical hold")),
        "Financial Services":     (("bank charter approved", "deregulation", "crypto regulation clear"), ("capital requirements", "basel iii", "dodd-frank", "fdic", "crypto crackdown")),
        "Energy":                 (("drilling permit", "green energy bill", "ira", "lng permit"), ("climate regulation", "epa rule", "windfall tax")),
        "Industrials":            (("infrastructure bill", "defense spending", "chips act", "space force funding", "pentagon contract"), ("tariff", "trade war", "defense budget cut", "pentagon cut")),
        "Consumer Cyclical":      (("ev subsidy", "tax credit", "tariff exemption"), ("tariff", "consumer protection", "nhtsa probe")),
        "Consumer Defensive":     (("food subsidy",), ("food regulation", "price cap", "tariff")),
        "Basic Materials":        (("mining permit", "critical minerals"), ("tariff", "environmental regulation")),
        "Real Estate":            (("rate cut", "housing subsidy"), ("rate hike", "housing policy", "mortgage")),
        "Utilities":              (("green energy bill", "ira", "nuclear funding", "grid investment", "ppa"), ("epa rule", "climate regulation")),
    },
}


@st.cache_data(ttl=86400)
def _get_sector(ticker: str) -> str:
    t = ticker.strip().upper()
    if t in KNOWN_SECTORS:
        return KNOWN_SECTORS[t]
    if t in CFG["trail"]["leverage_etfs"] or t in _ETF_NO_EARNINGS:
        return "ETF"
    try:
        info = yf.Ticker(t).info or {}
        return str(info.get("sector") or "").strip()
    except Exception:
        return ""


@st.cache_data(ttl=CFG["cache"]["policy"])
def _fetch_policy_news() -> list:
    items = []
    query = (
        "(president OR congress OR senate OR fed OR federal reserve OR antitrust OR regulation "
        "OR tariff OR legislation OR election) stock market when:3d"
    )
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=5)
        if r.status_code == 200 and r.content:
            for el in ET.fromstring(r.content).findall('.//item')[:35]:
                t_el, l_el, p_el = el.find('title'), el.find('link'), el.find('pubDate')
                pub_dt = None
                if p_el is not None and p_el.text:
                    try:
                        pub_dt = parsedate_to_datetime(p_el.text)
                    except Exception:
                        pass
                if pub_dt is None:
                    continue
                age = _hours_since(pub_dt)
                if age > 72:
                    continue
                items.append({
                    "title": (t_el.text or "").strip() if t_el is not None else "",
                    "link": (l_el.text or "#").strip() if l_el is not None else "#",
                    "pub": pub_dt,
                    "age": age,
                })
    except Exception as e:
        LOG.debug("Policy RSS fetch failed: %s", e)
    return items


# ------------------------------------------------------------------------------
# [Agent 1] Data Agent
# ------------------------------------------------------------------------------
def run_data_agent(ticker: str, hist: pd.DataFrame, rt_quote: dict) -> AgentReport:
    if hist is None or hist.empty or len(hist) < 25:
        return AgentReport("Data", 0, "DANGER", "차트 데이터 부족", {})
    price = safe_float((rt_quote or {}).get("price"), safe_float(hist['Close'].iloc[-1]))
    prev_close = safe_float((rt_quote or {}).get("prev_close"), safe_float(hist['Close'].iloc[-2], price))
    if price <= 0:
        return AgentReport("Data", 0, "DANGER", "시세 데이터 비정상 ($0)", {})
    src = (rt_quote or {}).get("source", "Live Sync")
    return AgentReport(
        "Data",
        25,
        "GOOD",
        f"${price:,.2f} ({src})",
        {
            "price": price,
            "prev_close": prev_close,
            "company_name": (rt_quote or {}).get("company_name", ""),
            "source": src,
            "ext_price": safe_float((rt_quote or {}).get("ext_price"), 0.0),
            "ext_label": str((rt_quote or {}).get("ext_label") or ""),
            "ext_change_pct": safe_float((rt_quote or {}).get("ext_change_pct"), 0.0),
        },
    )


# ------------------------------------------------------------------------------
# [Agent 2] Chart Agent
# ------------------------------------------------------------------------------
def run_chart_agent(
    ticker: str,
    current_price: float,
    ema10: float,
    ema20: float,
    ema50: float,
    ema200: float,
    box_high: float,
    box_low: float,
    atr: float,
    atr_pct: float,
    rsi: float,
    vol_ratio: float,
) -> AgentReport:
    score = 0
    reasons = []
    if current_price > ema20:
        score += 20
        reasons.append("20일선 상회")
    else:
        score -= 20
        reasons.append("20일선 이탈")
    if ema10 > ema20 > ema50:
        score += 30
        reasons.append("완벽 정배열")
    elif ema10 < ema20 < ema50:
        score -= 30
        reasons.append("역배열")
    if current_price >= box_high:
        score += 20
        reasons.append("20일 신고가 돌파")
    if current_price < ema200:
        score -= 15
        reasons.append("200일선 이탈")
    if rsi <= 30:
        score += 15
        reasons.append(f"과매도 RSI {rsi:.1f}")
    elif rsi >= 70:
        score -= 15
        reasons.append(f"과열 RSI {rsi:.1f}")

    score = max(-100, min(100, score))
    if current_price < ema200 and rsi <= 30:
        status = "DANGER"
        summary = f"떨어지는 칼날 (RSI {rsi:.1f} · 200일선 하회)"
    elif current_price < ema200:
        status = "BEARISH"
        summary = f"200일선 하회 (RSI {rsi:.1f})"
    elif score >= 30:
        status = "BULLISH"
        summary = f"상승 추세 ({score:+d}점 · RSI {rsi:.1f})"
    elif score <= -30:
        status = "BEARISH"
        summary = f"하락 추세 ({score:+d}점 · RSI {rsi:.1f})"
    else:
        status = "NEUTRAL"
        summary = f"혼조/박스 ({score:+d}점 · RSI {rsi:.1f})"

    return AgentReport(
        "Chart",
        score,
        status,
        summary,
        {
            "atr": atr,
            "atr_pct": atr_pct,
            "ema10": ema10,
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "support": box_low,
            "resistance": box_high,
            "rsi": rsi,
            "vol_ratio": vol_ratio,
            "reasons": reasons,
        },
    )


# ------------------------------------------------------------------------------
# [Agent 3] Macro Agent
# ------------------------------------------------------------------------------
def run_macro_agent(indices: list, cat: dict = None) -> AgentReport:
    idx = {i["name"]: i for i in (indices or [])}
    vix = safe_float((idx.get("VIX 변동성") or {}).get("price"), 18.0)
    if cat is not None:
        raw_score = int(safe_float(cat.get("macro_score"), 0))
        alerts = list(cat.get("macro_alerts") or [])
    else:
        raw_score = 0
        alerts = []
    # Scale macro_score (-40~+30 range) to (-100~+100) for Chief AI Manager
    scaled_score = max(-100, min(100, int(round(raw_score * 2.2))))
    if raw_score <= -25 or vix >= 25.0:
        regime, status = "CRISIS", "DANGER"
    elif raw_score <= -12 or vix >= 23.0:
        regime, status = "BEAR", "BEARISH"
    elif raw_score >= 12:
        regime, status = "BULL", "BULLISH"
    else:
        regime, status = "NEUTRAL", "NEUTRAL"
    return AgentReport(
        "Macro",
        scaled_score,
        status,
        f"[{regime}] 거시 {raw_score:+d}점 (VIX {vix:.1f})",
        {"regime": regime, "raw_score": raw_score, "vix": vix, "alerts": alerts},
    )


# ------------------------------------------------------------------------------
# [Agent 4] Master Agent (6대 대가 기법)
# ------------------------------------------------------------------------------
def run_master_agent(chart_r: AgentReport, pass_count: int, master_score_100: int, has_bad: bool = False) -> AgentReport:
    if chart_r.status == "DANGER" and has_bad:
        return AgentReport("Master", -80, "DANGER", "차트 붕괴 + 악재로 대가 기법 진입 차단", {"pass_count": pass_count, "master_score_100": master_score_100})
    scaled = int(round(((pass_count - 3) / 3.0) * 100))
    scaled = max(-100, min(100, scaled))
    if pass_count >= 5:
        status, summary = "BULLISH", f"👑 6대 대가 {pass_count}/6 통과 (강력 매수)"
    elif pass_count >= 4:
        status, summary = "BULLISH", f"👑 6대 대가 {pass_count}/6 통과 ({master_score_100}점)"
    elif pass_count == 3:
        status, summary = "NEUTRAL", f"👑 6대 대가 {pass_count}/6 통과 (관망)"
    else:
        status, summary = "BEARISH", f"👑 6대 대가 {pass_count}/6 통과 (부적합)"
    return AgentReport(
        "Master",
        scaled,
        status,
        summary,
        {"pass_count": pass_count, "master_score_100": master_score_100},
    )


# ------------------------------------------------------------------------------
# [Agent 5] News & Earnings Agent
# ------------------------------------------------------------------------------
def run_news_agent_from_cat(cat: dict, recovery_bonus: int = 0, bull_fade_penalty: float = 0.0) -> AgentReport:
    eff_cat = safe_float(cat.get("catalyst_score"), 0.0) - bull_fade_penalty + recovery_bonus
    score = max(-100, min(100, int(round(eff_cat * 2.5))))
    sev_cnt = int(cat.get("severe_bad_hits", 0))
    bad_cnt = int(cat.get("bad_news_hits", 0))
    bull_cnt = int(cat.get("contract_hits", 0)) + int(cat.get("earnings_bull_hits", 0))
    has_bad = (sev_cnt >= 1 or bad_cnt >= 2) and recovery_bonus == 0

    if has_bad:
        status = "DANGER"
        summary = f"🚨 중대/최신 악재 {bad_cnt}건 (매수 차단)"
    elif score >= 20 or bull_cnt >= 1:
        status = "BULLISH"
        summary = f"🤝 최신 호재 {bull_cnt}건 ({eff_cat:+.1f}점)"
    elif score <= -20 or bad_cnt >= 1:
        status = "BEARISH"
        summary = f"⚠️ 주의 뉴스 {bad_cnt}건 ({eff_cat:+.1f}점)"
    else:
        status = "NEUTRAL"
        summary = "📰 최근 48h 특이 호악재 없음"

    return AgentReport(
        "News",
        score,
        status,
        summary,
        {
            "bad_cnt": bad_cnt,
            "severe_cnt": sev_cnt,
            "bull_cnt": bull_cnt,
            "recovery_bonus": recovery_bonus,
            "earnings_info": cat.get("earnings_info", ""),
            "news_items": cat.get("news_items", []),
        },
    )


# ------------------------------------------------------------------------------
# [Agent 6] Policy Agent (정치/법안/규제/선거/관세 전담팀)
# ------------------------------------------------------------------------------
def run_policy_agent(ticker: str, raw_ticker_news: list = None) -> AgentReport:
    try:
        sector = _get_sector(ticker)
        news = list(_fetch_policy_news() or [])
        # 종목 개별 뉴스 중 정책·규제·관세 관련 헤드라인도 함께 병합 검사
        if raw_ticker_news:
            for item in raw_ticker_news[:15]:
                news.append({
                    "title": str(item.get("raw_title") or ""),
                    "link": str(item.get("raw_link") or "#"),
                    "pub": item.get("pub_dt"),
                    "age": safe_float(item.get("age_h"), 24.0),
                })

        if not news:
            return AgentReport("Policy", 0, "NEUTRAL", f"정책 중립 ({sector or '일반'})", {"sector": sector, "matched": []})

        sector_bull_kws, sector_bear_kws = (), ()
        if sector in POLICY_CFG["sector"]:
            sector_bull_kws, sector_bear_kws = POLICY_CFG["sector"][sector]

        score = 0.0
        bull_cnt, bear_cnt, election_cnt, crisis_cnt = 0, 0, 0, 0
        matched = []
        seen_p = set()
        crisis_kws = (
            "trade war", "tariff hike", "export ban", "chip ban", "antitrust lawsuit",
            "government shutdown", "debt ceiling default", "entity list", "sanctions",
        )

        for item in news:
            raw_t = str(item.get("title") or "").strip()
            if not raw_t:
                continue
            norm_k = _normalize_title(raw_t)
            if norm_k in seen_p:
                continue
            tl = raw_t.lower()
            age = safe_float(item.get("age"), 24.0)
            w = 1.15 if age <= 24 else (1.0 if age <= 48 else 0.75)

            is_bull = _any_kw(tl, POLICY_CFG["bull"]) or _any_kw(tl, sector_bull_kws)
            is_bear = _any_kw(tl, POLICY_CFG["bear"]) or _any_kw(tl, sector_bear_kws)
            is_election = _any_kw(tl, POLICY_CFG["election"])
            is_crisis = _any_kw(tl, crisis_kws)

            if is_bull and not is_bear:
                seen_p.add(norm_k)
                score += 6.0 * w
                bull_cnt += 1
                matched.append({"title": html.escape(raw_t), "link": safe_url(item.get("link", "#")), "sentiment": "🟢 정책호재", "age": age})
            elif is_bear and not is_bull:
                seen_p.add(norm_k)
                score -= 6.0 * w
                bear_cnt += 1
                matched.append({"title": html.escape(raw_t), "link": safe_url(item.get("link", "#")), "sentiment": "🔴 정책악재", "age": age})
                if is_crisis:
                    crisis_cnt += 1
            elif is_election:
                seen_p.add(norm_k)
                election_cnt += 1
                matched.append({"title": html.escape(raw_t), "link": safe_url(item.get("link", "#")), "sentiment": "🗳️ 선거이슈", "age": age})

        score_int = max(-100, min(100, int(round(score))))
        sec_label = sector or "글로벌"
        if crisis_cnt >= 2 and bear_cnt >= 4 and score_int <= -20:
            status = "DANGER"
            summary = f"🚨 정책 리스크 경보 (악재 {bear_cnt}건 · {sec_label})"
        elif score_int >= 12:
            status = "BULLISH"
            summary = f"🏛️ 정책 호재 우위 (호재 {bull_cnt}건 · {sec_label})"
        elif score_int <= -12:
            status = "BEARISH"
            summary = f"🏛️ 정책 역풍 주의 (악재 {bear_cnt}건 · {sec_label})"
        else:
            status = "NEUTRAL"
            summary = f"🏛️ 정책 중립 ({sec_label} · 호재 {bull_cnt}/악재 {bear_cnt})"

        return AgentReport(
            "Policy",
            score_int,
            status,
            summary,
            {
                "sector": sector,
                "bull_cnt": bull_cnt,
                "bear_cnt": bear_cnt,
                "election_cnt": election_cnt,
                "crisis_cnt": crisis_cnt,
                "matched": matched[:8],
            },
        )
    except Exception as e:
        LOG.debug("Policy agent error for %s: %s", ticker, e)
        return AgentReport("Policy", 0, "NEUTRAL", "🏛️ 정책 중립", {"sector": "", "matched": []})


# ------------------------------------------------------------------------------
# [Agent 7] Options Flow Agent (옵션 흐름/감마/이상 콜·풋 거래 전담)
# ------------------------------------------------------------------------------
@st.cache_data(ttl=CFG["cache"]["options_flow"])
def _get_options_flow_data(ticker: str) -> dict:
    t = ticker.strip().upper()
    if not t or any(c in t for c in ("^", "=", "-")):
        return {}
    try:
        stock = yf.Ticker(t)
        exps = stock.options
        if not exps:
            return {}
        ny_today = _ny_today_date()
        valid = []
        for e in exps[:5]:
            try:
                if (datetime.strptime(e, "%Y-%m-%d").date() - ny_today).days >= 2:
                    valid.append(e)
            except Exception:
                pass
        target = valid[0] if valid else exps[0]
        chain = stock.option_chain(target)
        calls, puts = chain.calls, chain.puts
        if (calls is None or calls.empty) and (puts is None or puts.empty):
            return {}

        c_vol = calls['volume'].fillna(0) if 'volume' in calls.columns else pd.Series(dtype="float64")
        p_vol = puts['volume'].fillna(0) if 'volume' in puts.columns else pd.Series(dtype="float64")
        c_oi = calls['openInterest'].fillna(0) if 'openInterest' in calls.columns else pd.Series(dtype="float64")
        p_oi = puts['openInterest'].fillna(0) if 'openInterest' in puts.columns else pd.Series(dtype="float64")

        cv = safe_float(c_vol.sum(), 0.0)
        pv = safe_float(p_vol.sum(), 0.0)
        coi = safe_float(c_oi.sum(), 0.0)
        poi = safe_float(p_oi.sum(), 0.0)

        cavg = safe_float(c_vol.mean(), 0.0)
        pavg = safe_float(p_vol.mean(), 0.0)
        uc = int((c_vol >= max(50.0, cavg * 3.0)).sum()) if cavg > 0 else 0
        up = int((p_vol >= max(50.0, pavg * 3.0)).sum()) if pavg > 0 else 0

        return {
            "expiry": target,
            "call_vol": int(cv),
            "put_vol": int(pv),
            "call_oi": int(coi),
            "put_oi": int(poi),
            "pc_vol_ratio": round(pv / cv, 2) if cv > 0 else 1.0,
            "pc_oi_ratio": round(poi / coi, 2) if coi > 0 else 1.0,
            "unusual_calls": uc,
            "unusual_puts": up,
        }
    except Exception:
        return {}


def run_options_agent(ticker: str, current_price: float, gex_data: dict = None) -> AgentReport:
    flow = _get_options_flow_data(ticker)
    gex = gex_data or {}
    if not flow and not gex.get("call_wall"):
        return AgentReport("Options", 0, "NEUTRAL", "옵션 데이터 없음 (기본 추세 모드)", {})

    pcv = safe_float(flow.get("pc_vol_ratio"), 1.0)
    uc = int(flow.get("unusual_calls", 0))
    up = int(flow.get("unusual_puts", 0))
    mp = safe_float(gex.get("max_pain"), 0.0)
    cw = safe_float(gex.get("call_wall"), 0.0)
    pw = safe_float(gex.get("put_wall"), 0.0)

    score, reasons = 0, []
    if pcv < 0.65:
        score += 20
        reasons.append(f"콜 거래 우위 (P/C {pcv:.2f})")
    elif pcv > 1.45:
        score -= 20
        reasons.append(f"풋 거래 우위 (P/C {pcv:.2f})")
    if uc >= 3:
        score += 15
        reasons.append(f"이상 콜 스윕 {uc}건")
    if up >= 3:
        score -= 15
        reasons.append(f"이상 풋 스윕 {up}건")

    if mp > 0 and current_price > 0:
        dist = ((current_price - mp) / current_price) * 100.0
        if dist > 6.0:
            score -= 10
            reasons.append(f"맥스페인(${mp:,.1f}) 하방 자석")
        elif dist < -6.0:
            score += 10
            reasons.append(f"맥스페인(${mp:,.1f}) 상방 자석")

    if gex.get("is_gamma_squeeze_zone"):
        score += 20
        reasons.append("감마스퀴즈 점화 구간")

    score = max(-100, min(100, score))
    if up >= 5 and pcv >= 1.35:
        status, summary = "DANGER", f"🚨 대량 풋 베팅 포착 ({up}건 · P/C {pcv:.2f})"
    elif score >= 20:
        status, summary = "BULLISH", f"🔥 콜 옵션 수급 우위 (P/C {pcv:.2f} · 이상콜 {uc}건)"
    elif score <= -20:
        status, summary = "BEARISH", f"⚠️ 풋 옵션 쏠림 (P/C {pcv:.2f} · 이상풋 {up}건)"
    else:
        status, summary = "NEUTRAL", f"💹 옵션 중립 (P/C {pcv:.2f} · 이상콜 {uc}/풋 {up})"

    details = dict(flow)
    details.update({
        "call_wall": cw,
        "put_wall": pw,
        "max_pain": mp,
        "reasons": reasons,
    })
    return AgentReport("Options", score, status, summary, details)


# ------------------------------------------------------------------------------
# [Agent 8] Onchain Agent (크립토 온체인 BTC/ETH 전담)
# ------------------------------------------------------------------------------
@st.cache_data(ttl=CFG["cache"]["onchain"])
def _fetch_crypto_onchain() -> dict:
    out = {}
    for sym, name, yh_sym in [("BTCUSDT", "BTC", "BTC-USD"), ("ETHUSDT", "ETH", "ETH-USD")]:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}", timeout=4)
            if r.status_code == 200:
                j = r.json()
                px = safe_float(j.get("lastPrice"), 0.0)
                if px > 0:
                    out[name] = {
                        "price": px,
                        "change": safe_float(j.get("priceChangePercent"), 0.0),
                        "volume": safe_float(j.get("quoteVolume"), 0.0),
                    }
                    continue
        except Exception:
            pass
        q = get_realtime_quote(yh_sym)
        if q.get("price", 0.0) > 0:
            out[name] = {
                "price": safe_float(q.get("price"), 0.0),
                "change": safe_float(q.get("change_pct"), 0.0),
                "volume": safe_float(q.get("volume"), 0.0),
            }
    return out


def run_onchain_agent(ticker: str) -> AgentReport:
    t = ticker.strip().upper()
    if t not in CRYPTO_TICKERS:
        return AgentReport("Onchain", 0, "NEUTRAL", "비크립토 종목 (가중치 자동 제외)", {"applicable": False})
    data = _fetch_crypto_onchain()
    if not data or "BTC" not in data:
        return AgentReport("Onchain", 0, "NEUTRAL", "온체인 시세 대기", {"applicable": True})

    btc = data["BTC"]
    eth = data.get("ETH", {"change": 0.0, "price": 0.0, "volume": 0.0})
    btc_chg, eth_chg = safe_float(btc.get("change")), safe_float(eth.get("change"))
    score, reasons = 0, []
    if btc_chg >= 3.0:
        score += 30
        reasons.append(f"BTC 강세 ({btc_chg:+.1f}%)")
    elif btc_chg >= 1.0:
        score += 15
        reasons.append(f"BTC 완만한 상승 ({btc_chg:+.1f}%)")
    elif btc_chg <= -3.0:
        score -= 30
        reasons.append(f"BTC 급락 ({btc_chg:+.1f}%)")
    elif btc_chg <= -1.0:
        score -= 15
        reasons.append(f"BTC 약세 ({btc_chg:+.1f}%)")

    diff = eth_chg - btc_chg
    if diff >= 2.0:
        score += 10
        reasons.append(f"ETH 상대강세 ({diff:+.1f}%p)")
    elif diff <= -2.0:
        score -= 10
        reasons.append(f"ETH 상대약세 ({diff:+.1f}%p)")

    if safe_float(btc.get("volume")) > 0:
        reasons.append(f"BTC 24h 거래대금 ${btc['volume']/1e9:.1f}B")

    score = max(-100, min(100, score))
    if btc_chg <= -8.0:
        status, summary = "DANGER", f"🚨 BTC 급락 경보 ({btc_chg:+.1f}%)"
    elif score >= 20:
        status, summary = "BULLISH", f"⛓️ 크립토 온체인 강세 (BTC {btc_chg:+.1f}%)"
    elif score <= -20:
        status, summary = "BEARISH", f"⛓️ 크립토 온체인 약세 (BTC {btc_chg:+.1f}%)"
    else:
        status, summary = "NEUTRAL", f"⛓️ BTC {btc_chg:+.1f}% / ETH {eth_chg:+.1f}%"

    return AgentReport(
        "Onchain",
        score,
        status,
        summary,
        {
            "applicable": True,
            "btc_price": btc.get("price", 0.0),
            "btc_change": btc_chg,
            "btc_volume": btc.get("volume", 0.0),
            "eth_price": eth.get("price", 0.0),
            "eth_change": eth_chg,
            "reasons": reasons,
        },
    )


# ------------------------------------------------------------------------------
# [Agent 9] Supply Chain Agent (섹터별 공급망 동반 종목 추적)
# ------------------------------------------------------------------------------
@st.cache_data(ttl=CFG["cache"]["supply"])
def _fetch_supply_basket(sector: str, exclude_ticker: str = "") -> dict:
    peers = [p for p in SUPPLY_MAP.get(sector, []) if p != exclude_ticker.upper()]
    if not peers:
        return {}
    changes = []
    with ThreadPoolExecutor(max_workers=min(5, len(peers))) as ex:
        fut_map = {ex.submit(get_realtime_quote, p): p for p in peers}
        for fut in as_completed(fut_map):
            p = fut_map[fut]
            try:
                q = fut.result() or {}
                if safe_float(q.get("price"), 0.0) > 0:
                    changes.append((p, round(safe_float(q.get("change_pct"), 0.0), 2)))
            except Exception:
                pass
    if not changes:
        return {}
    changes.sort(key=lambda x: peers.index(x[0]) if x[0] in peers else 99)
    avg = sum(c for _, c in changes) / len(changes)
    return {"sector": sector, "avg_change": round(avg, 2), "peers": changes, "count": len(changes)}


def run_supply_agent(ticker: str, sector: str = "") -> AgentReport:
    sec = sector or _get_sector(ticker)
    if not sec or sec not in SUPPLY_MAP:
        return AgentReport("Supply", 0, "NEUTRAL", f"공급망 비대상 ({sec or '일반'})", {"applicable": False})
    data = _fetch_supply_basket(sec, exclude_ticker=ticker)
    if not data:
        return AgentReport("Supply", 0, "NEUTRAL", f"{sec} 공급망 보합", {"applicable": False})

    avg = safe_float(data.get("avg_change"), 0.0)
    score = int(round(np.clip(avg * 12.0, -100.0, 100.0)))
    if avg <= -4.0:
        status, summary = "DANGER", f"🚨 {sec} 공급망 급락 ({avg:+.1f}%)"
    elif avg >= 1.5:
        status, summary = "BULLISH", f"🏭 {sec} 공급망 순풍 ({avg:+.1f}%)"
    elif avg <= -1.5:
        status, summary = "BEARISH", f"🏭 {sec} 공급망 역풍 ({avg:+.1f}%)"
    else:
        status, summary = "NEUTRAL", f"🏭 {sec} 공급망 보합 ({avg:+.1f}%)"

    return AgentReport(
        "Supply",
        score,
        status,
        summary,
        {
            "applicable": True,
            "sector": sec,
            "avg_change": avg,
            "peers": data.get("peers", []),
        },
    )


# ------------------------------------------------------------------------------
# [Agent 10] Squeeze Agent (숏스퀴즈 + 감마스퀴즈 통합 전담)
# ------------------------------------------------------------------------------
def run_squeeze_agent_from_eval(squeeze_eval: dict, short_data: dict, gex_data: dict) -> AgentReport:
    sq_score = int(squeeze_eval.get("sq_score", 0))
    if sq_score >= 70:
        status = "BULLISH"
        summary = f"🌋 더블 스퀴즈 경보 ({sq_score}/100점)"
    elif sq_score >= 40:
        status = "BULLISH"
        summary = f"⚡ 스퀴즈 잠재력 우수 ({sq_score}/100점)"
    else:
        status = "NEUTRAL"
        summary = f"⚖️ 일반 수급 ({sq_score}/100점)"
    return AgentReport(
        "Squeeze",
        sq_score,
        status,
        summary,
        {
            "sq_score": sq_score,
            "grade": squeeze_eval.get("grade", ""),
            "badge": squeeze_eval.get("badge", "badge-blue"),
            "guide": squeeze_eval.get("guide", ""),
            "reasons": squeeze_eval.get("reasons", []),
            "short_data": short_data,
            "gamma_data": gex_data,
        },
    )


# ------------------------------------------------------------------------------
# [Agent 11] Insider Agent (SEC Form 4 내부자 거래 전담)
# ------------------------------------------------------------------------------
@st.cache_data(ttl=CFG["cache"]["insider"])
def run_insider_agent(ticker: str) -> AgentReport:
    t = ticker.strip().upper()
    if not t or any(c in t for c in ("^", "=", "-")) or t in CFG["trail"]["leverage_etfs"] or t in _ETF_NO_EARNINGS:
        return AgentReport("Insider", 0, "NEUTRAL", "ETF/지수 (내부자 공시 제외)", {})

    buys, sells = [], []
    cutoff = datetime.now() - timedelta(days=90)

    # 1차: Finnhub Insider Transactions API (키 설정 시 초고속)
    if FINNHUB_KEY:
        try:
            u_in = f"https://finnhub.io/api/v1/stock/insider-transactions?symbol={urllib.parse.quote(t)}&token={FINNHUB_KEY}"
            r_in = requests.get(u_in, headers=BROWSER_HEADERS, timeout=4)
            if r_in.status_code == 200:
                rows_in = (r_in.json() or {}).get("data") or []
                for rw in rows_in[:40]:
                    dt_s = str(rw.get("transactionDate") or "")[:10]
                    try:
                        if datetime.strptime(dt_s, "%Y-%m-%d") < cutoff:
                            continue
                    except Exception:
                        pass
                    code = str(rw.get("transactionCode") or "").upper()
                    chg_sh = safe_float(rw.get("change"), 0.0)
                    px_sh = safe_float(rw.get("transactionPrice"), 0.0)
                    val_usd = abs(chg_sh * px_sh)
                    nm = str(rw.get("name") or "").strip()
                    if code == "P" and chg_sh > 0:
                        buys.append({"name": nm, "pos": "INSIDER", "shares": abs(chg_sh), "value": val_usd, "date": dt_s})
                    elif code == "S" and chg_sh < 0:
                        sells.append({"name": nm, "pos": "INSIDER", "shares": abs(chg_sh), "value": val_usd, "date": dt_s})
        except Exception:
            pass

    # 2차: yfinance insider_transactions
    if not buys and not sells:
        try:
            stock = yf.Ticker(t)
            insider = stock.insider_transactions
            if insider is not None and hasattr(insider, "empty") and not insider.empty:
                try:
                    if "Start Date" in insider.columns:
                        recent = insider[pd.to_datetime(insider["Start Date"], errors="coerce") >= cutoff]
                    else:
                        recent = insider
                except Exception:
                    recent = insider
                if recent is not None and not recent.empty:
                    for _, row in recent.iterrows():
                        txn = str(row.get("Transaction", "") or row.get("Text", "")).lower().strip()
                        shares = safe_float(row.get("Shares", 0))
                        value = safe_float(row.get("Value", 0))
                        insider_name = str(row.get("Insider", "")).strip()
                        pos = str(row.get("Position", "")).strip().upper()
                        date_s = str(row.get("Start Date", ""))[:10]
                        if any(k in txn for k in ("buy", "purchase", "acquire")):
                            buys.append({"name": insider_name, "pos": pos, "shares": shares, "value": value, "date": date_s})
                        elif any(k in txn for k in ("sale", "sell", "disposition")):
                            txn_clean = txn.replace(" ", "")
                            if "sale+oe" not in txn_clean and "tax" not in txn_clean:
                                sells.append({"name": insider_name, "pos": pos, "shares": shares, "value": value, "date": date_s})
        except Exception as e:
            LOG.debug("Insider fetch skipped for %s: %s", t, e)

    buy_cnt, sell_cnt = len(buys), len(sells)
    buy_val = sum(safe_float(b.get("value", 0)) for b in buys)
    sell_val = sum(safe_float(s.get("value", 0)) for s in sells)
    ceo_cfo_buys = [b for b in buys if any(k in b.get("pos", "") for k in ("CEO", "CFO", "CHIEF", "DIRECTOR", "OFFICER"))]

    if buy_cnt == 0 and sell_cnt == 0:
        return AgentReport("Insider", 0, "NEUTRAL", "최근 90일 특이 내부자 매매 없음", {"buy_cnt": 0, "sell_cnt": 0, "reasons": ["최근 90일 Form 4 특이 장내 매매 없음"]})

    score, reasons = 0, []
    if buy_cnt >= 3 and sell_cnt == 0:
        score = 40
        reasons.append(f"🔥 내부자 연속 순매수 ({buy_cnt}건 · ${buy_val/1e6:.2f}M)")
    elif buy_cnt >= 2 and buy_cnt > sell_cnt * 2:
        score = 25
        reasons.append(f"🟢 내부자 순매수 우위 (매수 {buy_cnt}건 vs 매도 {sell_cnt}건)")
    elif buy_cnt >= 1 and sell_cnt == 0:
        score = 15
        reasons.append(f"🟢 내부자 장내 매수 ({buy_cnt}건)")
    elif sell_cnt >= 6 and buy_cnt == 0 and sell_val >= 5e6:
        score = -50
        reasons.append(f"🚨 내부자 집중 매도 ({sell_cnt}건 · ${sell_val/1e6:.1f}M)")
    elif sell_cnt >= 3:
        score = -25
        reasons.append(f"🔴 내부자 매도 우위 ({sell_cnt}건 · ${sell_val/1e6:.1f}M)")
    elif sell_cnt >= 1:
        score = -10
        reasons.append(f"🟠 내부자 매도 ({sell_cnt}건)")

    if ceo_cfo_buys:
        score = min(100, score + 20)
        reasons.append(f"👑 핵심 임원(CEO/CFO/이사) 매수 {len(ceo_cfo_buys)}건")

    score = max(-100, min(100, score))
    if score <= -50:
        status, summary = "DANGER", f"🚨 내부자 대량 매도 ({sell_cnt}건 · ${sell_val/1e6:.1f}M)"
    elif score <= -20:
        status, summary = "BEARISH", f"🔴 내부자 매도 우위 (매도 {sell_cnt}건)"
    elif score >= 20:
        status, summary = "BULLISH", f"🟢 내부자 매수 포착 (매수 {buy_cnt}건)"
    else:
        status, summary = "NEUTRAL", f"🔬 내부자 매수 {buy_cnt}건 / 매도 {sell_cnt}건"

    return AgentReport(
        "Insider",
        score,
        status,
        summary,
        {
            "buy_cnt": buy_cnt,
            "sell_cnt": sell_cnt,
            "buy_value": buy_val,
            "sell_value": sell_val,
            "ceo_cfo_buys": len(ceo_cfo_buys),
            "top_buys": buys[:4],
            "top_sells": sells[:4],
            "reasons": reasons,
        },
    )


# ------------------------------------------------------------------------------
# [Agent 12] Institutional Agent (13F 메이저 기관 보유 전담)
# ------------------------------------------------------------------------------
@st.cache_data(ttl=CFG["cache"]["institutional"])
def run_institutional_agent(ticker: str) -> AgentReport:
    t = ticker.strip().upper()
    if not t or any(c in t for c in ("^", "=", "-")) or t in CFG["trail"]["leverage_etfs"] or t in _ETF_NO_EARNINGS:
        return AgentReport("Institutional", 0, "NEUTRAL", "ETF/지수 (13F 기관 집계 제외)", {})
    try:
        stock = yf.Ticker(t)
        inst = stock.institutional_holders
        if inst is None or (hasattr(inst, "empty") and inst.empty):
            return AgentReport("Institutional", 0, "NEUTRAL", "13F 기관 데이터 미제공/소형주", {})

        pct_col = None
        for c in ("% Out", "pctHeld", "pct_held", "Pct Held"):
            if c in inst.columns:
                pct_col = c
                break

        holders = []
        total_pct = 0.0
        for _, row in inst.iterrows():
            holder = str(row.get("Holder", "")).strip()
            if not holder:
                continue
            shares = safe_float(row.get("Shares", 0))
            value = safe_float(row.get("Value", 0))
            pct = 0.0
            if pct_col:
                raw = row.get(pct_col, 0)
                if isinstance(raw, str):
                    pct = safe_float(raw.replace("%", "").strip())
                else:
                    pct = safe_float(raw)
                    if 0 < pct <= 1.0:
                        pct *= 100.0
            total_pct += pct
            holders.append({"holder": holder, "shares": shares, "pct": round(pct, 2), "value": value})

        total_pct = min(100.0, round(total_pct, 2))
        major_kw = {
            "blackrock", "vanguard", "state street", "fidelity", "jpmorgan",
            "goldman", "morgan stanley", "bank of america", "wells fargo", "geode", "citadel",
        }
        has_major = any(any(m in h["holder"].lower() for m in major_kw) for h in holders[:10])

        score, reasons = 0, []
        if total_pct >= 60:
            score = 25
            reasons.append(f"🏦 상위 기관 지분율 우수 ({total_pct:.1f}%)")
        elif total_pct >= 35:
            score = 15
            reasons.append(f"🏦 상위 기관 보유 양호 ({total_pct:.1f}%)")
        elif total_pct >= 15:
            score = 5
            reasons.append(f"🏦 상위 기관 보유 적정 ({total_pct:.1f}%)")
        else:
            score = -5
            reasons.append(f"⚠️ 상위 기관 지분율 낮음 ({total_pct:.1f}%)")

        if has_major:
            score += 10
            reasons.append("🎯 블랙록·뱅가드 등 메이저 기관 편입")

        score = max(-100, min(100, score))
        if score >= 25:
            status, summary = "BULLISH", f"🏦 메이저 기관 편입 (상위10 합계 {total_pct:.1f}%)"
        elif score <= -10:
            status, summary = "BEARISH", f"⚠️ 기관 지분율 낮음 ({total_pct:.1f}%)"
        else:
            status, summary = "NEUTRAL", f"🏦 상위 기관 {total_pct:.1f}% ({len(holders)}개사)"

        return AgentReport(
            "Institutional",
            score,
            status,
            summary,
            {
                "total_pct": total_pct,
                "holder_cnt": len(holders),
                "top_holders": holders[:5],
                "has_major": has_major,
                "reasons": reasons,
            },
        )
    except Exception as e:
        LOG.debug("Institutional agent skipped for %s: %s", t, e)
        return AgentReport("Institutional", 0, "NEUTRAL", "🏦 기관 데이터 기본 모드", {})


# ------------------------------------------------------------------------------
# [Agent 13] Chief AI Manager (12개 팀 통합 & 8단계 Veto 컨트롤 타워)
# ------------------------------------------------------------------------------
def run_chief_manager(
    ticker: str,
    current_price: float,
    data_r: AgentReport,
    chart_r: AgentReport,
    macro_r: AgentReport,
    master_r: AgentReport,
    news_r: AgentReport,
    policy_r: AgentReport,
    options_r: AgentReport,
    onchain_r: AgentReport,
    supply_r: AgentReport,
    squeeze_r: AgentReport,
    insider_r: AgentReport,
    institutional_r: AgentReport,
) -> ChiefDecision:
    regime = macro_r.details.get("regime", "NEUTRAL")
    base_weights = {
        "BULL":    {"chart": 0.18, "master": 0.16, "news": 0.12, "macro": 0.08, "policy": 0.08,
                    "options": 0.08, "onchain": 0.00, "supply": 0.08, "squeeze": 0.15,
                    "insider": 0.04, "institutional": 0.03},
        "BEAR":    {"chart": 0.10, "master": 0.06, "news": 0.18, "macro": 0.15, "policy": 0.12,
                    "options": 0.05, "onchain": 0.00, "supply": 0.08, "squeeze": 0.13,
                    "insider": 0.08, "institutional": 0.05},
        "NEUTRAL": {"chart": 0.13, "master": 0.10, "news": 0.15, "macro": 0.10, "policy": 0.08,
                    "options": 0.08, "onchain": 0.00, "supply": 0.08, "squeeze": 0.15,
                    "insider": 0.08, "institutional": 0.05},
        "CRISIS":  {"chart": 0.06, "master": 0.00, "news": 0.22, "macro": 0.18, "policy": 0.15,
                    "options": 0.05, "onchain": 0.00, "supply": 0.08, "squeeze": 0.12,
                    "insider": 0.08, "institutional": 0.06},
    }
    weights = dict(base_weights.get(regime, base_weights["NEUTRAL"]))

    # 온체인: 크립토 종목일 때만 15% 활성화
    if onchain_r.details.get("applicable"):
        total_others = sum(v for k, v in weights.items() if k != "onchain" and v > 0)
        if total_others > 0:
            for k in weights:
                if k != "onchain" and weights[k] > 0:
                    weights[k] = weights[k] * 0.85 / total_others
        weights["onchain"] = 0.15

    # 공급망: 미적용 섹터는 가중치 0으로 제외 후 정규화
    if not supply_r.details.get("applicable"):
        weights["supply"] = 0.0

    total_w = sum(weights.values())
    if total_w > 0:
        weights = {k: v / total_w for k, v in weights.items()}

    # Squeeze score는 0~100 범위이므로 -20~+100 범위로 매핑하여 반영
    sq_norm = (squeeze_r.score - 25.0) * 1.33
    total = round(
        max(
            -100.0,
            min(
                100.0,
                chart_r.score * weights["chart"]
                + master_r.score * weights["master"]
                + news_r.score * weights["news"]
                + macro_r.score * weights["macro"]
                + policy_r.score * weights["policy"]
                + options_r.score * weights["options"]
                + onchain_r.score * weights["onchain"]
                + supply_r.score * weights["supply"]
                + sq_norm * weights["squeeze"]
                + insider_r.score * weights["insider"]
                + institutional_r.score * weights["institutional"],
            ),
        ),
        1,
    )

    agent_reports = [
        data_r, chart_r, macro_r, master_r, news_r, policy_r,
        options_r, onchain_r, supply_r, squeeze_r, insider_r, institutional_r,
    ]

    atr = safe_float(chart_r.details.get("atr"), current_price * 0.04)
    support = safe_float(chart_r.details.get("support"), current_price * 0.95)
    ema200 = safe_float(chart_r.details.get("ema200"), 0.0)
    sl_mult = 3.0 if regime == "BULL" else (1.0 if regime == "CRISIS" else 2.0)
    stop_loss = max(current_price - (atr * sl_mult), support * 0.98)
    target_1 = current_price + (atr * (5.0 if regime == "BULL" else 3.0))
    target_2 = current_price + (atr * (8.0 if regime == "BULL" else 5.0))

    # ===== 8단계 기관급 Veto (거부권) 우선순위 =====
    veto_Checks = [
        (data_r.status == "DANGER", "Veto #1 [Data]", f"데이터 오류: {data_r.summary}", "🚨 데이터 오류"),
        (news_r.status == "DANGER", "Veto #2 [News]", f"치명적 뉴스 악재: {news_r.summary}", "🚨 악재 투매 경보"),
        (policy_r.status == "DANGER", "Veto #3 [Policy]", f"정책/규제 경보: {policy_r.summary}", "🏛️ 정책 리스크 경보"),
        (options_r.status == "DANGER" and regime in ("BEAR", "CRISIS"), "Veto #4 [Options]", f"약세장 대량 풋 베팅: {options_r.summary}", "💹 옵션 하방 경보"),
        (onchain_r.status == "DANGER" and onchain_r.details.get("applicable"), "Veto #5 [Onchain]", f"크립토 급락 연동: {onchain_r.summary}", "⛓️ 온체인 급락 경보"),
        (supply_r.status == "DANGER" and supply_r.details.get("applicable"), "Veto #6 [Supply]", f"섹터 공급망 붕괴: {supply_r.summary}", "🏭 공급망 급락 경보"),
        (insider_r.status == "DANGER", "Veto #7 [Insider]", f"내부자 집중 매도: {insider_r.summary}", "🔬 내부자 매도 경보"),
        (current_price < ema200 and regime in ("BEAR", "CRISIS"), "Veto #8 [Tudor Jones 200MA]", "폴 튜더 존스 법칙: 약세·위기장 200일선 아래 신규 매수 금지", "🛡️ 200일선 하회 방어"),
    ]
    for cond, v_tag, v_msg, v_meta in veto_Checks:
        if cond:
            return ChiefDecision(
                ticker=ticker,
                action="🚨 NO_ENTRY (VETO)",
                score=total,
                entry_price=round(current_price, 2),
                stop_loss=round(stop_loss, 2),
                target_1=round(target_1, 2),
                target_2=round(target_2, 2),
                position_size="0% (신규 진입 차단)",
                briefing=f"🛑 [{v_tag} 발동] {v_msg}",
                agent_reports=agent_reports,
                meta_action=v_meta,
                meta_badge="badge-red",
                regime=regime,
                veto_triggered=True,
                veto_reason=f"{v_tag}: {v_msg}",
                weights_used=weights,
            )

    if total >= 45:
        action, base_pct, meta, badge = "🟢 STRONG_BUY", 25.0, "🔥 12팀 합산 강력 매수", "badge-green"
    elif total >= 20:
        action, base_pct, meta, badge = "🟡 BUY", 15.0, "📈 12팀 합산 분할 매수", "badge-green"
    elif total <= -25:
        action, base_pct, meta, badge = "🔴 EXIT", 0.0, "🚨 리스크 회피 / 비중 축소", "badge-red"
    else:
        action, base_pct, meta, badge = "⚪ WAIT", 5.0, "⏸️ 관망 / 타점 대기", "badge-blue"

    vol_pct = (atr / current_price) * 100.0 if current_price > 0 else 3.0
    pos_pct = min(base_pct, base_pct * (2.5 / max(vol_pct, 2.0))) if base_pct > 0 else 0.0
    position_size = f"계좌의 {pos_pct:.1f}%" if pos_pct > 0 else "0% (현금 관망)"

    # 조지 소로스 재료소진 익절 규칙
    if news_r.status == "BULLISH" and safe_float(chart_r.details.get("rsi"), 50.0) >= 72.0 and total >= 30:
        action, meta, badge = "🔵 TAKE_PROFIT", "🔵 소로스식 재료소진 분할익절", "badge-blue"
        position_size = "보유 물량 40~50% 분할 익절"

    # 더블 스퀴즈 점화 오버라이드
    if squeeze_r.details.get("sq_score", 0) >= 75 and news_r.status != "DANGER":
        action, meta, badge = "🌋 SQUEEZE_HOLD", "🌋 더블 스퀴즈 오버슈팅 추종", "badge-orange"
        position_size = f"보유 유지 + 코어 트레일링 ({pos_pct:.0f}% 한도)"

    briefing = (
        f"[{regime} 레짐] 12개 팀 가중합산 {total:+.1f}점 | "
        f"일일 변동성(ATR {vol_pct:.1f}%) 역비례 사이징 → 권장 비중: {position_size} "
        f"(8단계 기관 Veto 전항목 통과)"
    )
    return ChiefDecision(
        ticker=ticker,
        action=action,
        score=total,
        entry_price=round(current_price, 2),
        stop_loss=round(stop_loss, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        position_size=position_size,
        briefing=briefing,
        agent_reports=agent_reports,
        meta_action=meta,
        meta_badge=badge,
        regime=regime,
        veto_triggered=False,
        veto_reason="",
        weights_used=weights,
    )


def execute_12_agents_parallel(
    ticker: str,
    hist: pd.DataFrame,
    rt_quote: dict,
    indices: list,
    cat: dict,
    short_data: dict,
    gex_data: dict,
    squeeze_eval: dict,
    current_price: float,
    ema10: float,
    ema20: float,
    ema50: float,
    ema200: float,
    box_high: float,
    box_low: float,
    atr: float,
    atr_pct: float,
    rsi: float,
    vol_ratio: float,
    pass_count: int,
    master_score_100: int,
    has_bad: bool,
    recovery_bonus: int,
    bull_fade_penalty: float,
) -> ChiefDecision:
    """
    ⭐ [17.0] ThreadPoolExecutor 병렬 실행 엔진:
    외부 API/yfinance 호출이 필요한 에이전트들(Policy, Options Flow, Onchain, Supply, Insider, Institutional)을
    멀티스레드로 동시에 실행하여 체감 지연을 최소화합니다.
    """
    sector = _get_sector(ticker)
    raw_cand = fetch_raw_news_candidates(ticker, company_name=(rt_quote or {}).get("company_name", ""))

    data_r = run_data_agent(ticker, hist, rt_quote)
    chart_r = run_chart_agent(
        ticker, current_price, ema10, ema20, ema50, ema200,
        box_high, box_low, atr, atr_pct, rsi, vol_ratio,
    )
    macro_r = run_macro_agent(indices, cat=cat)
    master_r = run_master_agent(chart_r, pass_count, master_score_100, has_bad=has_bad)
    news_r = run_news_agent_from_cat(cat, recovery_bonus=recovery_bonus, bull_fade_penalty=bull_fade_penalty)
    squeeze_r = run_squeeze_agent_from_eval(squeeze_eval, short_data, gex_data)

    # 병렬 I/O 실행 (Policy, Options Flow, Onchain, Supply, Insider, Institutional)
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_pol = ex.submit(run_policy_agent, ticker, raw_cand)
        f_opt = ex.submit(run_options_agent, ticker, current_price, gex_data)
        f_onc = ex.submit(run_onchain_agent, ticker)
        f_sup = ex.submit(run_supply_agent, ticker, sector)
        f_ins = ex.submit(run_insider_agent, ticker)
        f_inst = ex.submit(run_institutional_agent, ticker)

        policy_r = f_pol.result()
        options_r = f_opt.result()
        onchain_r = f_onc.result()
        supply_r = f_sup.result()
        insider_r = f_ins.result()
        institutional_r = f_inst.result()

    return run_chief_manager(
        ticker, current_price,
        data_r, chart_r, macro_r, master_r, news_r, policy_r,
        options_r, onchain_r, supply_r, squeeze_r, insider_r, institutional_r,
    )


# ------------------------------------------------------------------------------
# [Journal Agent] 실전 매매일지 통계 & 8대 잘못된 매매 습관(Behavioral Biases) 진단
# ------------------------------------------------------------------------------
def analyze_trade_journal() -> AgentReport:
    """매매일지 DB를 분석하여 기법별·심리별·종목별 성과 통계 + 8대 매매 습관 편향 진단을 반환."""
    entries = db_get_journal_entries(limit=500)
    if not entries:
        return AgentReport("Journal", 0, "NEUTRAL", "매매일지 데이터 없음 (복기 기록 필요)", {
            "total": 0, "total_pnl": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
            "expectancy": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "strategy_stats": [], "emotion_stats": [], "ticker_stats": [],
            "biases": [], "signal_stats": [],
        })

    df = pd.DataFrame(entries)
    pnls = np.array([safe_float(p) for p in df["실현손익($)"].values], dtype="float64")
    total = len(pnls)
    total_pnl = float(pnls.sum())
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    win_rate = (len(wins) / total * 100.0) if total > 0 else 0.0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(abs(losses.mean())) if len(losses) > 0 else 0.0
    gross_win, gross_loss = float(wins.sum()), float(abs(losses.sum()))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    expectancy = (win_rate / 100.0) * avg_win - (1.0 - win_rate / 100.0) * avg_loss

    # 1) 6대 대가 기법별 성과
    strategy_stats = []
    for strat, group in df.groupby("적용기법"):
        g = np.array([safe_float(x) for x in group["실현손익($)"].values], dtype="float64")
        gw, gl = g[g > 0], g[g < 0]
        gwr = (len(gw) / len(g) * 100.0) if len(g) > 0 else 0.0
        gpf = (gw.sum() / abs(gl.sum())) if len(gl) > 0 and gl.sum() != 0 else (99.0 if len(gw) > 0 else 0.0)
        strategy_stats.append({
            "기법": str(strat or "기타"),
            "거래": int(len(g)),
            "승률": round(float(gwr), 1),
            "총손익": round(float(g.sum()), 2),
            "평균손익": round(float(g.mean()), 2),
            "PF": round(float(gpf), 2),
            "승": int(len(gw)),
            "패": int(len(gl)),
        })
    strategy_stats.sort(key=lambda x: -x["총손익"])

    # 2) 심리상태별 성과
    emotion_stats = []
    for emo, group in df.groupby("심리상태"):
        e = np.array([safe_float(x) for x in group["실현손익($)"].values], dtype="float64")
        ew = e[e > 0]
        ewr = (len(ew) / len(e) * 100.0) if len(e) > 0 else 0.0
        emotion_stats.append({
            "심리": str(emo or "미기록"),
            "거래": int(len(e)),
            "승률": round(float(ewr), 1),
            "총손익": round(float(e.sum()), 2),
            "평균손익": round(float(e.mean()), 2),
        })
    emotion_stats.sort(key=lambda x: -x["총손익"])

    # 3) 종목별 성과
    ticker_stats = []
    for tk, group in df.groupby("티커"):
        t_arr = np.array([safe_float(x) for x in group["실현손익($)"].values], dtype="float64")
        tw = t_arr[t_arr > 0]
        twr = (len(tw) / len(t_arr) * 100.0) if len(t_arr) > 0 else 0.0
        ticker_stats.append({
            "티커": str(tk),
            "거래": int(len(t_arr)),
            "승률": round(float(twr), 1),
            "총손익": round(float(t_arr.sum()), 2),
        })
    ticker_stats.sort(key=lambda x: -x["총손익"])

    # 4) ⚠️ 잘못된 매매 습관 자동 지적 (8대 Behavioral Biases)
    biases = []

    fomo_df = df[df["심리상태"].astype(str).str.contains("FOMO", na=False)]
    if len(fomo_df) >= 1:
        fp = np.array([safe_float(x) for x in fomo_df["실현손익($)"].values], dtype="float64")
        if fp.sum() < 0:
            biases.append({
                "level": "DANGER",
                "type": "🔥 FOMO 추격매수 손실 집중",
                "desc": f"FOMO 추격매수 {len(fp)}건 누적손익 ${fp.sum():+,.0f}. 급등 캔들 추격 진입을 중단하고 다바스 박스 돌파/눌림목 원칙만 진입하십시오.",
            })

    revenge_df = df[df["심리상태"].astype(str).str.contains("복수|뇌동", na=False, regex=True)]
    if len(revenge_df) >= 1:
        rp = np.array([safe_float(x) for x in revenge_df["실현손익($)"].values], dtype="float64")
        if rp.sum() < 0:
            biases.append({
                "level": "DANGER",
                "type": "😡 복수/뇌동매매 경보",
                "desc": f"복수·뇌동매매 {len(rp)}건 누적손익 ${rp.sum():+,.0f}. 손절 직후 당일 즉각 재진입을 금지하는 쿨다운(Cool-down) 규칙이 필요합니다.",
            })

    fear_df = df[df["심리상태"].astype(str).str.contains("공포", na=False)]
    if len(fear_df) >= 2:
        fp2 = np.array([safe_float(x) for x in fear_df["실현손익($)"].values], dtype="float64")
        if fp2.mean() < pnls.mean() * 0.7:
            biases.append({
                "level": "WARN",
                "type": "😨 공포 조기매도 (수익 단타화)",
                "desc": f"공포 상태 평균 손익 ${fp2.mean():+,.1f} (전체 평균 ${pnls.mean():+,.1f}). 잔파도 노이즈에 흔들리지 말고 샹들리에 청산선까지 홀딩하십시오.",
            })

    if len(wins) > 0 and len(losses) > 0:
        if avg_loss > avg_win * 1.3:
            biases.append({
                "level": "DANGER",
                "type": "⚖️ 손실 회피 편향 (Disposition Effect)",
                "desc": f"평균 손실(${avg_loss:,.0f})이 평균 수익(${avg_win:,.0f})의 1.3배를 초과합니다. 익절은 짧고 손절은 미루는 전형적 계좌 마모 패턴입니다.",
            })
        if profit_factor < 1.0:
            biases.append({
                "level": "DANGER",
                "type": "📉 손익비 역전 (Profit Factor < 1.0)",
                "desc": f"현재 손익비(PF) {profit_factor:.2f}. 총손실이 총수익보다 큽니다. 타이트 손절선(-7% 또는 ATR 스탑) 기계적 준수가 시급합니다.",
            })

    try:
        date_counts = df.groupby("일자").size()
        overtrade_days = date_counts[date_counts >= 3]
        if len(overtrade_days) >= 3:
            biases.append({
                "level": "WARN",
                "type": "🎰 과매매 (Overtrading)",
                "desc": f"하루 3건 이상 매매한 날이 {len(overtrade_days)}일 포착되었습니다. 매매 횟수를 줄이고 12팀 합산 45점 이상 A급 타점에만 집중하십시오.",
            })
    except Exception:
        pass

    if len(ticker_stats) >= 3 and total_pnl > 0:
        top_pnl = ticker_stats[0]["총손익"]
        if top_pnl / total_pnl > 0.8:
            biases.append({
                "level": "INFO",
                "type": f"🎯 특정 종목 편식 ({ticker_stats[0]['티커']})",
                "desc": f"전체 누적 수익의 {top_pnl/total_pnl*100:.0f}%가 {ticker_stats[0]['티커']} 한 종목에 집중되어 있습니다. 섹터 분산으로 계좌 변동성을 낮추십시오.",
            })

    if "심리상태" in df.columns:
        no_emotion = int(df["심리상태"].isna().sum() + (df["심리상태"].astype(str).str.strip() == "").sum())
        if total > 0 and no_emotion / total > 0.3:
            biases.append({
                "level": "INFO",
                "type": "📝 심리 상태 기록 누락",
                "desc": f"전체 {total}건 중 {no_emotion}건의 심리 태그가 비어 있습니다. 매매 당시 심리를 기록해야 정확한 행동재무학 교정이 가능합니다.",
            })

    if len(strategy_stats) >= 2:
        best_s = max(strategy_stats, key=lambda x: x["승률"])
        worst_s = min(strategy_stats, key=lambda x: x["승률"])
        if best_s["승률"] - worst_s["승률"] >= 20:
            biases.append({
                "level": "INFO",
                "type": "🎓 대가 기법별 승률 격차 확인",
                "desc": f"'{best_s['기법']}' 승률({best_s['승률']:.1f}%)이 '{worst_s['기법']}'({worst_s['승률']:.1f}%)보다 월등히 높습니다. 본인에게 가장 잘 맞는 '{best_s['기법']}' 비중을 확대하십시오.",
            })

    if not biases:
        biases.append({
            "level": "INFO",
            "type": "✅ 원칙 중심의 모범적 매매 습관",
            "desc": "현재 기록된 매매일지에서 치명적인 FOMO·복수매매·손실회피 편향이 발견되지 않았습니다. 현재의 손익비와 원칙을 그대로 유지하십시오!",
        })

    signal_stats = db_get_signal_stats()
    if total_pnl > 0 and profit_factor >= 1.5 and win_rate >= 50:
        score, status = 80, "BULLISH"
    elif total_pnl >= 0 and profit_factor >= 1.0:
        score, status = 55, "NEUTRAL"
    else:
        score, status = 25, "BEARISH"

    summary = (
        f"총 {total}건 | 승률 {win_rate:.1f}% | PF {profit_factor:.2f} | "
        f"누적 ${total_pnl:+,.0f} | 기대값 ${expectancy:+.1f}/건"
    )
    return AgentReport(
        name="Journal",
        score=score,
        status=status,
        summary=summary,
        details={
            "total": total,
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 1),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "strategy_stats": strategy_stats,
            "emotion_stats": emotion_stats,
            "ticker_stats": ticker_stats,
            "biases": biases,
            "signal_stats": signal_stats,
        },
    )


def render_chief_control_tower_ui(chief: ChiefDecision):
    """Tab 1에 표시되는 12대 에이전트 통합 컨트롤 타워 & 8단계 Veto 카드."""
    regime_badge_map = {
        "BULL": ("🟢 BULL (강세장 가중치)", "badge-green"),
        "NEUTRAL": ("⚖️ NEUTRAL (중립장 가중치)", "badge-indigo"),
        "BEAR": ("🟠 BEAR (약세장 방어가중치)", "badge-yellow"),
        "CRISIS": ("🚨 CRISIS (위기장 비상가중치)", "badge-red"),
    }
    reg_txt, reg_cls = regime_badge_map.get(chief.regime, ("⚖️ NEUTRAL", "badge-indigo"))
    veto_html = (
        f'<span class="badge badge-red">🛑 {html.escape(chief.veto_reason)}</span>'
        if chief.veto_triggered
        else '<span class="badge badge-teal">✅ 8단계 기관 Veto 전항목 통과</span>'
    )
    border_c = "#f43f5e" if chief.veto_triggered else ("#10b981" if chief.score >= 20 else "#38bdf8")

    icon_map = {
        "Data": "📊 데이터",
        "Chart": "📈 차트",
        "Macro": "🌍 매크로",
        "Master": "👑 6대대가",
        "News": "📰 뉴스/실적",
        "Policy": "🏛️ 정책/규제",
        "Options": "💹 옵션흐름",
        "Onchain": "⛓️ 온체인",
        "Supply": "🏭 공급망",
        "Squeeze": "🌋 스퀴즈",
        "Insider": "🔬 내부자(F4)",
        "Institutional": "🏦 기관(13F)",
    }
    st_color_map = {
        "BULLISH": "#10b981",
        "GOOD": "#10b981",
        "NEUTRAL": "#94a3b8",
        "BEARISH": "#f59e0b",
        "DANGER": "#f43f5e",
    }

    cells = []
    for rep in chief.agent_reports:
        lbl = icon_map.get(rep.name, rep.name)
        sc_col = st_color_map.get(rep.status, "#94a3b8")
        sc_str = f"{rep.score:+.0f}점" if rep.name not in ("Data", "Squeeze") else (f"{rep.score:.0f}/100" if rep.name == "Squeeze" else "LIVE")
        cells.append(f"""
        <div style="background:rgba(0,0,0,.42); border:1px solid {sc_col if rep.status=='DANGER' else 'rgba(255,255,255,.08)'}; padding:8px 9px; border-radius:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
                <span style="font-size:10px; font-weight:800; color:#e2e8f0;">{lbl}</span>
                <span class="mono" style="font-size:10px; font-weight:800; color:{sc_col};">{sc_str}</span>
            </div>
            <div style="font-size:10px; color:{sc_col}; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="{html.escape(rep.summary)}">
                {html.escape(rep.summary)}
            </div>
        </div>""")

    render_html(f"""
    <div class="chief-card" style="border-color:{border_c};">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,.12); padding-bottom:8px;">
            <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <span style="font-size:15px; font-weight:800; color:#38bdf8;">🧠 Chief AI Manager — 12대 전담팀 통합 컨트롤 타워</span>
                <span class="badge {reg_cls}">{reg_txt}</span>
            </div>
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <span class="badge {chief.meta_badge}">{html.escape(chief.action)} ({chief.score:+.1f}점)</span>
                {veto_html}
            </div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin-bottom:10px;">
            {"".join(cells)}
        </div>
        <div style="background:rgba(15,23,42,.85); border-left:4px solid {border_c}; padding:9px 13px; border-radius:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <div style="font-size:11px; color:#f8fafc; font-weight:700; line-height:1.5;">
                🎯 <b>Chief 브리핑:</b> {html.escape(chief.briefing)}
            </div>
            <div class="mono" style="font-size:11px; color:#38bdf8; font-weight:800;">
                손절 ${chief.stop_loss:,.2f} | 1차 ${chief.target_1:,.2f} | 2차 ${chief.target_2:,.2f}
            </div>
        </div>
    </div>""")

    with st.expander("🔍 12대 전문 에이전트 심층 브리핑 상세보기 (정책 · SEC 내부자 · 13F 기관 · 공급망 · 온체인 · 옵션흐름)", expanded=False):
        rep_map = {r.name: r for r in chief.agent_reports}
        pol_d = rep_map.get("Policy", AgentReport("Policy", 0, "NEUTRAL", "")).details
        ins_d = rep_map.get("Insider", AgentReport("Insider", 0, "NEUTRAL", "")).details
        inst_d = rep_map.get("Institutional", AgentReport("Institutional", 0, "NEUTRAL", "")).details
        sup_d = rep_map.get("Supply", AgentReport("Supply", 0, "NEUTRAL", "")).details
        onc_d = rep_map.get("Onchain", AgentReport("Onchain", 0, "NEUTRAL", "")).details
        opt_d = rep_map.get("Options", AgentReport("Options", 0, "NEUTRAL", "")).details

        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("##### 🏛️ [Agent 6] 정책·법안·관세·규제 (Policy)")
            st.caption(f"섹터: **{pol_d.get('sector') or '일반'}** | 정책호재 {pol_d.get('bull_cnt', 0)}건 · 정책악재 {pol_d.get('bear_cnt', 0)}건 · 선거 {pol_d.get('election_cnt', 0)}건")
            for m in (pol_d.get("matched") or [])[:4]:
                st.markdown(f"- {m['sentiment']} [{m['title']}]({m['link']}) ({m['age']:.0f}h 전)")
            if not pol_d.get("matched"):
                st.caption("• 최근 72h 내 특이 워싱턴/섹터 규제 충돌 없음")

            st.markdown("##### 🔬 [Agent 11] SEC Form 4 내부자 거래 (최근 90일)")
            st.caption(f"장내 매수 **{ins_d.get('buy_cnt', 0)}건** (${ins_d.get('buy_value', 0)/1e6:.2f}M) | 장내 매도 **{ins_d.get('sell_cnt', 0)}건** (${ins_d.get('sell_value', 0)/1e6:.2f}M)")
            for r_txt in (ins_d.get("reasons") or []):
                st.caption(f"• {r_txt}")

            st.markdown("##### 🏭 [Agent 9] 섹터 공급망 동반 모니터 (Supply)")
            if sup_d.get("applicable") and sup_d.get("peers"):
                peer_str = " · ".join(f"**{p}** ({c:+.2f}%)" for p, c in sup_d["peers"])
                st.caption(f"동반 그룹 평균 **{sup_d.get('avg_change', 0.0):+.2f}%** → {peer_str}")
            else:
                st.caption("• 개별 모멘텀 중심 종목 (공급망 바스켓 비대상)")

        with c_b:
            st.markdown("##### 🏦 [Agent 12] 13F 메이저 기관 보유 (Institutional)")
            st.caption(f"상위 기관 지분 합계: **{inst_d.get('total_pct', 0.0):.1f}%** | 메이저(블랙록/뱅가드 등) 편입: **{'예' if inst_d.get('has_major') else '미확인'}**")
            for h_item in (inst_d.get("top_holders") or [])[:4]:
                st.caption(f"• **{h_item['holder']}**: {h_item['pct']:.2f}% ({h_item['shares']:,.0f}주)")

            st.markdown("##### 💹 [Agent 7] 옵션 플로우 & 이상 스윕 (Options Flow)")
            st.caption(
                f"만기: **{opt_d.get('expiry', 'N/A')}** | P/C 거래량비: **{opt_d.get('pc_vol_ratio', 1.0):.2f}** | "
                f"이상 콜거래: **{opt_d.get('unusual_calls', 0)}건** | 이상 풋거래: **{opt_d.get('unusual_puts', 0)}건**"
            )

            st.markdown("##### ⛓️ [Agent 8] 크립토 온체인 (Onchain BTC/ETH)")
            if onc_d.get("applicable"):
                st.caption(
                    f"BTC: **${onc_d.get('btc_price', 0):,.0f}** ({onc_d.get('btc_change', 0):+.2f}%) | "
                    f"ETH: **${onc_d.get('eth_price', 0):,.0f}** ({onc_d.get('eth_change', 0):+.2f}%)"
                )
            else:
                st.caption("• 크립토 직접 연동 종목 아님 (온체인 가중치 0% 자동 제외)")


# ==============================================================================
# 14) TAB 1: 개별 종목 분석 (⭐ 실시간 시세 동기화 + [16.4] 과거 호악재 패스 & 중대악재 방어)
# ==============================================================================
def render_tab_analysis(indices, usd_krw):
    if "selected_ticker" not in st.session_state:
        st.session_state.selected_ticker = "IREN"
    c_inp, c1, c2, c3, c4, c5, c6, c_ref = st.columns([2.2, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 0.65])
    with c_inp:
        ticker_input = st.text_input("종목 코드 입력", value=st.session_state.selected_ticker,
                                     label_visibility="collapsed", placeholder="예: TSLA")
        ticker = ticker_input.upper().strip()
    chips = [(c1, "NVDA"), (c2, "TSLA"), (c3, "PLTR"), (c4, "MSTR"), (c5, "IREN"), (c6, "IONQ")]
    for col, q in chips:
        with col:
            if st.button(q, key=f"chip_{q}", use_container_width=True):
                st.session_state.selected_ticker = q
                st.rerun()
    with c_ref:
        if st.button("🔄", key="top_refresh_btn", help="실시간 시세 강제 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    if not ticker:
        return
    safe_ticker = html.escape(ticker)
    hist = get_history(ticker)
    if hist.empty or len(hist) < 25:
        st.warning(f"'{safe_ticker}' 시세 데이터를 불러오지 못했습니다. 잠시 후 다시 시도하거나 아래 캐시 초기화 버튼을 눌러주세요.")
        if st.button("🔄 캐시 초기화 & 재연결", key="retry_hist_btn"):
            st.cache_data.clear()
            st.rerun()
        return

    hist = hist.copy()
    rt_quote = get_realtime_quote(ticker)
    if rt_quote and safe_float(rt_quote.get("price"), 0.0) > 0:
        hist = _stitch_realtime_quote(hist, rt_quote)

    current_price = safe_float(hist['Close'].iloc[-1], 0.0)
    prev_close = safe_float(hist['Close'].iloc[-2], current_price)
    if rt_quote and safe_float(rt_quote.get("price"), 0.0) > 0:
        current_price = safe_float(rt_quote["price"], current_price)
        if safe_float(rt_quote.get("prev_close"), 0.0) > 0:
            prev_close = safe_float(rt_quote["prev_close"], prev_close)

    if current_price <= 0:
        st.warning(f"'{safe_ticker}' 데이터 비정상")
        return
    change = current_price - prev_close
    change_pct = (change / prev_close) * 100 if prev_close > 0 else 0.0
    last_bar_date = pd.Timestamp(hist.index[-1]).strftime("%Y-%m-%d")
    quote_src = rt_quote.get("source", "Live Sync") if rt_quote else "Daily Sync"
    comp_name = str(rt_quote.get("company_name") or "") if rt_quote else ""
    ext_px = safe_float(rt_quote.get("ext_price"), 0.0) if rt_quote else 0.0
    ext_chg = safe_float(rt_quote.get("ext_change"), 0.0) if rt_quote else 0.0
    ext_chg_pct = safe_float(rt_quote.get("ext_change_pct"), 0.0) if rt_quote else 0.0
    ext_lbl = str(rt_quote.get("ext_label") or "") if rt_quote else ""

    hist['EMA10'] = hist['Close'].ewm(span=10, adjust=False).mean()
    hist['EMA20'] = hist['Close'].ewm(span=20, adjust=False).mean()
    hist['EMA50'] = hist['Close'].ewm(span=50, adjust=False).mean()
    hist['EMA200'] = hist['Close'].ewm(span=200, adjust=False).mean()
    hist['Box_High'] = hist['High'].rolling(20).max()
    hist['Box_Low'] = hist['Low'].rolling(20).min()
    hist['BB_Mid'] = hist['Close'].rolling(20).mean()
    hist['BB_Std'] = hist['Close'].rolling(20).std().fillna(0.0)
    hist['BB_Upper'] = hist['BB_Mid'] + 2 * hist['BB_Std']
    hist['BB_Lower'] = hist['BB_Mid'] - 2 * hist['BB_Std']
    hist['Typical'] = (hist['High'] + hist['Low'] + hist['Close']) / 3
    vc = hist['Volume'].cumsum().replace(0, np.nan)
    vr5 = hist['Volume'].rolling(5).sum().replace(0, np.nan)
    hist['VWAP_Year'] = ((hist['Typical'] * hist['Volume']).cumsum() / vc).fillna(hist['Close'])
    hist['VWAP_Week'] = ((hist['Typical'] * hist['Volume']).rolling(5).sum() / vr5).fillna(hist['Close'])
    hist['Vol_MA20'] = hist['Volume'].rolling(20).mean().fillna(0.0)
    hist['RSI'] = compute_wilder_rsi(hist['Close'], 14)
    ema12 = hist['Close'].ewm(span=12, adjust=False).mean()
    ema26 = hist['Close'].ewm(span=26, adjust=False).mean()
    hist['MACD'] = ema12 - ema26
    hist['MACD_Signal'] = hist['MACD'].ewm(span=9, adjust=False).mean()
    hist['MACD_Hist'] = hist['MACD'] - hist['MACD_Signal']
    ema10 = safe_float(hist['EMA10'].iloc[-1], current_price)
    ema20 = safe_float(hist['EMA20'].iloc[-1], current_price)
    ema50 = safe_float(hist['EMA50'].iloc[-1], current_price)
    ema200 = safe_float(hist['EMA200'].iloc[-1], ema50) if len(hist) >= 200 else ema50
    box_high = safe_float(hist['Box_High'].iloc[-1], current_price)
    box_low = safe_float(hist['Box_Low'].iloc[-1], current_price)
    rsi = safe_float(hist['RSI'].iloc[-1], 50.0)
    avg_vol = safe_float(hist['Vol_MA20'].iloc[-1], 0.0)
    curr_vol = safe_float(hist['Volume'].iloc[-1], 0.0)
    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
    vwap_year_val = safe_float(hist['VWAP_Year'].iloc[-1], current_price)
    vwap_week_val = safe_float(hist['VWAP_Week'].iloc[-1], current_price)
    bb_upper_val = safe_float(hist['BB_Upper'].iloc[-1], current_price)
    bb_lower_val = safe_float(hist['BB_Lower'].iloc[-1], current_price)
    bb_mid_val = safe_float(hist['BB_Mid'].iloc[-1], current_price)
    tr1 = hist['High'] - hist['Low']
    tr2 = (hist['High'] - hist['Close'].shift(1)).abs()
    tr3 = (hist['Low'] - hist['Close'].shift(1)).abs()
    atr = safe_float(pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean().iloc[-1], current_price * 0.03)
    if atr <= 0:
        atr = current_price * 0.03
    atr_pct = (atr / current_price) * 100
    mkt_cap = get_market_cap(ticker)
    cap_profile = get_stock_cap_and_trailing_profile(ticker, mkt_cap, atr_pct)
    ts_tight_pct = cap_profile['ts_tight_pct']
    ts_core_pct = cap_profile['ts_core_pct']
    fng = get_fear_and_greed_index()
    indices_key = normalize_indices_key(indices)
    use_llm = bool(os.getenv("OPENAI_API_KEY"))
    cat = analyze_macro_and_stock_catalysts(ticker, indices_key, company_name=comp_name, use_llm=use_llm)

    # ⭐⭐⭐ [16.4] 과거 악재 가격 회복 보정 + 주가 역행(Sell-the-news) 과거 호재 자동 패스 ⭐⭐⭐
    recovery_bonus = 0
    recovery_note = ""
    bull_fade_penalty = 0.0
    catalyst_summary_display = list(cat['catalyst_summary'])
    try:
        newest_bad_h = safe_float(cat.get("bad_newest_hours", 9999.0), 9999.0)
        min_age_h = CFG["news"]["recovery_min_age_hours"]
        if (cat.get("bad_news_hits", 0) >= 1 or cat.get("bad_news_total", 0) >= 1) and newest_bad_h >= min_age_h:
            lookback_bars = max(2, min(6, int(round(newest_bad_h / 24.0)) + 1))
            if len(hist) > lookback_bars:
                ref_px = float(hist['Close'].iloc[-(lookback_bars + 1)])
                if ref_px > 0:
                    rec_pct = (current_price / ref_px - 1) * 100
                    if rec_pct >= CFG["news"]["recovery_pct_forgive"]:
                        recovery_bonus = int(CFG["news"]["recovery_bonus"])
                        recovery_note = f"과거 악재({newest_bad_h:.0f}h 전) 후 +{rec_pct:.1f}% 반등 → 악재 선반영 패스 (+{recovery_bonus}점 환급)"

        # 호재 기사가 18시간 이상 지났는데 주가가 20일선 아래에서 -2% 이상 하락 중이면 '재료 소멸(과거 호재)'로 가산점 패스
        newest_bull_h = safe_float(cat.get("bull_newest_hours", 9999.0), 9999.0)
        if cat.get("bull_score", 0.0) > 0 and newest_bull_h >= 18.0 and (current_price < ema20 and change_pct <= -2.0):
            bull_fade_penalty = float(cat.get("bull_score", 0.0))
            catalyst_summary_display.append(f"⏭️ 호재({newest_bull_h:.0f}h 전) 후 주가 역행({change_pct:+.1f}%) → 재료 소멸 패스")
    except Exception:
        pass
    if recovery_note:
        catalyst_summary_display.append(f"💡 {recovery_note}")

    # 중대 악재 1건 이상이거나 최근 48h 악재 2건 이상이면 즉시 악재 경보 발동!
    has_bad = (cat.get("severe_bad_hits", 0) >= 1 or cat.get("bad_news_hits", 0) >= 2) and recovery_bonus == 0

    noise_eval = evaluate_holding_noise_filter(ticker, hist)
    short_data = get_short_interest_data(ticker)
    gex_data = get_gamma_wall_and_gex_data(ticker, current_price)
    squeeze_eval = evaluate_squeeze_potential(short_data, gex_data, current_price, box_high, vol_ratio)
    color = "text-red" if change < 0 else "text-green"
    arrow = "▼" if change < 0 else "▲"

    is_oneil = current_price >= box_high and vol_ratio >= 1.5
    oneil_status = "EXPLOSIVE 🚀" if is_oneil else ("VOL-UP 🟢" if vol_ratio >= 1.2 else "WAIT ⚪")
    is_minervini = current_price > ema10 and ema10 > ema20 and ema20 > ema50 and current_price > ema200
    bw = (bb_upper_val - bb_lower_val) / bb_mid_val if bb_mid_val > 0 else 0.0
    bws = (hist['BB_Upper'] - hist['BB_Lower']) / hist['BB_Mid'].replace(0, np.nan)
    avg_bw = safe_float(bws.rolling(20).mean().iloc[-1], bw)
    is_vcp = bw < avg_bw * 0.95 if avg_bw > 0 else False
    minervini_status = "SEPA PASS 🟢" if is_minervini else ("VCP 수축 🟡" if is_vcp else "WAIT ⚪")
    darvas_status = "BOX BREAK 🔥" if current_price >= box_high else ("IN-BOX 🟢" if box_low <= current_price < box_high and current_price >= ema20 else "LOW-BOX 🔴")
    if current_price > ema50 and ema50 > ema200:
        weinstein_stage, weinstein_status = "2단계 상승 국면 (최적 매수)", "STAGE 2 🟢"
    elif current_price < ema50 and ema50 < ema200:
        weinstein_stage, weinstein_status = "4단계 하락 국면 (금지)", "STAGE 4 🔴"
    elif current_price > ema200 and current_price < ema50:
        weinstein_stage, weinstein_status = "3단계 천장 분배 (주의)", "STAGE 3 ⚠️"
    else:
        weinstein_stage, weinstein_status = "1단계 바닥 매집", "STAGE 1 🟡"

    # ⭐ 중대 악재(has_bad)가 있을 때는 RSI <= 25라도 PANIC BUY(공포 역발상 매수) 신호를 차단!
    is_panic = (current_price < ema20 and rsi <= 25.0) and (not has_bad)
    if current_price < ema20 and rsi <= 25.0 and has_bad:
        livermore_status = "악재투매 위험 🔴"
    elif is_panic:
        livermore_status = "PANIC BUY 🟢"
    elif current_price >= box_high:
        livermore_status = "PIVOT 돌파 🟢"
    elif rsi <= 35.0:
        livermore_status = "과매도 🟡"
    else:
        livermore_status = "NEUTRAL ⚪"

    is_tudor = current_price > ema200 and current_price > vwap_year_val
    if is_tudor and current_price > vwap_week_val:
        tudor_status = "기관수급 우위 🟢"
    elif current_price <= bb_lower_val:
        tudor_status = "BB하단 과매도 🟡"
    elif current_price < ema200:
        tudor_status = "200일선 하회 🔴"
    else:
        tudor_status = "수급 공방 ⚪"
    pass_count = sum([1 if (is_oneil or vol_ratio >= 1.2) else 0, 1 if (is_minervini or is_vcp) else 0,
                      1 if (current_price >= box_high or (box_low <= current_price < box_high and current_price >= ema20)) else 0,
                      1 if ("STAGE 2" in weinstein_status or "STAGE 1" in weinstein_status) else 0,
                      1 if (is_panic or current_price >= box_high) else 0, 1 if is_tudor else 0])
    master_score = 40 + pass_count * 10
    if is_oneil: master_score += 10
    if is_panic: master_score += 15
    if current_price < ema20 and not is_panic: master_score -= 20
    master_score = max(0, min(100, master_score))

    if has_bad and current_price < ema20:
        summoned = "👑 [리스크 관리 소환] 폴 튜더 존스 & 스탠 와인스타인"
        meta_action, meta_badge = "🚨 악재 투매 경보 — 진입 금지 (FALLING KNIFE)", "badge-red"
        meta_headline = f"최근 48h 악재 포착 + 20일선(${ema20:,.2f}) 이탈 (RSI {rsi:.1f})"
        meta_desc = "계약 중단·희석·하향 등 펀더멘털 악재가 동반된 하락입니다. 단순 RSI 과매도 역발상 매수를 엄금합니다."
        stop_loss = current_price * 0.96
        target_1, target_2 = current_price * 1.03, current_price * 1.05
        tp1_ratio, tp2_ratio, hold_ratio = 0.80, 0.20, 0.00
        seed_alloc = "0% (신규 진입 금지)"
        sizing_rule = "신규 물타기 금지, 기술적 반등 시 현금 비중 확보"
    elif current_price >= box_high and vol_ratio >= 1.5:
        summoned = "👑 [제1명인 소환] 윌리엄 오닐 & 니콜라스 다바스"
        meta_action, meta_badge = "🔥 강력 돌파 매수 (SUPER STRONG BUY)", "badge-green"
        meta_headline = "CANSLIM 거래량 폭발 + 다바스 박스 돌파"
        meta_desc = f"20일 신고가(${box_high:,.2f}) 돌파 + 거래량 {vol_ratio:.1f}배."
        stop_loss = max(box_high * 0.96, current_price - 2 * atr)
        target_1, target_2 = current_price * 1.10, current_price * 1.25
        tp1_ratio, tp2_ratio, hold_ratio = 0.30, 0.40, 0.30
        seed_alloc = "계좌의 20~25%"
        sizing_rule = "1차(30%) 익절 후 손절선을 매수 본전가(BE)로 이동"
    elif current_price >= box_high:
        summoned = "👑 [제2명인 소환] 니콜라스 다바스 & 제시 리버모어"
        meta_action, meta_badge = "📈 피봇 돌파 매수 (TREND BUY)", "badge-green"
        meta_headline = "다바스 박스권 상단 저항 돌파"
        meta_desc = "미너비니 'Sell Half' 법칙에 따라 1차 목표가에서 40% 수익 확정."
        stop_loss = current_price * 0.96
        target_1, target_2 = current_price * 1.07, current_price * 1.15
        tp1_ratio, tp2_ratio, hold_ratio = 0.40, 0.30, 0.30
        seed_alloc = "계좌의 15~20%"
        sizing_rule = "1차(40%) 익절 확정 후 잔여 물량 추세 추종"
    elif is_panic:
        summoned = "👑 [제5명인 소환] 래리 코너스 & 폴 튜더 존스"
        meta_action, meta_badge = "🟢 공포 투매 역발상 (PANIC BUY)", "badge-green"
        meta_headline = f"개별 악재 없는 기술적 과매도 클라이맥스 (RSI {rsi:.1f})"
        meta_desc = "코너스 '70:30' 익절 법칙."
        stop_loss = current_price * 0.94
        target_1, target_2 = current_price * 1.06, current_price * 1.12
        tp1_ratio, tp2_ratio, hold_ratio = 0.70, 0.30, 0.00
        seed_alloc = "계좌의 10~15%"
        sizing_rule = "1차(+6%) 70% 익절 후 30% 본전 스탑"
    elif is_minervini and current_price > ema10:
        summoned = "👑 [제3명인 소환] 마크 미너비니 & 스탠 와인스타인"
        meta_action, meta_badge = "✅ 주도주 정배열 홀딩 (STRONG HOLD)", "badge-yellow"
        meta_headline = "와인스타인 2단계 + 완벽 정배열"
        meta_desc = "1·2차 30%씩 분할 익절, 40% 코어는 20일선 이탈까지 홀딩."
        stop_loss = ema20 * 0.98
        target_1, target_2 = current_price * 1.08, current_price * 1.18
        tp1_ratio, tp2_ratio, hold_ratio = 0.30, 0.30, 0.40
        seed_alloc = "기존 물량 홀딩"
        sizing_rule = "코어 40%는 20일선 종가 이탈까지 홀딩"
    elif current_price < ema20:
        summoned = "👑 [제4명인 소환] 스탠 와인스타인 & 폴 튜더 존스"
        meta_action, meta_badge = "⚠️ 생명선 이탈 관망 (RISK OFF)", "badge-red"
        meta_headline = f"20일선(${ema20:,.2f}) 이탈 — 방어 모드"
        meta_desc = "튜더 존스 '20일선 방어' 법칙."
        stop_loss = current_price * 0.97
        target_1, target_2 = current_price * 1.03, current_price * 1.05
        tp1_ratio, tp2_ratio, hold_ratio = 0.70, 0.30, 0.00
        seed_alloc = "0% (현금 확보)"
        sizing_rule = "70% 이상 비중 축소, 반등 시 잔량 매도"
    else:
        summoned = "👑 [제6명인 소환] 존 볼린저 & 마크 미너비니"
        meta_action, meta_badge = "⏸️ 변동성 수축 관망 (VCP WAIT)", "badge-blue"
        meta_headline = "볼린저 수축 & 박스 에너지 응축"
        meta_desc = "박스 수렴 구간. 정찰병 소액 진입 후 돌파 시 확대."
        stop_loss = box_low * 0.98
        target_1, target_2 = current_price * 1.05, current_price * 1.10
        tp1_ratio, tp2_ratio, hold_ratio = 0.50, 0.30, 0.20
        seed_alloc = "계좌의 5~10%"
        sizing_rule = "박스 상단 50% 익절, 돌파 시 잔량 홀딩"

    eff_catalyst_score = cat['catalyst_score'] - bull_fade_penalty
    grand = int(np.clip(master_score + cat['macro_score'] + eff_catalyst_score + recovery_bonus + squeeze_eval['bonus'], 0, 100))
    has_macro_crisis = cat['macro_score'] <= -15

    if has_bad and current_price < ema20:
        fv_title, fv_color = "🚨 [최종 결론] 최신 중대 악재 + 추세 이탈 — 진입 금지", "#f43f5e"
        fv_summary = f"최근 48h 악재 {cat['bad_news_hits']}건(중대 {cat.get('severe_bad_hits', 0)}건) + 20일선 이탈. 역발상 물타기 중단 및 현금 수성."
    elif has_bad:
        fv_title, fv_color = "⚠️ [최종 결론] 최신 악재 경보 — 추격매수 금지·비중 축소", "#f43f5e"
        fv_summary = f"최근 48h 내 악재({cat['bad_news_hits']}건) 발생. 신규 매수 보류 및 타이트 손절선(-{ts_tight_pct:.1f}%) 엄수."
    elif has_macro_crisis and "BUY" in meta_action:
        fv_title, fv_color = "⚠️ [최종 결론] 차트 돌파지만 매크로 경보 — 시드 50% 축소", "#f59e0b"
        fv_summary = f"매크로 경보 발령. 시드 절반만 진입 + 타이트 스탑(-{ts_tight_pct:.1f}%)."
    elif cat['earnings_imminent'] and "BUY" in meta_action:
        fv_title, fv_color = f"⚡ [최종 결론] {cat['earnings_info']} — 분할 대응", "#fbbf24"
        fv_summary = "실적 직전 풀시드 금지. 선취매 50%만 유지."
    elif grand >= 75 and ("BUY" in meta_action or "HOLD" in meta_action):
        fv_title, fv_color = "🏆 [최종 결론] 매크로 안정 + 6대 대가 승인", "#10b981"
        bonus_txt = "스퀴즈 모멘텀 가세 + " if squeeze_eval['bonus'] >= 5 else ""
        rec_txt = f"[악재 소화 보정 +{recovery_bonus}] " if recovery_bonus else ""
        fv_summary = f"{rec_txt}{bonus_txt}종합 {grand}점. {seed_alloc} 진입 후 1차(${target_1:,.2f}) {int(tp1_ratio*100)}% 익절, 코어 트레일링 -{ts_core_pct:.1f}%."
    elif "PANIC" in meta_action:
        fv_title, fv_color = "🟢 [최종 결론] 극단 공포 투매 클라이맥스", "#34d399"
        fv_summary = f"최근 48h 악재 없는 기술적 과매도(RSI {rsi:.1f}). 1차 반등(${target_1:,.2f}) 시 70% 수익 확정."
    elif current_price < ema20:
        fv_title, fv_color = "🛡️ [최종 결론] 추세 약세 — 현금 확보", "#f43f5e"
        fv_summary = f"20일선(${ema20:,.2f}) 이탈. 회복 전 보수적 대응."
    else:
        fv_title, fv_color = "🧭 [최종 결론] 에너지 응축 · 추세 지속", "#38bdf8"
        fv_summary = f"종합 {grand}점. 박스 하단(${box_low:,.2f}) 방어, 상단(${box_high:,.2f}) 돌파 시 확대."

    ts_from_curr_tight = current_price * (1 - ts_tight_pct / 100)
    ts_from_curr_core = current_price * (1 - ts_core_pct / 100)
    ts_from_high_core = box_high * (1 - ts_core_pct / 100)

    rec_badge = f'<span class="badge badge-teal">💡 악재 소화 +{recovery_bonus}</span>' if recovery_bonus else ""
    ext_html = ""
    if ext_px > 0 and ext_lbl:
        ext_col = "#10b981" if ext_chg >= 0 else "#f43f5e"
        ext_sign = "+" if ext_chg >= 0 else ""
        ext_html = f'<div style="font-size:12px; font-family:\'JetBrains Mono\'; color:#cbd5e1; margin-bottom:4px;">🌙 <b>{html.escape(ext_lbl)}:</b> <span style="color:{ext_col}; font-weight:800;">${ext_px:,.2f} ({ext_sign}${ext_chg:,.2f} / {ext_chg_pct:+.2f}%)</span></div>'

    render_html(f"""
    <div class="main-hero-card">
        <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
            <span style="font-size:24px; font-weight:800; color:#fff;">{safe_ticker}</span>
            <span class="badge {cap_profile['cap_badge']}">{cap_profile['cap_tier']}</span>
            <span class="badge {meta_badge}">{meta_action.split('(')[0].strip()}</span>
            <span class="badge badge-purple">종합 {grand}점</span>
            <span class="badge {squeeze_eval['badge']}">스퀴즈 {squeeze_eval['sq_score']}점</span>
            <span class="badge badge-indigo">🕒 {html.escape(last_bar_date)} · {html.escape(quote_src)}</span>
            {rec_badge}
        </div>
        <div style="font-size:30px; font-weight:800; font-family:'JetBrains Mono'; margin:6px 0;" class="{color}">
            ${current_price:,.2f} <span style="font-size:16px;">{arrow} ${abs(change):,.2f} ({change_pct:+.2f}%)</span>
        </div>
        {ext_html}
        <div style="color:#94a3b8; font-size:12px;">
            {cap_profile['cap_desc']} | 전일종가: <b class="text-white">${prev_close:,.2f}</b> | ATR: <b class="text-white">${atr:.2f} ({atr_pct:.1f}%)</b> | 거래량: <b class="text-white">{vol_ratio:.1f}x</b> | Wilder RSI: <b class="text-white">{rsi:.1f}</b>
        </div>
    </div>""")

    mb = "".join([f"<div style='margin-bottom:2px;'>• {html.escape(m)}</div>" for m in cat['macro_alerts']])
    cb = "".join([f"<div style='margin-bottom:2px;'>• {html.escape(c)}</div>" for c in catalyst_summary_display])
    render_html(f"""
    <div class="verdict-card" style="border-color:{fv_color};">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,.12); padding-bottom:8px;">
            <span style="font-size:15px; font-weight:800; color:{fv_color};">{fv_title}</span>
            <span class="badge {cat.get('earnings_badge', 'badge-indigo')}">{cat['earnings_info']}</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:10px;">
            <div style="background:rgba(0,0,0,.4); padding:9px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.08);">
                <div style="font-size:11px; font-weight:800; color:#38bdf8; margin-bottom:4px;">🌍 ① 거시·지정학</div>
                <div style="font-size:10px; color:#cbd5e1; line-height:1.45;">{mb}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:9px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.08);">
                <div style="font-size:11px; font-weight:800; color:#a855f7; margin-bottom:4px;">🏢 ② 실적·계약·악재 (48h 선별)</div>
                <div style="font-size:10px; color:#cbd5e1; line-height:1.45;">{cb}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:9px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.08);">
                <div style="font-size:11px; font-weight:800; color:#fbbf24; margin-bottom:4px;">👑 ③ 6대 대가 + 스퀴즈</div>
                <div style="font-size:10px; color:#cbd5e1; line-height:1.45;">
                    • 6대 거장: <b class="text-white">{pass_count}/6 ({master_score}점)</b><br>
                    • 스퀴즈 가산: <b class="text-orange">+{squeeze_eval['bonus']}점</b><br>
                    • 악재 소화: <b class="text-teal">+{recovery_bonus}점</b>
                </div>
            </div>
        </div>
        <div style="background:rgba(15,23,42,.85); border-left:4px solid {fv_color}; padding:10px 14px; border-radius:8px;">
            <div style="font-size:12px; font-weight:700; color:#f8fafc; line-height:1.6;">
                💡 <b>AI 펀드매니저 지침:</b> {html.escape(fv_summary)}
            </div>
        </div>
    </div>""")

    # ⭐ [17.0] 12대 전문 에이전트 병렬 실행 & Chief AI Manager (8단계 Veto) 컨트롤 타워
    chief_decision = execute_12_agents_parallel(
        ticker=ticker,
        hist=hist,
        rt_quote=rt_quote,
        indices=indices,
        cat=cat,
        short_data=short_data,
        gex_data=gex_data,
        squeeze_eval=squeeze_eval,
        current_price=current_price,
        ema10=ema10,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        box_high=box_high,
        box_low=box_low,
        atr=atr,
        atr_pct=atr_pct,
        rsi=rsi,
        vol_ratio=vol_ratio,
        pass_count=pass_count,
        master_score_100=master_score,
        has_bad=has_bad,
        recovery_bonus=recovery_bonus,
        bull_fade_penalty=bull_fade_penalty,
    )
    render_chief_control_tower_ui(chief_decision)

    call_wall = gex_data.get("call_wall")
    put_wall = gex_data.get("put_wall")
    max_pain = gex_data.get("max_pain")
    sq_reasons_str = " / ".join(squeeze_eval["reasons"])
    render_html(f"""
    <div class="squeeze-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px; border-bottom:1px solid rgba(249,115,22,.3); padding-bottom:8px;">
            <span style="font-size:14px; font-weight:800; color:#fb923c;">🔥 숏스퀴즈 & 옵션 감마스퀴즈 레이더</span>
            <span class="badge {squeeze_eval['badge']}">{squeeze_eval['grade']} ({squeeze_eval['sq_score']}/100)</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; text-align:center; font-family:'JetBrains Mono'; margin-bottom:10px;">
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">공매도 비중</div>
                <div style="font-size:14px; font-weight:800; color:#fb923c;">{short_data['short_pct']:.1f}%</div>
                <div style="font-size:9px; color:#64748b;">20%↑ 과열</div>
            </div>
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">커버일수</div>
                <div style="font-size:14px; font-weight:800; color:#fbbf24;">{short_data['days_to_cover']:.1f}일</div>
                <div style="font-size:9px; color:#64748b;">Short Ratio</div>
            </div>
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">Call/Put OI</div>
                <div style="font-size:14px; font-weight:800; color:#38bdf8;">{gex_data['cp_oi_ratio']:.2f}x</div>
                <div style="font-size:9px; color:#64748b;">콜 우위</div>
            </div>
            <div style="background:rgba(0,0,0,.45); padding:8px 4px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">콜벽/맥스페인</div>
                <div style="font-size:13px; font-weight:800; color:#10b981;">{f'${call_wall:,.1f}' if call_wall else 'N/A'} / {f'${max_pain:,.1f}' if max_pain else 'N/A'}</div>
                <div style="font-size:9px; color:#64748b;">풋지지 {f'${put_wall:,.1f}' if put_wall else 'N/A'}</div>
            </div>
        </div>
        <div style="font-size:11px; color:#cbd5e1; line-height:1.55;">
            • <b>GEX 판정:</b> <span class="text-white">{gex_data['gex_status']}</span> ({html.escape(sq_reasons_str)})<br>
            • <b>대응:</b> {squeeze_eval['guide']}
        </div>
    </div>""")

    if noise_eval:
        nb_color = "#10b981" if noise_eval['noise_used_ratio'] < 55 else ("#f59e0b" if noise_eval['noise_used_ratio'] < 85 else "#f43f5e")
        render_html(f"""
        <div class="noise-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
                <span style="font-size:14px; font-weight:800; color:#2dd4bf;">🌊 보유주 노이즈 필터</span>
                <span class="badge {noise_eval['badge']}">{noise_eval['signal']} | {noise_eval['wave_status']}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1; margin-bottom:4px;">
                <span>20일 고점(${box_high:,.2f}) 대비: <b class="mono text-white">{noise_eval['drawdown_from_high_pct']:+.1f}%</b> (한계: <b class="mono text-yellow">-{ts_core_pct:.1f}%</b>)</span>
                <span>소진율: <b class="mono" style="color:{nb_color};">{noise_eval['noise_used_ratio']:.0f}%</b></span>
            </div>
            <div style="width:100%; height:9px; background:#090d16; border-radius:6px; overflow:hidden; margin-bottom:8px; border:1px solid #1e293b;">
                <div style="width:{min(100, max(4, noise_eval['noise_used_ratio']))}%; height:100%; background:{nb_color};"></div>
            </div>
            <div style="font-size:11px; color:#e2e8f0; line-height:1.5;">
                • <b>진단:</b> {noise_eval['headline']}<br>
                • <b>지침:</b> {noise_eval['action_guide']}
            </div>
        </div>""")

    render_html(f"""
    <div class="sentiment-card">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
            <span style="font-size:14px; font-weight:800; color:#a5b4fc;">🧭 CNN Fear & Greed Index</span>
            <span class="badge {fng['badge_cls']}">{fng['kr_label']} ({fng['score']}/100)</span>
        </div>
        <div style="width:100%; height:10px; background:#0f172a; border-radius:6px; overflow:hidden; margin-bottom:8px; border:1px solid #312e81;">
            <div style="width:{min(100, max(5, fng['score']))}%; height:100%; background:{fng['bar_color']};"></div>
        </div>
        <div style="font-size:11px; color:#e0e7ff; line-height:1.5;">• <b>코칭:</b> {fng['advice']}</div>
    </div>""")

    render_html(f"""
    <div class="master-card">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:12px; border-bottom:1px solid rgba(245,158,11,.3); padding-bottom:8px;">
            <span style="font-size:15px; font-weight:800; color:#fbbf24;">{summoned}</span>
            <span style="font-size:11px; color:#cbd5e1; background:rgba(245,158,11,.2); padding:3px 8px; border-radius:6px; font-weight:700;">{weinstein_stage}</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:12px;">
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">① 오닐</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{oneil_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">② 미너비니</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{minervini_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">③ 다바스</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{darvas_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">④ 와인스타인</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{weinstein_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">⑤ 리버모어</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{livermore_status}</div>
            </div>
            <div style="background:rgba(0,0,0,.38); padding:8px 10px; border-radius:8px; border:1px solid rgba(255,255,255,.07);">
                <div style="font-size:10px; color:#94a3b8;">⑥ 튜더존스</div>
                <div style="font-size:12px; font-weight:800; color:#f8fafc; margin-top:2px;">{tudor_status}</div>
            </div>
        </div>
        <div style="background:rgba(0,0,0,.45); border-left:3px solid #f59e0b; padding:10px 14px; border-radius:6px; margin-bottom:12px;">
            <div style="font-size:13px; font-weight:800; color:#fef08a;">{meta_headline}</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:3px; line-height:1.5;">{meta_desc}</div>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; text-align:center; font-family:'JetBrains Mono'; margin-bottom:10px;">
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px;">
                <div style="font-size:10px; color:#94a3b8;">박스 하단</div>
                <div style="font-size:13px; font-weight:800; color:#10b981;">${box_low:,.2f}</div>
            </div>
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px;">
                <div style="font-size:10px; color:#94a3b8;">타이트 손절</div>
                <div style="font-size:13px; font-weight:800; color:#f43f5e;">${stop_loss:,.2f}</div>
            </div>
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px; border:1px solid rgba(56,189,248,.25);">
                <div style="font-size:10px; color:#94a3b8;">1차({int(tp1_ratio*100)}%)</div>
                <div style="font-size:13px; font-weight:800; color:#38bdf8;">${target_1:,.2f}</div>
            </div>
            <div style="background:rgba(255,255,255,.04); padding:7px 4px; border-radius:6px; border:1px solid rgba(168,85,247,.25);">
                <div style="font-size:10px; color:#94a3b8;">2차({int(tp2_ratio*100)}%)</div>
                <div style="font-size:13px; font-weight:800; color:#a855f7;">${target_2:,.2f}</div>
            </div>
        </div>
        <div style="background:rgba(15,23,42,.75); border:1px solid rgba(245,158,11,.35); border-radius:8px; padding:9px 12px; font-size:11px;">
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px; margin-bottom:4px;">
                <span style="color:#fbbf24; font-weight:800;">⚖️ 분할: 1차({int(tp1_ratio*100)}%) : 2차({int(tp2_ratio*100)}%) : 홀딩({int(hold_ratio*100)}%)</span>
                <span style="color:#38bdf8; font-weight:700;">시드: {seed_alloc}</span>
            </div>
            <div style="color:#cbd5e1;">• <b>수칙:</b> {sizing_rule}</div>
        </div>
    </div>""")

    render_html(f"""
    <div class="trailing-card">
        <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:6px; margin-bottom:10px; border-bottom:1px solid rgba(56,189,248,.25); padding-bottom:8px;">
            <span style="font-size:14px; font-weight:800; color:#38bdf8;">🛡️ 미래에셋 트레일링 스탑</span>
            <span class="badge {cap_profile['cap_badge']}">{cap_profile['cap_tier']} | ATR {atr_pct:.1f}%</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; text-align:center;">
            <div style="background:rgba(0,0,0,.4); border:1px solid rgba(56,189,248,.3); padding:10px 6px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">① 단기</div>
                <div style="font-size:18px; font-weight:800; color:#38bdf8; font-family:'JetBrains Mono';">-{ts_tight_pct:.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">${ts_from_curr_tight:,.2f}</div>
            </div>
            <div style="background:rgba(16,185,129,.1); border:1px solid #10b981; padding:10px 6px; border-radius:8px;">
                <div style="font-size:10px; color:#34d399;">② 중기</div>
                <div style="font-size:18px; font-weight:800; color:#10b981; font-family:'JetBrains Mono';">-{ts_core_pct:.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">${ts_from_curr_core:,.2f}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); border:1px solid rgba(168,85,247,.3); padding:10px 6px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">③ 샹들리에</div>
                <div style="font-size:18px; font-weight:800; color:#c084fc; font-family:'JetBrains Mono';">${ts_from_high_core:,.2f}</div>
                <div style="font-size:10px; color:#cbd5e1;">20일 고점 대비</div>
            </div>
        </div>
    </div>""")

    with st.expander("💰 수익 & 분할익절 계산기", expanded=False):
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            buy_price = st.number_input("평단($)", value=float(round(current_price, 2)), step=0.1)
        with col_b2:
            qty = st.number_input("수량(주)", value=100.0, step=10.0)
        with col_b3:
            fee_rate = st.selectbox("수수료", options=[0.0007, 0.001, 0.0025, 0.0],
                                    format_func=lambda x: f"{x*100:.2f}%" if x > 0 else "무료", index=2)
        if buy_price > 0 and qty > 0:
            invest_usd = buy_price * qty
            current_usd = current_price * qty
            fee_usd = (invest_usd + current_usd) * fee_rate
            net_usd = (current_usd - invest_usd) - fee_usd
            net_krw = net_usd * usd_krw
            roi_pct = (net_usd / invest_usd) * 100.0
            p_color = "text-green" if net_usd >= 0 else "text-red"

            qty_tp1 = int(round(qty * tp1_ratio))
            qty_tp2 = int(round(qty * tp2_ratio))
            qty_hold = max(0, int(qty) - qty_tp1 - qty_tp2)

            p_tp1 = (target_1 - buy_price) * qty_tp1 * (1 - fee_rate)
            p_tp2 = (target_2 - buy_price) * qty_tp2 * (1 - fee_rate)

            p_tp1_color = "text-green" if p_tp1 >= 0 else "text-red"
            p_tp2_color = "text-green" if p_tp2 >= 0 else "text-red"
            p_tp1_str = f"{'+' if p_tp1>=0 else '-'}${abs(p_tp1):,.1f}"
            p_tp2_str = f"{'+' if p_tp2>=0 else '-'}${abs(p_tp2):,.1f}"

            tp1_label = "1차 익절" if target_1 > buy_price else "1차 반등축소"
            tp2_label = "2차 익절" if target_2 > buy_price else "2차 반등축소"

            render_html(f"""
            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:12px; margin-top:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:700; font-size:13px;">현재 순손익:</span>
                    <span class="{p_color} mono" style="font-size:16px; font-weight:800;">${net_usd:,.2f} ({roi_pct:+.2f}%) / {net_krw:+,.0f}원</span>
                </div>
                <hr style="margin:8px 0;">
                <div style="font-size:11px; color:#cbd5e1; line-height:1.6;">
                    • <b>{tp1_label} (${target_1:,.2f}):</b> {qty_tp1}주 → <b class="{p_tp1_color}">{p_tp1_str}</b><br>
                    • <b>{tp2_label} (${target_2:,.2f}):</b> {qty_tp2}주 → <b class="{p_tp2_color}">{p_tp2_str}</b><br>
                    • <b>코어 홀딩:</b> 잔여 {qty_hold}주 → 미래에셋 트레일링 <b>-{ts_core_pct:.1f}%</b> 설정
                </div>
            </div>""")

            b_save1, b_save2 = st.columns(2)
            with b_save1:
                if st.button("💾 보유주식 DB에 저장", use_container_width=True):
                    db_upsert_holding(ticker, buy_price, qty, 15.0, 7.0)
                    st.success(f"{ticker} 저장 완료!")
            with b_save2:
                if st.button("📓 매매일지에 기록", use_container_width=True):
                    db_add_journal_entry(datetime.now().strftime("%Y-%m-%d"), ticker, "익절/청산",
                                         current_price, qty, round(net_usd, 2),
                                         summoned.split("]")[1].strip() if "]" in summoned else "6대 대가",
                                         "원칙준수", f"평단 ${buy_price:,.2f} → ${current_price:,.2f} ({roi_pct:+.1f}%)")
                    st.success(f"{ticker} 매매일지 기록 완료! (📓 매매일지 탭에서 확인)")

    col_c1, col_c2, col_c3 = st.columns([1, 1, 1.5])
    with col_c1: show_vwap_y = st.checkbox("1년 VWAP", value=True)
    with col_c2: show_vwap_w = st.checkbox("1주 VWAP", value=False)
    with col_c3: show_gamma = st.checkbox("감마벽 라인", value=True)

    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.55, 0.15, 0.15, 0.15],
                        subplot_titles=(f"{ticker} 가격 & 추세", "거래량", "MACD", "Wilder RSI(14)"))

    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'],
                                 low=hist['Low'], close=hist['Close'],
                                 name="주가",
                                 increasing_line_color='#10b981', decreasing_line_color='#f43f5e',
                                 increasing_fillcolor='#10b981', decreasing_fillcolor='#f43f5e'), row=1, col=1)

    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA10'], name="EMA10 (단기)", line=dict(color='#38bdf8', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA20'], name="EMA20 (생명선)", line=dict(color='#fbbf24', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['EMA50'], name="EMA50 (중기)", line=dict(color='#a855f7', width=1.2, dash='dot')), row=1, col=1)

    fig.add_trace(go.Scatter(x=hist.index, y=hist['Box_High'], name="20일 고점(저항)", line=dict(color='#ef4444', width=1, dash='dash')), row=1, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['Box_Low'], name="20일 저점(지지)", line=dict(color='#10b981', width=1, dash='dash')), row=1, col=1)

    if show_vwap_y:
        fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Year'], name="1년 VWAP", line=dict(color='#f97316', width=1.2)), row=1, col=1)
    if show_vwap_w:
        fig.add_trace(go.Scatter(x=hist.index, y=hist['VWAP_Week'], name="1주 VWAP", line=dict(color='#ec4899', width=1.2)), row=1, col=1)

    if show_gamma and call_wall:
        fig.add_hline(y=call_wall, line=dict(color="#f43f5e", width=1.5, dash="dash"), row=1, col=1)
    if show_gamma and put_wall:
        fig.add_hline(y=put_wall, line=dict(color="#10b981", width=1.5, dash="dash"), row=1, col=1)

    vcolors = ['#10b981' if c >= o else '#f43f5e' for c, o in zip(hist['Close'], hist['Open'])]
    fig.add_trace(go.Bar(x=hist.index, y=hist['Volume'], name="거래량", marker_color=vcolors, opacity=0.8), row=2, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['Vol_MA20'], name="거래량 20MA", line=dict(color='#94a3b8', width=1)), row=2, col=1)

    mcolors = ['#10b981' if v >= 0 else '#f43f5e' for v in hist['MACD_Hist']]
    fig.add_trace(go.Bar(x=hist.index, y=hist['MACD_Hist'], name="MACD Hist", marker_color=mcolors), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD'], name="MACD 선", line=dict(color='#38bdf8', width=1.2)), row=3, col=1)
    fig.add_trace(go.Scatter(x=hist.index, y=hist['MACD_Signal'], name="MACD 시그널", line=dict(color='#fbbf24', width=1.2)), row=3, col=1)

    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], name="Wilder RSI", line=dict(color='#a855f7', width=1.5)), row=4, col=1)
    fig.add_hline(y=70, line=dict(color="rgba(244,63,94,0.7)", width=1, dash="dot"), row=4, col=1)
    fig.add_hline(y=30, line=dict(color="rgba(16,185,129,0.7)", width=1, dash="dot"), row=4, col=1)
    fig.add_hline(y=25, line=dict(color="#10b981", width=1.5, dash="dash"), row=4, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=680,
        margin=dict(l=30, r=30, t=50, b=20),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        paper_bgcolor="#080c14", plot_bgcolor="#080c14",
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#0f172a", font_size=11, font_family="JetBrains Mono")
    )

    fig.update_xaxes(gridcolor="#1e293b", showgrid=True)
    fig.update_yaxes(gridcolor="#1e293b", showgrid=True)
    st.plotly_chart(fig, use_container_width=True)

    render_html("""<div style="font-weight:700; color:#38bdf8; font-size:13px; margin:14px 0 8px 0;">📰 실시간 뉴스 & AI 판독 (48h 내 유효 호악재 반영 · 48h 경과 과거뉴스 자동 패스)</div>""")
    if not cat['news_items']:
        render_html("""<div style="color:#64748b; font-size:12px; padding:12px; background:#0f172a; border:1px solid #1e293b; border-radius:8px;">최근 72시간 이내 관련 뉴스가 없습니다.</div>""")
    for n in cat['news_items']:
        render_html(f"""
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:8px; padding:10px 14px; margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <span class="badge {n['badge_class']}">{n['sentiment']}</span>
                <span style="font-size:10px; color:#64748b;">{n['date']}</span>
            </div>
            <a href="{n['link']}" target="_blank" rel="noopener noreferrer" style="color:#e2e8f0; font-size:12px; font-weight:700; text-decoration:none;">{n['title']}</a>
        </div>""")


# ==============================================================================
# 15) TAB 2: 보유 모니터
# ==============================================================================
def render_tab_holdings_monitor(usd_krw):
    render_html("""
    <div style="margin-bottom:12px;">
        <div style="font-size:18px; font-weight:800; color:#fff;">🛡️ 보유주식 노이즈 필터 모니터 & AI 리밸런싱</div>
        <div style="font-size:12px; color:#94a3b8; margin-top:2px;">
            작은 파도는 무시, 큰 변곡점만 포착. <b>신호 발생 시 봇 승률 자동 검증 예약</b>.
        </div>
    </div>""")
    with st.expander("➕ 종목 추가/삭제 & 📲 텔레그램", expanded=False):
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.1, 1.1, 1.1])
        with c1: in_t = st.text_input("티커", value="NVDA", key="db_t").upper().strip()
        with c2: in_bp = st.number_input("평단($)", value=125.0, min_value=0.0, step=0.5, key="db_bp")
        with c3: in_q = st.number_input("수량(주)", value=50.0, min_value=0.0, step=1.0, key="db_q")
        with c4: in_tr = st.number_input("목표수익(%)", value=15.0, min_value=1.0, step=1.0, key="db_tr")
        with c5: in_sl = st.number_input("손절폭(%)", value=7.0, min_value=1.0, step=0.5, key="db_sl")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("💾 저장", use_container_width=True, type="primary"):
                db_upsert_holding(in_t, in_bp, in_q, in_tr, in_sl)
                st.rerun()
        with b2:
            if st.button("🗑️ 삭제", use_container_width=True):
                db_delete_holding(in_t)
                st.rerun()
        with b3:
            auto_ref = st.checkbox("60초 자동", value=False)
            if auto_ref and HAS_AUTOREFRESH:
                st_autorefresh(interval=60_000, key="holdings_autorefresh")
        st.markdown("---")
        tcol1, tcol2 = st.columns(2)
        with tcol1: tg_token = st.text_input("Bot Token", value=os.getenv("TELEGRAM_BOT_TOKEN", ""), type="password")
        with tcol2: tg_chat = st.text_input("Chat ID", value=os.getenv("TELEGRAM_CHAT_ID", ""))
    holdings = db_get_holdings()
    if not holdings:
        st.info("등록된 보유 종목이 없습니다.")
        if st.button("🧪 샘플 (IREN·NVDA·TSLA·PLTR) 로드"):
            for sym, bp, q in [("IREN", 12.5, 200), ("NVDA", 125.0, 50), ("TSLA", 240.0, 40), ("PLTR", 42.0, 100)]:
                db_upsert_holding(sym, bp, q, 15.0, 7.0)
            st.rerun()
        return
    eval_list = []
    for h in holdings:
        res = evaluate_holding_noise_filter_cached(
            ticker=h["ticker"], buy_price=h["buy_price"], qty=h["qty"],
            target_roi_pct=h["target_roi"], custom_stop_pct=h["stop_loss_pct"])
        if res:
            eval_list.append(res)
            if res['severity'] >= 2:
                db_register_signal_for_eval(res['ticker'], res['signal'], res['curr_price'])
    eval_list.sort(key=lambda x: (-x['severity'], -abs(x['day_chg_pct'])))
    urgent_list = [x for x in eval_list if x['severity'] >= 3]
    watch_cnt = sum(1 for x in eval_list if x['severity'] == 2)
    calm_cnt = sum(1 for x in eval_list if x['severity'] <= 1)
    total_pnl_usd = sum(x['pnl_usd'] for x in eval_list)
    pnl_color = "#10b981" if total_pnl_usd >= 0 else "#f43f5e"
    cut_candidates = [x['ticker'] for x in eval_list if x['severity'] >= 4]
    tp_candidates = [x['ticker'] for x in eval_list if x['severity'] == 3]
    strong_leaders = [x['ticker'] for x in eval_list if x['signal'] == SIGNAL_HOLD_LONG]
    rebal_msgs = []
    if cut_candidates:
        rebal_msgs.append(f"🔴 <b>즉시 축소/청산:</b> {', '.join(cut_candidates)}")
    if tp_candidates:
        rebal_msgs.append(f"🔵 <b>분할 익절 대상:</b> {', '.join(tp_candidates)}")
    if strong_leaders:
        rebal_msgs.append(f"🟢 <b>코어 홀딩:</b> {', '.join(strong_leaders)}")
    if not rebal_msgs:
        rebal_msgs.append("⚖️ 전 종목 허용 노이즈 범위 내 등락 — 기존 비중 유지.")
    render_html(f"""
    <div class="rebal-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:6px;">
            <span style="font-size:14px; font-weight:800; color:#c084fc;">🔄 AI 리밸런싱 & 자금 재배치</span>
            <span class="mono" style="font-size:13px; font-weight:800; color:{pnl_color};">
                총 평가손익: ${total_pnl_usd:+,.2f} ({total_pnl_usd*usd_krw:+,.0f}원)
            </span>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;">
            <span class="badge badge-red">🚨 행동요망: {len(urgent_list)}</span>
            <span class="badge badge-yellow">🟠 경계: {watch_cnt}</span>
            <span class="badge badge-green">🌊 홀딩: {calm_cnt}</span>
        </div>
        <div style="font-size:11px; color:#e9d5ff; line-height:1.55;">
            {"<br>".join(f"• {m}" for m in rebal_msgs)}
        </div>
    </div>""")
    if st.button("📲 텔레그램 리포트 전송", use_container_width=True):
        lines = [f"⚡ [GANGJIN] 리포트 ({datetime.now().strftime('%H:%M')})"]
        for it in eval_list:
            lines.append(f"• {it['ticker']}: {it['signal']} | ${it['curr_price']:,.2f} ({it['roi_pct']:+.1f}%) | 청산 ${it['chandelier_stop']:,.2f}")
            if it['severity'] >= 3:
                db_log_alert(it['ticker'], it['signal'], it['curr_price'], it['headline'])
        ok, msg = send_telegram_alert("\n".join(lines), tg_token, tg_chat)
        if ok: st.success(msg)
        else: st.warning(msg)
    for item in eval_list:
        d_col = "#10b981" if item['day_chg_pct'] >= 0 else "#f43f5e"
        r_col = "#10b981" if item['roi_pct'] >= 0 else "#f43f5e"
        nb_col = "#10b981" if item['noise_used_ratio'] < 55 else ("#f59e0b" if item['noise_used_ratio'] < 85 else "#f43f5e")
        border_col = "#f43f5e" if item['severity'] >= 4 else ("#3b82f6" if item['severity'] == 3 else ("#f59e0b" if item['severity'] == 2 else "#1e293b"))
        render_html(f"""
        <div style="background:#0f172a; border:1.5px solid {border_col}; border-radius:12px; padding:14px 16px; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                    <span style="font-size:18px; font-weight:800; font-family:'JetBrains Mono'; color:#fff;">{item['ticker']}</span>
                    <span class="badge {item['badge']}">{item['signal']}</span>
                    <span style="font-size:11px; color:#94a3b8; font-weight:700;">{item['wave_status']}</span>
                </div>
                <div class="mono" style="text-align:right;">
                    <span style="font-size:16px; font-weight:800; color:#fff;">${item['curr_price']:,.2f}</span>
                    <span style="font-size:12px; font-weight:700; color:{d_col}; margin-left:6px;">({item['day_chg_pct']:+.2f}%)</span>
                </div>
            </div>
            <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; text-align:center; font-family:'JetBrains Mono'; background:rgba(0,0,0,.35); padding:8px; border-radius:8px; margin-bottom:8px; font-size:11px;">
                <div><div style="color:#64748b; font-size:9px;">평단/수익</div><div style="color:{r_col}; font-weight:800;">${item['buy_price']:,.2f} ({item['roi_pct']:+.1f}%)</div></div>
                <div><div style="color:#64748b; font-size:9px;">ATR</div><div style="color:#e2e8f0; font-weight:700;">±{item['atr_pct']:.1f}%</div></div>
                <div><div style="color:#64748b; font-size:9px;">샹들리에</div><div style="color:#f43f5e; font-weight:800;">${item['chandelier_stop']:,.2f}</div></div>
                <div><div style="color:#64748b; font-size:9px;">EMA20/RSI</div><div style="color:#38bdf8; font-weight:700;">${item['ema20']:,.2f}|{item['rsi']:.0f}</div></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:10px; color:#94a3b8; margin-bottom:3px;">
                <span>낙폭: <b class="text-white">{item['drawdown_from_high_pct']:+.1f}%</b></span>
                <span>소진: <b style="color:{nb_col};">{item['noise_used_ratio']:.0f}%</b></span>
            </div>
            <div style="width:100%; height:7px; background:#090d16; border-radius:4px; overflow:hidden; margin-bottom:8px;">
                <div style="width:{min(100, max(4, item['noise_used_ratio']))}%; height:100%; background:{nb_col};"></div>
            </div>
            <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">
                • <b style="color:#fef08a;">{item['headline']}</b><br>
                • <b>지침:</b> {item['action_guide']}
            </div>
        </div>""")


# ==============================================================================
# 16) TAB 3: 스캐너
# ==============================================================================
def render_tab_scanner():
    render_html("""
    <div style="margin-bottom:12px;">
        <div style="font-size:18px; font-weight:800; color:#fff;">🎯 100종목 스캐너</div>
        <div style="font-size:12px; color:#94a3b8; margin-top:2px;">6대 거장 + Wilder RSI + ATR 트레일링 스탑</div>
    </div>""")
    presets = {
        "🔥 서학개미 Top 100": "NVDA TSLA AAPL MSFT AMZN GOOGL META PLTR AMD COIN MSTR SOXL TQQQ SMCI MARA RIOT IREN CLSK IONQ RKLB ASTS ARM TSM AVGO CRWD PANW NFLX DIS INTC SOFI HOOD OPEN LCID RIVN U RBLX SNOW BABA NIO XPEV LI BIDU PDD BILI UPST AFRM SQ PYPL SHOP SE CPNG PATH AI PLUG ENPH SEDG FCEL CHPT BLNK QS DKNG PENN WYNN LVS CCL RCL NCLH UAL DAL AAL LUV BA RTX LMT GD NOC XOM CVX OXY SLB HAL COP F GM TM HMC NKE LULU SBUX MCD KO PEP PG JNJ PFE MRK LLY UNH ABBV",
        "🤖 AI & 반도체": "NVDA AMD TSM AVGO ARM ASML QCOM MU INTC MRVL AMAT LRCX KLAC ON NXPI ADI MPWR SMCI",
        "⚡ 양자 & 우주": "IONQ RGTI QBTS QUBT RKLB LUNR ASTS PL RDYW BKSY SPIR",
        "💎 크립토": "MSTR COIN MARA RIOT IREN CLSK CIFR HUT BITF CORZ WULF BTDR",
    }
    p1, p2 = st.columns([1, 2])
    with p1: sel = st.selectbox("프리셋", list(presets.keys()), key="s_preset")
    with p2: txt = st.text_area("티커", value=presets[sel], height=70, key="s_txt")
    b1, b2 = st.columns([1, 2])
    with b1: start = st.button("🚀 스캔", type="primary", use_container_width=True)
    with b2: filt = st.radio("필터", ["전체", "🔥 STRONG BUY", "🟢 PANIC BUY", "매수 전체"], horizontal=True, key="s_filt")
    if start or "s_res" in st.session_state:
        if start:
            with st.spinner("스캔 중..."):
                st.session_state.s_res = scan_watchlist(txt)
        data = st.session_state.get("s_res", [])
        if not data:
            st.warning("결과 없음")
            return
        ff = data
        if filt == "🔥 STRONG BUY": ff = [r for r in data if "STRONG" in r['action']]
        elif filt == "🟢 PANIC BUY": ff = [r for r in data if "PANIC" in r['action']]
        elif filt == "매수 전체": ff = [r for r in data if r['is_buy']]
        render_html(f"""<div style="margin:12px 0;font-size:13px;font-weight:700;">총 {len(data)}개 중 <b style="color:#38bdf8;">{len(ff)}개</b> 포착</div>""")
        for it_ in ff:
            cc = "#10b981" if it_['change_pct'] >= 0 else "#f43f5e"
            cs = "+" if it_['change_pct'] >= 0 else ""
            render_html(f"""
            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:10px 14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div style="display:flex; align-items:center; gap:10px; min-width:160px;">
                    <span style="font-size:16px; font-weight:800; font-family:'JetBrains Mono'; color:#fff;">{it_['ticker']}</span>
                    <span class="badge {it_['badge']}">{it_['action']}</span>
                </div>
                <div class="mono" style="text-align:right; min-width:100px;">
                    <div style="font-size:14px; font-weight:800; color:#fff;">${it_['price']:,.2f}</div>
                    <div style="font-size:11px; color:{cc};">{cs}{it_['change_pct']:.2f}%</div>
                </div>
                <div style="font-size:11px; color:#94a3b8; display:flex; gap:12px; flex-wrap:wrap;">
                    <span>RSI <b class="text-white">{it_['rsi']:.1f}</b></span>
                    <span>거래량 <b class="text-white">{it_['vol']:.1f}x</b></span>
                    <span>ATR <b class="text-white">{it_['atr_pct']:.1f}%</b></span>
                    <span>TS <b style="color:#38bdf8;">-{it_['ts_rec']:.1f}%</b></span>
                </div>
            </div>""")
        csv = pd.DataFrame(data).to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 CSV", csv, f"scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")


# ==============================================================================
# 17) TAB 4: 백테스트
# ==============================================================================
def render_tab_backtest():
    render_html("""<div style="margin-bottom:12px;">
    <div style="font-size:18px;font-weight:800;color:#fff;">🧪 전략 백테스트</div>
    <div style="font-size:12px;color:#94a3b8;margin-top:2px;">6대 대가 + 샹들리에 vs Buy&Hold</div>
    </div>""")
    c1, c2, c3 = st.columns([1.5, 1.2, 1.5])
    with c1: bt_t = st.text_input("티커", value="NVDA", key="bt_t").upper().strip()
    with c2: bt_p = st.selectbox("기간", ["1y", "2y", "5y"], index=1)
    with c3: bt_cap = st.number_input("시드($)", value=10000.0, min_value=1000.0, step=1000.0)
    if st.button("🚀 실행", type="primary", use_container_width=True) or "bt_res" not in st.session_state:
        with st.spinner(f"{bt_t} 백테스트 중..."):
            st.session_state.bt_res = run_strategy_backtest(bt_t, bt_p, bt_cap)
    res = st.session_state.get("bt_res", {})
    if not res:
        st.warning("데이터 부족")
        return
    sc = "#10b981" if res['strat_ret'] >= 0 else "#f43f5e"
    bcc = "#10b981" if res['bh_ret'] >= 0 else "#f43f5e"
    render_html(f"""
    <div class="glass-card">
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono';">
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">AI 전략</div>
                <div style="font-size:18px; font-weight:800; color:{sc};">{res['strat_ret']:+.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">${res['final_equity']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">Buy&Hold</div>
                <div style="font-size:18px; font-weight:800; color:{bcc};">{res['bh_ret']:+.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">전략 MDD</div>
                <div style="font-size:18px; font-weight:800; color:#38bdf8;">{res['mdd_strat']:.1f}%</div>
                <div style="font-size:10px; color:#64748b;">보유 {res['mdd_bh']:.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">승률 / 매매</div>
                <div style="font-size:18px; font-weight:800; color:#fbbf24;">{res['win_rate']:.1f}%</div>
                <div style="font-size:10px; color:#cbd5e1;">{res['total_trades']}회</div>
            </div>
        </div>
    </div>""")
    eq = res["eq_df"]
    f = go.Figure()
    f.add_trace(go.Scatter(x=eq.index, y=eq["strategy_eq"], name="전략", line=dict(color="#10b981", width=2.2)))
    f.add_trace(go.Scatter(x=eq.index, y=eq["bh_eq"], name="Buy&Hold", line=dict(color="#64748b", width=1.5, dash="dot")))
    f.update_layout(template="plotly_dark", height=360, margin=dict(l=30, r=30, t=30, b=20),
                    paper_bgcolor="#080c14", plot_bgcolor="#080c14", hovermode="x unified",
                    legend=dict(orientation="h", y=1.1))
    st.plotly_chart(f, use_container_width=True)
    if res["trades"]:
        with st.expander(f"📋 거래 내역 ({len(res['trades'])}건)", expanded=False):
            st.dataframe(pd.DataFrame(res["trades"]), use_container_width=True, hide_index=True)


# ==============================================================================
# 18) TAB 5: WFA
# ==============================================================================
def render_tab_wfa():
    render_html("""<div style="margin-bottom:12px;">
    <div style="font-size:18px;font-weight:800;color:#fff;">🔬 Walk-Forward 전진 분석</div>
    <div style="font-size:12px;color:#94a3b8;margin-top:2px;">IS 최적화 → OOS 실전 검증. 실전 강건성(WFE).</div>
    </div>""")
    c1, c2, c3 = st.columns(3)
    with c1: wt = st.text_input("티커", value="NVDA", key="wfa_t").upper().strip()
    with c2: wp = st.selectbox("기간", ["2y", "3y", "5y"], index=1, key="wfa_p")
    with c3: ws = st.selectbox("Fold", [3, 4, 5], index=1, key="wfa_s")
    if st.button("🔬 WFA 실행", type="primary", use_container_width=True) or "wfa_res" not in st.session_state:
        with st.spinner(f"{wt} WFA 연산 중..."):
            st.session_state.wfa_res = run_walk_forward(wt, period=wp, n_splits=int(ws))
    wr = st.session_state.get("wfa_res", {})
    if not wr:
        st.warning("데이터 부족")
        return
    oc = "#10b981" if wr["cum_oos_pct"] >= 0 else "#f43f5e"
    render_html(f"""
    <div class="glass-card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-size:14px; font-weight:800; color:#38bdf8;">🏆 판정: {wr['verdict']}</span>
            <span class="badge badge-teal">일관성: {wr['consistency']:.0f}%</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(3,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono';">
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">OOS 누적</div>
                <div style="font-size:18px; font-weight:800; color:{oc};">{wr['cum_oos_pct']:+.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">평균 IS vs OOS</div>
                <div style="font-size:15px; font-weight:800; color:#f8fafc;">{wr['avg_is_pct']:+.1f}% / {wr['avg_oos_pct']:+.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">WFE</div>
                <div style="font-size:18px; font-weight:800; color:#fbbf24;">{wr['wfe']:.1f}%</div>
            </div>
        </div>
    </div>""")
    st.markdown("##### 📊 Fold별 성적")
    st.dataframe(pd.DataFrame(wr["folds"]), use_container_width=True, hide_index=True)


# ==============================================================================
# 19) TAB 6: 리스크
# ==============================================================================
def render_tab_portfolio_risk(usd_krw):
    render_html("""<div style="margin-bottom:12px;">
    <div style="font-size:18px;font-weight:800;color:#fff;">📊 포트폴리오 통합 리스크 & 역변동성 리밸런싱</div>
    <div style="font-size:12px;color:#94a3b8;margin-top:2px;">VaR · CVaR · 베타 · 상관계수 · 리스크 패리티</div>
    </div>""")
    holdings = db_get_holdings()
    if not holdings:
        st.info("보유주식 DB 비어 있어 기본(NVDA·TSLA·PLTR·IREN)으로 시뮬레이션합니다.")
        holdings = [{"ticker": "NVDA", "qty": 50.0}, {"ticker": "TSLA", "qty": 40.0},
                    {"ticker": "PLTR", "qty": 100.0}, {"ticker": "IREN", "qty": 200.0}]
    if st.button("📊 리스크 진단", type="primary", use_container_width=True) or "risk_rep" not in st.session_state:
        with st.spinner("VaR·상관계수 연산 중..."):
            st.session_state.risk_rep = build_full_risk_report(holdings)
    rep = st.session_state.get("risk_rep", {})
    if not rep:
        st.warning("리스크 리포트 생성 실패")
        return
    render_html(f"""
    <div class="glass-card">
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono'; margin-bottom:10px;">
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">VaR 95%</div>
                <div style="font-size:16px; font-weight:800; color:#f43f5e;">{rep['var_95_pct']:.2f}%</div>
                <div style="font-size:10px; color:#fca5a5;">-${rep['var_95_usd']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">CVaR 95%</div>
                <div style="font-size:16px; font-weight:800; color:#fb7185;">{rep['cvar_95_pct']:.2f}%</div>
                <div style="font-size:10px; color:#fca5a5;">-${rep['cvar_95_usd']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">β vs SPY</div>
                <div style="font-size:16px; font-weight:800; color:#38bdf8;">{rep['beta']:.2f}</div>
                <div style="font-size:10px; color:#94a3b8;">연변동 {rep['ann_vol']:.1f}%</div>
            </div>
            <div style="background:rgba(0,0,0,.35); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">샤프 / HHI</div>
                <div style="font-size:16px; font-weight:800; color:#10b981;">{rep['sharpe']:.2f}</div>
                <div style="font-size:10px; color:#94a3b8;">집중 {rep['hhi']:.0f}점</div>
            </div>
        </div>
        <div style="background:rgba(244,63,94,.1); border:1px solid rgba(244,63,94,.3); border-radius:8px; padding:8px 12px; font-size:11px; color:#fecdd3;">
            • <b>🔥 스트레스:</b> SPY -5% 시 -${rep['stress_5pct_usd']:,.0f} | SPY -10% 시 -${rep['stress_10pct_usd']:,.0f}
        </div>
    </div>""")
    if rep.get("rebal_actions"):
        render_html(f"""
        <div class="rebal-card">
            <div style="font-size:13px; font-weight:800; color:#c084fc; margin-bottom:6px;">⚖️ 리스크 패리티(역변동성) 비중 리밸런싱</div>
            <div style="font-size:11px; color:#e9d5ff; line-height:1.55;">
                {"<br>".join(f"• {a}" for a in rep['rebal_actions'])}
            </div>
        </div>""")
    cL, cR = st.columns([1.2, 1.3])
    with cL:
        st.markdown("##### ⚖️ 현재 vs 권장 비중")
        st.dataframe(pd.DataFrame(rep["weights_table"]), use_container_width=True, hide_index=True)
    with cR:
        st.markdown("##### 🔗 상관계수")
        st.dataframe(rep["corr_matrix"], use_container_width=True)


# ==============================================================================
# 20) TAB 7: 매매일지
# ==============================================================================
def render_tab_journal(usd_krw):
    db_eval_pending_signals()
    render_html("""
    <div style="margin-bottom:12px;">
        <div style="font-size:18px; font-weight:800; color:#fff;">📓 매매일지 & 신호 이중 검증 센터</div>
        <div style="font-size:12px; color:#94a3b8; margin-top:2px;">
            <b>① 봇 신호 자동 승률 검증</b> (시스템) + <b>② 내 매매일지</b> (수동) — 이중 추적.
        </div>
    </div>""")

    signal_stats = db_get_signal_stats()
    if signal_stats:
        sig10 = [s for s in signal_stats if s['horizon'] == 10]
        total_sig = sum(s['total'] for s in sig10)
        total_win = sum(s['wins'] for s in sig10)
        overall_win = (total_win / total_sig * 100) if total_sig > 0 else 0
        stat_rows = []
        for s in sorted(signal_stats, key=lambda x: (-x['horizon'], -x['win_rate'])):
            wr_color = "#10b981" if s['win_rate'] >= 55 else ("#f59e0b" if s['win_rate'] >= 45 else "#f43f5e")
            stat_rows.append(f"""
            <div style="background:rgba(0,0,0,.35); border:1px solid #1e293b; border-radius:8px; padding:8px 12px; margin-bottom:5px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:13px; font-weight:800; color:#fff;">{s['signal']}</span>
                    <span class="badge badge-indigo">{s['horizon']}일</span>
                </div>
                <div style="font-size:11px; font-family:'JetBrains Mono'; display:flex; gap:10px; flex-wrap:wrap;">
                    <span style="color:#94a3b8;">총 <b class="text-white">{s['total']}</b></span>
                    <span style="color:#10b981;">승 <b>{s['wins']}</b></span>
                    <span style="color:#f43f5e;">패 <b>{s['losses']}</b></span>
                    <span style="color:{wr_color}; font-weight:800;">승률 {s['win_rate']:.1f}%</span>
                    <span style="color:{('#10b981' if s['avg_return']>=0 else '#f43f5e')};">평균 {s['avg_return']:+.2f}%</span>
                </div>
            </div>""")
        render_html(f"""
        <div class="signal-card">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
                <span style="font-size:14px; font-weight:800; color:#a5b4fc;">🤖 봇 신호 자동 승률 검증 (5/10/20일 후 평가)</span>
                <span class="badge {('badge-green' if overall_win >= 55 else ('badge-yellow' if overall_win >= 45 else 'badge-red'))}">
                    전체 승률 {overall_win:.0f}% ({total_win}/{total_sig})
                </span>
            </div>
            <div style="font-size:11px; color:#cbd5e1; margin-bottom:6px;">
                • Tab 2 진입 시마다 자동 예약 → 지정된 일자가 지나면 자동으로 WIN/LOSS 판정
            </div>
            {"".join(stat_rows)}
        </div>""")
    else:
        render_html("""
        <div class="signal-card">
            <div style="font-size:14px; font-weight:800; color:#a5b4fc; margin-bottom:8px;">🤖 봇 신호 자동 승률 검증</div>
            <div style="font-size:11px; color:#94a3b8; text-align:center; padding:20px 0;">
                아직 검증할 신호가 없습니다.<br>
                <span style="font-size:10px;">Tab 2에서 보유 종목을 등록하면 신호가 자동 예약되며, 5/10/20일 뒤 실제 주가로 승률이 산출됩니다.</span>
            </div>
        </div>""")

    with st.expander("✍️ 신규 매매일지 기록하기", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1: j_date = st.text_input("매매일자", value=datetime.now().strftime("%Y-%m-%d"), key="j_dt")
        with c2: j_ticker = st.text_input("티커", value="IREN", key="j_tk").upper().strip()
        with c3: j_side = st.selectbox("구분", ["1차익절", "2차익절", "트레일링청산", "원칙손절", "신규매수"], key="j_sd")
        with c4: j_pnl = st.number_input("실현손익 ($)", value=250.0, step=10.0, key="j_pnl")
        c5, c6, c7, c8 = st.columns([1, 1, 1.3, 1.3])
        with c5: j_px = st.number_input("체결단가 ($)", value=15.5, min_value=0.0, step=0.1, key="j_px")
        with c6: j_qty = st.number_input("수량 (주)", value=100.0, min_value=0.0, step=1.0, key="j_qty")
        with c7: j_strat = st.selectbox("적용 대가 기법",
            ["오닐 CANSLIM 돌파", "미너비니 SEPA/VCP", "다바스 박스 돌파",
             "와인스타인 2단계", "코너스 RSI 역발상", "튜더존스 200일선", "기타/재량"], key="j_st")
        with c8: j_emo = st.selectbox("매매 심리 상태",
            ["✅ 원칙준수 (냉정)", "🔥 FOMO 추격매수", "😨 공포 조기매도", "😡 복수/뇌동매매"], key="j_em")
        j_memo = st.text_input("한줄 복기 메모", value="거래량 1.8배 돌파 확인 후 분할 익절 원칙 준수", key="j_mm")
        if st.button("💾 매매일지 저장", type="primary", use_container_width=True):
            db_add_journal_entry(j_date, j_ticker, j_side, j_px, j_qty, j_pnl, j_strat, j_emo, j_memo)
            st.rerun()

    entries = db_get_journal_entries()
    if not entries:
        st.info("아직 기록된 매매일지가 없습니다. 위 입력창에서 첫 매매 복기를 기록하거나 아래 샘플 데이터를 로드해 AI 습관 진단을 체험해보세요!")
        if st.button("🧪 샘플 매매일지 (6대 대가 기법 & 심리 복기 6건) 자동 로드", use_container_width=True):
            sample_rows = [
                ("2026-10-15", "NVDA", "1차익절", 138.5, 50, 675.0, "오닐 CANSLIM 돌파", "✅ 원칙준수 (냉정)", "20일 신고가 + 거래량 1.8배 돌파 매수 후 1차 익절"),
                ("2026-10-16", "IREN", "2차익절", 15.8, 200, 520.0, "다바스 박스 돌파", "✅ 원칙준수 (냉정)", "박스 상단 돌파 후 트레일링 스탑 홀딩 익절"),
                ("2026-10-18", "TSLA", "원칙손절", 228.0, 30, -180.0, "기타/재량", "🔥 FOMO 추격매수", "장초반 급등 추격매수 후 20일선 이탈 손절"),
                ("2026-10-19", "PLTR", "1차익절", 44.2, 100, 390.0, "미너비니 SEPA/VCP", "✅ 원칙준수 (냉정)", "VCP 변동성 수축 돌파 진입 후 분할 익절"),
                ("2026-10-20", "MSTR", "원칙손절", 195.0, 20, -140.0, "코너스 RSI 역발상", "😡 복수/뇌동매매", "직전 손절 만회하려 성급히 진입했다가 손절"),
                ("2026-10-21", "IONQ", "트레일링청산", 14.5, 150, 410.0, "와인스타인 2단계", "✅ 원칙준수 (냉정)", "2단계 정배열 추세 추종 후 샹들리에 익절"),
            ]
            for r_dt, r_tk, r_sd, r_px, r_q, r_pnl, r_st, r_em, r_mm in sample_rows:
                db_add_journal_entry(r_dt, r_tk, r_sd, r_px, r_q, r_pnl, r_st, r_em, r_mm)
            st.rerun()
        return

    # ⭐ [17.0] Journal Agent 실행 — 종합 성과 + 8대 잘못된 매매 습관(Behavioral Biases) 자동 진단
    journal_r = analyze_trade_journal()
    jd = journal_r.details
    total_realized = jd["total_pnl"]
    win_rate = jd["win_rate"]
    profit_factor = jd["profit_factor"]
    expectancy = jd["expectancy"]
    tot_col = "#10b981" if total_realized >= 0 else "#f43f5e"
    exp_col = "#10b981" if expectancy >= 0 else "#f43f5e"

    render_html(f"""
    <div class="journal-card">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
            <span style="font-size:14px; font-weight:800; color:#34d399;">📋 내 매매일지 종합 성과 (총 {jd['total']}건)</span>
            <span class="badge badge-green">Journal Agent 행동재무학 진단</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:8px; text-align:center; font-family:'JetBrains Mono';">
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">누적 실현손익</div>
                <div style="font-size:16px; font-weight:800; color:{tot_col};">${total_realized:+,.2f}</div>
                <div style="font-size:10px; color:#cbd5e1;">{total_realized*usd_krw:+,.0f}원</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">실현 승률</div>
                <div style="font-size:16px; font-weight:800; color:#fbbf24;">{win_rate:.1f}%</div>
                <div style="font-size:10px; color:#64748b;">평균수익 ${jd['avg_win']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">손익비 (PF)</div>
                <div style="font-size:16px; font-weight:800; color:#38bdf8;">{profit_factor:.2f}</div>
                <div style="font-size:10px; color:#64748b;">평균손실 ${jd['avg_loss']:,.0f}</div>
            </div>
            <div style="background:rgba(0,0,0,.4); padding:10px; border-radius:8px;">
                <div style="font-size:10px; color:#94a3b8;">건당 기대값</div>
                <div style="font-size:16px; font-weight:800; color:{exp_col};">${expectancy:+,.1f}</div>
                <div style="font-size:10px; color:#64748b;">Expectancy/Trade</div>
            </div>
        </div>
    </div>""")

    if jd.get("biases"):
        st.markdown("##### ⚠️ AI 매니저의 매매 습관 & 심리 편향 진단")
        for b in jd["biases"]:
            lvl_color = {"DANGER": "#f43f5e", "WARN": "#f59e0b", "INFO": "#38bdf8"}.get(b["level"], "#38bdf8")
            lvl_badge = {"DANGER": "badge-red", "WARN": "badge-yellow", "INFO": "badge-blue"}.get(b["level"], "badge-blue")
            render_html(f"""
            <div style="background:#0f172a; border:1px solid {lvl_color}; border-left:4px solid {lvl_color}; border-radius:10px; padding:11px 15px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                    <span style="font-size:13px; font-weight:800; color:#fff;">{html.escape(b['type'])}</span>
                    <span class="badge {lvl_badge}">{b['level']}</span>
                </div>
                <div style="font-size:11px; color:#cbd5e1; line-height:1.5;">{html.escape(b['desc'])}</div>
            </div>""")

    col_j1, col_j2 = st.columns(2)
    with col_j1:
        st.markdown("##### 👑 6대 대가 기법별 승률")
        for s in jd.get("strategy_stats", []):
            s_col = "#10b981" if s["총손익"] >= 0 else "#f43f5e"
            wr_c = "#10b981" if s["승률"] >= 55 else ("#f59e0b" if s["승률"] >= 45 else "#f43f5e")
            render_html(f"""
            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:9px; padding:9px 12px; margin-bottom:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
                    <span style="font-size:12px; font-weight:800; color:#fff;">{html.escape(s['기법'])}</span>
                    <span class="mono" style="font-size:12px; font-weight:800; color:{s_col};">${s['총손익']:+,.0f}</span>
                </div>
                <div class="mono" style="font-size:10px; color:#94a3b8; display:flex; gap:10px; flex-wrap:wrap;">
                    <span>{s['거래']}건 ({s['승']}승 {s['패']}패)</span>
                    <span style="color:{wr_c}; font-weight:700;">승률 {s['승률']:.1f}%</span>
                    <span>PF {s['PF']:.2f}</span>
                </div>
            </div>""")

    with col_j2:
        st.markdown("##### 🧠 심리 상태별 & 종목별 성과")
        for e in jd.get("emotion_stats", []):
            e_col = "#10b981" if e["총손익"] >= 0 else "#f43f5e"
            render_html(f"""
            <div style="background:#0f172a; border:1px solid #1e293b; border-radius:9px; padding:8px 12px; margin-bottom:5px; display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:12px; font-weight:800; color:#fff;">{html.escape(e['심리'])}</span>
                <span class="mono" style="font-size:11px; color:#cbd5e1;">{e['거래']}건 · 승률 {e['승률']:.0f}% · <b style="color:{e_col};">${e['총손익']:+,.0f}</b></span>
            </div>""")
        if jd.get("ticker_stats"):
            top_tk_str = " | ".join(
                f"<b>{html.escape(t['티커'])}</b> ${t['총손익']:+,.0f} ({t['승률']:.0f}%)"
                for t in jd["ticker_stats"][:5]
            )
            render_html(f"""
            <div style="background:rgba(56,189,248,.08); border:1px solid rgba(56,189,248,.25); border-radius:8px; padding:8px 11px; margin-top:6px; font-size:11px; color:#cbd5e1;">
                🎯 <b>종목 Top 5:</b> {top_tk_str}
            </div>""")

    df_j = pd.DataFrame(entries)
    st.dataframe(df_j.drop(columns=["id"], errors="ignore"), use_container_width=True, hide_index=True)

    c_del, c_dl = st.columns([1.5, 1.5])
    with c_del:
        del_id = st.selectbox("삭제할 기록", options=[e["id"] for e in entries],
                              format_func=lambda x: f"#{x} ({next((e['티커']+' '+e['일자'] for e in entries if e['id']==x), '')})")
        if st.button("🗑️ 선택 일지 삭제", use_container_width=True):
            db_delete_journal_entry(del_id)
            st.rerun()
    with c_dl:
        st.write("")
        st.write("")
        st.download_button("📥 매매일지 CSV", data=df_j.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"trading_journal_{datetime.now().strftime('%Y%m%d')}.csv",
                           mime="text/csv", use_container_width=True)


# ==============================================================================
# 21) MAIN ENTRY
# ==============================================================================
def main():
    btc_price, btc_change, usd_krw = get_top_bar_data()
    eff_krw = usd_krw if usd_krw > 0 else CFG["usd_krw_fallback"]
    render_live_ny_header(btc_price, btc_change, eff_krw)
    indices = get_market_indices()
    idx_cards = []
    for item in indices:
        color = "text-green" if item['change'] >= 0 else "text-red"
        sign = "+" if item['change'] >= 0 else ""
        if "국채" in item['name'] or "금리" in item['name']:
            price_display = f"{item['price']:.2f}%"
        elif item['price'] > 1000:
            price_display = f"{item['price']:,.0f}"
        else:
            price_display = f"{item['price']:,.2f}"
        idx_cards.append(f"""<div class="index-card">
<div class="index-name">{html.escape(item['name'])}</div>
<div class="index-price {color}">{price_display}</div>
<div class="index-change {color}">{sign}{item['change']:.2f}%</div>
</div>""")
    render_html(f"""<div class="index-wrapper">{"".join(idx_cards)}</div>""")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 개별분석", "🛡️ 보유모니터", "🎯 스캐너", "🧪 백테스트",
        "🔬 WFA검증", "📊 리스크", "📓 매매일지",
    ])
    with tab1:
        render_tab_analysis(indices, eff_krw)
    with tab2:
        render_tab_holdings_monitor(eff_krw)
    with tab3:
        render_tab_scanner()
    with tab4:
        render_tab_backtest()
    with tab5:
        render_tab_wfa()
    with tab6:
        render_tab_portfolio_risk(eff_krw)
    with tab7:
        render_tab_journal(eff_krw)


if __name__ == "__main__":
    main()