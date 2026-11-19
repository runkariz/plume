"""Why a model may not be released yet (the model gold gate), shared by the gate and release."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GateFailure:
    message: str
    overridable: bool  # a maintainer may release over it with a reason (never for invented)
