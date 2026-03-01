# Smart Weighting Implementation - Wyman Cove Weather

## What Changed

Upgraded the hyperlocal temperature correction from simple replacement to **smart distance+elevation weighted bias correction**.

## Before (Simple Method)
```python
bias_temp = wu_observed - model_temp
corrected_temp = wu_observed  # Just replace model with observation
```

**Problem:** This treats the WU multi-station average as gospel truth for YOUR location, ignoring the fact that:
- Stations are at different distances
- Stations are at different elevations (0-82ft vs your 30ft)
- Some stations might have stale or bad data
- The model actually has value - it's gridded to YOUR exact coordinates

## After (Smart Method)
```python
# For each good station:
bias_at_station = station_obs - model_temp  # Model is biased
weight = (1/distance²) × exp(-|elev_diff|/30)  # Distance + elevation
weighted_bias = Σ(bias × weight) / Σ(weight)
corrected_temp = model_temp + weighted_bias  # Correct the model
```

**Why this is better:**
1. **Uses model for YOUR location** - The GFS/HRRR model is already optimized for 42.5014, -70.8750
2. **Applies smart corrections** - Uses nearby stations to fix systematic model errors
3. **Weights by distance** - Closer stations matter more (inverse square law)
4. **Weights by elevation** - Stations at 30ft matter more than stations at 82ft
5. **Quality filtering** - Rejects stale data (>30min) and outliers (>2σ)

## Quality Filtering Applied

**Data Freshness:**
- Reject stations with data >30 minutes old
- Only use stations with valid temperature + distance

**Outlier Rejection:**
- Calculate median temperature across all stations
- Calculate standard deviation
- Reject stations >2σ from median
- Prevents one broken sensor from skewing results

**Minimum Threshold:**
- Require at least 3 good stations
- Fall back to simple method if insufficient data

## Weighting Formula

**Distance Weight:**
```
dist_weight = 1 / (distance_miles²)
```
- Station 0.5 mi away: weight = 4.0
- Station 1.0 mi away: weight = 1.0  
- Station 2.0 mi away: weight = 0.25

**Elevation Weight:**
```
elev_weight = exp(-|station_elev - 30ft| / 30)
```
Characteristic scale = 30ft (chosen to match typical elevation variations in Marblehead)
- Same elevation (30ft): weight = 1.0
- 15ft different: weight = 0.61
- 30ft different: weight = 0.37
- 60ft different: weight = 0.14

**Combined Weight:**
```
total_weight = dist_weight × elev_weight
```

## New Diagnostics Added

The hyperlocal object now includes:

```json
{
  "model_temp": 28.5,           // Model forecast for YOUR location
  "wu_temp": 29.8,              // Weighted average of WU stations
  "bias_temp": 1.3,             // Weighted bias (not simple difference)
  "corrected_temp": 29.8,       // Model + weighted bias
  "stations_used": 10,          // After quality filtering
  "stations_total": 15,         // Total available
  "effective_radius_mi": 1.2,   // Weighted average distance
  "confidence": "High"          // Based on station agreement
}
```

**Confidence Levels:**
- **High**: Station biases agree within 1°F (std < 1.0)
- **Moderate**: Station biases agree within 2°F (std < 2.0)  
- **Low**: Station biases scattered >2°F (std >= 2.0)

## Display Recommendations

Update the Hyperlocal Comparison card in `index.html` to show:

1. **Station metadata row:**
   - "Using 10 of 15 stations"
   - "Effective radius: 1.2 mi"
   - "Confidence: High"

2. **Keep existing temp display but add context:**
   ```
   TEMPERATURE
   Model (GFS)     28.5°F
   WU Multi-Station 29.8°F (weighted avg)
   Bias            +1.3°F (distance+elevation weighted)
   Corrected       29.8°F (model + bias)
   ```

3. **Optional: Show rejected stations**
   - "Rejected 2 outliers, 3 stale"

## Testing Notes

The smart weighting will show differences from the simple method when:
- Stations cluster at different elevations
- Some stations are much closer than others
- Outlier stations exist (broken sensors)
- Data freshness varies

It will produce similar results to simple method when:
- All stations roughly same distance/elevation
- All stations reporting similar values
- All data fresh and good quality

## Fallback Behavior

If smart weighting fails (not enough good stations), falls back to simple method:
```python
corrected_temp = wu_observed  # Same as before
```

This ensures robustness - you never lose corrections even if scraper has issues.

## Next Steps (Wind - Phase 2)

Apply similar logic to wind corrections with directional exposure:
```python
# Weight stations based on exposure similarity
if wind from NW:
    weight = dist_weight × elev_weight × exposure_similarity
```

Where `exposure_similarity` gives higher weight to stations with similar NW exposure.
