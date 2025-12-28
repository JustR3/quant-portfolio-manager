"""
Fama-French Factor Returns Loader
Factor God: Kenneth French's empirical factor return data

Downloads and parses Fama-French factor returns from Kenneth French's data library.
Provides factor regime analysis for portfolio factor tilting.
"""

import pandas as pd
import requests
from typing import Optional, Dict, List
from pathlib import Path
import zipfile
import io
import sys
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.utils import default_cache, retry_with_backoff


# Fama-French data URLs (Kenneth French Data Library)
FF_3_FACTOR_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
FF_5_FACTOR_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"


def download_ff_factors(factor_set: str = "3factor") -> Optional[pd.DataFrame]:
    """
    Download Fama-French factor returns.
    
    Args:
        factor_set: "3factor" (Mkt-RF, SMB, HML) or "5factor" (adds RMW, CMA)
    
    Returns:
        DataFrame with monthly factor returns (%) and RF rate
    """
    url = FF_3_FACTOR_URL if factor_set == "3factor" else FF_5_FACTOR_URL
    
    print(f"📊 Downloading Fama-French {factor_set} data...")
    
    def fetch():
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Extract ZIP file
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # Get the CSV file (usually first file in zip)
                csv_name = z.namelist()[0]
                with z.open(csv_name) as f:
                    content = f.read().decode('utf-8')
            
            # Parse the CSV content
            # Fama-French files have a header section, then monthly data, then annual data
            lines = content.split('\n')
            
            # Find where monthly data starts (usually after a few header lines)
            data_start = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('19') or line.strip().startswith('20'):
                    data_start = i - 1  # Previous line is column headers
                    break
            
            # Find where monthly data ends (before annual data section)
            data_end = len(lines)
            for i, line in enumerate(lines[data_start:], start=data_start):
                if 'Annual' in line or (line.strip() and not line.strip()[0].isdigit()):
                    if i > data_start + 10:  # Ensure we found actual data first
                        data_end = i
                        break
            
            # Parse monthly data section
            df = pd.read_csv(
                io.StringIO('\n'.join(lines[data_start:data_end])),
                skipinitialspace=True
            )
            
            # Clean up column names
            df.columns = df.columns.str.strip()
            
            # Convert date column (format: YYYYMM)
            date_col = df.columns[0]
            df['Date'] = pd.to_datetime(df[date_col].astype(str), format='%Y%m')
            
            # Keep only relevant columns
            factor_cols = ['Date']
            for col in df.columns:
                col_upper = col.upper()
                if any(x in col_upper for x in ['MKT-RF', 'MKT_RF', 'MKTRF', 'SMB', 'HML', 'RMW', 'CMA', 'RF']):
                    factor_cols.append(col)
            
            df = df[factor_cols].copy()
            
            # Rename columns for consistency
            rename_map = {}
            for col in df.columns:
                col_upper = col.upper().replace('-', '_').replace(' ', '_')
                if 'MKT' in col_upper and 'RF' in col_upper:
                    rename_map[col] = 'Mkt_RF'
                elif col_upper == 'SMB':
                    rename_map[col] = 'SMB'
                elif col_upper == 'HML':
                    rename_map[col] = 'HML'
                elif col_upper == 'RMW':
                    rename_map[col] = 'RMW'
                elif col_upper == 'CMA':
                    rename_map[col] = 'CMA'
                elif col_upper == 'RF':
                    rename_map[col] = 'RF'
            
            df = df.rename(columns=rename_map)
            
            # Convert factor returns to numeric (they're in percentage points)
            for col in df.columns:
                if col != 'Date':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Drop rows with missing data
            df = df.dropna()
            
            return df
            
        except Exception as e:
            print(f"  ⚠️  Error downloading Fama-French data: {e}")
            return None
    
    result = retry_with_backoff(fetch, max_attempts=3)
    
    if result is not None:
        print(f"✅ Downloaded {len(result)} months of Fama-French data")
        return result
    else:
        print("❌ Failed to download Fama-French data")
        return None


def get_ff_factors(
    factor_set: str = "3factor",
    use_cache: bool = True,
    cache_expiry_hours: int = 168
) -> Optional[pd.DataFrame]:
    """
    Get Fama-French factor returns with caching.
    
    Args:
        factor_set: "3factor" or "5factor"
        use_cache: Whether to use cached data
        cache_expiry_hours: Cache freshness in hours (default: 168 = 1 week)
    
    Returns:
        DataFrame with factor returns
    """
    cache_key = f"ff_{factor_set}_data"
    
    # Try cache first
    if use_cache:
        cached = default_cache.get(cache_key, expiry_hours=cache_expiry_hours)
        if cached is not None:
            print(f"✅ Loaded Fama-French {factor_set} data from cache ({len(cached)} rows)")
            return cached
    
    # Download fresh data
    df = download_ff_factors(factor_set)
    
    if df is not None:
        # Cache it
        default_cache.set(cache_key, df)
    
    return df


