from __future__ import annotations

from veriflow.core import VeriFlowError
from veriflow.framework.stage import Stage


class StageRegistry:
    _registry: dict[str, type[Stage]] = {}

    @classmethod
    def register(cls, name: str, stage_cls: type[Stage]) -> None:
        if name in cls._registry:
            raise VeriFlowError(
                f"Stage '{name}' is already registered",
                code="VF_STAGE_DUPLICATE",
            )
        cls._registry[name] = stage_cls

    @classmethod
    def get(cls, name: str) -> type[Stage]:
        if name not in cls._registry:
            raise VeriFlowError(
                f"Unknown stage '{name}'",
                code="VF_STAGE_UNKNOWN",
            )
        return cls._registry[name]

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()


__all__ = ["StageRegistry"]
