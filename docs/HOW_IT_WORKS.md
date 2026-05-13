# How It Works

MyWeather doesn't just display model forecasts. Every temperature reading you see has been corrected using a network of 38 local weather stations — 29 personal stations from Weather Underground and 9 Tempest stations — all within 1.5 miles of Wyman Cove.

## The problem with weather models

Numerical weather models like HRRR and GFS are remarkably good at predicting large-scale atmospheric patterns: storm tracks, pressure systems, frontal passages. But they run on grids with cells several kilometers wide. A single grid cell covers the entire Marblehead Neck peninsula and the open water beyond it. The model has no idea that Wyman Cove sits at the end of a narrow spit of land surrounded by Salem Sound, or that an afternoon sea breeze from the southeast arrives here an hour before it reaches the airport.

The result: on a clear summer afternoon, the model might say 78°F while every thermometer within a mile reads 74°F. That four-degree gap is real, systematic, and predictable.

## Local stations as correction

The most direct fix is to look outside. With 38 stations within 1.5 miles, we have a dense network of actual measurements. Each station's reading is weighted by two factors: how close it is (nearer stations matter more, following an inverse-square relationship) and how similar its elevation is to Wyman Cove (stations at a similar height are more representative).

The weighted average of what those stations are reading gives us a correction to apply to the model. If the model says 78°F and the stations collectively say 74°F, we correct down.

## The self-calibration problem

Personal weather stations aren't government-grade sensors. They sit on rooftops, in gardens, next to brick walls. Some run consistently warm. Some run cold. If you average them naively, the bad actors drag the answer in the wrong direction.

The solution is a technique called leave-one-out calibration. Every 10 minutes, each station is compared not to an external reference, but to the consensus of all its neighbors. If one station consistently reads 2.7°F warmer than every other station around it, that's not weather — that's a miscalibrated sensor. We track that chronic offset over a 48-hour rolling window and subtract it before the station contributes to the correction.

This runs separately for temperature, humidity, and pressure. Temperature also splits by time of day: a station shaded by a tree in the afternoon might read accurately at midnight but run cool during the day. The system learns both patterns independently.

## Knowing when not to trust the stations

On most days, the 30+ active stations agree within about 1°F of each other. When they agree, we trust them almost completely.

But sometimes they don't — during a fast-moving front, when sensors are icing up, or when half the network goes offline overnight. Blindly averaging disagreeing stations would produce a worse answer than just using the model.

We handle this with a blend factor that determines how much of the station-based correction to apply. When stations strongly agree, stations get 90% of the say. When they moderately agree, 65%. When they're noisy or sparse, 40% — and the model gets meaningful weight back. This is the same principle used by the National Weather Service in its Real-Time Mesoscale Analysis, which blends model output with surface observations the same way.

## KBVY as an outside check

The leave-one-out approach is a closed loop: stations calibrate against each other. If the entire network drifts warm together — say, a hot summer with every station absorbing more radiant heat — the system won't catch it, because every station looks fine relative to its neighbors.

Beverly Municipal Airport (KBVY), 6.3 miles northwest, is the outside check. It's an FAA-certified ASOS station, maintained by the National Weather Service to instrument-grade standards. We log the difference between our local corrected temperature and KBVY's reading every 10 minutes. Over time, that gap reveals the normal marine and elevation offset between the airport and Wyman Cove. If it suddenly widens or narrows, it signals that the local network has shifted as a whole.

## Wind

Wind is handled differently. A weighted average of wind speeds across 38 stations would be meaningless — wind varies too much over short distances depending on terrain, buildings, and fetch. Instead, we take the highest observed gust from any station or the airport, on the principle that at an exposed coastal site, the highest reading is the most relevant one. That observed value is then blended into the 24-hour forecast with a linear decay, so the forecast transitions smoothly from what's actually happening now to what the model expects later.

## What you see

The temperature on the main screen is the output of all of the above: model baseline, corrected by a self-calibrating network of local stations, blended with a confidence-weighted gain, validated against a certified reference station 6 miles away. It updates every 10 minutes.
