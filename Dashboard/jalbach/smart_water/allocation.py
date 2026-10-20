"""Direct transfers with lexicographic priority then cost optimization."""
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from .data import ValidationError

TRANSFER_COLUMNS=['timestamp','source_zone','destination_zone','volume_m3','unit_cost','reason']


def risk(percent,medium=10.,high=25.):
    return np.select([percent<=0,percent<medium,percent<high],['None','Low','Medium'],default='High')


def shortage_plan(forecast,supply,zones,conservative=False,medium=10.,high=25.):
    if not 0 < medium < high <= 100:
        raise ValidationError('Risk thresholds must satisfy 0 < medium < high <= 100%.')
    plan=forecast.merge(supply,on=['timestamp','zone_id'],how='left',validate='one_to_one')
    if plan.available_supply_m3.isna().any():
        missing=plan.loc[plan.available_supply_m3.isna(),['timestamp','zone_id']].head(3)
        raise ValidationError(f'Supply schedule does not cover all forecast intervals. Missing examples: {missing.to_dict("records")}. '
                              'Provide explicit interval deliveries; missing supply is not assumed zero.')
    plan=plan.merge(zones[['zone_id','zone_name','priority_weight']],on='zone_id',validate='many_to_one')
    plan['planned_demand']=plan.upper_m3 if conservative else plan.predicted_demand
    plan['shortage_m3']=(plan.planned_demand-plan.available_supply_m3).clip(lower=0)
    plan['surplus_m3']=(plan.available_supply_m3-plan.planned_demand).clip(lower=0)
    plan['shortage_pct']=np.divide(plan.shortage_m3,plan.planned_demand,out=np.zeros(len(plan)),where=plan.planned_demand.to_numpy()>0)*100
    plan['risk']=risk(plan.shortage_pct,medium,high)
    return plan


def allocate(plan,connections,method='Optimization',medium=10.,high=25.):
    if method not in ('Optimization','Priority baseline'):
        raise ValueError('Unknown allocation method.')
    transfers=[]
    for timestamp,block in plan.groupby('timestamp'):
        block=block.set_index('zone_id')
        # Bounded demand/risk multipliers keep declared priorities meaningful.
        maximum=max(float(block.predicted_demand.max()),1e-9)
        score=block.priority_weight*(1+block.shortage_pct/100)*(1+block.predicted_demand/maximum)
        donors=block.surplus_m3.to_dict()
        needs=block.shortage_m3.to_dict()
        edges=[e for e in connections.itertuples() if donors.get(e.source_zone,0)>0 and needs.get(e.destination_zone,0)>0 and e.capacity_m3>0]
        if not edges:
            continue
        if method=='Priority baseline':
            edges.sort(key=lambda e:(-score.loc[e.destination_zone],e.transfer_cost,e.source_zone,e.destination_zone))
            volumes=[]
            for edge in edges:
                amount=min(donors[edge.source_zone],needs[edge.destination_zone],edge.capacity_m3)
                donors[edge.source_zone]-=amount
                needs[edge.destination_zone]-=amount
                volumes.append(amount)
        else:
            constraints=[]
            bounds=[]
            for zone in block.index:
                constraints.append([float(e.source_zone==zone) for e in edges]); bounds.append(donors[zone])
                constraints.append([float(e.destination_zone==zone) for e in edges]); bounds.append(needs[zone])
            weights=np.array([score.loc[e.destination_zone] for e in edges])
            limits=[(0,e.capacity_m3) for e in edges]
            first=linprog(-weights,A_ub=constraints,b_ub=bounds,bounds=limits,method='highs')
            if not first.success:
                raise RuntimeError(f'Allocation solver failed: {first.message}')
            # Preserve the optimal weighted amount served, then minimize transfer cost.
            costs=np.array([e.transfer_cost for e in edges])
            second=linprog(costs,A_ub=constraints,b_ub=bounds,A_eq=[weights],b_eq=[float(weights@first.x)],bounds=limits,method='highs')
            if not second.success:
                raise RuntimeError(f'Cost optimization failed: {second.message}')
            volumes=second.x
        for edge,volume in zip(edges,volumes):
            if volume>1e-8:
                transfers.append({'timestamp':timestamp,'source_zone':edge.source_zone,'destination_zone':edge.destination_zone,
                    'volume_m3':float(volume),'unit_cost':edge.transfer_cost,
                    'reason':f'{edge.source_zone} retains its planned demand; {edge.destination_zone} has unmet demand '
                             f'(priority {block.loc[edge.destination_zone,"priority_weight"]:g}, demand {block.loc[edge.destination_zone,"predicted_demand"]:g} m³, shortage {block.loc[edge.destination_zone,"shortage_pct"]:.1f}%, allocation score {score.loc[edge.destination_zone]:.2f}). Allowed direct connection; '
                             f'capacity {edge.capacity_m3:g} m³/interval. {method}.'})
    transfers=pd.DataFrame(transfers,columns=TRANSFER_COLUMNS)
    result=plan.copy()
    if transfers.empty:
        result['received_m3']=0.; result['sent_m3']=0.
    else:
        incoming=transfers.groupby(['timestamp','destination_zone']).volume_m3.sum().rename('received_m3')
        outgoing=transfers.groupby(['timestamp','source_zone']).volume_m3.sum().rename('sent_m3')
        result=result.merge(incoming,left_on=['timestamp','zone_id'],right_index=True,how='left')
        result=result.merge(outgoing,left_on=['timestamp','zone_id'],right_index=True,how='left')
        result[['received_m3','sent_m3']]=result[['received_m3','sent_m3']].fillna(0.)
    result['supply_after_m3']=result.available_supply_m3+result.received_m3-result.sent_m3
    result['remaining_shortage_m3']=(result.planned_demand-result.supply_after_m3).clip(lower=0)
    result['remaining_shortage_pct']=np.divide(result.remaining_shortage_m3,result.planned_demand,out=np.zeros(len(result)),where=result.planned_demand.to_numpy()>0)*100
    result['risk_after']=risk(result.remaining_shortage_pct,medium,high)
    # Runtime invariants catch regressions before displaying a recommendation.
    if (result.sent_m3-result.surplus_m3>1e-6).any() or (result.received_m3-result.shortage_m3>1e-6).any():
        raise RuntimeError('Allocation violated donor or recipient constraints.')
    if not np.isclose(result.sent_m3.sum(),result.received_m3.sum(),atol=1e-6):
        raise RuntimeError('Allocation violated conservation.')
    return result,transfers
