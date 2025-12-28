#!/usr/bin/env python3
"""
Build historical regime dataset (2000-2024).
Pre-computes regime states for all trading days to enable faster backtests.

Usage:
    python tools/build_regime_history.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from tqdm import tqdm

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.portfolio.regime import RegimeDetector, MarketRegime


def build_regime_history(
    start_date: str = "2000-01-01",
    end_date: str = "2024-12-31",
    output_dir: str = "data/historical/metadata"
):
    """
    Build comprehensive regime history dataset.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_dir: Output directory for parquet file
    """
    print("=" * 80)
    print("BUILDING HISTORICAL REGIME DATASET")
    print("=" * 80)
    print()
    
    # Parse dates
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    print(f"Period: {start_date} to {end_date}")
    print(f"Output: {output_dir}/regime_history.parquet")
    print()
    
    # Create date range (trading days only - Mon-Fri)
    all_dates = pd.date_range(start, end, freq='D')
    trading_days = [d for d in all_dates if d.weekday() < 5]  # Mon=0, Fri=4
    
    print(f"Total days: {len(all_dates)}")
    print(f"Trading days: {len(trading_days)}")
    print()
    
    # Initialize detector
    detector = RegimeDetector()
    
    # Build history
    print("Computing historical regimes...")
    print("⏱️  This will take 10-30 minutes depending on API rate limits...")
    print()
    
    regimes = []
    failed_dates = []
    
    for date in tqdm(trading_days, desc="Processing", unit="day"):
        date_str = date.strftime('%Y-%m-%d')
        
        try:
            # Get regime as of this date (point-in-time)
            result = detector.get_regime_with_details(
                use_cache=False,  # Don't cache during historical build
                method='combined',
                as_of_date=date_str
            )
            
            if result:
                regime_data = {
                    'date': date,
                    'regime': result.regime.value,
                    'method': result.method,
                    
                    # SPY data
                    'spy_price': result.current_price if result.current_price else None,
                    'spy_sma_200': result.sma_200 if result.sma_200 else None,
                    'spy_signal': ((result.current_price - result.sma_200) / result.sma_200 * 100) 
                                  if (result.current_price and result.sma_200) else None,
                    
                    # VIX data
                    'vix': result.vix_structure.vix if result.vix_structure else None,
                    'vix9d': result.vix_structure.vix9d if result.vix_structure else None,
                    'vix3m': result.vix_structure.vix3m if result.vix_structure else None,
                    'vix_backwardation': result.vix_structure.is_backwardation if result.vix_structure else None,
                }
                
                regimes.append(regime_data)
            else:
                failed_dates.append(date_str)
                
        except Exception as e:
            print(f"\n⚠️  Error on {date_str}: {str(e)}")
            failed_dates.append(date_str)
            continue
    
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    
    if regimes:
        df = pd.DataFrame(regimes)
        
        # Statistics
        print(f"✅ Successfully computed: {len(regimes)} days")
        print(f"❌ Failed: {len(failed_dates)} days")
        print(f"📊 Success rate: {len(regimes)/len(trading_days)*100:.1f}%")
        print()
        
        # Regime distribution
        print("Regime Distribution:")
        regime_counts = df['regime'].value_counts()
        for regime, count in regime_counts.items():
            pct = count / len(df) * 100
            print(f"  {regime}: {count} days ({pct:.1f}%)")
        print()
        
        # Sample transitions
        transitions = []
        for i in range(1, len(df)):
            if df.iloc[i]['regime'] != df.iloc[i-1]['regime']:
                transitions.append({
                    'date': df.iloc[i]['date'],
                    'from': df.iloc[i-1]['regime'],
                    'to': df.iloc[i]['regime']
                })
        
        print(f"Regime Transitions: {len(transitions)}")
        if transitions:
            print("\nFirst 10 transitions:")
            for t in transitions[:10]:
                print(f"  {t['date'].strftime('%Y-%m-%d')}: {t['from']} → {t['to']}")
        print()
        
        # Key crisis dates
        print("Key Crisis Date Regimes:")
        crisis_dates = {
            '2000-03-10': 'Dot-com peak',
            '2001-09-11': '9/11 attacks',
            '2008-09-15': 'Lehman collapse',
            '2008-10-10': 'Market bottom',
            '2020-02-19': 'COVID peak',
            '2020-03-23': 'COVID bottom',
            '2022-10-12': '2022 bear bottom'
        }
        
        for date_str, description in crisis_dates.items():
            try:
                date = pd.to_datetime(date_str)
                regime_row = df[df['date'] == date]
                if not regime_row.empty:
                    regime = regime_row.iloc[0]['regime']
                    print(f"  {date_str} ({description}): {regime}")
            except:
                pass
        print()
        
        # Save to parquet
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        output_file = output_path / "regime_history.parquet"
        df.to_parquet(output_file, index=False)
        
        print(f"✅ Saved to: {output_file}")
        print(f"📦 File size: {output_file.stat().st_size / 1024:.1f} KB")
        print()
        
        # Save failed dates log
        if failed_dates:
            failed_file = output_path / "regime_history_failed.txt"
            with open(failed_file, 'w') as f:
                f.write('\n'.join(failed_dates))
            print(f"⚠️  Failed dates logged to: {failed_file}")
            print()
        
        print("=" * 80)
        print("✅ REGIME HISTORY BUILD COMPLETE")
        print("=" * 80)
        print()
        print("Usage in backtests:")
        print("  - RegimeDetector will automatically use this dataset")
        print("  - 100-1000x faster than API calls")
        print("  - Fully reproducible results")
        print()
        
        return df
    else:
        print("❌ ERROR: No regimes computed successfully")
        print()
        if failed_dates:
            print("Failed dates:")
            for date in failed_dates[:20]:
                print(f"  {date}")
            if len(failed_dates) > 20:
                print(f"  ... and {len(failed_dates) - 20} more")
        print()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Build historical regime dataset for faster backtests"
    )
    parser.add_argument(
        '--start',
        type=str,
        default='2000-01-01',
        help='Start date (YYYY-MM-DD, default: 2000-01-01)'
    )
    parser.add_argument(
        '--end',
        type=str,
        default='2024-12-31',
        help='End date (YYYY-MM-DD, default: 2024-12-31)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/historical/metadata',
        help='Output directory (default: data/historical/metadata)'
    )
    
    args = parser.parse_args()
    
    # Build history
    df = build_regime_history(
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir
    )
    
    if df is not None:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
