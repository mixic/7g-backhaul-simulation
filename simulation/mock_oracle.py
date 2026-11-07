"""Honest name for the stack compiler: the Mock Oracle.

The implementation lives in :mod:`simulation.llm_compiler` (the original module
name is kept so existing imports do not break).  This module re-exports the same
objects under the accurate name.  Read the docstring of
:mod:`simulation.llm_compiler` for the key clarification: this is a deterministic
**Mock Oracle**, not an LLM, and H7 tests the **symbolic guardrails against
injected hallucinated inputs**, not the reasoning capability of a real LLM.

The installed output of the mock is the canonical ``C→E→F`` order (the guardrail
forces it on every hallucination), which is bit-identical to the greedy
heuristic — so the H7 wire-byte result is a property of the mock's policy, not of
LLMs in general.
"""

from __future__ import annotations

from .llm_compiler import (  # noqa: F401
    HALLUCINATION_PROB,
    KIND_TO_NAME,
    NAME_TO_KIND,
    CompileResult,
    build_prompt,
    compile_stack,
    greedy_heuristic,
    mock_llm,
    proposal_json,
    static_stack,
)

__all__ = [
    "CompileResult",
    "HALLUCINATION_PROB",
    "KIND_TO_NAME",
    "NAME_TO_KIND",
    "build_prompt",
    "compile_stack",
    "greedy_heuristic",
    "mock_llm",
    "proposal_json",
    "static_stack",
]
