import osmnx as ox
import pandas as pd
from pathlib import Path
import sys

# Setup directories
BACKEND_DIR = Path(__file__).resolve().parent.parent
RAW_OSM_DIR = BACKEND_DIR / "data" / "raw" / "osm"
RAW_OSM_DIR.mkdir(parents=True, exist_ok=True)

NODE_OUT = RAW_OSM_DIR / "bengaluru_nodes.gpkg"
EDGE_OUT = RAW_OSM_DIR / "bengaluru_roads.gpkg"

def run_pipeline():
    city_name = "Bengaluru, Karnataka, India"
    print("Downloading OSM drive network (this may take a few minutes)...")
    
    # osmnx 1.x and 2.x compatibility
    graph_from_place = getattr(ox, "graph_from_place", getattr(getattr(ox, "graph", None), "graph_from_place", None))
    graph_to_gdfs = getattr(ox, "graph_to_gdfs", getattr(getattr(ox, "convert", None), "graph_to_gdfs", None))
    if graph_from_place is None or graph_to_gdfs is None:
        raise RuntimeError("Compatible graph_from_place or graph_to_gdfs not found in osmnx")

    # Download the network
    # Note: simplify=True cleans up interstitial nodes so edges are unbroken road segments
    G = graph_from_place(
        city_name,
        network_type="drive",
        simplify=True
    )
    
    # Extract GeoDataFrames
    nodes, edges = graph_to_gdfs(G)
    
    # IMPORTANT CRS REQUIREMENT
    # The default CRS from OSMnx is EPSG:4326 (WGS-84).
    # We will preserve this for storage. 
    # For future metric calculations (length, nearest-road matching, buffer mapping), 
    # the network must be projected to EPSG:32643 (UTM Zone 43N) since it covers Bengaluru 
    # and provides highly accurate Cartesian distances in metres.
    
    # Save to GeoPackage (perfect for preserving LineString geometries)
    nodes.to_file(NODE_OUT, driver="GPKG")
    edges.to_file(EDGE_OUT, driver="GPKG")
    
    # IMPORTANT ATTRIBUTES TO CHECK
    attrs_to_check = [
        "highway", "lanes", "maxspeed", "oneway", 
        "junction", "surface", "lit", "bridge", 
        "tunnel", "name", "ref", "geometry"
    ]
    
    attr_status = {}
    missing_summary = {}
    
    for attr in attrs_to_check:
        if attr in edges.columns:
            attr_status[attr] = "Present"
            # Count missing (NaN or None)
            pct_missing = edges[attr].isna().sum() / len(edges) * 100
            missing_summary[attr] = f"{pct_missing:.1f}% missing"
        else:
            attr_status[attr] = "Missing"
            missing_summary[attr] = "100.0% missing (column not found)"
            
    # Highway distribution
    if "highway" in edges.columns:
        # highway can sometimes be a list of tags. Convert lists to string for value_counts
        hw_dist = edges["highway"].apply(lambda x: str(x) if isinstance(x, list) else x).value_counts().head(10)
    else:
        hw_dist = pd.Series(dtype=int)
        
    print("\n================================")
    print("RouteGuard AI - OSM Network Report")
    print("================================\n")
    print("City:")
    print(city_name + "\n")
    print("Nodes:")
    print(f"{len(nodes):,}\n")
    print("Road edges:")
    print(f"{len(edges):,}\n")
    print("CRS:")
    print(f"{edges.crs}")
    print("\n*Note: Geometries preserved in EPSG:4326. For future spatial matching,")
    print("reproject to EPSG:32643 (UTM Zone 43N) to calculate accurate distances in metres.*\n")
    
    print("Important attributes:")
    for attr in attrs_to_check:
        print(f"{attr:<15} {attr_status[attr]}")
    
    print("\nHighway distribution:")
    if not hw_dist.empty:
        for k, v in hw_dist.items():
            print(f"{k:<25} {v:,}")
    else:
        print("Not available.")
        
    print("\nMissing-value summary:")
    for attr, status in missing_summary.items():
        print(f"{attr:<15} {status}")
        
    print("\nOutput:")
    print(NODE_OUT.name)
    print(EDGE_OUT.name)
    print("================================\n")


if __name__ == "__main__":
    run_pipeline()
