import math
import random
import pytest
from backend.allocation import allocate


def zones(demands):
    return [dict(id=str(i), name=f'Zone {i}', predicted_demand=d) for i,d in enumerate(demands)]


def test_zero_and_excess_supply():
    assert allocate(zones([40, 60]), 0)['allocated'] == 0
    full = allocate(zones([40, 60]), 150)
    assert full['allocated'] == 100
    assert full['shortage'] == 0
    assert full['unused_supply'] == 50
    assert allocate(zones([0, 0]), 10)['coverage_pct'] == 100


def test_priorities_improve_coverage_and_cap_at_demand():
    result = allocate(zones([100, 100]), 120, {'0': 5, '1': 1})
    assert result['zones'][0]['allocation'] == pytest.approx(100)
    assert result['zones'][1]['allocation'] == pytest.approx(20)
    assert result['shortage'] == pytest.approx(80)


def test_random_scenarios_conserve_water():
    rng = random.Random(42)
    for _ in range(200):
        demands = [rng.uniform(0, 5000) for _ in range(7)]
        supply = rng.uniform(0, sum(demands) * 1.5)
        result = allocate(zones(demands), supply, {str(i): rng.randint(1,5) for i in range(7)})
        assert result['allocated'] == pytest.approx(min(supply, sum(demands)))
        assert result['allocated'] + result['unused_supply'] == pytest.approx(supply)
        for row in result['zones']:
            assert 0 <= row['allocation'] <= row['demand']
            assert row['allocation'] + row['shortage'] == pytest.approx(row['demand'])


@pytest.mark.parametrize('supply', [-1, math.nan, math.inf])
def test_invalid_supply(supply):
    with pytest.raises(ValueError):
        allocate(zones([10]), supply)


def test_invalid_scenario():
    with pytest.raises(ValueError):
        allocate(zones([10]), 10, {'0': 0})
    with pytest.raises(ValueError):
        allocate(zones([10]), 10, {'unknown': 2})
