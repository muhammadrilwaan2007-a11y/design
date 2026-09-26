import pandas as pd
import numpy as np
from scipy.stats import pearsonr, spearmanr
from pathlib import Path
import sys
import io

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
CSV_PATH = DATA_DIR / "osm_road_accident_features.csv"

def run_analysis():
    print("==================================================")
    print("1. LOAD THE ROAD-LEVEL DATA")
    print("==================================================")
    df = pd.read_csv(CSV_PATH)
    print("Columns and Types:")
    print(df.dtypes)
    print(f"\nTotal rows loaded: {len(df):,}")

    print("\n==================================================")
    print("2. ANALYZE ZERO INFLATION")
    print("==================================================")
    total_roads = len(df)
    zero_acc = (df['accident_count'] == 0).sum()
    nonzero_acc = total_roads - zero_acc
    print(f"Total roads: {total_roads:,}")
    print(f"Roads with accident_count = 0: {zero_acc:,} ({(zero_acc/total_roads)*100:.2f}%)")
    print(f"Roads with accident_count > 0: {nonzero_acc:,} ({(nonzero_acc/total_roads)*100:.2f}%)")

    def print_stats(name, s):
        print(f"\n{name} statistics:")
        print(f"  Min:    {s.min():.4f}")
        print(f"  Max:    {s.max():.4f}")
        print(f"  Mean:   {s.mean():.4f}")
        print(f"  Median: {s.median():.4f}")
        print(f"  Std:    {s.std():.4f}")
        print(f"  75th %: {np.percentile(s, 75):.4f}")
        print(f"  90th %: {np.percentile(s, 90):.4f}")
        print(f"  95th %: {np.percentile(s, 95):.4f}")
        print(f"  99th %: {np.percentile(s, 99):.4f}")

    print_stats("accident_count", df['accident_count'])
    print_stats("fatal_accident_count", df['fatal_accident_count'])
    print_stats("accident_density_per_km", df['accident_density_per_km'])

    print("\n==================================================")
    print("3. ANALYZE ROAD LENGTH")
    print("==================================================")
    print_stats("length_km", df['length_km'])
    
    pearson_corr, _ = pearsonr(df['length_km'], df['accident_count'])
    spearman_corr, _ = spearmanr(df['length_km'], df['accident_count'])
    print(f"\nCorrelation between length_km and accident_count:")
    print(f"  Pearson:  {pearson_corr:.4f}")
    print(f"  Spearman: {spearman_corr:.4f}")

    print("\n==================================================")
    print("4. EXPOSURE-NORMALIZED ANALYSIS")
    print("==================================================")
    
    # Handle list-type highways by taking the first element for grouping if needed
    def clean_hw(hw):
        hw = str(hw)
        if hw.startswith("["):
            hw = hw.replace("[", "").replace("]", "").replace("'", "")
            return hw.split(",")[0].strip()
        return hw

    df['hw_clean'] = df['highway'].apply(clean_hw)
    
    grp = df.groupby('hw_clean').agg(
        num_edges=('unique_edge_id', 'count'),
        total_len_km=('length_km', 'sum'),
        total_acc=('accident_count', 'sum'),
        total_fatal=('fatal_accident_count', 'sum'),
        roads_with_acc=('accident_count', lambda x: (x > 0).sum())
    )
    
    grp['acc_per_km'] = np.where(grp['total_len_km'] > 0, grp['total_acc'] / grp['total_len_km'], 0)
    grp['fatal_per_km'] = np.where(grp['total_len_km'] > 0, grp['total_fatal'] / grp['total_len_km'], 0)
    grp['pct_roads_with_acc'] = (grp['roads_with_acc'] / grp['num_edges']) * 100
    
    grp = grp.sort_values('total_len_km', ascending=False).head(15)
    
    print(grp[['num_edges', 'total_len_km', 'total_acc', 'acc_per_km', 'total_fatal', 'fatal_per_km', 'pct_roads_with_acc']].to_string())

    print("\n==================================================")
    print("5. INVESTIGATE THE TARGET OPTIONS")
    print("==================================================")
    print("OPTION A - REGRESSION")
    skew = df['accident_density_per_km'].skew()
    print(f"accident_density_per_km skewness: {skew:.4f}")
    
    log_density = np.log1p(df['accident_density_per_km'])
    print_stats("log1p(accident_density_per_km)", log_density)

    print("\nOPTION B - BINARY CLASSIFICATION")
    class_1 = (df['accident_count'] > 0).sum()
    class_0 = total_roads - class_1
    print(f"Class 0 (No accident): {class_0:,} ({(class_0/total_roads)*100:.2f}%)")
    print(f"Class 1 (Has accident): {class_1:,} ({(class_1/total_roads)*100:.2f}%)")
    print(f"Imbalance ratio: {class_0/class_1:.1f}:1")

    print("\nOPTION C - MULTI-CLASS RISK BINS")
    df_nonzero = df[df['accident_count'] > 0]
    print("Non-zero accident_density_per_km quantiles:")
    print(f"  25th: {np.percentile(df_nonzero['accident_density_per_km'], 25):.4f}")
    print(f"  50th: {np.percentile(df_nonzero['accident_density_per_km'], 50):.4f}")
    print(f"  75th: {np.percentile(df_nonzero['accident_density_per_km'], 75):.4f}")
    print(f"  90th: {np.percentile(df_nonzero['accident_density_per_km'], 90):.4f}")

    print("\nNon-zero accident_count quantiles:")
    print(f"  25th: {np.percentile(df_nonzero['accident_count'], 25):.4f}")
    print(f"  50th: {np.percentile(df_nonzero['accident_count'], 50):.4f}")
    print(f"  75th: {np.percentile(df_nonzero['accident_count'], 75):.4f}")
    print(f"  90th: {np.percentile(df_nonzero['accident_count'], 90):.4f}")

    print("\n==================================================")
    print("6. FATALITY INFORMATION")
    print("==================================================")
    roads_with_fatal = (df['fatal_accident_count'] > 0).sum()
    print(f"Roads with fatal accidents: {roads_with_fatal:,} ({(roads_with_fatal/total_roads)*100:.4f}%)")
    print(f"Roads without fatal accidents: {total_roads - roads_with_fatal:,}")
    print_stats("fatal_accident_count (among roads with fatal)", df[df['fatal_accident_count'] > 0]['fatal_accident_count'])
    
    fatal_both = ((df['fatal_accident_count'] > 0) & (df['accident_count'] > 0)).sum()
    print(f"\nRoads with fatal_accident_count > 0 AND accident_count > 0: {fatal_both:,}")

    print("\n==================================================")
    print("7. CHECK DUPLICATE/IDENTICAL INFORMATION")
    print("==================================================")
    print(f"Unique accident_count values: {df['accident_count'].nunique()}")
    print(f"Unique fatal_accident_count values: {df['fatal_accident_count'].nunique()}")
    print(f"Unique accident_density_per_km values: {df['accident_density_per_km'].nunique()}")

if __name__ == "__main__":
    run_analysis()
