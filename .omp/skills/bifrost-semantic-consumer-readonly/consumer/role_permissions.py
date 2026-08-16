"""
六角色最小权限矩阵

本阶段只实现查询权限，不修改企业权限系统。
- factory：可查询全部已物化实体
- line：shift、work_order
- quality：defect_detail、quality_freeze
- equipment：downtime_event
- process：shift、downtime_event
- supply：purchase_order、inventory_snapshot、material_detail
- 其他组合返回 BLOCKED_ROLE_SCOPE
"""

# 角色到允许查询的语义实体映射
ROLE_ENTITY_PERMISSIONS = {
    "factory": None,  # None = 全部已物化实体
    "line": {"shift", "work_order"},
    "quality": {"defect_detail", "quality_freeze"},
    "equipment": {"downtime_event"},
    "process": {"shift", "downtime_event"},
    "supply": {"purchase_order", "inventory_snapshot", "material_detail"},
}

# 角色中文名
ROLE_NAMES = {
    "factory": "厂长",
    "line": "线长",
    "quality": "质量",
    "equipment": "设备",
    "process": "工艺",
    "supply": "供应链",
}

VALID_ROLES = set(ROLE_ENTITY_PERMISSIONS.keys())


def validate_consumer_role_scope(role: str, semantic_entity: str) -> dict:
    """
    验证角色是否有权查询指定语义实体。

    返回:
        {
            "allowed": bool,
            "blocked_code": str | None,
            "reason": str
        }
    """
    if role not in VALID_ROLES:
        return {
            "allowed": False,
            "blocked_code": "BLOCKED_ROLE_SCOPE",
            "reason": f"未知角色: {role}，有效角色: {sorted(VALID_ROLES)}"
        }

    allowed_entities = ROLE_ENTITY_PERMISSIONS[role]

    # factory 可查询全部
    if allowed_entities is None:
        return {
            "allowed": True,
            "blocked_code": None,
            "reason": f"角色 {role}({ROLE_NAMES[role]}) 可查询全部已物化实体"
        }

    if semantic_entity in allowed_entities:
        return {
            "allowed": True,
            "blocked_code": None,
            "reason": f"角色 {role}({ROLE_NAMES[role]}) 有权查询 {semantic_entity}"
        }
    else:
        return {
            "allowed": False,
            "blocked_code": "BLOCKED_ROLE_SCOPE",
            "reason": (
                f"角色 {role}({ROLE_NAMES[role]}) 无权查询实体 {semantic_entity}，"
                f"允许的实体: {sorted(allowed_entities)}"
            )
        }


def get_allowed_entities(role: str) -> set | None:
    """获取角色允许查询的实体集合，None 表示全部"""
    if role not in VALID_ROLES:
        return set()
    return ROLE_ENTITY_PERMISSIONS[role]
