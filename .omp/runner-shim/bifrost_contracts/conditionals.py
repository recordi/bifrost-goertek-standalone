# GENERATED FILE — DO NOT EDIT.
#
# Source: packages/contracts/schemas/*.schema.json
# Regenerate: pnpm --filter @bifrost/contracts gen
"""Conditional (if/then/else) rules extracted from the JSON Schemas.

datamodel-code-generator 0.72.1 does not translate JSON Schema
conditionals into pydantic validators, so a generated model alone accepts documents
the schema forbids — ChartSpec(kind="bar", marks="path") among them. This module
restores those rules so Python and TypeScript/ajv agree on the same document.

Only the keywords the schemas actually use are implemented: const, enum, required,
properties, items, not, allOf/anyOf/oneOf and $ref.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ConditionalError", "RULES", "check_conditionals"]


class ConditionalError(ValueError):
    """A document violated an if/then rule declared in the JSON Schema."""

    def __init__(self, contract: str, path: str, message: str) -> None:
        self.contract = contract
        self.path = path
        super().__init__(f"{contract}{path}: {message}")


RULES: dict[str, Any] = {
    "AnalysisPlan": {
        "properties": {
            "questions": {
                "items": {
                    "$ref": "#/$defs/Question"
                }
            }
        }
    },
    "Baseline": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "kind": {
                            "const": "target"
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "required": [
                        "ref"
                    ]
                }
            },
            {
                "if": {
                    "properties": {
                        "kind": {
                            "enum": [
                                "period_over_period",
                                "year_over_year"
                            ]
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "required": [
                        "offset"
                    ]
                }
            }
        ]
    },
    "ChartSpec": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "kind": {
                            "enum": [
                                "line",
                                "area"
                            ]
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "properties": {
                        "marks": {
                            "const": "path"
                        }
                    }
                }
            },
            {
                "if": {
                    "properties": {
                        "kind": {
                            "const": "bar"
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "properties": {
                        "marks": {
                            "const": "rect"
                        }
                    }
                }
            },
            {
                "if": {
                    "properties": {
                        "kind": {
                            "const": "scatter"
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "properties": {
                        "marks": {
                            "const": "circle"
                        }
                    }
                }
            },
            {
                "if": {
                    "properties": {
                        "kind": {
                            "enum": [
                                "bar",
                                "area"
                            ]
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "properties": {
                        "y": {
                            "properties": {
                                "zeroBased": {
                                    "const": True
                                }
                            }
                        }
                    }
                }
            },
            {
                "if": {
                    "properties": {
                        "orientation": {
                            "const": "horizontal"
                        }
                    },
                    "required": [
                        "orientation"
                    ]
                },
                "then": {
                    "properties": {
                        "kind": {
                            "const": "bar"
                        }
                    }
                }
            }
        ],
        "properties": {
            "y": {
                "allOf": [
                    {
                        "if": {
                            "properties": {
                                "zeroBased": {
                                    "const": False
                                }
                            },
                            "required": [
                                "zeroBased"
                            ]
                        },
                        "then": {
                            "required": [
                                "domain"
                            ]
                        }
                    }
                ]
            }
        }
    },
    "Dataset": {
        "properties": {
            "source": {
                "$ref": "#/$defs/DatasetSource"
            }
        }
    },
    "DatasetSource": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "kind": {
                            "enum": [
                                "csv",
                                "xlsx",
                                "parquet"
                            ]
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "not": {
                        "required": [
                            "connection_ref"
                        ]
                    },
                    "required": [
                        "uri"
                    ]
                }
            },
            {
                "if": {
                    "properties": {
                        "kind": {
                            "enum": [
                                "mysql",
                                "postgres",
                                "bitable"
                            ]
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "not": {
                        "required": [
                            "uri"
                        ]
                    },
                    "required": [
                        "connection_ref",
                        "table"
                    ]
                }
            },
            {
                "if": {
                    "properties": {
                        "kind": {
                            "const": "xlsx"
                        }
                    },
                    "required": [
                        "kind"
                    ]
                },
                "then": {
                    "required": [
                        "sheet"
                    ]
                }
            }
        ]
    },
    "Dimension": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "type": {
                            "const": "time"
                        }
                    },
                    "required": [
                        "type"
                    ]
                },
                "then": {
                    "required": [
                        "grain"
                    ]
                }
            }
        ]
    },
    "FactEmission": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "series": {
                            "const": True
                        }
                    },
                    "required": [
                        "series"
                    ]
                },
                "then": {
                    "required": [
                        "x_column"
                    ]
                }
            }
        ]
    },
    "FeishuDelivery": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "status": {
                            "const": "sent"
                        }
                    },
                    "required": [
                        "status"
                    ]
                },
                "then": {
                    "required": [
                        "delivered_at",
                        "card_message_id"
                    ]
                }
            },
            {
                "if": {
                    "properties": {
                        "status": {
                            "const": "failed"
                        }
                    },
                    "required": [
                        "status"
                    ]
                },
                "then": {
                    "required": [
                        "error_message"
                    ]
                }
            }
        ]
    },
    "MemoryEntry": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "layer": {
                            "const": "org"
                        }
                    },
                    "required": [
                        "layer"
                    ]
                },
                "then": {
                    "required": [
                        "confirmed_by"
                    ]
                }
            }
        ]
    },
    "Metric": {
        "allOf": [
            {
                "if": {
                    "properties": {
                        "type": {
                            "enum": [
                                "ratio",
                                "derived"
                            ]
                        }
                    },
                    "required": [
                        "type"
                    ]
                },
                "then": {
                    "required": [
                        "type_params"
                    ]
                }
            }
        ]
    },
    "Metrics": {
        "properties": {
            "dimensions": {
                "items": {
                    "$ref": "#/$defs/Dimension"
                }
            },
            "metrics": {
                "items": {
                    "$ref": "#/$defs/Metric"
                }
            }
        }
    },
    "Query": {
        "properties": {
            "emits_facts": {
                "items": {
                    "$ref": "#/$defs/FactEmission"
                }
            }
        }
    },
    "QuerySet": {
        "properties": {
            "queries": {
                "items": {
                    "$ref": "#/$defs/Query"
                }
            }
        }
    },
    "Question": {
        "properties": {
            "baselines": {
                "items": {
                    "$ref": "#/$defs/Baseline"
                }
            }
        }
    }
}


def check_conditionals(contract: str, data: Any) -> None:
    """Raise ConditionalError if *data* breaks a conditional rule of *contract*."""
    rule = RULES.get(contract)
    if rule is not None:
        _apply(rule, data, contract, "")


def _apply(rule: Any, data: Any, contract: str, path: str) -> None:
    if not isinstance(rule, dict):
        return

    condition = rule.get("if")
    if condition is not None and _matches(condition, data):
        branch = rule.get("then")
        if branch is not None and not _matches(branch, data):
            raise ConditionalError(contract, path, _explain(condition, branch, data))

    if condition is not None and not _matches(condition, data):
        branch = rule.get("else")
        if branch is not None and not _matches(branch, data):
            raise ConditionalError(contract, path, _explain(condition, branch, data, negated=True))

    ref = rule.get("$ref")
    if ref is not None:
        target = RULES.get(ref.removeprefix("#/$defs/"))
        if target is not None:
            _apply(target, data, contract, path)

    for key in ("allOf", "anyOf", "oneOf"):
        for entry in rule.get(key, []):
            _apply(entry, data, contract, path)

    for name, sub in rule.get("properties", {}).items():
        if isinstance(data, dict) and name in data:
            _apply(sub, data[name], contract, f"{path}.{name}")

    item_rule = rule.get("items")
    if item_rule is not None and isinstance(data, list):
        for index, item in enumerate(data):
            _apply(item_rule, item, contract, f"{path}[{index}]")


def _matches(schema: Any, data: Any) -> bool:
    """Evaluate a subschema as a boolean, per JSON Schema semantics."""
    if isinstance(schema, bool):
        return schema
    if not isinstance(schema, dict):
        return True

    for key in schema.get("required", []):
        if not isinstance(data, dict) or key not in data:
            return False

    if "const" in schema and data != schema["const"]:
        return False

    if "enum" in schema and data not in schema["enum"]:
        return False

    if "not" in schema and _matches(schema["not"], data):
        return False

    ref = schema.get("$ref")
    if ref is not None:
        target = RULES.get(ref.removeprefix("#/$defs/"))
        if target is not None and not _matches(target, data):
            return False

    for entry in schema.get("allOf", []):
        if not _matches(entry, data):
            return False

    if "anyOf" in schema and not any(_matches(e, data) for e in schema["anyOf"]):
        return False

    if "oneOf" in schema and sum(_matches(e, data) for e in schema["oneOf"]) != 1:
        return False

    for name, sub in schema.get("properties", {}).items():
        # An absent property vacuously satisfies its subschema.
        if isinstance(data, dict) and name in data and not _matches(sub, data[name]):
            return False

    item_schema = schema.get("items")
    if item_schema is not None and isinstance(data, list):
        if not all(_matches(item_schema, item) for item in data):
            return False

    return True


def _explain(condition: Any, branch: Any, data: Any, negated: bool = False) -> str:
    """Describe which rule failed and what it required, so the message guides the fix."""
    trigger = _describe(condition, data)
    prefix = "does not match" if negated else "matches"
    missing = [k for k in branch.get("required", []) if not isinstance(data, dict) or k not in data]

    parts: list[str] = []
    if missing:
        parts.append("requires " + ", ".join(repr(k) for k in missing))
    for name, sub in branch.get("properties", {}).items():
        if isinstance(data, dict) and name in data and not _matches(sub, data[name]):
            parts.append(f"requires {name}={_expected(sub)!r}, got {data[name]!r}")
    if "not" in branch and _matches(branch["not"], data):
        forbidden = branch["not"].get("required", [])
        parts.append("forbids " + ", ".join(repr(k) for k in forbidden))

    detail = "; ".join(parts) or "failed the conditional branch"
    return f"because {trigger} {prefix}, the schema {detail}"


def _describe(condition: Any, data: Any) -> str:
    bits = []
    for name, sub in condition.get("properties", {}).items():
        if isinstance(data, dict) and name in data:
            bits.append(f"{name}={data[name]!r}")
        else:
            bits.append(name)
    return ", ".join(bits) or "the condition"


def _expected(sub: Any) -> Any:
    if "const" in sub:
        return sub["const"]
    if "enum" in sub:
        return sub["enum"]
    if "properties" in sub:
        return {k: _expected(v) for k, v in sub["properties"].items()}
    return sub
