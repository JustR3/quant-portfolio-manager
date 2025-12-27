"""DCF-Aware Portfolio Optimization

Extracts the DCF-specific optimization logic from modules/portfolio/optimizer.py.
Uses DCF valuation results (upside %, conviction) to create Black-Litterman views.

This is a legacy toolkit for fundamental analysis-based portfolio construction.
For production systematic portfolios, use src/models/optimizer.py.
"""

from typing import Dict, Optional, List, Tuple
import pandas as pd
import numpy as np

from pypfopt import EfficientFrontier, black_litterman, expected_returns, risk_models

from modules.portfolio.optimizer import (
    PortfolioEngine,
    OptimizationMethod,
    PortfolioMetrics
)
from config import config


class DCFPortfolioOptimizer(PortfolioEngine):
    """Portfolio optimizer with DCF-based views via Black-Litterman."""

    def optimize_with_dcf_views(
        self,
        dcf_results: Dict[str, dict],
        confidence: float = 0.3,
        method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
        weight_bounds: Tuple[float, float] = (0, 1)
    ) -> Optional[PortfolioMetrics]:
        """
        Optimize using Black-Litterman with DCF valuations as views.

        Uses Monte Carlo probabilities as confidence weights and filters by conviction.

        Args:
            dcf_results: Dict of {ticker: enriched_dcf_result}
            confidence: Base view confidence (0-1)
            method: Optimization objective
            weight_bounds: Min/max weight per asset

        Returns:
            PortfolioMetrics or None if optimization fails
        """
        try:
            if self.prices is None:
                self._last_error = "No price data"
                return None

            # Build views with conviction-based filtering FIRST
            viewdict = {}
            view_confidences = []
            viable_tickers = []

            for ticker in self.tickers:
                if ticker not in dcf_results:
                    continue

                dcf = dcf_results[ticker]

                # Skip if no positive value
                if dcf.get('value_per_share', 0) <= 0:
                    continue

                upside = dcf['upside_downside'] / 100.0
                conviction_data = dcf.get('conviction', {})
                conviction = conviction_data.get('label', 'N/A')
                mc_data = dcf.get('monte_carlo', {})
                mc_probability = mc_data.get('probability', 0) if mc_data else 0

                # Conviction-based filtering and discounting
                if conviction == 'HIGH CONVICTION':
                    viewdict[ticker] = upside
                    view_confidences.append(0.3 + (mc_probability / 100) * 0.3)
                    viable_tickers.append(ticker)

                elif conviction == 'MODERATE':
                    viewdict[ticker] = upside
                    view_confidences.append(0.2 + (mc_probability / 100) * 0.2)
                    viable_tickers.append(ticker)

                elif conviction == 'SPECULATIVE':
                    viewdict[ticker] = upside * 0.5
                    view_confidences.append(0.1 + (mc_probability / 100) * 0.1)
                    viable_tickers.append(ticker)

                # HOLD/PASS: Exclude entirely

            if not viewdict:
                self._last_error = "No valid DCF results after conviction filtering"
                return None

            # Filter prices to viable tickers only and recalculate matrices
            filtered_prices = self.prices[viable_tickers]

            # Recalculate expected returns and covariance for filtered tickers
            mu = expected_returns.capm_return(filtered_prices, risk_free_rate=self.risk_free_rate)
            S = risk_models.CovarianceShrinkage(filtered_prices).ledoit_wolf()

            # Get market caps for Black-Litterman
            market_caps = pd.Series({t: dcf_results.get(t, {}).get('market_cap', 1.0)
                                     for t in viewdict.keys()})

            # Convert to numpy array
            confidences_array = np.array(view_confidences)

            bl = black_litterman.BlackLittermanModel(
                S, pi="market", market_caps=market_caps,
                absolute_views=viewdict, omega="idzorek", view_confidences=confidences_array
            )
            bl_returns = bl.bl_returns()

            ef = EfficientFrontier(bl_returns, S, weight_bounds=weight_bounds)
            try:
                if method == OptimizationMethod.MAX_SHARPE:
                    ef.max_sharpe(risk_free_rate=self.risk_free_rate)
                elif method == OptimizationMethod.MIN_VOLATILITY:
                    ef.min_volatility()
                else:
                    ef.efficient_risk(target_volatility=0.15)
            except ValueError:
                # If all returns are below risk-free rate, fall back to min volatility
                ef = EfficientFrontier(bl_returns, S, weight_bounds=weight_bounds)
                ef.min_volatility()

            weights = {k: v for k, v in ef.clean_weights().items() if v > 0.001}
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self.risk_free_rate)
            self.optimized_weights = weights

            # Calculate comprehensive risk metrics
            risk_metrics = self.calculate_risk_metrics(weights)

            self.performance = PortfolioMetrics(
                expected_annual_return=perf[0] * 100,
                annual_volatility=perf[1] * 100,
                sharpe_ratio=perf[2],
                weights=weights,
                optimization_method=f"{method.value}_black_litterman",
                sortino_ratio=risk_metrics.get('sortino_ratio'),
                calmar_ratio=risk_metrics.get('calmar_ratio'),
                max_drawdown=risk_metrics.get('max_drawdown'),
                var_95=risk_metrics.get('var_95'),
                cvar_95=risk_metrics.get('cvar_95'),
            )
            return self.performance
        except Exception as e:
            self._last_error = str(e)
            return None


def optimize_portfolio_with_dcf(
    dcf_results: Dict[str, dict],
    method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
    period: str = "2y",
    risk_free_rate: float = None,
    confidence: float = 0.3
) -> Optional[PortfolioMetrics]:
    """
    Optimize portfolio using DCF valuations via Black-Litterman.

    Args:
        dcf_results: Dict of {ticker: enriched_dcf_result}
        method: Optimization objective
        period: Historical data period
        risk_free_rate: Risk-free rate (default: from config)
        confidence: View confidence

    Returns:
        PortfolioMetrics or None if fails
    """
    tickers = list(dcf_results.keys())
    if not tickers:
        return None

    if risk_free_rate is None:
        risk_free_rate = config.DEFAULT_RISK_FREE_RATE

    engine = DCFPortfolioOptimizer(tickers=tickers, risk_free_rate=risk_free_rate)
    if not engine.fetch_data(period=period):
        return None
    return engine.optimize_with_dcf_views(
        dcf_results=dcf_results,
        confidence=confidence,
        method=method
    )
