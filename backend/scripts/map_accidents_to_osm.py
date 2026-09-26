import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path
import sys
import io

# Fix Windows console encoding for Unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

ACCIDENTS_CSV = DATA_DIR / "processed" / "validated_accidents.csv"
ROADS_GPKG = DATA_DIR / "raw" / "osm" / "bengaluru_roads.gpkg"

MATCHES_GPKG = DATA_DIR / "processed" / "accident_road_matches.gpkg"
AGG_ROADS_GPKG = DATA_DIR / "processed" / "osm_roads_with_accidents.gpkg"
AGG_ROADS_CSV = DATA_DIR / "processed" / "osm_road_accident_features.csv"

MAX_MATCH_DISTANCE_M = 50.0

def run_pipeline():
    print("==================================================")
    print("TASK 1 — INSPECT HISTORICAL ACCIDENT DATA")
    print("==================================================")
    
    df_acc = pd.read_csv(ACCIDENTS_CSV)
    total_acc = len(df_acc)
    print(f"Total rows: {total_acc:,}")

    # ── STABLE ACCIDENT IDENTIFIER ──────────────────────────────────────────
    # Assign a unique accident_id based on the CSV row index.
    # Multiple genuine accidents CAN share the same (Lat, Lon), so we must
    # never deduplicate using coordinates alone.  The row position in the
    # validated CSV is a stable surrogate for a real accident record ID.
    df_acc['accident_id'] = df_acc.index  # 0-based integer, unique per row

    # Check valid coords
    valid_mask = df_acc['Latitude'].notna() & df_acc['Longitude'].notna()
    invalid_coords = (~valid_mask).sum()
    print(f"Valid coordinates rows: {valid_mask.sum():,}")
    print(f"Invalid/missing coordinates: {invalid_coords:,}")
    
    lat_min, lat_max = df_acc['Latitude'].min(), df_acc['Latitude'].max()
    lon_min, lon_max = df_acc['Longitude'].min(), df_acc['Longitude'].max()
    print(f"Coordinate range: Lat [{lat_min:.4f}, {lat_max:.4f}], Lon [{lon_min:.4f}, {lon_max:.4f}]")
    
    fatal_acc = df_acc['is_fatal'].sum()
    nonfatal_acc = len(df_acc) - fatal_acc
    print(f"Number of fatal accidents: {fatal_acc:,}")
    print(f"Number of non-fatal accidents: {nonfatal_acc:,}")
    
    # Verify: unique accident_id count must equal total_acc
    assert df_acc['accident_id'].nunique() == total_acc, "accident_id is not unique!"
    print(f"Unique accident_id values: {df_acc['accident_id'].nunique():,} (matches total rows)")

    # Convert to GeoDataFrame — accident_id travels with every row
    gdf_acc = gpd.GeoDataFrame(
        df_acc, 
        geometry=gpd.points_from_xy(df_acc.Longitude, df_acc.Latitude),
        crs="EPSG:4326"
    )

    print("\n==================================================")
    print("TASK 2 — LOAD OSM ROAD NETWORK")
    print("==================================================")
    
    gdf_roads = gpd.read_file(ROADS_GPKG)
    print(f"CRS: {gdf_roads.crs}")
    print(f"Geometry type: {gdf_roads.geom_type.unique()}")
    print(f"Number of road edges: {len(gdf_roads):,}")
    
    invalid_geoms = (~gdf_roads.is_valid).sum()
    print(f"Invalid geometries: {invalid_geoms:,}")
    
    attrs_to_check = ['highway', 'oneway', 'lanes', 'maxspeed', 'junction', 'bridge', 'tunnel', 'name', 'ref', 'geometry']
    print("Important attributes:")
    for attr in attrs_to_check:
        if attr in gdf_roads.columns:
            missing = gdf_roads[attr].isna().sum()
            print(f"  {attr:<15} Present (Missing: {missing:,})")
        else:
            print(f"  {attr:<15} Missing completely")

    # If osmid is an index or column
    if 'osmid' not in gdf_roads.columns:
        if gdf_roads.index.name == 'osmid' or (isinstance(gdf_roads.index, pd.MultiIndex) and 'osmid' in gdf_roads.index.names):
            gdf_roads = gdf_roads.reset_index()
        else:
            gdf_roads['osmid'] = gdf_roads.index
            
    # Ensure osmid is unique for grouping
    if gdf_roads['osmid'].duplicated().any():
        print(f"\nWarning: multiple edges have the same osmid ({gdf_roads['osmid'].duplicated().sum()} duplicates).")
        print("This happens because OSMnx splits edges at intersections. We will group by a unique edge identifier.")
        gdf_roads['unique_edge_id'] = range(len(gdf_roads))
    else:
        gdf_roads['unique_edge_id'] = gdf_roads['osmid']

    print("\n==================================================")
    print("TASK 3 & 4 — PROJECT TO METRIC CRS & CLEAN GEOMS")
    print("==================================================")
    
    gdf_acc_utm = gdf_acc.to_crs("EPSG:32643")
    gdf_roads_utm = gdf_roads.to_crs("EPSG:32643")
    print("Successfully reprojected both to EPSG:32643 (UTM Zone 43N)")
    
    null_geoms_count = gdf_roads_utm.geometry.isna().sum()
    empty_geoms_count = gdf_roads_utm.geometry.is_empty.sum()
    total_discarded = null_geoms_count + empty_geoms_count
    
    gdf_roads_utm = gdf_roads_utm[gdf_roads_utm.geometry.notna() & ~gdf_roads_utm.geometry.is_empty]
    
    print(f"Number of valid roads: {len(gdf_roads_utm):,}")
    print(f"Number of invalid/null roads: {total_discarded:,}")
    print(f"Number repaired: 0")
    print(f"Number discarded: {total_discarded:,}")

    print("\n==================================================")
    print("TASK 5 — SPATIAL MATCHING")
    print("==================================================")
    print("Performing unconstrained nearest-neighbor matching (this may take a moment)...")
    
    # Calculate road lengths in EPSG:32643 BEFORE joining
    gdf_roads_utm['length_m'] = gdf_roads_utm.geometry.length
    gdf_roads_utm['length_km'] = gdf_roads_utm['length_m'] / 1000.0
    
    # spatial join nearest
    matches = gpd.sjoin_nearest(gdf_acc_utm, gdf_roads_utm, how='left', distance_col='nearest_road_distance_m')
    
    dists = matches['nearest_road_distance_m'].dropna()
    print("\nNearest-road distance distribution:")
    print(f"  Min:    {dists.min():.2f}m")
    print(f"  Mean:   {dists.mean():.2f}m")
    print(f"  Median: {dists.median():.2f}m")
    print(f"  90th %: {np.percentile(dists, 90):.2f}m")
    print(f"  95th %: {np.percentile(dists, 95):.2f}m")
    print(f"  99th %: {np.percentile(dists, 99):.2f}m")
    print(f"  Max:    {dists.max():.2f}m")
    
    d_10 = (dists <= 10).sum()
    d_25 = (dists <= 25).sum()
    d_50 = (dists <= 50).sum()
    d_100 = (dists <= 100).sum()
    
    print("\nAccidents matching within thresholds:")
    print(f"  <= 10m : {d_10:,} ({(d_10/len(dists))*100:.1f}%)")
    print(f"  <= 25m : {d_25:,} ({(d_25/len(dists))*100:.1f}%)")
    print(f"  <= 50m : {d_50:,} ({(d_50/len(dists))*100:.1f}%)")
    print(f"  <= 100m: {d_100:,} ({(d_100/len(dists))*100:.1f}%)")
    
    print(f"\nApplying threshold MAX_MATCH_DISTANCE_M = {MAX_MATCH_DISTANCE_M}...")
    within_threshold = matches[matches['nearest_road_distance_m'] <= MAX_MATCH_DISTANCE_M].copy()

    # ── CARTESIAN / EQUIDISTANT DEDUPLICATION ───────────────────────────────
    # sjoin_nearest can return MULTIPLE rows for one accident when that
    # point is equidistant to several OSM edges (e.g., at an intersection).
    # We resolve this by keeping exactly ONE edge per accident_id:
    #   sort ascending by distance → drop_duplicates on accident_id → keep first
    # This preserves all genuine accidents, including those that share the
    # same (Lat, Lon) coordinates, because each still has a unique accident_id.
    rows_before_dedup = len(within_threshold)
    unique_acc_before  = within_threshold['accident_id'].nunique()

    valid_matches = (
        within_threshold
        .sort_values('nearest_road_distance_m', ascending=True)
        .drop_duplicates(subset=['accident_id'], keep='first')
        .copy()
    )
    rows_after_dedup  = len(valid_matches)
    multi_road_rows   = rows_before_dedup - rows_after_dedup
    unique_acc_after  = valid_matches['accident_id'].nunique()

    # Sanity: accident_id must still equal unique_acc_after
    assert unique_acc_after == rows_after_dedup, \
        "Each accident should map to exactly one road after dedup!"

    # Source accidents that fell outside the threshold
    all_source_ids     = set(gdf_acc['accident_id'])
    matched_ids        = set(valid_matches['accident_id'])
    unmatched_acc_ids  = all_source_ids - matched_ids
    unmatched_count    = len(unmatched_acc_ids)

    print(f"\nPost-threshold rows (before dedup) : {rows_before_dedup:,}")
    print(f"Unique accidents within threshold   : {unique_acc_before:,}")
    print(f"Rows removed (Cartesian duplicates) : {multi_road_rows:,}")
    print(f"Final matched accidents (1 row each): {rows_after_dedup:,}")
    print(f"Unmatched accidents (outside 50m)   : {unmatched_count:,}")
    print(f"  Note: {total_acc:,} source - {rows_after_dedup:,} matched = {unmatched_count:,} unmatched")

    # Verify distinct Lat/Lon locations vs matched accident count differ
    distinct_latlon_in_matches = valid_matches[['Latitude','Longitude']].drop_duplicates()
    print(f"  Distinct (Lat,Lon) locations in matches: {len(distinct_latlon_in_matches):,}")
    print(f"  Matched accident_id count              : {rows_after_dedup:,}")
    if rows_after_dedup != len(distinct_latlon_in_matches):
        print(f"  ✓ CONFIRMED: matched accidents ({rows_after_dedup:,}) != unique Lat/Lon "
              f"locations ({len(distinct_latlon_in_matches):,}) — genuine multi-accident "
              f"coordinates are preserved.")

    print("\n==================================================")
    print("TASK 6 — CREATE ACCIDENT-TO-ROAD MAPPING")
    print("==================================================")
    
    # Save deduplicated matches
    valid_matches.to_file(MATCHES_GPKG, driver="GPKG")
    print(f"Saved matched accidents to {MATCHES_GPKG.name} ({rows_after_dedup:,} rows, 1 per accident)")

    print("\n==================================================")
    print("TASK 7 — AGGREGATE ACCIDENTS BY ROAD")
    print("==================================================")
    
    # ── ROAD-LEVEL AGGREGATION (using deduplicated 1-per-accident table) ─────
    # After deduplication, valid_matches has exactly one row per accident_id.
    # groupby.size() now correctly counts unique accidents per road.
    acc_counts   = valid_matches.groupby('unique_edge_id').size().reset_index(name='accident_count')
    fatal_counts = valid_matches.groupby('unique_edge_id')['is_fatal'].sum().reset_index(name='fatal_accident_count')
    
    # Merge back to full road network
    roads_with_acc = gdf_roads_utm.merge(acc_counts,   on='unique_edge_id', how='left')
    roads_with_acc = roads_with_acc.merge(fatal_counts, on='unique_edge_id', how='left')
    
    # Fill NAs for roads with zero accidents
    roads_with_acc['accident_count']        = roads_with_acc['accident_count'].fillna(0).astype(int)
    roads_with_acc['fatal_accident_count']  = roads_with_acc['fatal_accident_count'].fillna(0).astype(int)
    roads_with_acc['nonfatal_accident_count'] = (
        roads_with_acc['accident_count'] - roads_with_acc['fatal_accident_count']
    )
    roads_with_acc['fatal_rate'] = np.where(
        roads_with_acc['accident_count'] > 0, 
        roads_with_acc['fatal_accident_count'] / roads_with_acc['accident_count'], 
        0.0
    )
    roads_with_acc['accident_density_per_km'] = np.where(
        roads_with_acc['length_km'] > 0,
        roads_with_acc['accident_count'] / roads_with_acc['length_km'],
        0.0
    )
    # Binary target for XGBoost
    roads_with_acc['has_accident'] = (roads_with_acc['accident_count'] > 0).astype(int)

    # ── INTEGRITY CHECK ───────────────────────────────────────────────────────
    sum_road_count = roads_with_acc['accident_count'].sum()
    assert sum_road_count == rows_after_dedup, (
        f"Road-level sum ({sum_road_count}) != matched accidents ({rows_after_dedup})!"
    )
    print(f"\n✓ Integrity check passed: sum(accident_count)={sum_road_count:,} "
          f"== matched unique accidents={rows_after_dedup:,}")

    # Save geospatial output
    roads_with_acc.to_file(AGG_ROADS_GPKG, driver="GPKG")
    print(f"Saved geospatial aggregated roads to {AGG_ROADS_GPKG.name}")
    
    # Save ML-friendly flat CSV (drop geometry)
    df_features = pd.DataFrame(roads_with_acc.drop(columns='geometry'))
    df_features.to_csv(AGG_ROADS_CSV, index=False)
    print(f"Saved ML features table to {AGG_ROADS_CSV.name}")

    print("\n==================================================")
    print("TASK 9 — DETAILED DISTRIBUTION REPORT")
    print("==================================================")
    
    total_roads = len(roads_with_acc)
    roads_w_acc = (roads_with_acc['accident_count'] >= 1).sum()
    roads_zero  = (roads_with_acc['accident_count'] == 0).sum()

    print(f"\n=== AUDIT REPORT ===")
    print(f"  Total source accidents            : {total_acc:,}")
    print(f"  Matched unique accidents (<=50m)  : {rows_after_dedup:,}")
    print(f"  Unmatched accidents               : {unmatched_count:,}")
    print(f"  Multi-road rows removed (Cartesian): {multi_road_rows:,}")
    print(f"  Final roads with accidents        : {roads_w_acc:,}")
    print(f"  Total accident_count after fix    : {roads_with_acc['accident_count'].sum():,}")
    print(f"  Max accident_count on one road    : {roads_with_acc['accident_count'].max()}")
    print(f"  Positive roads (has_accident=1)   : {roads_with_acc['has_accident'].sum():,}")
    print(f"  Negative roads (has_accident=0)   : {(roads_with_acc['has_accident']==0).sum():,}")
    n_pos = roads_with_acc['has_accident'].sum()
    print(f"  Positive-class percentage         : {n_pos/total_roads*100:.2f}%")
    print("====================")

    print(f"\n1. Total OSM road edges: {total_roads:,}")
    print(f"2. Roads with >=1 accident: {roads_w_acc:,}")
    print(f"3. Roads with zero accidents: {roads_zero:,}")
    print(f"4. Percentage of roads with accidents: {(roads_w_acc / total_roads) * 100:.2f}%")
    print(f"5. Total matched accidents (deduplicated): {rows_after_dedup:,}")
    print(f"6. Total unmatched accidents: {unmatched_count:,}")
    
    def rpt_stats(name, s, cond=None):
        if cond is not None:
            s = s[cond]
        if len(s) == 0:
            print(f"\n{name} (No matching records)")
            return
        print(f"\n{name}:")
        print(f"  Min:    {s.min():.2f}")
        print(f"  Max:    {s.max():.2f}")
        print(f"  Mean:   {s.mean():.2f}")
        print(f"  Median: {s.median():.2f}")
        if len(s) >= 4:
            print(f"  75th %: {np.percentile(s, 75):.2f}")
            print(f"  90th %: {np.percentile(s, 90):.2f}")
            print(f"  95th %: {np.percentile(s, 95):.2f}")
            print(f"  99th %: {np.percentile(s, 99):.2f}")
            
    rpt_stats("7. Accident count (among all roads)", roads_with_acc['accident_count'])
    rpt_stats("   Accident count (among roads with accidents)", roads_with_acc['accident_count'], roads_with_acc['accident_count'] > 0)
    
    rpt_stats("8. Fatal accident count (among roads with accidents)", roads_with_acc['fatal_accident_count'], roads_with_acc['accident_count'] > 0)
    
    rpt_stats("9. Accident density per km (among roads with accidents)", roads_with_acc['accident_density_per_km'], roads_with_acc['accident_count'] > 0)
    
    print("\n10. Highway distribution:")
    def format_hw(hw):
        return str(hw) if isinstance(hw, list) else hw
        
    print("  Among ALL roads:")
    hw_all = roads_with_acc['highway'].apply(format_hw).value_counts().head(5)
    for k, v in hw_all.items():
        print(f"    {k:<20} {v:,}")
        
    print("  Among ROADS WITH ACCIDENTS:")
    hw_acc = roads_with_acc[roads_with_acc['accident_count'] > 0]['highway'].apply(format_hw).value_counts().head(5)
    for k, v in hw_acc.items():
        print(f"    {k:<20} {v:,}")

    print("\n11. Collision_Type distribution for matched accidents:")
    if 'Collision_Type' in valid_matches.columns:
        for k, v in valid_matches['Collision_Type'].value_counts().head(5).items():
            print(f"  {k:<30} {v:,}")
    
    print("\n12. Severity distribution for matched accidents:")
    if 'severity_normalised' in valid_matches.columns:
        sev_col = 'severity_normalised'
    elif 'Severity' in valid_matches.columns:
        sev_col = 'Severity'
    else:
        sev_col = None
    if sev_col:
        for k, v in valid_matches[sev_col].value_counts().head(5).items():
            print(f"  {k:<30} {v:,}")

    print("\n==================================================")
    print("TASK 10 — CHECK FOR DATA PROBLEMS")
    print("==================================================")
    
    long_roads = (roads_with_acc['length_m'] > 5000).sum()
    print(f"- Accidents matched to roads > 5km long: {(valid_matches['length_m'] > 5000).sum():,} accidents (on {long_roads} roads)")
    
    far_matches = (dists > 100).sum()
    print(f"- Accidents unusually far from ANY road (>100m): {far_matches:,}")
    
    dup_accs = df_acc.duplicated(subset=['Latitude', 'Longitude']).sum()
    print(f"- Duplicate accident coordinates in original dataset: {dup_accs:,}")
    
    huge_acc = (roads_with_acc['accident_count'] > 50).sum()
    print(f"- Roads with extremely large accident counts (>50): {huge_acc:,}")
    
    miss_hw = roads_with_acc['highway'].isna().sum()
    print(f"- Roads with missing highway values: {miss_hw:,}")

    print("\nDone. Final report generated successfully.")


if __name__ == "__main__":
    run_pipeline()
