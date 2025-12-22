
import pandas as pd
from pathlib import Path

print("=" * 80)
print("DIAGNOSTIC CHECK")
print("=" * 80)

BASE_DIR = Path(r"D:\Stocks Analysis\Apex Nifty Trading")
INSTRUMENTS_FILE = BASE_DIR / "instruments.csv"

print(f"\n1. Base directory exists: {BASE_DIR.exists()}")
print(f"   Path: {BASE_DIR}")

print(f"\n2. Instruments file exists: {INSTRUMENTS_FILE.exists()}")
print(f"   Path: {INSTRUMENTS_FILE}")

if INSTRUMENTS_FILE.exists():
    print("\n3. Trying to load CSV...")
    try:
        df = pd.read_csv(INSTRUMENTS_FILE)
        print(f"   ✓ SUCCESS! Loaded {len(df):,} rows")
        print(f"   Columns: {list(df.columns)}")
        
        # Check for indices with options
        if 'instrument_type' in df.columns:
            ce_count = len(df[df['instrument_type'] == 'CE'])
            print(f"\n4. CE options found: {ce_count:,}")
            
            if ce_count > 0:
                ce_names = df[df['instrument_type'] == 'CE']['name'].unique()
                print(f"   Unique index names with CE: {len(ce_names)}")
                
                # Check for our indices
                our_indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']
                found = [idx for idx in our_indices if idx in ce_names]
                print(f"   Our indices found: {found}")
    except Exception as e:
        print(f"   ✗ ERROR: {e}")
else:
    print("\n   ✗ File not found!")

print("\n" + "=" * 80)
