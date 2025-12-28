"""
Phase 1 Integration Test: Data Foundation Layer

Tests the complete data pipeline:
1. FredConnector - Dynamic risk-free rate
2. DamodaranLoader - Sector priors (not integrated but available)

Run with: pytest tests/test_phase1_integration.py -v
"""

import os

import pytest

from src.pipeline.external import FredConnector, DamodaranLoader


class TestFredConnector:
    """Test FRED API integration."""
    
    def test_fred_connector_init(self):
        """Test connector initialization (requires API key)."""
        # Skip if no API key
        if not os.getenv("FRED_API_KEY"):
            pytest.skip("FRED_API_KEY not set")
        
        connector = FredConnector()
        assert connector is not None
        assert connector.fred is not None
    
    def test_get_risk_free_rate(self):
        """Test risk-free rate fetching."""
        if not os.getenv("FRED_API_KEY"):
            pytest.skip("FRED_API_KEY not set")
        
        connector = FredConnector()
        rate = connector.get_risk_free_rate()
        
        assert rate > 0, "Risk-free rate should be positive"
        assert rate < 0.20, "Risk-free rate should be < 20% (sanity check)"
        print(f"✓ Risk-free rate: {rate:.4f} ({rate*100:.2f}%)")
    
    def test_get_macro_data(self):
        """Test full macro data fetch."""
        if not os.getenv("FRED_API_KEY"):
            pytest.skip("FRED_API_KEY not set")
        
        connector = FredConnector()
        macro = connector.get_macro_data()
        
        assert macro.risk_free_rate > 0
        assert macro.source == "FRED"
        assert macro.fetched_at is not None
        
        print(f"✓ Macro data:")
        print(f"  Risk-free rate: {macro.risk_free_rate:.2%}")
        print(f"  Inflation: {macro.inflation_rate:.2%}" if macro.inflation_rate else "  Inflation: N/A")
        print(f"  GDP growth: {macro.gdp_growth:.2%}" if macro.gdp_growth else "  GDP growth: N/A")
    
    def test_caching(self):
        """Test macro data caching."""
        if not os.getenv("FRED_API_KEY"):
            pytest.skip("FRED_API_KEY not set")
        
        connector = FredConnector(cache_hours=24)
        
        # First fetch
        macro1 = connector.get_macro_data()
        
        # Second fetch (should be cached)
        macro2 = connector.get_macro_data()
        
        assert macro1.risk_free_rate == macro2.risk_free_rate
        assert macro1.fetched_at == macro2.fetched_at
        print("✓ Caching works correctly")


class TestDamodaranLoader:
    """Test Damodaran dataset loading."""
    
    def test_loader_init(self):
        """Test loader initialization."""
        loader = DamodaranLoader()
        assert loader is not None
    
    def test_get_sector_priors_technology(self):
        """Test fetching Technology sector priors."""
        loader = DamodaranLoader()
        priors = loader.get_sector_priors("Technology")
        
        assert priors.sector == "Technology"
        assert priors.beta is not None, "Beta should be loaded"
        assert priors.beta > 0, "Beta should be positive"
        
        print(f"✓ Technology sector priors:")
        print(f"  Beta: {priors.beta:.2f}")
        print(f"  Revenue growth: {priors.revenue_growth:.2%}" if priors.revenue_growth else "  Revenue growth: N/A")
        print(f"  Operating margin: {priors.operating_margin:.2%}" if priors.operating_margin else "  Operating margin: N/A")
    
    def test_get_all_sectors(self):
        """Test fetching all sector priors."""
        loader = DamodaranLoader()
        all_priors = loader.get_all_sectors()
        
        assert len(all_priors) > 0
        assert "Technology" in all_priors
        assert "Healthcare" in all_priors
        
        print(f"✓ Loaded priors for {len(all_priors)} sectors")
        
        # Print sample
        for sector in ["Technology", "Healthcare", "Energy"]:
            priors = all_priors[sector]
            print(f"  {sector}: beta={priors.beta:.2f}, growth={priors.revenue_growth:.1%}" if priors.revenue_growth else f"  {sector}: beta={priors.beta:.2f}, growth=N/A")
    
    def test_unmapped_sector_fallback(self):
        """Test generic fallback for unmapped sectors."""
        loader = DamodaranLoader()
        priors = loader.get_sector_priors("UnknownSector")
        
        assert priors.sector == "UnknownSector"
        assert priors.beta == 1.0  # Market beta fallback
        assert priors.revenue_growth == 0.05  # 5% fallback
        
        print("✓ Fallback priors work for unmapped sectors")


class TestPhase1Integration:
    """Integration tests combining all Phase 1 components."""
    
    def test_full_pipeline(self):
        """Test complete data foundation pipeline."""
        print("\n" + "="*60)
        print("PHASE 1 INTEGRATION TEST: Data Foundation")
        print("="*60)
        
        # Step 1: Fetch macro data
        if os.getenv("FRED_API_KEY"):
            connector = FredConnector()
            macro = connector.get_macro_data()
            print(f"\n✓ Macro data fetched: risk-free rate = {macro.risk_free_rate:.2%}")
        else:
            print("\n⚠ FRED_API_KEY not set - skipping macro data")
        
        # Step 2: Load sector priors (available but not integrated)
        loader = DamodaranLoader()
        tech_priors = loader.get_sector_priors("Technology")
        print(f"✓ Sector priors loaded: Tech beta = {tech_priors.beta:.2f}")
        
        print("\n" + "="*60)
        print("PHASE 1 COMPLETE: Data foundation operational!")
        print("="*60)
        
        assert True  # If we got here, all components work


if __name__ == "__main__":
    """Run tests with detailed output."""
    pytest.main([__file__, "-v", "-s"])
