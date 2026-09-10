1. Project setup
   - Created the project folder structure for raw data, processed data, external archives, models, scripts, and map outputs.
   - Set up a Python virtual environment and installed the required data-science libraries.
   - Your project can now keep downloaded data, clean data, ML outputs, and maps separately.
2. Live NASA FIRMS data download
   - Connected the project to NASA FIRMS, which provides satellite thermal-anomaly detections.
   - Downloaded recent global thermal detections from the FIRMS API.
   - Learned that the normal FIRMS API endpoint provides up to the last 5 days at one time.
   - The downloader can fetch worldwide data, not just India.
A detection means that a satellite saw an unusually hot location. It could be a wildfire, crop burning, gas flare, power plant, refinery, industrial process, volcano, and more.
3. Data exploration
   - Built scripts to inspect downloaded FIRMS CSV files.
   - Checked:
     - Number of detections
     - Columns available
     - Missing values
     - Dates
     - Day/night detection counts
     - Confidence levels
     - Temperature values
     - FRP values
FRP means Fire Radiative Power. In simple words, it is an estimate of how strongly the satellite observed thermal energy from that location.
4. Basic hotspot analysis
   - Built hotspot analysis using nearby/repeated thermal detections.
   - Identified locations where satellite detections occur repeatedly.
   - Calculated useful values such as:
     - Total detections
     - Average FRP
     - Maximum FRP
     - Average temperature
     - Number of active days
This gives us a first way to separate one-time fire events from places that appear active repeatedly.
5. Interactive global maps
   - Created interactive Leaflet/Folium maps that show thermal detections around the world.
   - Added marker clustering, so dense areas do not overload the map.
   - Created maps for:
     - Raw recent FIRMS detections
     - Historical hotspots
     - Historical risk hotspots
     - Live alerts
     - Hybrid ML + historical alerts
The repeating world map issue is only a visual/UI issue with map tiles. The data and alert logic are still working correctly. We can fix the UI later.
6. Downloaded a large historical NASA archive
   - Requested and downloaded the official 2025 worldwide VIIRS NOAA-20 historical archive from NASA FIRMS.
   - The ZIP was about 1.4 GB compressed.
   - Processed it safely in chunks, so the laptop did not need to load all data into memory at once.
Historical archive result:
- Total records processed: 18,466,569
- Invalid timestamps removed: 0
- Output created: archive_2025_noaa20_clean.csv
This historical data is the foundation for understanding which locations have repeated thermal activity across a full year.
7. Used FIRMS “type” as a weak training clue
The archive includes a type field. We used it carefully:
- type = 0: vegetation fire-like detection
- type = 2: other static land source
We extracted type = 2 locations as likely static thermal-source candidates.
Important: type = 2 does not guarantee “industrial facility.” It is only a useful starting clue. It may include oil/gas activity, industrial heat, and other persistent non-vegetation thermal sources.
8. Built historical static-source hotspots
   - Grouped nearby historical type-2 detections into grid-based hotspots.
   - Used a roughly 0.05-degree grid, approximately a few kilometres wide.
   - Calculated how persistent each hotspot was through 2025.
This changed the project from “a list of millions of satellite points” into “a manageable list of repeated thermal locations.”
9. Created a manual-labeling workflow
   - Created a geographically diverse hotspot sample.
   - Created an interactive map for manually checking whether selected hotspots look industrial.
   - Started OpenStreetMap-based enrichment for nearby industrial evidence.
One hotspot was confidently connected to an OSM petroleum feature. However, OSM/Overpass public servers were unreliable, so we did not pretend that missing OSM information means a location is not industrial.
10. Historical industrial thermal-risk scoring
    - Created a risk-scoring system for historical hotspots.
    - Combined:
      - Persistence across days
      - Number of detections
      - Thermal intensity / FRP
      - Night-time activity
Why night-time matters: a source active at night can sometimes be more consistent with fixed operations, because sunlight-related effects and some day-only activity are reduced. But it is still only evidence, not proof.
The risk score categorizes hotspots into:
- High
- Medium
- Low
A “High” score means a high-priority repeated thermal source candidate. It does not mean a confirmed industrial incident or an emergency.
11. Live detections matched with historical behavior
    - Built a script that compares new live FIRMS detections against historical hotspot risk.
    - If a current detection appears near a historically persistent thermal location, it receives more attention.
This lets the project answer a more useful question:
“Is this new heat detection happening in a location that has shown repeated thermal activity before?”

12. First machine-learning model
    - Created an ML training sample from the 2025 archive.
    - Trained a classifier to separate:
      - likely static-source-like detections (type = 2)
      - vegetation-fire-like detections (type = 0)
    - Saved the trained model here:
models/static_source_classifier_2025.joblib
Training result:
- Test accuracy: about 96%
- ROC-AUC: about 0.989
This is technically a strong result for reproducing the historical FIRMS type labels.
Important limitation: this does not mean the model is “96% accurate at identifying industries.” It is currently a baseline model learning the FIRMS type-0/type-2 pattern. We will improve it later with better labels, spatial testing, and external industrial datasets.
13. Used the ML model on live global data
    - Ran the trained model on recent live satellite detections.
    - Analysed 85,052 live detections.
    - Found 29,050 detections that the model considers static-source-like candidates.
    - Saved them to:
