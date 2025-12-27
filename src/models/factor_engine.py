"""
Factor Engine for Stock Ranking
Phase 2: Multi-Factor Stock Ranking System

Ranks stocks based on:
- Value: FCF Yield + Earnings Yield
- Quality: ROIC + Gross Margin
- Momentum: 12-Month Price Return
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import List, Dict
import warnings

warnings.filterwarnings('ignore')


class FactorEngine:
    """
    Multi-factor stock ranking engine.
    
    Fetches fundamental and price data, calculates factor scores,
    and ranks stocks by composite Z-score.
    """
    
    def __init__(self, tickers: List[str]):
        """
        Initialize the Factor Engine.
        
        Args:
            tickers: List of stock tickers to analyze
        """
        self.tickers = tickers
        self.data = {}
        self.factor_scores = None
        self.universe_stats = {}  # Store mean/std for each factor
        self.raw_factors = None  # Store raw factor values for auditing
        
    def fetch_data(self) -> None:
        """
        Bulk download all required data for the ticker universe.
        Downloads: Price history, income statement, balance sheet, cash flow.
        """
        print(f"📊 Fetching data for {len(self.tickers)} tickers...")
        
        # Bulk download price history (much faster than individual downloads)
        try:
            tickers_obj = yf.Tickers(' '.join(self.tickers))
            
            for ticker in self.tickers:
                try:
                    stock = tickers_obj.tickers[ticker]
                    
                    # Get price history (2 years for momentum calculation)
                    hist = stock.history(period='2y')
                    
                    # Get financial statements
                    income_stmt = stock.income_stmt
                    balance_sheet = stock.balance_sheet
                    cash_flow = stock.cashflow
                    
                    # Get current market cap and price
                    info = stock.info
                    
                    self.data[ticker] = {
                        'history': hist,
                        'income_stmt': income_stmt,
                        'balance_sheet': balance_sheet,
                        'cash_flow': cash_flow,
                        'info': info
                    }
                    
                except Exception as e:
                    print(f"  ⚠️  Failed to fetch {ticker}: {e}")
                    self.data[ticker] = None
                    
        except Exception as e:
            print(f"❌ Bulk download failed: {e}")
            
        print(f"✅ Data fetched for {len([v for v in self.data.values() if v is not None])} tickers\n")
    
    def calculate_value_factor(self, ticker: str) -> float:
        """
        Calculate Value Factor: FCF Yield (50%) + Earnings Yield (50%)
        
        FCF Yield = Free Cash Flow / Market Cap
        Earnings Yield = EBIT / Enterprise Value (approximated as Market Cap)
        """
        try:
            data = self.data.get(ticker)
            if data is None:
                return np.nan
            
            info = data['info']
            income_stmt = data['income_stmt']
            cash_flow = data['cash_flow']
            
            # Get market cap
            market_cap = info.get('marketCap')
            if not market_cap or market_cap <= 0:
                return np.nan
            
            # FCF Yield
            fcf_yield = 0
            if not cash_flow.empty and 'Free Cash Flow' in cash_flow.index:
                fcf = cash_flow.loc['Free Cash Flow'].iloc[0]  # Most recent
                if pd.notna(fcf) and fcf > 0:
                    fcf_yield = fcf / market_cap
            
            # Earnings Yield (using EBIT)
            earnings_yield = 0
            if not income_stmt.empty and 'EBIT' in income_stmt.index:
                ebit = income_stmt.loc['EBIT'].iloc[0]  # Most recent
                if pd.notna(ebit) and ebit > 0:
                    earnings_yield = ebit / market_cap
            
            # Composite: 50/50 blend
            value_score = 0.5 * fcf_yield + 0.5 * earnings_yield
            return value_score if value_score > 0 else np.nan
            
        except Exception as e:
            # print(f"  Value calc failed for {ticker}: {e}")
            return np.nan
    
    def calculate_quality_factor(self, ticker: str) -> float:
        """
        Calculate Quality Factor: ROIC (50%) + Gross Margin (50%)
        
        ROIC = EBIT / Invested Capital
        Invested Capital ≈ Total Assets - Current Liabilities
        Gross Margin = Gross Profit / Revenue
        """
        try:
            data = self.data.get(ticker)
            if data is None:
                return np.nan
            
            income_stmt = data['income_stmt']
            balance_sheet = data['balance_sheet']
            
            # ROIC calculation
            roic = 0
            if not income_stmt.empty and not balance_sheet.empty:
                if 'EBIT' in income_stmt.index:
                    ebit = income_stmt.loc['EBIT'].iloc[0]
                    
                    # Invested Capital = Total Assets - Current Liabilities
                    total_assets = balance_sheet.loc['Total Assets'].iloc[0] if 'Total Assets' in balance_sheet.index else 0
                    current_liabilities = balance_sheet.loc['Current Liabilities'].iloc[0] if 'Current Liabilities' in balance_sheet.index else 0
                    
                    invested_capital = total_assets - current_liabilities
                    
                    if invested_capital > 0 and pd.notna(ebit):
                        roic = ebit / invested_capital
            
            # Gross Margin
            gross_margin = 0
            if not income_stmt.empty:
                if 'Gross Profit' in income_stmt.index and 'Total Revenue' in income_stmt.index:
                    gross_profit = income_stmt.loc['Gross Profit'].iloc[0]
                    revenue = income_stmt.loc['Total Revenue'].iloc[0]
                    
                    if revenue > 0 and pd.notna(gross_profit):
                        gross_margin = gross_profit / revenue
            
            # Composite: 50/50 blend
            quality_score = 0.5 * roic + 0.5 * gross_margin
            return quality_score if not np.isnan(quality_score) else np.nan
            
        except Exception as e:
            # print(f"  Quality calc failed for {ticker}: {e}")
            return np.nan
    
    def calculate_momentum_factor(self, ticker: str) -> float:
        """
        Calculate Momentum Factor: 12-Month Price Return
        
        Return = (Price_Now / Price_12M_Ago) - 1
        """
        try:
            data = self.data.get(ticker)
            if data is None:
                return np.nan
            
            hist = data['history']
            
            if hist.empty or len(hist) < 250:  # Need at least ~1 year of data
                return np.nan
            
            # Get current price and 12-month ago price
            current_price = hist['Close'].iloc[-1]
            
            # Try to get price from ~252 trading days ago (1 year)
            lookback_days = min(252, len(hist) - 1)
            past_price = hist['Close'].iloc[-lookback_days]
            
            if pd.notna(current_price) and pd.notna(past_price) and past_price > 0:
                momentum = (current_price / past_price) - 1
                return momentum
            else:
                return np.nan
                
        except Exception as e:
            # print(f"  Momentum calc failed for {ticker}: {e}")
            return np.nan
    
    def calculate_z_scores(self, values: pd.Series, factor_name: str = None) -> pd.Series:
        """
        Calculate Z-scores and winsorize at +/- 3.
        
        Z-Score = (Value - Mean) / StdDev
        
        Args:
            values: Series of raw factor values
            factor_name: Name of the factor (for storing universe stats)
        """
        # Drop NaN values for mean/std calculation
        valid_values = values.dropna()
        
        if len(valid_values) < 2:
            # Not enough data to calculate std
            if factor_name:
                self.universe_stats[factor_name] = {'mean': 0, 'std': 0, 'count': len(valid_values)}
            return pd.Series(0, index=values.index)
        
        mean = valid_values.mean()
        std = valid_values.std()
        
        # Store universe statistics for this factor
        if factor_name:
            self.universe_stats[factor_name] = {
                'mean': mean,
                'std': std,
                'count': len(valid_values),
                'min': valid_values.min(),
                'max': valid_values.max()
            }
        
        if std == 0 or np.isnan(std):
            # No variation, return zeros
            return pd.Series(0, index=values.index)
        
        # Calculate Z-scores
        z_scores = (values - mean) / std
        
        # Fill NaN with 0 (neutral score for missing data)
        z_scores = z_scores.fillna(0)
        
        # Winsorize at +/- 3
        z_scores = z_scores.clip(-3, 3)
        
        return z_scores
    
    def rank_universe(self) -> pd.DataFrame:
        """
        Calculate all factors and rank stocks by composite score.
        
        Returns:
            DataFrame with columns: [Ticker, Value_Z, Quality_Z, Momentum_Z, Total_Score]
            sorted by Total_Score descending
        """
        if not self.data:
            self.fetch_data()
        
        print("🔬 Calculating factor scores...")
        
        # Calculate raw factor values for all tickers
        results = []
        
        for ticker in self.tickers:
            value = self.calculate_value_factor(ticker)
            quality = self.calculate_quality_factor(ticker)
            momentum = self.calculate_momentum_factor(ticker)
            
            results.append({
                'Ticker': ticker,
                'Value_Raw': value,
                'Quality_Raw': quality,
                'Momentum_Raw': momentum
            })
        
        df = pd.DataFrame(results)
        
        # Store raw factors for auditing
        self.raw_factors = df.copy()
        
        # Calculate Z-scores with universe statistics
        df['Value_Z'] = self.calculate_z_scores(df['Value_Raw'], 'value')
        df['Quality_Z'] = self.calculate_z_scores(df['Quality_Raw'], 'quality')
        df['Momentum_Z'] = self.calculate_z_scores(df['Momentum_Raw'], 'momentum')
        
        # Composite score: 40% Value, 40% Quality, 20% Momentum
        df['Total_Score'] = (
            0.4 * df['Value_Z'] +
            0.4 * df['Quality_Z'] +
            0.2 * df['Momentum_Z']
        )
        
        # Sort by total score descending
        df = df.sort_values('Total_Score', ascending=False).reset_index(drop=True)
        
        # Store full dataframe with raw values
        self.factor_scores = df
        
        # Return simplified view
        output_df = df[['Ticker', 'Value_Z', 'Quality_Z', 'Momentum_Z', 'Total_Score']].copy()
        
        print("✅ Factor ranking complete!\n")
        return output_df
    
    def generate_audit_report(self, ticker: str) -> Dict:
        """
        Generate a detailed audit report for a specific stock.
        
        Args:
            ticker: Stock ticker to audit
            
        Returns:
            Dictionary containing detailed factor analysis and ranking explanation
        """
        if self.factor_scores is None:
            raise ValueError("No rankings available. Run rank_universe() first.")
        
        # Find the ticker in the results
        stock_data = self.factor_scores[self.factor_scores['Ticker'] == ticker]
        
        if stock_data.empty:
            raise ValueError(f"Ticker {ticker} not found in universe.")
        
        row = stock_data.iloc[0]
        
        # Calculate rank and percentile
        rank = stock_data.index[0] + 1
        total_stocks = len(self.factor_scores)
        percentile = 1 - (rank - 1) / total_stocks
        
        # Extract scores
        value_z = row['Value_Z']
        quality_z = row['Quality_Z']
        momentum_z = row['Momentum_Z']
        total_score = row['Total_Score']
        
        # Get raw values
        value_raw = row['Value_Raw']
        quality_raw = row['Quality_Raw']
        momentum_raw = row['Momentum_Raw']
        
        # Helper function to interpret Z-score
        def interpret_z(z: float) -> str:
            if z > 1.5:
                return "Very Strong Positive"
            elif z > 0.5:
                return "Strong Positive"
            elif z > -0.5:
                return "Neutral"
            elif z > -1.5:
                return "Weak/Negative"
            else:
                return "Very Weak/Negative"
        
        # Build the report
        report = {
            'ticker': ticker,
            'rank': rank,
            'total_stocks': total_stocks,
            'rank_percentile': percentile,
            'total_score': total_score,
            'factors': {
                'value': {
                    'z_score': value_z,
                    'raw_value': value_raw,
                    'universe_mean': self.universe_stats.get('value', {}).get('mean', 0),
                    'universe_std': self.universe_stats.get('value', {}).get('std', 0),
                    'contribution': 0.4 * value_z,
                    'interpretation': interpret_z(value_z)
                },
                'quality': {
                    'z_score': quality_z,
                    'raw_value': quality_raw,
                    'universe_mean': self.universe_stats.get('quality', {}).get('mean', 0),
                    'universe_std': self.universe_stats.get('quality', {}).get('std', 0),
                    'contribution': 0.4 * quality_z,
                    'interpretation': interpret_z(quality_z)
                },
                'momentum': {
                    'z_score': momentum_z,
                    'raw_value': momentum_raw,
                    'universe_mean': self.universe_stats.get('momentum', {}).get('mean', 0),
                    'universe_std': self.universe_stats.get('momentum', {}).get('std', 0),
                    'contribution': 0.2 * momentum_z,
                    'interpretation': interpret_z(momentum_z)
                }
            }
        }
        
        # Generate summary
        strengths = []
        weaknesses = []
        
        for factor_name, factor_data in report['factors'].items():
            if factor_data['z_score'] > 0.5:
                strengths.append(factor_name.capitalize())
            elif factor_data['z_score'] < -0.5:
                weaknesses.append(factor_name.capitalize())
        
        if strengths and weaknesses:
            summary = f"Mixed profile. Strong in {', '.join(strengths)}. Weak in {', '.join(weaknesses)}."
        elif strengths:
            summary = f"Strong {', '.join(strengths)} play. Outperforming peers."
        elif weaknesses:
            summary = f"Weak across {', '.join(weaknesses)}. Underperforming peers."
        else:
            summary = "Neutral profile. Near universe average across all factors."
        
        report['summary'] = summary
        
        return report
    
    def display_audit_report(self, ticker: str) -> None:
        """
        Display a formatted audit report for a specific stock.
        
        Args:
            ticker: Stock ticker to audit
        """
        try:
            report = self.generate_audit_report(ticker)
        except ValueError as e:
            print(f"❌ {e}")
            return
        
        print("\n" + "=" * 80)
        print(f"🔍 FACTOR AUDIT REPORT: {report['ticker']}")
        print("=" * 80)
        
        print(f"\n📊 OVERALL RANKING")
        print(f"   Rank: #{report['rank']} of {report['total_stocks']} stocks")
        print(f"   Percentile: {report['rank_percentile']:.1%}")
        print(f"   Total Score: {report['total_score']:.3f}")
        
        print(f"\n📈 FACTOR BREAKDOWN\n")
        
        for factor_name, factor_data in report['factors'].items():
            print(f"   {factor_name.upper()}:")
            print(f"      Z-Score: {factor_data['z_score']:>8.2f}  ({factor_data['interpretation']})")
            print(f"      Raw Value: {factor_data['raw_value']:>6.4f}  (Universe Mean: {factor_data['universe_mean']:.4f})")
            print(f"      Contribution to Total Score: {factor_data['contribution']:>+.3f}")
            print()
        
        print(f"💡 SUMMARY")
        print(f"   {report['summary']}")
        
        print("\n" + "=" * 80 + "\n")
    
    def display_rankings(self) -> None:
        """Display the rankings in a formatted table."""
        if self.factor_scores is None:
            print("❌ No rankings available. Run rank_universe() first.")
            return
        
        print("=" * 80)
        print("📈 FACTOR-BASED STOCK RANKINGS")
        print("=" * 80)
        print(f"{'Rank':<6} {'Ticker':<8} {'Value Z':<10} {'Quality Z':<12} {'Momentum Z':<12} {'Total Score':<12}")
        print("-" * 80)
        
        for idx, row in self.factor_scores.iterrows():
            rank = idx + 1
            print(f"{rank:<6} {row['Ticker']:<8} {row['Value_Z']:>9.2f} {row['Quality_Z']:>11.2f} {row['Momentum_Z']:>11.2f} {row['Total_Score']:>11.2f}")
        
        print("=" * 80)
        print("\n💡 Higher scores = Better ranking")
        print("   Weights: Value 40% | Quality 40% | Momentum 20%\n")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🚀 PHASE 2: FACTOR ENGINE - MINI-UNIVERSE TEST")
    print("=" * 80 + "\n")
    
    # Mini-universe: 5 diverse stocks
    test_tickers = ["NVDA", "XOM", "JPM", "PFE", "TSLA"]
    
    print(f"Testing with mini-universe: {test_tickers}\n")
    
    # Initialize engine
    engine = FactorEngine(tickers=test_tickers)
    
    # Rank stocks
    rankings = engine.rank_universe()
    
    # Display results
    engine.display_rankings()
    
    # Test the audit report for the top-ranked stock
    print("\n" + "=" * 80)
    print("🔍 TESTING AUDIT REPORT - Top Ranked Stock")
    print("=" * 80)
    top_ticker = rankings.iloc[0]['Ticker']
    engine.display_audit_report(top_ticker)
    
    # Export to CSV
    output_file = "factor_rankings_test.csv"
    rankings.to_csv(output_file, index=False)
    print(f"💾 Rankings saved to: {output_file}\n")
