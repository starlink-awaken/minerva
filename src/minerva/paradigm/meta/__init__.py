"""Meta-Paradigm Engine — now powered by Sophia (extracted package).

Re-exports from sophia for backward compatibility. New code should import
directly from `sophia`.

Install: pip install sophia
"""

from sophia.symbols import (  # noqa: F401
    AtomicOp,
    BASE_TRANSITIONS,
    ParadigmProgram,
    ResearchState,
    TransitionRule,
)
from sophia.compiler import compile_paradigm  # noqa: F401
from sophia.learner import ParadigmLearner, ResearchTrace  # noqa: F401

__all__ = [
    "AtomicOp", "ResearchState", "TransitionRule", "ParadigmProgram",
    "BASE_TRANSITIONS", "compile_paradigm", "ParadigmLearner", "ResearchTrace",
]
