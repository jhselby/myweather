"""Sanity checks on the GOES high-top ch truth (v0.7.171): missed tops vs the cloud mask, daytime sunlight by GOES/model
high-cloud class, conditional MAE + bias by band. Run from the repo root: PYTHONPATH=. .venv/bin/python analysis/ch_goes_truth_check.py"""
import json, collections, statistics as st
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ET=ZoneInfo("America/New_York"); OUTD=Path("analysis/output")
G={}; NHT={}
for l in open(OUTD/"goes_cloud_layers.jsonl"):
    r=json.loads(l); G[r["hour"]]=100*sum(1 for v in r["ht"] if v is not None and v>=6000)/9; NHT[r["hour"]]=r["n_ht"]
M={}
for l in open(OUTD/"goes_cc_truth.jsonl"):
    r=json.loads(l); M[r["hour"]]=r.get("cf3")
def utc(vt): return datetime.strptime(vt[:16],"%Y-%m-%dT%H:%M").replace(tzinfo=ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
# A: missed tops
both=[h for h in G if h in M and M[h] is not None]
miss=[h for h in both if M[h]>=0.67 and NHT[h]<=2]
print(f"A. hours with mask+heights {len(both)}; mask cloudy (>=2/3) but <=2 heights: {len(miss)} ({100*len(miss)/max(1,len(both)):.1f}%)")
# sr clearness (lead 0, one per valid hour)
p=Path.home()/".cache/myweather/forecast_error_log.jsonl"
SR={}; CH=collections.defaultdict(list)
with open(p) as f:
    for line in f:
        if '"field": "sr"' in line:
            r=json.loads(line)
            if r.get("lead_h")==0 and r.get("observed") is not None: SR[r["valid_time"][:13]]=r["observed"]
        elif '"field": "ch"' in line:
            r=json.loads(line); L=r.get("lead_h")
            if L is None or r.get("forecast_l1") is None or r.get("forecast_raw_nbm") is None: continue
            g=G.get(utc(r["valid_time"]))
            if g is None: continue
            CH[r["valid_time"][:13]].append((L,r["forecast_l1"],r["forecast_raw_nbm"],g))
# clear-sky envelope: max sr at same local hour within +-4 days
def env(k):
    d=datetime.strptime(k,"%Y-%m-%dT%H"); best=0
    for o,v in SR.items():
        do=datetime.strptime(o,"%Y-%m-%dT%H")
        if do.hour==d.hour and abs((do-d).days)<=4: best=max(best,v)
    return best
cls=collections.defaultdict(list)
for k,rows in CH.items():
    if k not in SR: continue
    e=env(k)
    if e<150: continue
    ci=SR[k]/e
    L,hr,nb,g=min(rows)  # shortest lead
    for tag,ok in (("goes0_nbm>=50",g==0 and nb>=50),("goes0_nbm<20",g==0 and nb<20),("goes>=67",g>=67),
                   ("goes0_hrrr>=50",g==0 and hr>=50),("goes0_hrrr<20",g==0 and hr<20),("goes>=67_hrrr<20",g>=67 and hr<20),("goes>=67_hrrr>=50",g>=67 and hr>=50)):
        if ok: cls[tag].append(ci)
print("B. daytime clearness (obs sr / clear-day envelope), median [n]:")
for t,v in cls.items(): print(f"   {t:15} {st.median(v):.2f}  [{len(v)}]")
# C: conditional MAE + bias, all leads, by band
def band(L): return "0-5" if L<6 else "6-11" if L<12 else "12-23" if L<24 else "24-47"
A=collections.defaultdict(lambda:[0,0,0,0,0]); C=collections.defaultdict(lambda:[0,0,0]); days=collections.defaultdict(lambda:[0,0,0])
for k,rows in CH.items():
    for L,hr,nb,g in rows:
        a=A[band(L)]; a[0]+=abs(hr-g); a[1]+=abs(nb-g); a[2]+=hr-g; a[3]+=nb-g; a[4]+=1
        if g>=33: c=C[band(L)]; c[0]+=abs(hr-g); c[1]+=abs(nb-g); c[2]+=1
        if 6<=L<48: dd=days[k[:10]]; dd[0]+=abs(hr-g); dd[1]+=abs(nb-g); dd[2]+=1
print("C. all hours: MAE hrrr/nbm, bias hrrr/nbm  | GOES high>=33%: MAE hrrr/nbm n")
for b in ("0-5","6-11","12-23","24-47"):
    a=A[b]; c=C[b]; n=a[4] or 1; m=c[2] or 1
    print(f"   {b:6} {a[0]/n:5.1f} {a[1]/n:5.1f}  {a[2]/n:+6.1f} {a[3]/n:+6.1f} | {c[0]/m:5.1f} {c[1]/m:5.1f} {c[2]}")
w=sum(1 for v in days.values() if v[0]<v[1]); print(f"   days HRRR better (6-47h): {w}/{len(days)}")
print(f"   GOES high>0 in {100*sum(1 for h in G.values() if h>0)/len(G):.0f}% of {len(G)} hours")
