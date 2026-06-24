"""Stage 0 — Lightning proximity × downstream MAE.

When Tempest stations report close lightning, the atmosphere is in
thunderstorm regime — distinct from regular regimes. Does cloud/wind MAE
blow up around lightning events?

Pair log doesn't carry lightning per-pair, but we can pull recent
thunderstorm flags from live weather_data["derived"]["thunderstorm"]
snapshots. Without historical snapshots, fall back to a simpler test:
do pa-elevated periods (precip_amount observed > threshold) correlate
with cloud/wind MAE elevation?

That's redundant with precip_obs which we already tested. Better angle:
join pair log with the Tempest lightning_strike_last_3hr / lightning_distance
fields from the obs_temp_log... which aren't in the pair log either.

Compromise: use sky_override pattern from briefing — when sky_override is
'thunder' the model deviated from baseline. But sky_override is in
weather_data not pair log.

Honest answer: this hypothesis needs lightning data that isn't in the pair
log. Document as "NOT DOABLE FROM PAIR LOG", skip, recommend logging
lightning_count in pair-log rows.
"""
print("Lightning proximity hypothesis: NOT DOABLE FROM PAIR LOG.")
print()
print("The pair log doesn't carry lightning data per row. Tempest station")
print("history records lightning_strike_last_3hr and lightning_strike_last_distance,")
print("but those live in station_history.json, not forecast_error_log.jsonl.")
print()
print("Infrastructure needed: add a `lightning_proximity_km` field to each pair")
print("when the row is logged in forecast_error_log.py. Source: minimum of")
print("Tempest station lightning_distance fields within last hour, or a 'none'")
print("flag if no Tempest reports lightning.")
print()
print("Then this hypothesis becomes testable: does MAE on cloud/wind/temp blow")
print("up when lightning_proximity_km < 20 vs > 50?")
print()
print("→ Logged as INFRASTRUCTURE GAP, not killed. Re-test once pair log has")
print("  the field.")
