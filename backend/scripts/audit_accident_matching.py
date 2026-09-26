"""
scripts/audit_accident_matching.py
====================================
Read-only audit of the accident-to-OSM road matching pipeline.
Does NOT modify any files.
"""

from __future__ import annotations
import sys, io
import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8","utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA = BACKEND_DIR / "data" / "processed"

def hr(title=""):
    print(f"\n{'='*55}\n{title}\n{'='*55}")

def main():
    # ── Load source accident CSV
    hr("1. LOAD SOURCE ACCIDENT DATA")
    df_raw = pd.read_csv(DATA / "validated_accidents.csv")
    print(f"  Total rows in validated_accidents.csv : {len(df_raw):,}")

    # Build a stable accident identifier from row index (position in CSV)
    # Government CSV has no guaranteed unique ID field; we use the row position
    # as a surrogate stable key matching the order used in the original pipeline.
    df_raw["_acc_id"] = df_raw.index
    print(f"  Unique _acc_id values (row positions) : {df_raw['_acc_id'].nunique():,}")
    dup_latlon = df_raw.duplicated(subset=["Latitude","Longitude"]).sum()
    print(f"  Rows with identical Lat/Lon to another: {dup_latlon:,}")

    # Inspect duplicate coord clusters
    dup_groups = (
        df_raw.groupby(["Latitude","Longitude"])
        .size()
        .to_frame("count")
        .reset_index()
        .query("count > 1")
        .sort_values("count", ascending=False)
    )
    print(f"  Distinct duplicate (Lat,Lon) locations: {len(dup_groups):,}")
    print(f"  Top-5 stacked-coordinate clusters:")
    for _, r in dup_groups.head(5).iterrows():
        print(f"    ({r.Latitude:.4f}, {r.Longitude:.4f}) → {int(r['count'])} accidents")

    # ── Load matched file
    hr("2. LOAD accident_road_matches.gpkg")
    gdf = gpd.read_file(DATA / "accident_road_matches.gpkg")
    print(f"  Total rows in matches file : {len(gdf):,}")
    print(f"  Columns                    : {list(gdf.columns)}")

    # Check which column carries the accident identifier
    # The sjoin_nearest may carry '_acc_id' if it was in gdf_acc, else use index_left
    id_col = "_acc_id" if "_acc_id" in gdf.columns else None

    if id_col:
        print(f"\n  Accident ID column found   : '{id_col}'")
        unique_matched_acc = gdf[id_col].nunique()
    else:
        # Fall back to Latitude+Longitude composite
        print("\n  No '_acc_id' column — using Lat+Lon composite as surrogate.")
        gdf["_composite"] = gdf["Latitude"].astype(str) + "_" + gdf["Longitude"].astype(str)
        id_col = "_composite"
        unique_matched_acc = gdf[id_col].nunique()

    print(f"  Unique accident IDs present : {unique_matched_acc:,}")

    # ── CHECK 3: one accident → multiple OSM edges (Cartesian product)
    hr("3. CARTESIAN PRODUCT CHECK (1 accident → multiple roads)")
    acc_counts = gdf[id_col].value_counts()
    multi_match = (acc_counts > 1).sum()
    max_mult    = acc_counts.max()
    total_rows_from_multi = acc_counts[acc_counts > 1].sum()
    print(f"  Accidents matched to exactly 1 road: {(acc_counts==1).sum():,}")
    print(f"  Accidents matched to >1 roads       : {multi_match:,}")
    print(f"  Max road matches for one accident   : {max_mult}")
    print(f"  Extra rows caused by multi-matches  : {total_rows_from_multi - multi_match:,}")
    if multi_match > 0:
        print(f"  Example (top 5 most-duplicated accidents):")
        for acc_id, cnt in acc_counts[acc_counts>1].head(5).items():
            sub = gdf[gdf[id_col]==acc_id][["nearest_road_distance_m","unique_edge_id"]].head(3)
            print(f"    acc_id={acc_id}  → {cnt} road matches, distances: {sub['nearest_road_distance_m'].tolist()}")

    # ── CHECK 4: Equidistant matches (distance identical for multiple edges)
    hr("4. EQUIDISTANT MATCH CHECK")
    if multi_match > 0:
        multi_gdf = gdf[gdf[id_col].isin(acc_counts[acc_counts>1].index)].copy()
        # For each accident that hit multiple roads, check if distances are equal
        equi = 0
        for acc_id, grp in multi_gdf.groupby(id_col):
            if grp["nearest_road_distance_m"].nunique() == 1:
                equi += 1
        print(f"  Multi-matched accidents with IDENTICAL distances (equidistant): {equi:,}")
        print(f"  Multi-matched accidents with DIFFERENT distances (ambiguous)  : {multi_match - equi:,}")
    else:
        print("  No multi-matched accidents detected.")

    # ── CHECK 5: Unique accident records in current 10,710 matched rows
    hr("5. UNIQUE ACCIDENT RECORDS IN MATCHED FILE")
    print(f"  Total rows in matches file   : {len(gdf):,}")
    print(f"  Unique accident IDs matched  : {unique_matched_acc:,}")
    inflation = len(gdf) - unique_matched_acc
    print(f"  Row inflation from duplicates: {inflation:,}")
    if inflation > 0:
        print("  ⚠ The current matched file contains MORE ROWS than unique accidents.")
        print("    This means the accident_count in the road-level dataset may be inflated.")

    # ── CHECK 6: Road-level accident_count inflation
    hr("6. ROAD-LEVEL accident_count INFLATION CHECK")
    df_roads = pd.read_csv(DATA / "osm_road_accident_features.csv", low_memory=False)
    sum_road_acc = df_roads["accident_count"].sum()
    print(f"  Sum of accident_count across all roads : {sum_road_acc:,}")
    print(f"  Unique accident IDs in matches file    : {unique_matched_acc:,}")
    if sum_road_acc != unique_matched_acc:
        diff = sum_road_acc - unique_matched_acc
        print(f"  ⚠ MISMATCH: road-level sum inflated by {diff:,} counts")
        print("    Cause: sjoin_nearest produced Cartesian rows; groupby.size() counted")
        print("    all rows including duplicates instead of unique accidents per road.")
    else:
        print("  ✓ Road-level sum matches unique accident count exactly.")

    # ── CHECK 7: Accidents matched >5km (previously 55 reported)
    hr("7. LONG-ROAD MATCH CHECK (previously flagged 55 accidents)")
    dist_col = "nearest_road_distance_m"
    if dist_col in gdf.columns:
        far = gdf[gdf[dist_col] > 50]
        print(f"  Rows with match distance > 50m  : {len(far):,}")
        really_far = gdf[gdf[dist_col] > 5000]
        print(f"  Rows with match distance > 5000m: {len(really_far):,}")
        if len(really_far):
            print(f"  (These should have been filtered by the 50m threshold — investigate)")
    else:
        print("  nearest_road_distance_m column not found.")

    # ── CHECK 8: Duplicate Lat/Lon accidents in matched data
    hr("8. DUPLICATE LAT/LON IN MATCHED DATA")
    if "Latitude" in gdf.columns and "Longitude" in gdf.columns:
        dup_in_matches = gdf.duplicated(subset=["Latitude","Longitude"]).sum()
        print(f"  Rows with duplicate Lat/Lon in matches file: {dup_in_matches:,}")
        # How many distinct (Lat,Lon) pairs in matches?
        distinct_locations = gdf[["Latitude","Longitude"]].drop_duplicates()
        print(f"  Distinct (Lat,Lon) locations in matches    : {len(distinct_locations):,}")
        # Same-location clusters
        loc_grp = gdf.groupby(["Latitude","Longitude"]).size().to_frame("n").reset_index()
        stacked_loc = loc_grp[loc_grp["n"] > 1]
        print(f"  Stacked locations (same point, >1 record)  : {len(stacked_loc):,}")
        print(f"  Top-5 stacked locations in matches:")
        for _, r in stacked_loc.sort_values("n",ascending=False).head(5).iterrows():
            print(f"    ({r.Latitude:.4f}, {r.Longitude:.4f}) → {int(r.n)} records")
    else:
        print("  Latitude/Longitude columns not found in matches file.")

    # ── CHECK 9: Consistency check
    hr("9. CONSISTENCY CHECK: sum(road accident_count) == unique accidents?")
    # Recalculate correctly: count distinct accident IDs per road
    if id_col in gdf.columns:
        correct_counts = (
            gdf[gdf["nearest_road_distance_m"] <= 50]
            .groupby("unique_edge_id")[id_col]
            .nunique()
            .sum()
        )
        print(f"  Correct unique-accident sum (nunique per road): {correct_counts:,}")
        print(f"  Current road-level sum (may be inflated)       : {sum_road_acc:,}")
        if correct_counts == sum_road_acc:
            print("  ✓ Consistent — no inflation detected in current dataset.")
        else:
            print(f"  ⚠ Inflation = {sum_road_acc - correct_counts:,} counts")
            print("    Recommendation: re-aggregate using nunique(_acc_id) per road,")
            print("    not groupby.size(), to correct the road-level accident_count.")

    hr("AUDIT COMPLETE")

if __name__ == "__main__":
    main()
