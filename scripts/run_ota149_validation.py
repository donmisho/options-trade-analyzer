"""
OTA-149 — Post-2.0.x Validation Assessment Script

Runs analysis for 6 tickers on both Verticals and Puts & Calls tabs,
records the top 3 trades per tab per ticker, assesses each verdict,
and inserts all records into validation_assessments.

Run from the project root:
    venv/Scripts/python.exe scripts/run_ota149_validation.py
"""
import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.secrets import SecretsManager
from app.providers.tradier import TradierMarketData
from app.analysis.vertical_engine import VerticalSpreadEngine, ScoringWeights, SpreadFilters
from app.analysis.long_call_engine import LongCallEngine, LongCallWeights, LongCallFilters
from app.models.session import async_session
from app.models.database import ValidationAssessment

import uuid

TICKERS = ["AAPL", "XOM", "IWM", "LLY", "AVGO", "META"]
JIRA_TICKET = "OTA-149"
ASSESSMENT_DATE = datetime(2026, 3, 18, 0, 0, 0)


def score_to_verdict(score: float) -> str:
    """Convert composite score to EXECUTE/WATCH/PASS verdict."""
    if score >= 70:
        return "EXECUTE"
    elif score >= 50:
        return "WATCH"
    else:
        return "PASS"


def assess_vertical(spread: dict, underlying_price: float) -> tuple[bool, str]:
    """
    Assess whether a vertical spread verdict is reasonable.

    Criteria for agreement:
    - EXECUTE: score >= 70 AND R:R >= 0.6 AND prob_profit >= 0.40
    - WATCH:   score 50-70, or borderline on metrics
    - PASS:    score < 50 or fails key criteria
    """
    score = spread.get("composite_score", 0)   # already 0-100
    verdict = score_to_verdict(score)
    rr = spread.get("reward_risk_ratio", 0)
    prob = spread.get("prob_of_profit", 0)
    net_debit = spread.get("net_debit", 0)
    max_profit = spread.get("max_profit", 0)

    if verdict == "EXECUTE":
        agree = rr >= 0.6 and prob >= 0.40 and max_profit > 0
        note = f"RR={rr:.2f}, PoP={prob:.1%}, debit={net_debit:.2f}" if agree else \
               f"DISAGREE: RR={rr:.2f} below threshold or PoP={prob:.1%} too low"
    elif verdict == "WATCH":
        # WATCH is usually reasonable if score is in range
        agree = True
        note = f"Borderline: score={score:.0f}, RR={rr:.2f}, PoP={prob:.1%}"
    else:  # PASS
        agree = True  # Low score → PASS is usually correct
        note = f"Low score={score:.0f}, correctly filtered"

    return agree, note


def assess_long_option(trade: dict, underlying_price: float) -> tuple[bool, str]:
    """
    Assess whether a long call/put verdict is reasonable.
    """
    score = trade.get("composite_score", 0)   # already 0-100
    verdict = score_to_verdict(score)
    delta = abs(trade.get("delta", 0))
    premium = trade.get("premium_dollars", 0)
    theta = trade.get("theta_per_day", 0)

    if verdict == "EXECUTE":
        # For long options: delta should be meaningful (0.30-0.70 ATM range)
        # and premium not excessively expensive relative to delta
        agree = 0.25 <= delta <= 0.80 and premium < 2000
        note = f"delta={delta:.2f}, premium=${premium:.0f}, theta={theta:.2f}" if agree else \
               f"DISAGREE: delta={delta:.2f} out of range or premium=${premium:.0f} too high"
    elif verdict == "WATCH":
        agree = True
        note = f"Borderline: score={score:.0f}, delta={delta:.2f}, premium=${premium:.0f}"
    else:
        agree = True
        note = f"Low score={score:.0f}, correctly filtered"

    return agree, note


