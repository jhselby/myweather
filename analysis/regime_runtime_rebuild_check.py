import json, sys, collections
sys.path.insert(0,'.')
from weather_collector.processors.regime_classifier import classify_synoptic_regime as cls
P='/Users/josephselby/.cache/myweather/forecast_error_log.jsonl'
# pass 1: per (run,valid) gather HRRR-side (pre-swap) value + selector source for wd ws t cc
pre=collections.defaultdict(dict); src=collections.defaultdict(dict); rows=[]
def hrrr(r):
    for k in ('forecast_l1r','forecast_l6','forecast_l5','forecast_l4','forecast_l3','forecast_l2','forecast_l1'):
        if r.get(k) is not None: return r[k]
for line in open(P):
    r=json.loads(line)
    if r['run_time']<'2026-09-29': continue
    key=(r['run_time'],r['valid_time']); f=r['field']
    if f in ('wd','ws','t','cc'):
        pre[key][f]=hrrr(r); src[key][f]=r.get('selector_source')
    if f=='sr' or f=='t':
        rows.append((key,f,r['lead_h'],r['state_fc'],r.get('selector_mechanism')))
tot=dis=0; by_swap=collections.Counter(); trans=collections.Counter(); sr_learn=collections.Counter()
for key,f,lead,sfc,mech in rows:
    p=pre.get(key,{})
    if not all(k in p for k in ('wd','ws','t','cc')): continue
    hr=int(key[1][11:13])
    r_pre=cls(p['wd'],p['ws'],sfc.get('pressure_in'),sfc.get('pressure_trend_hpa_3h'),hr,p['t'],cloud_cover=p['cc'])
    r_log=sfc.get('regime_synoptic')
    swapped=any(src[key].get(k)=='nbm' for k in ('wd','ws','t','cc'))
    if f=='t':
        tot+=1; d=r_pre!=r_log; dis+=d; by_swap[(swapped,d)]+=1
        if d: trans[(r_pre,r_log)]+=1
    if f=='sr' and mech=='learned_gbm':
        b='0-5' if lead<6 else '6-11' if lead<12 else '12-23' if lead<24 else '24-47'
        sr_learn[(r_pre,b)]+=1
print(f"rows {tot}  label disagreement {dis} ({100*dis/tot:.1f}%)")
for s in (False,True):
    n=by_swap[(s,False)]+by_swap[(s,True)]
    if n: print(f"  any of wd/ws/t/cc routed to NBM={s}: n={n} disagree {100*by_swap[(s,True)]/n:.1f}%")
print("top transitions (runtime -> logged):", trans.most_common(8))
print("sr learned_gbm rows by RECOMPUTED runtime cell:", sorted(sr_learn.items(), key=lambda x:-x[1])[:10])

# paired read by runtime cell
S=collections.defaultdict(lambda:[0,0.0,0.0]); D=collections.defaultdict(lambda:[0,0.0,0.0])
for line in open(P):
    if '"field": "sr"' not in line or 'learned_gbm' not in line: continue
    r=json.loads(line)
    if r['run_time']<'2026-09-29' or r.get('selector_mechanism')!='learned_gbm' or r.get('error_l5_nbm') is None: continue
    key=(r['run_time'],r['valid_time']); p=pre.get(key,{})
    if not all(k in p for k in ('wd','ws','t','cc')): continue
    sfc=r['state_fc']; hr=int(key[1][11:13])
    reg=cls(p['wd'],p['ws'],sfc.get('pressure_in'),sfc.get('pressure_trend_hpa_3h'),hr,p['t'],cloud_cover=p['cc'])
    l=r['lead_h']; b='0-5' if l<6 else '6-11' if l<12 else '12-23' if l<24 else '24-47'
    a=abs(r['error_'+r['applied_layer']]); bp=abs(r['error_l5_nbm'])
    for T,k in ((S,(reg,b)),(D,(reg,b,r['obs_time'][:10]))):
        T[k][0]+=1; T[k][1]+=a; T[k][2]+=bp
print("\nPAIRED by runtime cell (served vs band_pool error_l5_nbm):")
for k,(n,a,b) in sorted(S.items()): print(k, n, f"served {a/n:6.2f} pool {b/n:6.2f}", f"{100*(b-a)/b:+.1f}%" if b else "n/a")
print("\nnw_flow/12-23 by day:")
for k,(n,a,b) in sorted(D.items()):
    if k[:2]==('nw_flow','12-23') and b: print(k[2], n, f"{a/n:6.2f} vs {b/n:6.2f} {100*(b-a)/b:+.1f}%")
