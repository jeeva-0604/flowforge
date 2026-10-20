"""Compatibility layer for Pydantic v1/v2 so FlowForge runs identically on modern
Windows Python 3.11+ environments (Pydantic v2) and restricted container environments
(Pydantic v1.10+).
"""
from __future__ import annotations

from typing import Any, Callable
import pydantic
from pydantic import BaseModel as _BaseModel, Field, ValidationError

PYDANTIC_V2 = int(pydantic.__version__.split(".")[0]) >= 2

if PYDANTIC_V2:
    from pydantic import ConfigDict, field_validator  # type: ignore[attr-defined]
else:
    from pydantic import validator as _v1_validator

    def ConfigDict(**kwargs: Any) -> dict[str, Any]:  # noqa: N802
        return kwargs

    def field_validator(*fields: str, **kwargs: Any) -> Callable[[Any], Any]:
        mode = kwargs.get("mode", "after")
        pre = mode == "before"
        return _v1_validator(*fields, pre=pre, allow_reuse=True)


class CompatBaseModel(_BaseModel):
    """BaseModel providing unified Pydantic v2 methods (`model_validate`, `model_dump`)
    even when running on Pydantic v1.10+.
    """

    class Config:
        orm_mode = True
        arbitrary_types_allowed = True

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any):  # type: ignore[override]
        if PYDANTIC_V2:
            return super().model_validate(obj, *args, **kwargs)  # type: ignore[misc]
        if isinstance(obj, cls):
            return obj
        if isinstance(obj, dict):
            return cls.parse_obj(obj)
        return cls.from_orm(obj)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        if PYDANTIC_V2:
            return super().model_dump(*args, **kwargs)  # type: ignore[misc]
        kwargs.pop("mode", None)
        return self.dict(*args, **kwargs)


__all__ = [
    "CompatBaseModel",
    "ConfigDict",
    "Field",
    "PYDANTIC_V2",
    "ValidationError",
    "field_validator",
]