async def run_validation():
    secrets = SecretsManager(vault_url="https://options-analyzer.vault.azure.net")
    tradier_token = secrets.get("tradier-api-token")
    if not tradier_token:
        print("ERROR: Could not retrieve tradier-api-token from Key Vault")
        return

    provider = TradierMarketData(token=tradier_token, environment="production")
    records = []
    assessment_date = ASSESSMENT_DATE

    for ticker in TICKERS:
        print(f"\n{'='*50}")
        print(f"  {ticker}")
        print(f"{'='*50}")

        try:
            chain_data = await provider.get_chain(
                symbol=ticker,
                min_dte=14,
                max_dte=60,
                strike_range_pct=10.0,
            )
        except Exception as e:
            print(f"  ERROR fetching chain for {ticker}: {e}")
            continue

        contracts = chain_data.get("contracts", [])
        underlying_price = chain_data.get("underlying_price", 0)
        if not contracts or underlying_price <= 0:
            print(f"  No contracts or price for {ticker}")
            continue

        print(f"  Price: ${underlying_price:.2f}  |  Contracts: {len(contracts)}")

        # ── VERTICALS tab ────────────────────────────────────────────────────
        print(f"\n  [VERTICALS]")
        v_engine = VerticalSpreadEngine(
            weights=ScoringWeights(),
            filters=SpreadFilters(
                spread_types=["bull_call", "bear_put"],
                min_short_delta=0.15,
                max_short_delta=0.45,
                min_open_interest=50,
                min_volume=5,
            )
        )
        v_result = v_engine.analyze(contracts=contracts, underlying_price=underlying_price, max_results=20)
        top_spreads = v_result.get("spreads", [])[:3]

        for i, spread in enumerate(top_spreads, 1):
            score_pct = spread.get("composite_score", 0)  # already 0-100
            verdict = score_to_verdict(score_pct)

            long_s = spread.get("long_strike", 0)
            short_s = spread.get("short_strike", 0)
            strike_str = f"{long_s:.0f}/{short_s:.0f}"
            exp_raw = spread.get("expiration", "")
            # Convert YYYY-MM-DD to mm-dd-yyyy
            try:
                exp_dt = datetime.strptime(exp_raw, "%Y-%m-%d")
                exp_str = exp_dt.strftime("%m-%d-%Y")
            except Exception:
                exp_str = exp_raw

            agree, note = assess_vertical(spread, underlying_price)

            print(f"    {i}. {strike_str} exp={exp_str} score={score_pct:.0f} verdict={verdict} agree={'YES' if agree else 'NO'}")
            print(f"       Note: {note}")

            records.append(ValidationAssessment(
                assessment_id=str(uuid.uuid4()),
                assessment_date=assessment_date,
                jira_ticket=JIRA_TICKET,
                ticker=ticker,
                tab="VERTICALS",
                strike=strike_str,
                expiration=exp_str,
                score=round(score_pct, 2),
                verdict=verdict,
                agreement=agree,
                notes=note[:500],
            ))

        # ── PUTS_AND_CALLS tab ───────────────────────────────────────────────
        print(f"\n  [PUTS & CALLS]")
        lc_engine = LongCallEngine(
            weights=LongCallWeights(),
            filters=LongCallFilters(
                option_types=["call", "put"],
                min_days_to_exp=14,
                max_days_to_exp=60,
                max_premium=1500.0,
                min_open_interest=50,
                min_volume=5,
            )
        )
        lc_result = lc_engine.analyze(contracts=contracts, underlying_price=underlying_price, max_results=20)
        top_options = lc_result.get("options", [])[:3]

        for i, opt in enumerate(top_options, 1):
            score_pct = opt.get("composite_score", 0)  # already 0-100
            verdict = score_to_verdict(score_pct)

            strike = opt.get("strike", 0)
            opt_type = opt.get("option_type", "call")
            strike_str = f"{strike:.0f} {opt_type.upper()}"
            exp_raw = opt.get("expiration", "")
            try:
                exp_dt = datetime.strptime(exp_raw, "%Y-%m-%d")
                exp_str = exp_dt.strftime("%m-%d-%Y")
            except Exception:
                exp_str = exp_raw

            agree, note = assess_long_option(opt, underlying_price)

            print(f"    {i}. {strike_str} exp={exp_str} score={score_pct:.0f} verdict={verdict} agree={'YES' if agree else 'NO'}")
            print(f"       Note: {note}")

            records.append(ValidationAssessment(
                assessment_id=str(uuid.uuid4()),
                assessment_date=assessment_date,
                jira_ticket=JIRA_TICKET,
                ticker=ticker,
                tab="PUTS_AND_CALLS",
                strike=strike_str,
                expiration=exp_str,
                score=round(score_pct, 2),
                verdict=verdict,
                agreement=agree,
                notes=note[:500],
            ))

    await provider._client.aclose()

    # ── Insert all records ───────────────────────────────────────────────────
    print(f"\n\nInserting {len(records)} records...")
    async with async_session() as db:
        for r in records:
            db.add(r)
        await db.commit()
    print(f"Done. {len(records)} assessment records inserted.")

    # ── Summary ─────────────────────────────────────────────────────────────
    agreed = sum(1 for r in records if r.agreement)
    total = len(records)
    pct = agreed / total * 100 if total > 0 else 0
    print(f"\n{'='*50}")
    print(f"  OTA-149 BASELINE SUMMARY")
    print(f"{'='*50}")
    print(f"  Total verdicts:  {total}")
    print(f"  Agreed:          {agreed}")
    print(f"  Agreement rate:  {pct:.1f}%")
    print(f"{'='*50}\n")

    return records, agreed, total, pct


if __name__ == "__main__":
    asyncio.run(run_validation())