data/processed/live_ml_predictions.csv
These are individual satellite detections, not 29,050 separate factories. Many detections can belong to the same facility or thermal region.
14. Built the hybrid alert system
This is the strongest completed feature so far.
The hybrid system combines:
- ML static-source probability
- Historical thermal-risk score
- Whether the live point matches a historical hotspot
- Live FRP and FIRMS information
It generated:
- 29,050 ML candidates
- 4,390 candidates matching historical hotspots
- 3,462 High alerts
- 877 Medium alerts
- 24,711 Low alerts
Output file:
data/processed/live_hybrid_alerts.csv
The hybrid alert score is better than relying only on ML or only on historical data.
15. Created the final hybrid alert map
- Created the interactive global map:
outputs/maps/live_industrial_alerts.html
When you click a point, it shows:
- Alert score and level
- Detection date and time
- FRP
- FIRMS confidence
- ML static-source probability
- Historical risk score
- Whether it matches a historical hotspot
This is your current working intelligence/alert map.
What the project can do right now
It can:
- Download recent worldwide satellite thermal data.
- Process a large historical global dataset.
- Detect repeated thermal hotspots.
- Score locations by historical thermal risk.
- Run an ML model on new detections.
- Combine ML predictions with historical behavior.
- Produce an interactive global alert map.
What it cannot claim yet
It cannot yet say with certainty:
- “This is definitely a factory.”
- “This is definitely an illegal fire.”
- “This is an emergency incident.”
- “This model is 96% accurate for industrial sites.”
Right now, it identifies high-priority persistent/static thermal candidates. That is a solid and honest first version.
---

# Version 2 - the place-level model (supersedes items 12-15 above)

## Why the old model was replaced

The detection-level model reported ~96% accuracy and ROC-AUC 0.989. That
number was not trustworthy. Two problems were found by testing it:

- `latitude` alone scored AUC 0.922. The model was mostly memorising a world
  map of where oil fields are, not learning what a flare looks like.
- `hour_utc` was longitude in disguise. NOAA-20 is sun-synchronous, so the
  UTC hour of an observation is essentially fixed by longitude.
- The random train/test split let the same flare appear in both halves,
  because one site is detected hundreds of times per year.

Do not quote the 96% / 0.989 figures. They measure memorisation.

## What version 2 does differently

| | v1 | v2 |
|---|---|---|
| One row is | one detection | one place (0.05 deg cell, ~5 km) |
| Features | 9, including lat/lon | 19, no coordinates at all |
| Validation | random split | 5-fold spatial blocks (held-out regions) |
| Headline metric | ROC-AUC | Average Precision (PR-AUC) |
| Score | 0.989 (inflated) | 0.902 +/- 0.029 (honest) |

ROC-AUC is not used as the headline any more: only 0.6% of places are static
sources, and ROC-AUC flatters rare classes. PR-AUC is the honest metric.

## Independent validation

The WRI Global Power Plant Database was used as ground truth. It was never a
feature and never a label, so it is a genuinely independent test.

Base rate: 0.224% of all places sit within 2 km of a thermal power plant.

Ties are broken at random and averaged over 200 draws. This matters:
night_fraction has ~15,000 places tied at exactly 1.0, so taking the "top
500" in file order silently re-ranks them by whatever the file is sorted by
and invents a result that is not real.

| ranking method | top 100 | top 500 | lift | stable? |
|---|---|---|---|---|
| ML model (out-of-fold) | 15.9% | 15.3% | 68x | yes (sd 0.3%) |
| NASA type2_fraction | 11.1% | 11.8% | 53x | yes |
| active_days alone | 4.0% | 11.2% | 50x | yes |
| night_fraction alone | 2.2% | 2.1% | 9x | no (sd 0.6%) |

Two things this settles:

1. The model beats "sort by active_days", so the persistence signal is not
   just circular repackaging of NASA's own type field.
2. The model beats NASA's `type = 2` label that it was trained on. It
   generalises past its own teacher rather than only copying it.

## Volcanoes

Smithsonian GVP Holocene volcano list is used as a filter. 605 places sit
within 10 km of a volcano and are labelled "Natural (volcano)" instead of
being counted as industrial. Nyamulagira in DR Congo was the single highest
live alert before this filter existed.

## Scripts

| Script | Purpose |
|---|---|
| `build_hotspot_dataset.py` | 18.5M detections -> 689,294 places with 19 features |
| `train_hotspot_model.py` | trains with spatial block CV, compares to baselines |
| `enrich_and_validate.py` | adds volcano/power-plant context, runs validation |
| `create_hotspot_alerts.py` | live detections -> alerts via their place history |
| `create_hotspot_alert_map.py` | map, one marker per place |
| `check_pipeline.py` | health check, 34 assertions |

Run in that order. `check_pipeline.py` fails loudly if a leaky feature
(lat/lon/hour) ever gets added back to the model.

## What it still cannot claim

- It finds persistent static thermal sources, not confirmed factories.
- 16.1% of High alerts are confirmed against a known power plant. The rest
  are unconfirmed - they may be gas flares, kilns or furnaces that are simply
  absent from our reference data, and that absence is not evidence against
  them.
- Training labels are still NASA's `fire_type`. Replacing them with EOG
  gas-flare ground truth is the next real improvement.