def calculate_rolling_stats(
    df: pd.DataFrame,
    factor_col: str,
    window_months: int = 12
) -> Dict:
    """
    Calculate rolling statistics for a factor.
    
    Args:
        df: DataFrame with factor returns
        factor_col: Name of factor column
        window_months: Rolling window in months
    
    Returns:
        Dictionary with rolling mean, volatility, and long-term stats
    """
    if factor_col not in df.columns:
        return {}
    
    factor_returns = df[factor_col]
    
    # Rolling statistics
    rolling_mean = factor_returns.rolling(window=window_months).mean().iloc[-1]
    rolling_std = factor_returns.rolling(window=window_months).std().iloc[-1]
    
    # Long-term statistics (all history)
    longterm_mean = factor_returns.mean()
    longterm_std = factor_returns.std()
    
    # Recent performance vs long-term
    recent_excess = rolling_mean - longterm_mean
    z_score = recent_excess / longterm_std if longterm_std > 0 else 0
    
    return {
        'rolling_mean': rolling_mean,
        'rolling_std': rolling_std,
        'longterm_mean': longterm_mean,
        'longterm_std': longterm_std,
        'recent_excess': recent_excess,
        'z_score': z_score
    }


def get_factor_regime(
    factor_set: str = "3factor",
    window_months: int = 12
) -> Dict:
    """
    Analyze current factor regimes.
    
    Args:
        factor_set: "3factor" or "5factor"
        window_months: Rolling window for regime detection (default: 12 months)
    
    Returns:
        Dictionary with regime information for each factor:
            - regime: "STRONG_POSITIVE", "POSITIVE", "NEUTRAL", "NEGATIVE", "STRONG_NEGATIVE"
            - weight: Suggested weight adjustment (0.5 to 1.5)
            - z_score: Recent performance vs long-term average
    """
    df = get_ff_factors(factor_set=factor_set)
    
    if df is None:
        # Return neutral if no data
        return {
            'available': False,
            'factors': {}
        }
    
    factor_cols = ['SMB', 'HML', 'Mkt_RF']
    if factor_set == "5factor":
        factor_cols.extend(['RMW', 'CMA'])
    
    factor_regimes = {}
    
    for factor in factor_cols:
        if factor not in df.columns:
            continue
        
        stats = calculate_rolling_stats(df, factor, window_months)
        
        if not stats:
            continue
        
        z = stats['z_score']
        
        # Classify regime based on Z-score
        if z > 1.5:
            regime = 'STRONG_POSITIVE'
            weight = 1.3
        elif z > 0.5:
            regime = 'POSITIVE'
            weight = 1.15
        elif z < -1.5:
            regime = 'STRONG_NEGATIVE'
            weight = 0.7
        elif z < -0.5:
            regime = 'NEGATIVE'
            weight = 0.85
        else:
            regime = 'NEUTRAL'
            weight = 1.0
        
        factor_regimes[factor] = {
            'regime': regime,
            'weight': weight,
            'z_score': z,
            'rolling_mean': stats['rolling_mean'],
            'longterm_mean': stats['longterm_mean']
        }
    
    return {
        'available': True,
        'window_months': window_months,
        'factors': factor_regimes,
        'as_of_date': df['Date'].iloc[-1].strftime('%Y-%m-%d')
    }


def get_factor_tilts(regime_info: Dict, tilt_strength: float = 0.5) -> Dict[str, float]:
    """
    Convert factor regimes to factor importance tilts.
    
    Maps Fama-French factors to our internal factors:
    - HML (High Minus Low) → Value
    - SMB (Small Minus Big) → Quality (inverse, since we prefer large caps)
    - Mkt_RF (Market excess return) → Overall equity exposure
    - RMW (Robust Minus Weak) → Quality
    - CMA (Conservative Minus Aggressive) → Quality
    
    Args:
        regime_info: Output from get_factor_regime()
        tilt_strength: How much to adjust factor weights (0=none, 1=full). Default 0.5.
    
    Returns:
        Dictionary with tilts for Value, Quality, Momentum
    """
    if not regime_info.get('available', False):
        return {'Value': 1.0, 'Quality': 1.0, 'Momentum': 1.0}
    
    factors = regime_info.get('factors', {})
    
    # Map to our internal factors
    raw_value_tilt = factors.get('HML', {}).get('weight', 1.0)
    
    # Quality is influenced by RMW and inverse of SMB
    quality_weight = factors.get('RMW', {}).get('weight', 1.0)
    smb_weight = factors.get('SMB', {}).get('weight', 1.0)
    # Inverse SMB: if small caps are doing well, reduce quality emphasis (large cap quality)
    raw_quality_tilt = quality_weight * (2.0 - smb_weight)
    
    # Apply tilt strength: interpolate between neutral (1.0) and raw tilt
    # tilt_strength=0 → no tilt (1.0), tilt_strength=1 → full tilt
    value_tilt = 1.0 + tilt_strength * (raw_value_tilt - 1.0)
    quality_tilt = 1.0 + tilt_strength * (raw_quality_tilt - 1.0)
    
    # Clip to reasonable range based on tilt strength
    max_range = 0.3 * tilt_strength  # e.g., 0.3 if tilt_strength=1.0
    value_tilt = max(1.0 - max_range, min(1.0 + max_range, value_tilt))
    quality_tilt = max(1.0 - max_range, min(1.0 + max_range, quality_tilt))
    
    # Momentum: no direct FF factor, keep neutral
    momentum_tilt = 1.0
    
    return {
        'Value': value_tilt,
        'Quality': quality_tilt,
        'Momentum': momentum_tilt,
        # Also include keys expected by display_factor_summary()
        'value_tilt': value_tilt,
        'quality_tilt': quality_tilt,
        'momentum_tilt': momentum_tilt,
        'value_regime': factors.get('HML', {}).get('regime', 'NEUTRAL'),
        'quality_regime': factors.get('RMW', {}).get('regime', 'NEUTRAL'),
        'hml_regime': factors.get('HML', {}).get('regime', 'NEUTRAL'),
        'quality_source': f"RMW={factors.get('RMW', {}).get('regime', 'N/A')}, SMB={factors.get('SMB', {}).get('regime', 'N/A')}"
    }


