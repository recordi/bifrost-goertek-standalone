# GENERATED FILE — DO NOT EDIT.
#
# Source: packages/contracts/schemas/*.schema.json
# Regenerate: pnpm --filter @bifrost/contracts gen
"""Bifrost cross-language contracts, pydantic v2.

Prefer validate_contract() over calling Model.model_validate directly: the generated
models carry structure only, while the conditional rules that make a document
actually contract-valid are applied separately.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from . import models
from .conditionals import ConditionalError, check_conditionals
from .models import (
    AnalysisPlan,
    AssertionResult,
    AssertionSpec,
    Baseline,
    ChartSpec,
    ColumnProfile,
    Dataset,
    DatasetId,
    DatasetSource,
    Defect,
    DefectType,
    DefinitionRef,
    Dimension,
    DisplayFormat,
    Dispute,
    Fact,
    FactEmission,
    FactFlag,
    FactId,
    FactSet,
    FeishuBitableWrite,
    FeishuCard,
    FeishuDelivery,
    Finding,
    GovernanceReport,
    MemId,
    MemoryEntry,
    Metric,
    MetricExpr,
    MetricTypeParams,
    Metrics,
    MetricsVersion,
    Profile,
    Provenance,
    Query,
    QuerySet,
    Question,
    Ratio01,
    Review,
    RoleProfile,
    Rubric,
    RubricSet,
    RunCreateRequest,
    RunId,
    Score,
    Semantic,
    Sensitivity,
    Series,
    Severity,
    SkillSlug,
    Slug,
    SqlHash,
    TimeGrain,
    Timestamp,
    Viewport,
)

__all__ = [
    "ConditionalError",
    "check_conditionals",
    "models",
    "validate_contract",
    "AnalysisPlan",
    "AssertionResult",
    "AssertionSpec",
    "Baseline",
    "ChartSpec",
    "ColumnProfile",
    "Dataset",
    "DatasetId",
    "DatasetSource",
    "Defect",
    "DefectType",
    "DefinitionRef",
    "Dimension",
    "DisplayFormat",
    "Dispute",
    "Fact",
    "FactEmission",
    "FactFlag",
    "FactId",
    "FactSet",
    "FeishuBitableWrite",
    "FeishuCard",
    "FeishuDelivery",
    "Finding",
    "GovernanceReport",
    "MemId",
    "MemoryEntry",
    "Metric",
    "MetricExpr",
    "MetricTypeParams",
    "Metrics",
    "MetricsVersion",
    "Profile",
    "Provenance",
    "Query",
    "QuerySet",
    "Question",
    "Ratio01",
    "Review",
    "RoleProfile",
    "Rubric",
    "RubricSet",
    "RunCreateRequest",
    "RunId",
    "Score",
    "Semantic",
    "Sensitivity",
    "Series",
    "Severity",
    "SkillSlug",
    "Slug",
    "SqlHash",
    "TimeGrain",
    "Timestamp",
    "Viewport",
]

TModel = TypeVar("TModel", bound=BaseModel)


def validate_contract(model: type[TModel], data: Any) -> TModel:
    """Validate *data* against *model* plus the schema's conditional rules.

    Raises ValidationError for structural problems and ConditionalError for a
    violated if/then rule. Both mean the document is not a valid contract instance.
    """
    check_conditionals(model.__name__, data)
    return model.model_validate(data)
