"""Validation for documentation specialization rule datasets."""

from __future__ import annotations

from collections import Counter

from ic_gamedata.specialization_rules.models import RuleDataset


def validate_rule_dataset(dataset: RuleDataset) -> list[str]:
    errors: list[str] = []
    lookups = dataset.lookups

    rule_ids = [rule.rule_id for rule in dataset.rules if rule.rule_id]
    for rule_id, count in Counter(rule_ids).items():
        if count > 1:
            errors.append(f"duplicate rule_id: {rule_id}")

    exception_ids = [item.exception_id for item in dataset.exceptions if item.exception_id]
    for exception_id, count in Counter(exception_ids).items():
        if count > 1:
            errors.append(f"duplicate exception_id: {exception_id}")

    known_champions = {rule.champion.casefold() for rule in dataset.rules if rule.champion}

    for rule in dataset.rules:
        if not rule.champion:
            errors.append(f"rule {rule.rule_id or '?'} missing champion")
        if rule.is_v3_shaped:
            if rule.run_goal and rule.run_goal not in lookups.run_goals:
                errors.append(f"rule {rule.rule_id}: unknown run_goal '{rule.run_goal}'")
            if rule.condition_field and rule.condition_field not in lookups.condition_fields:
                errors.append(f"rule {rule.rule_id}: unknown condition_field '{rule.condition_field}'")
            if rule.machine_default and rule.machine_default not in lookups.specialization_keys:
                errors.append(f"rule {rule.rule_id}: unknown machine_default '{rule.machine_default}'")
            if rule.machine_alternative and rule.machine_alternative not in lookups.specialization_keys:
                errors.append(
                    f"rule {rule.rule_id}: unknown machine_alternative '{rule.machine_alternative}'"
                )
        if rule.priority_code and rule.priority_code not in lookups.priorities:
            errors.append(f"rule {rule.rule_id}: unknown priority '{rule.priority_code}'")
        if rule.manual_review_code and rule.manual_review_code not in lookups.manual_review_codes:
            errors.append(f"rule {rule.rule_id}: unknown manual_review '{rule.manual_review_code}'")
        for tag in rule.tags:
            if tag not in lookups.tags:
                errors.append(f"rule {rule.rule_id}: unknown tag '{tag}'")

    for exc in dataset.exceptions:
        if not exc.champion:
            errors.append(f"exception {exc.exception_id or '?'} missing champion")
        elif exc.champion.casefold() not in known_champions and dataset.source == "v3_example":
            errors.append(
                f"exception {exc.exception_id}: champion '{exc.champion}' has no main rule"
            )
        if exc.trigger_field and exc.trigger_field not in lookups.condition_fields:
            errors.append(f"exception {exc.exception_id}: unknown trigger_field '{exc.trigger_field}'")
        if exc.manual_review_code and exc.manual_review_code not in lookups.manual_review_codes:
            errors.append(
                f"exception {exc.exception_id}: unknown manual_review '{exc.manual_review_code}'"
            )
        if exc.forced_specialization and exc.forced_specialization not in lookups.specialization_keys:
            if dataset.source != "v2_full":
                errors.append(
                    f"exception {exc.exception_id}: unknown forced_specialization "
                    f"'{exc.forced_specialization}'"
                )
        if exc.seat is not None and (exc.seat < 1 or exc.seat > 12):
            errors.append(f"exception {exc.exception_id}: invalid seat {exc.seat}")

    for rule in dataset.rules:
        if rule.seat is not None and (rule.seat < 1 or rule.seat > 12):
            errors.append(f"rule {rule.rule_id}: invalid seat {rule.seat}")

    return errors
