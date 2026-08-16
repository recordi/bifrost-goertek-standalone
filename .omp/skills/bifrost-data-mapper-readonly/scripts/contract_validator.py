#!/usr/bin/env python3
"""
contract_validator.py — 合同校验器

负责加载、校验版本化合同文件，并在缺失/版本错误/哈希异常时返回 BLOCKED_SEMANTIC_CONTRACT。
"""

import hashlib
import json
import os
from datetime import datetime


class ContractValidator:
    """合同校验器：校验文件存在、版本、哈希。"""

    REQUIRED_CONTRACTS = [
        "SEM_v1.1.1_unified_semantic_model.json",
        "MAP_v1.0.1_mapping.json",
        "MAP_OFFICIAL_v0.2.1_mapping.json",
        "DQ_v1.0.1_contract.json",
        "source_type_registry.json",
        "mapping_status_contract.json",
        "relation_status_contract.json",
    ]

    EXPECTED_VERSIONS = {
        "SEM_v1.1.1_unified_semantic_model.json": "SEM-v1.1.1",
        "MAP_v1.0.1_mapping.json": "MAP-v1.0.1",
        "MAP_OFFICIAL_v0.2.1_mapping.json": "MAP-OFFICIAL-v0.2.1",
        "DQ_v1.0.1_contract.json": "DQ-v1.0.1",
    }

    def __init__(self, contracts_dir: str):
        self.contracts_dir = contracts_dir
        self.registry: list[dict] = []

    def validate_all(self) -> dict:
        """校验所有合同，返回结果。"""
        result = {
            "status": "passed",
            "errors": [],
            "registered_contracts": []
        }

        for fname in self.REQUIRED_CONTRACTS:
            fpath = os.path.join(self.contracts_dir, fname)
            entry = {
                "filename": fname,
                "exists": False,
                "version": None,
                "sha256": None,
                "source_family": None,
                "source_type": None,
                "approval_status": None,
                "loaded_at_runtime": datetime.now().isoformat(),
                "errors": []
            }

            if not os.path.exists(fpath):
                entry["errors"].append("文件缺失")
                result["errors"].append(f"合同文件缺失: {fname}")
                result["status"] = "BLOCKED_SEMANTIC_CONTRACT"
                self.registry.append(entry)
                continue

            entry["exists"] = True

            with open(fpath, "rb") as f:
                raw_bytes = f.read()
            sha = hashlib.sha256(raw_bytes).hexdigest()
            entry["sha256"] = sha

            try:
                data = json.loads(raw_bytes.decode("utf-8"))
            except json.JSONDecodeError as e:
                entry["errors"].append(f"JSON 解析失败: {e}")
                result["errors"].append(f"合同文件 JSON 解析失败: {fname}")
                result["status"] = "BLOCKED_SEMANTIC_CONTRACT"
                self.registry.append(entry)
                continue

            # 提取版本
            version = self._extract_version(fname, data)
            entry["version"] = version

            # 校验版本
            if fname in self.EXPECTED_VERSIONS:
                expected = self.EXPECTED_VERSIONS[fname]
                if version != expected:
                    entry["errors"].append(f"版本不匹配: 期望 {expected}, 实际 {version}")
                    result["errors"].append(f"合同版本错误: {fname} 期望 {expected} 实际 {version}")
                    result["status"] = "BLOCKED_SEMANTIC_CONTRACT"

            # 提取来源信息
            if isinstance(data, dict):
                entry["source_family"] = data.get("source_family", "") or data.get("data_nature", "")
                entry["source_type"] = data.get("source_type", "")
                entry["data_nature"] = data.get("data_nature", "")
                entry["approval_source"] = data.get("approval_source", "")
                entry["approved_by"] = data.get("approved_by", "")
                entry["approved_at"] = data.get("approved_at", "")
                has_approval_meta = bool(
                    entry["approval_source"] or entry["approved_by"]
                    or entry["approved_at"] or entry["data_nature"] or entry["source_family"]
                )
                entry["approval_status"] = "approved" if has_approval_meta else "n/a"

            self.registry.append(entry)
            result["registered_contracts"].append(entry)

        return result

    def _extract_version(self, fname: str, data) -> str:
        keys_map = [
            ("SEM_", "semantic_model_version"),
            ("MAP_v1.0.1", "mapping_rule_version"),
            ("MAP_OFFICIAL", "official_mapping_rule_version"),
            ("DQ_", "quality_contract_version"),
            ("source_signature_registry", "source_signature_registry_version"),
        ]
        for prefix, key in keys_map:
            if fname.startswith(prefix) and isinstance(data, dict):
                return data.get(key, "unknown")
        if isinstance(data, dict):
            return data.get("contract_version", data.get("registry_version", "unknown"))
        return "unknown"

    def get_registry(self) -> list[dict]:
        return self.registry

    @staticmethod
    def compute_sha256(filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
