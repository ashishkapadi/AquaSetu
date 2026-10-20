"""Conserve water while distributing a limited shared supply."""
import math


def allocate(zones, supply, priorities=None, demand_multipliers=None):
    priorities = priorities or {}
    demand_multipliers = demand_multipliers or {}
    if not math.isfinite(supply) or supply < 0:
        raise ValueError('Supply must be a finite, nonnegative number.')
    ids = {z['id'] for z in zones}
    if (set(priorities) | set(demand_multipliers)) - ids:
        raise ValueError('Unknown zone in scenario.')
    demands, weights = [], []
    for z in zones:
        weight = float(priorities.get(z['id'], 1))
        multiplier = float(demand_multipliers.get(z['id'], 1))
        if not math.isfinite(weight) or not 1 <= weight <= 5:
            raise ValueError('Priority must be between 1 and 5.')
        if not math.isfinite(multiplier) or not .5 <= multiplier <= 2:
            raise ValueError('Demand multiplier must be between 0.5 and 2.')
        demand = float(z['predicted_demand']) * multiplier
        if not math.isfinite(demand) or demand < 0:
            raise ValueError('Demand must be finite and nonnegative.')
        demands.append(demand)
        weights.append(weight)
    total = sum(demands)
    target = min(supply, total)
    if target >= total:
        amounts = demands[:]
    else:
        lo, hi = 0., 1.
        for _ in range(70):
            scale = (lo + hi) / 2
            used = sum(min(d, scale * w * d) for d, w in zip(demands, weights))
            if used > target:
                hi = scale
            else:
                lo = scale
        amounts = [min(d, lo * w * d) for d, w in zip(demands, weights)]
    rows = []
    for z, d, w, a in zip(zones, demands, weights, amounts):
        shortage = max(0., d - a)
        coverage = 100 * a / d if d else 100.
        rows.append(dict(id=z['id'], name=z['name'], demand=d, allocation=a,
                         shortage=shortage, coverage_pct=coverage, priority=w,
                         risk='high' if coverage < 75 else 'medium' if coverage < 95 else 'low',
                         explanation=f'Priority {w:g}/5; {coverage:.1f}% of forecast demand covered. '
                                     + ('Demand fully covered.' if shortage < 1e-8 else
                                        'Additional supply is still needed to cover the remaining demand.')))
    allocated = sum(amounts)
    return dict(supply=supply, total_demand=total, allocated=allocated,
                shortage=max(0., total - allocated), unused_supply=max(0., supply - allocated),
                coverage_pct=100 * allocated / total if total else 100., zones=rows)
