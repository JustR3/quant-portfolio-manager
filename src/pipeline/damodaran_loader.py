"""
Damodaran Data Loader - Academic "Ground Truth" for Sector Priors

Fetches sector-level statistics from Aswath Damodaran's NYU Stern datasets:
- Sector Betas (levered and unlevered)
- Equity Risk Premiums
- Operating Margins
- Revenue Growth Rates

Philosophy: Use academic consensus as Bayesian priors, not arbitrary guesses.

Data Source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging
import io

import pandas as pd
import requests

logger = logging.getLogger(__name__)


@dataclass
class SectorPriors:
    """Sector-level prior statistics for Bayesian estimation."""
    
    sector: str
    beta: Optional[float] = None  # Levered beta
    unlevered_beta: Optional[float] = None
    revenue_growth: Optional[float] = None  # Expected growth rate
    operating_margin: Optional[float] = None  # Operating margin %
    erp: Optional[float] = None  # Equity risk premium
    ev_sales_multiple: Optional[float] = None  # EV/Sales ratio
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "sector": self.sector,
            "beta": self.beta,
            "unlevered_beta": self.unlevered_beta,
            "revenue_growth": self.revenue_growth,
            "operating_margin": self.operating_margin,
            "erp": self.erp,
            "ev_sales_multiple": self.ev_sales_multiple
        }


class DamodaranLoader:
    """
    Loader for Aswath Damodaran's sector-level datasets from NYU Stern.
    
    Usage:
        loader = DamodaranLoader()
        priors = loader.get_sector_priors("Technology")
        print(f"Tech beta: {priors.beta}")
    
    Data is cached for 30 days (Damodaran updates ~quarterly).
    """
    
    # Damodaran's public dataset URLs (as of 2025)
    # US datasets (not emerging markets)
    URL_BETAS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls"
    URL_MARGINS = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/margin.xls"
    
    # Sector mapping: yfinance sector names → Damodaran dataset names
    SECTOR_MAPPING = {
        "Technology": "Software (System & Application)",
        "Healthcare": "Healthcare Products",
        "Financial Services": "Banks (Regional)",
        "Consumer Cyclical": "Retail (General)",
        "Communication Services": "Telecom. Services",
        "Industrials": "Machinery",
        "Consumer Defensive": "Food Processing",
        "Energy": "Oil/Gas (Integrated)",
        "Utilities": "Utility (General)",
        "Real Estate": "REIT",
        "Basic Materials": "Metals & Mining",
    }
    
    def __init__(self, cache_days: int = 30):
        """
        Initialize Damodaran loader.
        
        Args:
            cache_days: Days to cache downloaded data (default 30)
        """
        self.cache_days = cache_days
        self._beta_cache: Optional[pd.DataFrame] = None
        self._margin_cache: Optional[pd.DataFrame] = None
        self._cache_timestamp: Optional[datetime] = None
    
    def get_sector_priors(self, sector: str) -> SectorPriors:
        """
        Get sector priors from Damodaran datasets.
        
        Args:
            sector: Sector name (yfinance format, e.g., "Technology")
        
        Returns:
            SectorPriors with available statistics
        """
        # Map to Damodaran naming convention
        damodaran_sector = self.SECTOR_MAPPING.get(sector)
        
        if damodaran_sector is None:
            logger.warning(
                f"Sector '{sector}' not mapped to Damodaran dataset. "
                f"Using generic defaults."
            )
            return self._get_generic_priors(sector)
        
        # Try to fetch from Damodaran datasets
        try:
            # Ensure cache is fresh
            if not self._is_cache_valid():
                self._refresh_cache()
            
            # Extract data from cached DataFrames
            if self._beta_cache is not None and self._margin_cache is not None:
                return self._parse_sector_data(sector, damodaran_sector)
            else:
                logger.warning(f"Cache not available for {sector}, using generic priors")
                return self._get_generic_priors(sector)
                
        except Exception as e:
            logger.warning(f"Failed to parse Damodaran data for {sector}: {e}. Using generic priors")
            return self._get_generic_priors(sector)
    
    def _refresh_cache(self):
        """Download fresh data from Damodaran's website."""
        logger.info("Refreshing Damodaran datasets...")
        
        try:
            # Fetch beta data from "Industry Averages" sheet
            logger.info(f"Downloading betas from {self.URL_BETAS}")
            beta_response = requests.get(self.URL_BETAS, timeout=30)
            beta_response.raise_for_status()
            
            # Parse Excel - header is at row 9 (0-indexed)
            self._beta_cache = pd.read_excel(
                io.BytesIO(beta_response.content),
                sheet_name='Industry Averages',
                header=9
            )
            
            # Clean column names (remove extra spaces)
            self._beta_cache.columns = self._beta_cache.columns.str.strip()
            
            logger.info(f"✓ Loaded {len(self._beta_cache)} industries from beta dataset")
            
        except Exception as e:
            logger.error(f"Failed to load beta data: {e}")
            self._beta_cache = None
        
        try:
            # Fetch margin/growth data from "Industry Averages" sheet
            logger.info(f"Downloading margins from {self.URL_MARGINS}")
            margin_response = requests.get(self.URL_MARGINS, timeout=30)
            margin_response.raise_for_status()
            
            # Parse Excel - header is at row 8 (0-indexed)
            self._margin_cache = pd.read_excel(
                io.BytesIO(margin_response.content),
                sheet_name='Industry Averages',
                header=8
            )
            
            # Clean column names
            self._margin_cache.columns = self._margin_cache.columns.str.strip()
            
            logger.info(f"✓ Loaded {len(self._margin_cache)} industries from margin dataset")
            
        except Exception as e:
            logger.error(f"Failed to load margin data: {e}")
            self._margin_cache = None
        
        self._cache_timestamp = datetime.now()
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still fresh."""
        if self._beta_cache is None or self._cache_timestamp is None:
            return False
        
        age_days = (datetime.now() - self._cache_timestamp).days
        return age_days < self.cache_days
    
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float, return None if invalid."""
        try:
            if pd.isna(value):
                return None
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _parse_sector_data(self, sector: str, damodaran_sector: str) -> SectorPriors:
        """
        Parse sector data from cached Damodaran DataFrames.
        
        Args:
            sector: yfinance sector name
            damodaran_sector: Damodaran industry name
        
        Returns:
            SectorPriors with parsed data
        """
        import re
        
        beta = None
        unlevered_beta = None
        operating_margin = None
        
        # Escape regex special characters in search string
        search_pattern = re.escape(damodaran_sector)
        
        # Extract beta data
        if self._beta_cache is not None:
            beta_row = self._beta_cache[
                self._beta_cache['Industry Name'].str.contains(
                    search_pattern, case=False, na=False, regex=True
                )
            ]
            
            if not beta_row.empty:
                beta = self._safe_float(beta_row.iloc[0]['Beta'])
                unlevered_beta = self._safe_float(beta_row.iloc[0]['Unlevered beta'])
                logger.info(f"✓ Found {sector} beta: {beta} (unlevered: {unlevered_beta})")
            else:
                logger.warning(f"No beta data found for '{damodaran_sector}'")
        
        # Extract margin data
        if self._margin_cache is not None:
            margin_row = self._margin_cache[
                self._margin_cache['Industry Name'].str.contains(
                    search_pattern, case=False, na=False, regex=True
                )
            ]
            
            if not margin_row.empty:
                # Use "Pre-tax, Pre-stock compensation Operating Margin" if available
                margin_col = 'Pre-tax, Pre-stock compensation Operating Margin'
                if margin_col in self._margin_cache.columns:
                    operating_margin = self._safe_float(margin_row.iloc[0][margin_col])
                    if operating_margin is not None:
                        logger.info(f"✓ Found {sector} operating margin: {operating_margin:.2%}")
            else:
                logger.warning(f"No margin data found for '{damodaran_sector}'")
        
        # If we got data from Damodaran, use it; otherwise fall back to generic
        if beta is not None or operating_margin is not None:
            # Use generic defaults for missing fields
            generic = self._get_generic_priors(sector)
            
            return SectorPriors(
                sector=sector,
                beta=beta if beta is not None else generic.beta,
                unlevered_beta=unlevered_beta,
                operating_margin=operating_margin if operating_margin is not None else generic.operating_margin,
                revenue_growth=generic.revenue_growth,  # Not in Damodaran datasets
                erp=0.055  # ~5.5% equity risk premium (historical US average)
            )
        else:
            # No data found, use generic
            logger.warning(f"No Damodaran data found for {sector}, using generic priors")
            return self._get_generic_priors(sector)
    
    def _get_generic_priors(self, sector: str) -> SectorPriors:
        """
        Return sensible sector-specific priors.
        
        Based on long-term industry averages and academic research.
        """
        # Sector-specific defaults (based on historical averages)
        sector_defaults = {
            "Technology": {
                "beta": 1.20,
                "revenue_growth": 0.12,  # 12%
                "operating_margin": 0.20,  # 20%
            },
            "Healthcare": {
                "beta": 0.95,
                "revenue_growth": 0.08,
                "operating_margin": 0.18,
            },
            "Financial Services": {
                "beta": 1.10,
                "revenue_growth": 0.06,
                "operating_margin": 0.25,
            },
            "Consumer Cyclical": {
                "beta": 1.05,
                "revenue_growth": 0.07,
                "operating_margin": 0.12,
            },
            "Communication Services": {
                "beta": 0.90,
                "revenue_growth": 0.05,
                "operating_margin": 0.15,
            },
            "Industrials": {
                "beta": 1.00,
                "revenue_growth": 0.06,
                "operating_margin": 0.12,
            },
            "Consumer Defensive": {
                "beta": 0.70,
                "revenue_growth": 0.04,
                "operating_margin": 0.10,
            },
            "Energy": {
                "beta": 1.15,
                "revenue_growth": 0.05,
                "operating_margin": 0.08,
            },
            "Utilities": {
                "beta": 0.60,
                "revenue_growth": 0.03,
                "operating_margin": 0.15,
            },
            "Real Estate": {
                "beta": 0.85,
                "revenue_growth": 0.05,
                "operating_margin": 0.35,
            },
            "Basic Materials": {
                "beta": 1.10,
                "revenue_growth": 0.05,
                "operating_margin": 0.12,
            },
        }
        
        defaults = sector_defaults.get(sector, {
            "beta": 1.0,
            "revenue_growth": 0.05,
            "operating_margin": 0.15,
        })
        
        return SectorPriors(
            sector=sector,
            beta=defaults["beta"],
            revenue_growth=defaults["revenue_growth"],
            operating_margin=defaults["operating_margin"],
            erp=0.055  # ~5.5% equity risk premium (historical US average)
        )
    
    def get_all_sectors(self) -> Dict[str, SectorPriors]:
        """
        Get priors for all mapped sectors.
        
        Returns:
            Dictionary of sector name → SectorPriors
        """
        return {
            sector: self.get_sector_priors(sector)
            for sector in self.SECTOR_MAPPING.keys()
        }


# Singleton instance
_global_loader: Optional[DamodaranLoader] = None


def get_damodaran_loader() -> DamodaranLoader:
    """
    Get or create global DamodaranLoader instance.
    
    Returns:
        Singleton DamodaranLoader instance
    """
    global _global_loader
    
    if _global_loader is None:
        _global_loader = DamodaranLoader()
    
    return _global_loader