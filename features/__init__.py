"""ML feature engineering for the exchange simulator.

Provides real-time feature computation from order book and trade data,
label generation for supervised learning, and dataset building utilities.
"""

from features.engine import FeatureConfig, FeatureEngine

__all__ = ["FeatureEngine", "FeatureConfig"]
