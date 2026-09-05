"""Optional MLflow adapters for Trader research and runtime composition.

Importing this package does not import MLflow, pandas, or model frameworks.
"""

from .inference import MLflowLocalPyfuncAdapter, MLflowPyfuncPredictor

__all__ = ["MLflowLocalPyfuncAdapter", "MLflowPyfuncPredictor"]
