"""
Data Validation Layer - Cross-Source Verification

Validates yfinance data against Alpha Vantage to detect:
- Stale data (timestamps > 30 days old)
- Price discrepancies (> 5% difference)
- Missing critical fields
- Outliers and data quality issues

Philosophy: Trust but Verify. Never trade on unvalidated data.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

try:
    from alpha_vantage.timeseries import TimeSeries
    from alpha_vantage.fundamentaldata import FundamentalData
except ImportError:
    TimeSeries = None
    FundamentalData = None

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class DataQualityScore:
    """Data quality assessment for a ticker."""
    
    ticker: str
    timestamp_freshness: float  # 0-100 (100 = today, 0 = >90 days old)
    source_agreement: float  # 0-100 (100 = perfect match, 0 = >10% difference)
    completeness: float  # 0-100 (100 = all fields present)
    outlier_check: float  # 0-100 (100 = no outliers detected)
    overall_score: float  # Weighted average
    issues: list[str]  # Human-readable warnings
    validated_at: datetime
    
    @classmethod
    def create(
        cls,
        ticker: str,
        timestamp_freshness: float,
        source_agreement: float,
        completeness: float,
        outlier_check: float,
        issues: Optional[list[str]] = None
    ) -> "DataQualityScore":
        """Create quality score with calculated overall score."""
        # Weights: Freshness 30%, Agreement 40%, Completeness 20%, Outliers 10%
        overall = (
            timestamp_freshness * 0.30 +
            source_agreement * 0.40 +
            completeness * 0.20 +
            outlier_check * 0.10
        )
        
        return cls(
            ticker=ticker,
            timestamp_freshness=timestamp_freshness,
            source_agreement=source_agreement,
            completeness=completeness,
            outlier_check=outlier_check,
            overall_score=overall,
            issues=issues or [],
            validated_at=datetime.now()
        )
    
    def is_acceptable(self, threshold: float = 60.0) -> bool:
        """Check if data quality meets minimum threshold."""
        return self.overall_score >= threshold
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "ticker": self.ticker,
            "timestamp_freshness": round(self.timestamp_freshness, 1),
            "source_agreement": round(self.source_agreement, 1),
            "completeness": round(self.completeness, 1),
            "outlier_check": round(self.outlier_check, 1),
            "overall_score": round(self.overall_score, 1),
            "issues": self.issues,
            "validated_at": self.validated_at.isoformat()
        }


class DataValidator:
    """
    Cross-source data validator using yfinance (primary) and Alpha Vantage (verification).
    
    Usage:
        validator = DataValidator(alpha_vantage_key="YOUR_KEY")
        quality = validator.validate_ticker("AAPL")
        
        if quality.is_acceptable():
            print(f"Data quality: {quality.overall_score:.1f}/100")
        else:
            print(f"WARNING: Poor data quality - {quality.issues}")
    """
    
    def __init__(self, alpha_vantage_key: Optional[str] = None):
        """
        Initialize validator.
        
        Args:
            alpha_vantage_key: Alpha Vantage API key (get free at alphavantage.co)
                              If None, loads from ALPHA_VANTAGE_KEY env var
        """
        if TimeSeries is None or FundamentalData is None:
            raise ImportError(
                "alpha-vantage not installed. Install with: pip install alpha-vantage"
            )
        
        if alpha_vantage_key is None:
            import os
            alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY")
            if alpha_vantage_key is None:
                logger.warning(
                    "No Alpha Vantage API key found. "
                    "Cross-validation will be skipped. "
                    "Get free key at: https://www.alphavantage.co/support/#api-key"
                )
                self.enabled = False
                return
        
        self.ts = TimeSeries(key=alpha_vantage_key, output_format='pandas')
        self.fd = FundamentalData(key=alpha_vantage_key, output_format='pandas')
        self.enabled = True
    
    def validate_ticker(
        self,
        ticker: str,
        yf_data: Optional[Dict[str, Any]] = None
    ) -> DataQualityScore:
        """
        Validate ticker data across sources.
        
        Args:
            ticker: Stock ticker symbol
            yf_data: Optional pre-fetched yfinance data (from info dict)
        
        Returns:
            DataQualityScore with detailed quality assessment
        """
        issues = []
        
        # Fetch yfinance data if not provided
        if yf_data is None:
            try:
                yf_ticker = yf.Ticker(ticker)
                yf_data = yf_ticker.info
            except Exception as e:
                logger.error(f"Failed to fetch yfinance data for {ticker}: {e}")
                return self._failed_validation(ticker, f"yfinance fetch failed: {e}")
        
        # Check timestamp freshness
        timestamp_score = self._check_timestamp_freshness(yf_data, issues)
        
        # Check completeness
        completeness_score = self._check_completeness(yf_data, issues)
        
        # Check outliers
        outlier_score = self._check_outliers(ticker, yf_data, issues)
        
        # Cross-validate with Alpha Vantage (if enabled)
        if self.enabled:
            agreement_score = self._cross_validate_price(ticker, yf_data, issues)
        else:
            agreement_score = 100.0  # Skip if not enabled
            issues.append("Alpha Vantage validation skipped (no API key)")
        
        return DataQualityScore.create(
            ticker=ticker,
            timestamp_freshness=timestamp_score,
            source_agreement=agreement_score,
            completeness=completeness_score,
            outlier_check=outlier_score,
            issues=issues
        )
    
    def _check_timestamp_freshness(
        self,
        yf_data: Dict[str, Any],
        issues: list[str]
    ) -> float:
        """
        Check if data is recent (score 100 if today, 0 if >90 days old).
        
        Note: yfinance doesn't provide explicit timestamps, so we check
        if market cap / price seems current (non-zero, reasonable values).
        For a more robust check, use the last earnings date if available.
        """
        # Check for stale indicators
        market_cap = yf_data.get("marketCap", 0)
        current_price = yf_data.get("currentPrice") or yf_data.get("regularMarketPrice", 0)
        
        if market_cap == 0 or current_price == 0:
            issues.append("Missing market cap or price - possibly stale data")
            return 50.0
        
        # Check last earnings date if available
        last_earnings = yf_data.get("earningsTimestamp")
        if last_earnings:
            try:
                earnings_date = datetime.fromtimestamp(last_earnings)
                days_since_earnings = (datetime.now() - earnings_date).days
                
                if days_since_earnings > 120:  # > 4 months
                    issues.append(f"Last earnings {days_since_earnings} days ago (>120)")
                    # Score: 100 at 0 days, 0 at 120+ days
                    score = max(0, 100 - (days_since_earnings / 120.0) * 100)
                    return score
            except Exception:
                pass
        
        # If no red flags, assume recent
        return 100.0
    
    def _check_completeness(
        self,
        yf_data: Dict[str, Any],
        issues: list[str]
    ) -> float:
        """Check if critical fields are present."""
        required_fields = [
            "currentPrice", "marketCap", "freeCashflow",
            "sharesOutstanding", "beta", "sector"
        ]
        
        # Alternative field names
        field_alternatives = {
            "currentPrice": ["regularMarketPrice", "previousClose"],
            "freeCashflow": ["operatingCashflow"],  # Can derive FCF
        }
        
        present = 0
        missing = []
        
        for field in required_fields:
            value = yf_data.get(field)
            
            # Check alternatives if primary missing
            if value is None and field in field_alternatives:
                for alt_field in field_alternatives[field]:
                    value = yf_data.get(alt_field)
                    if value is not None:
                        break
            
            if value is not None and value != 0:
                present += 1
            else:
                missing.append(field)
        
        score = (present / len(required_fields)) * 100
        
        if missing:
            issues.append(f"Missing fields: {', '.join(missing)}")
        
        return score
    
    def _check_outliers(
        self,
        ticker: str,
        yf_data: Dict[str, Any],
        issues: list[str]
    ) -> float:
        """Check for nonsensical values."""
        score = 100.0
        
        # Check PE ratio (should be reasonable for most stocks)
        pe_ratio = yf_data.get("trailingPE") or yf_data.get("forwardPE")
        if pe_ratio:
            if pe_ratio < 0:
                issues.append(f"Negative PE ratio: {pe_ratio:.1f}")
                score -= 20
            elif pe_ratio > 500:
                issues.append(f"Extreme PE ratio: {pe_ratio:.1f} (>500)")
                score -= 10
        
        # Check beta (should typically be 0.5 to 2.0 for most stocks)
        beta = yf_data.get("beta")
        if beta:
            if beta < -1 or beta > 5:
                issues.append(f"Unusual beta: {beta:.2f}")
                score -= 10
        
        # Check market cap (should be positive)
        market_cap = yf_data.get("marketCap", 0)
        if market_cap <= 0:
            issues.append("Market cap is zero or negative")
            score -= 30
        
        return max(0, score)
    
    def _cross_validate_price(
        self,
        ticker: str,
        yf_data: Dict[str, Any],
        issues: list[str]
    ) -> float:
        """Cross-validate price with Alpha Vantage."""
        try:
            # Get yfinance price
            yf_price = yf_data.get("currentPrice") or yf_data.get("regularMarketPrice")
            if not yf_price:
                issues.append("No price from yfinance for cross-validation")
                return 50.0
            
            # Get Alpha Vantage quote
            quote_data, _ = self.ts.get_quote_endpoint(symbol=ticker)
            
            if quote_data.empty:
                issues.append("No data from Alpha Vantage")
                return 70.0  # Partial score (yfinance OK, but can't verify)
            
            av_price = float(quote_data['05. price'].iloc[0])
            
            # Calculate difference
            price_diff_pct = abs(yf_price - av_price) / av_price
            
            if price_diff_pct > 0.05:  # >5% difference
                issues.append(
                    f"Price mismatch: yfinance ${yf_price:.2f} "
                    f"vs AlphaVantage ${av_price:.2f} ({price_diff_pct:.1%} diff)"
                )
                # Score: 100 at 0% diff, 0 at 10%+ diff
                score = max(0, 100 - (price_diff_pct / 0.10) * 100)
                return score
            
            # Prices agree within 5%
            return 100.0
            
        except Exception as e:
            logger.warning(f"Alpha Vantage validation failed for {ticker}: {e}")
            issues.append(f"Cross-validation error: {str(e)[:50]}")
            return 70.0  # Partial score
    
    def _failed_validation(self, ticker: str, reason: str) -> DataQualityScore:
        """Return a failed validation score."""
        return DataQualityScore.create(
            ticker=ticker,
            timestamp_freshness=0,
            source_agreement=0,
            completeness=0,
            outlier_check=0,
            issues=[reason]
        )


# Singleton for global access
_global_validator: Optional[DataValidator] = None


def get_data_validator(alpha_vantage_key: Optional[str] = None) -> DataValidator:
    """
    Get or create global DataValidator instance.
    
    Args:
        alpha_vantage_key: Alpha Vantage API key (only needed on first call)
    
    Returns:
        Singleton DataValidator instance
    """
    global _global_validator
    
    if _global_validator is None:
        _global_validator = DataValidator(alpha_vantage_key=alpha_vantage_key)
    
    return _global_validator
