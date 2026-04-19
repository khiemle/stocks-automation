from __future__ import annotations

from signals.momentum_v1 import MomentumV1

ENGINE_REGISTRY: dict = {
    "MomentumV1": MomentumV1,
}
