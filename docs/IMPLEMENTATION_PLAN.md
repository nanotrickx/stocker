# Implementation Plan - ORB Strategy Enhancements

This plan outlines the changes required to refine the **Opening Range Breakout (ORB)** execution engine in `backend/app/engine.py` and `backend/app/orb_strategy.py` based on the user's raw requirements.

## Raw Requirements Analysis
1. **Timeframe:** 1-minute reference candle (9:15 to 9:16 AM).
2. **Double Breakout Confirmation:**
   - First, the index (Nifty 50) must break out above its opening high (bullish) or below its opening low (bearish).
   - Once the index breaks out, the respective option contract (CE for bullish, PE for bearish) must break out above its own first 1-minute candle high.
   - **Invalidation rule:** If the option contract breaks out above its own first candle high *before* the Nifty index spot price breaks out of its opening range, no entry is allowed for that contract.
3. **Premium Filter:**
   - Option entry price must be between ₹100 and ₹200.
   - If the ATM strike premium is above ₹200, shift to OTM strikes until a premium below ₹200 (but >= 100) is selected.
4. **Re-entry / Risk Management (Max 2 trades):**
   - Maximum of 2 entries per day (one High breakout, one Low breakout).
   - First trade: Stop Loss = 10%, Target = 10%.
   - If the first trade hits Stop Loss (10%), wait for the opposite breakout.
   - Second trade (opposite breakout): Stop Loss = 10%, Target = 15%.
5. **Time Cutoff:**
   - No new entries allowed after 11:00 AM IST.

---

## Proposed Changes

### 1. [MODIFY] [orb_strategy.py](file:///Users/shady/Content/Nanotricks/Stocker/backend/app/orb_strategy.py)
Extend `ORBState` to hold:
- `selected_ce_strike` & `selected_pe_strike`
- `ce_option_opening_high` & `pe_option_opening_high`
- `ce_option_already_broke_out` & `pe_option_already_broke_out`
- `index_high_broke_out` & `index_low_broke_out`
- `trades_taken`: List of strings/dicts containing trade directions taken today (e.g. `["BULLISH"]` or `["BEARISH"]`).
- `first_trade_hit_sl`: boolean indicating if the first trade was stopped out.

### 2. [MODIFY] [engine.py](file:///Users/shady/Content/Nanotricks/Stocker/backend/app/engine.py)
Refactor `evaluate_orb_strategy`:
- **Phase: WAITING_OPENING_CANDLE (at 9:16 AM):**
  - Record Nifty 50 first candle High, Low, and Close.
  - Calculate ATM strike for CE and PE.
  - Estimate CE premium and PE premium at the opening candle.
  - Calculate CE opening high ($P_{CE\_high}$ at index high) and PE opening high ($P_{PE\_high}$ at index low).
  - Transition to `WAITING_BREAKOUT`.
- **Phase: WAITING_BREAKOUT:**
  - Every 5-second tick:
    - Estimate current CE and PE option premiums based on current index spot price.
    - If current time is after 11:00 AM IST and no position is open, do not enter.
    - Track if CE premium crosses its opening high before index breaks high. If yes, set `ce_option_already_broke_out = True`.
    - Track if PE premium crosses its opening high before index breaks low. If yes, set `pe_option_already_broke_out = True`.
    - Check if index spot crosses opening high -> `index_high_broke_out = True`.
    - Check if index spot crosses opening low -> `index_low_broke_out = True`.
    - **Trigger CE Entry:** If `index_high_broke_out` is True, `ce_option_already_broke_out` is False, and the current CE premium crosses above `ce_option_opening_high`.
    - **Trigger PE Entry:** If `index_low_broke_out` is True, `pe_option_already_broke_out` is False, and the current PE premium crosses above `pe_option_opening_high`.
    - Apply the 100-200 premium filter on strike selection dynamically.
    - Apply appropriate Target (10% for first trade, 15% if first trade hit SL) and SL (10%).
- **Phase: IN_POSITION:**
  - Monitor options premium for target/SL exit.
  - If a trade exits, check exit reason.
  - If target hit or EOD, transition to `DONE`.
  - If stop loss hit:
    - Increment trade count.
    - If `trade_count < 2`, transition back to `WAITING_BREAKOUT` so the opposite breakout can be traded.
    - Else, transition to `DONE`.

---

## Verification Plan

### Automated Tests
- Build and run unit tests or manual script simulations on simulated spot movements to verify all double breakout conditions and re-entry targets.
