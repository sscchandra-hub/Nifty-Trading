import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Debug Test", layout="wide")

st.title("🔧 INSTRUMENT LOADING DEBUG TEST")

BASE_DIR = Path(r"D:\Stocks Analysis\Apex Nifty Trading")
INSTRUMENTS_FILE = BASE_DIR / "instruments.csv"

st.write("---")
st.header("Step 1: File Check")
st.write(f"**Base Dir:** `{BASE_DIR}`")
st.write(f"**Instruments File:** `{INSTRUMENTS_FILE}`")
st.write(f"**File Exists:** {INSTRUMENTS_FILE.exists()}")

if INSTRUMENTS_FILE.exists():
    st.success(f"✅ File exists! Size: {INSTRUMENTS_FILE.stat().st_size:,} bytes")
else:
    st.error("❌ File NOT found!")
    st.stop()

st.write("---")
st.header("Step 2: Load Test")

if st.button("🔨 Load Instruments Now", type="primary"):
    with st.spinner("Loading..."):
        try:
            df = pd.read_csv(INSTRUMENTS_FILE, encoding='latin-1')
            st.success(f"✅ Loaded {len(df):,} rows!")
            st.write(f"**Columns:** {list(df.columns)}")
            
            # Check for indices
            if 'instrument_type' in df.columns and 'name' in df.columns:
                ce_df = df[df['instrument_type'] == 'CE']
                indices = ce_df['name'].unique()
                
                st.write(f"**Indices with CE options:** {len(indices)}")
                
                target = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']
                found = [i for i in target if i in indices]
                
                st.write(f"**Our indices found:** {found}")
                
                if len(found) == 5:
                    st.balloons()
                    st.success("🎉 ALL 5 INDICES FOUND! The file is GOOD!")
                    
                    st.write("---")
                    st.info("✅ Your instruments.csv file is working perfectly!")
                    st.info("✅ The problem is in the main app code, not the file!")
                    st.info("✅ I need to fix how the main app loads this data!")
            
            with st.expander("View Sample"):
                st.dataframe(df.head(20))
                
        except Exception as e:
            st.error(f"❌ Error: {e}")
            import traceback
            st.code(traceback.format_exc())

st.write("---")
st.info("👆 Click the button above to test loading")
