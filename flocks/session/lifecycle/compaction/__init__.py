"""Session Compaction package.

Re-exports all public symbols so that existing imports like
``from flocks.session.lifecycle.compaction import SessionCompaction``
continue to work unchanged.
"""

from flocks.session.lifecycle.compaction.policy import (
    ContextTier,
    CompactionPolicy,
    _BOUNDS,
    _MIN_OVERFLOW_THRESHOLD,
    _DEFAULT_RATIOS,
    _TIER_OVERRIDES,
    _TIER_PRESERVE_LAST,
)
from flocks.session.lifecycle.compaction.models import (
    CompactionResult,
    TokenInfo,
    ModelLimits,
    PRUNE_MINIMUM,
    PRUNE_PROTECT,
    PRUNE_PROTECTED_TOOLS,
    PRESERVE_LAST_STEPS,
    DEFAULT_COMPACTION_PROMPT,
)
from flocks.session.lifecycle.compaction.compaction import SessionCompaction
from flocks.session.lifecycle.compaction.micro_compact import (
    apply_count_based as micro_compact_count_based,
    apply_time_based as micro_compact_time_based,
    MICRO_COMPACT_EXCLUDE,
    DEFAULT_KEEP_RECENT,
    MICRO_COMPACT_PLACEHOLDER,
)
from flocks.session.lifecycle.compaction.orchestrator import (
    build_compaction_policy,
    run_compaction,
)

__all__ = [
    # Policy
    "ContextTier",
    "CompactionPolicy",
    "_BOUNDS",
    "_MIN_OVERFLOW_THRESHOLD",
    "_DEFAULT_RATIOS",
    "_TIER_OVERRIDES",
    "_TIER_PRESERVE_LAST",
    # Models & constants
    "CompactionResult",
    "TokenInfo",
    "ModelLimits",
    "PRUNE_MINIMUM",
    "PRUNE_PROTECT",
    "PRUNE_PROTECTED_TOOLS",
    "PRESERVE_LAST_STEPS",
    "DEFAULT_COMPACTION_PROMPT",
    # Micro Compact
    "micro_compact_count_based",
    "micro_compact_time_based",
    "MICRO_COMPACT_EXCLUDE",
    "DEFAULT_KEEP_RECENT",
    "MICRO_COMPACT_PLACEHOLDER",
    # Orchestrator
    "SessionCompaction",
    "build_compaction_policy",
    "run_compaction",
]