def display_factor_regime_summary(factor_set: str = "3factor"):
    """Display a formatted summary of current factor regimes."""
    
    print("\n" + "=" * 80)
    print(f"📈 FAMA-FRENCH {factor_set.upper()} REGIME SUMMARY")
    print("=" * 80 + "\n")
    
    regime_info = get_factor_regime(factor_set=factor_set)
    
    if not regime_info.get('available', False):
        print("❌ Fama-French data unavailable")
        return
    
    factors = regime_info.get('factors', {})
    
    print(f"Analysis Window: {regime_info['window_months']} months")
    print(f"As of: {regime_info['as_of_date']}")
    print()
    
    print(f"{'Factor':<10} {'Regime':<20} {'Weight':<10} {'Z-Score':<10}")
    print("-" * 80)
    
    for factor_name, factor_data in factors.items():
        regime = factor_data['regime']
        weight = factor_data['weight']
        z_score = factor_data['z_score']
        
        print(f"{factor_name:<10} {regime:<20} {weight:<10.2f} {z_score:<10.2f}")
    
    print()
    
    # Show implied tilts
    tilts = get_factor_tilts(regime_info, tilt_strength=0.5)
    
    print("Implied Factor Tilts (for portfolio construction):")
    for factor, tilt in tilts.items():
        direction = "↑" if tilt > 1.05 else "↓" if tilt < 0.95 else "→"
        print(f"  {factor:<12} {tilt:.2f}x {direction}")
    
    print("\n" + "=" * 80 + "\n")


def display_factor_summary(tilt_data: dict):
    """Display formatted summary of factor tilts for portfolio integration.
    
    Args:
        tilt_data: Dictionary from get_factor_tilts() containing tilt multipliers
    """
    print(f"   Factor Regime Tilts:")
    print(f"      Value:    {tilt_data['value_tilt']:.2f}x ({tilt_data['value_regime']})")
    print(f"      Quality:  {tilt_data['quality_tilt']:.2f}x ({tilt_data['quality_regime']})")
    print(f"      Momentum: {tilt_data['momentum_tilt']:.2f}x (Market trend)")
    
    if 'hml_regime' in tilt_data:
        print(f"   Source: HML={tilt_data['hml_regime']}, RMW/SMB={tilt_data.get('quality_source', 'N/A')}")
    
    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    """Test the Fama-French factor loader."""
    
    print("\n" + "=" * 80)
    print("🧪 FAMA-FRENCH FACTOR LOADER TEST")
    print("=" * 80 + "\n")
    
    # Test 1: Download 3-factor data
    df = get_ff_factors(factor_set="3factor", use_cache=False)
    
    if df is not None:
        print(f"✅ Successfully loaded {len(df)} rows")
        print(f"   Date range: {df['Date'].min()} to {df['Date'].max()}")
        print(f"   Columns: {list(df.columns)}")
        print()
        
        # Show recent data
        print("Recent factor returns (%):")
        print(df.tail(10))
        print()
    
    # Test 2: Get factor regimes
    regime = get_factor_regime(factor_set="3factor", window_months=12)
    print("Factor Regimes:")
    for factor, data in regime.get('factors', {}).items():
        print(f"  {factor}: {data['regime']} (Z={data['z_score']:.2f})")
    print()
    
    # Test 3: Get factor tilts
    tilts = get_factor_tilts(regime, tilt_strength=0.5)
    print(f"Factor Tilts: {tilts}")
    print()
    
    # Test 4: Display summary
    display_factor_regime_summary("3factor")
