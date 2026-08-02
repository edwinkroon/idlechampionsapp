"""Documentation-driven specialization rules (V3 with v2_full production source)."""

from ic_gamedata.specialization_rules.context_builder import build_evaluation_context
from ic_gamedata.specialization_rules.evaluator import (
    apply_exception_rules,
    evaluate_condition,
    evaluate_specialization,
)
from ic_gamedata.specialization_rules.loader import (
    cached_documentation_rules,
    documentation_dir,
    load_documentation_rules,
)
from ic_gamedata.specialization_rules.models import AdviceResult, EvaluationContext, RuleDataset
from ic_gamedata.specialization_rules.provenance import RuleSourceType, classify_rule_provenance
from ic_gamedata.specialization_rules.route_mapper import map_label_to_upgrade_id, map_route_to_upgrade_id
from ic_gamedata.specialization_rules.validator import validate_rule_dataset

__all__ = [
    "AdviceResult",
    "EvaluationContext",
    "RuleDataset",
    "apply_exception_rules",
    "build_evaluation_context",
    "cached_documentation_rules",
    "documentation_dir",
    "evaluate_condition",
    "evaluate_specialization",
    "load_documentation_rules",
    "map_label_to_upgrade_id",
    "map_route_to_upgrade_id",
    "classify_rule_provenance",
    "RuleSourceType",
    "validate_rule_dataset",
]
