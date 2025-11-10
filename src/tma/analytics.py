import math, numpy as np, pandas as pd
from typing import Tuple
from .config import MARKET_FEE

def fmt_int(x): return f"{x:,.0f}"
def fmt_pct(x): return f"{x:.2%}"

def get_prices_amounts(row):
    prices, amnts = [], []
    for i in range(1, 11):
        p = pd.to_numeric(row.get(f"price_{i}"), errors="coerce")
        a = pd.to_numeric(row.get(f"amount_{i}"), errors="coerce")
        if pd.notna(p) and p > 0 and pd.notna(a) and a > 0:
            prices.append(int(p)); amnts.append(int(a))
    return prices, amnts

def min_price_and_amount(prices, amnts):
    if not prices: return np.nan, np.nan
    idx = int(np.argmin(prices))
    return int(prices[idx]), int(amnts[idx])

def max_price(prices):
    if not prices: return np.nan
    return int(np.max(prices))

def weighted_mean_all(prices, amnts):
    if not prices: return np.nan
    total_units = int(np.sum(amnts))
    if total_units == 0: return np.nan
    mean_val = np.dot(prices, amnts) / total_units
    return int(math.ceil(mean_val))

def mean_first_n_units(prices, amnts, n_units=20):
    if not prices: return (np.nan, 0, np.nan)
    arr = sorted(zip(prices, amnts), key=lambda x: x[0])
    remain, total_cost, used = n_units, 0, 0
    for p, a in arr:
        if remain <= 0: break
        take = min(a, remain)
        total_cost += int(p) * int(take)
        used += take
        remain -= take
    if used == 0: return (np.nan, 0, np.nan)
    mean_val = total_cost / used
    return (int(math.ceil(mean_val)), int(used), int(total_cost))

def cv_of_prices(prices):
    if not prices: return np.nan
    if len(prices) == 1: return 0.0
    mean = float(np.mean(prices))
    if mean == 0: return np.nan
    return float(np.std(prices, ddof=1) / mean)

def analyze_market(df_market: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    kpi_rows, sugg_rows = [], []
    for _, row in df_market.iterrows():
        item_id   = row.get("item_id")
        item_name = row.get("item_name")
        item_type = row.get("item_type")
        avg_price_api = pd.to_numeric(row.get("average_price"), errors="coerce")
        avg_price_api = int(avg_price_api) if pd.notna(avg_price_api) else np.nan
        my_qty = int(pd.to_numeric(row.get("my_quantity"), errors="coerce") or 1)

        prices, amnts = get_prices_amounts(row)
        p_min, q_at_min = min_price_and_amount(prices, amnts)
        p_max           = max_price(prices)
        total_stock     = int(np.sum(amnts)) if amnts else 0
        wmean_all       = weighted_mean_all(prices, amnts)
        mean20, units_used20, cost20 = mean_first_n_units(prices, amnts, n_units=20)
        cv_p            = cv_of_prices(prices)

        if pd.notna(p_min) and pd.notna(p_max):
            spread = int(p_max - p_min)
            spread_pct = (spread / p_min) if p_min > 0 else np.nan
        else:
            spread, spread_pct = np.nan, np.nan

        kpi_rows.append({
            "item_id": item_id,
            "item_name": item_name,
            "item_type": item_type,
            "average_price_api": avg_price_api,
            "price_min": p_min,
            "amount_at_min": q_at_min,
            "price_mean_20u": mean20,
            "units_used_for_20u": units_used20,
            "depth20_total_cost": cost20,
            "price_max": p_max,
            "weighted_mean_all_units": wmean_all,
            "price_range": spread,
            "spread_pct": spread_pct,
            "cv_price": cv_p,
            "total_stock": total_stock,
            "my_quantity": my_qty,
        })

        sell_price = mean20 if pd.notna(mean20) and mean20 > 0 else wmean_all
        if pd.isna(sell_price) or sell_price <= 0: sell_price = avg_price_api if pd.notna(avg_price_api) and avg_price_api > 0 else np.nan

        if pd.notna(sell_price) and sell_price > 0 and my_qty > 0:
            gross = int(sell_price) * my_qty
            fee   = int(math.ceil(gross * MARKET_FEE))
            net   = int(gross - fee)
            net_per_unit = int(math.ceil(net / my_qty))
        else:
            sell_price = gross = fee = net = net_per_unit = np.nan

        sugg_rows.append({
            "item_id": item_id,
            "item_name": item_name,
            "my_quantity": my_qty,
            "suggest_sell_price": sell_price,
            "gross_revenue": gross,
            "market_fee_5pct": fee,
            "net_revenue": net,
            "net_per_unit": net_per_unit,
            "ref_price_min": p_min,
            "ref_price_mean_20u": mean20,
            "ref_weighted_mean_all": wmean_all,
        })

    return pd.DataFrame(kpi_rows), pd.DataFrame(sugg_rows)