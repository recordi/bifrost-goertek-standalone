#!/usr/bin/env python3
"""
mapper_cli.py — BIFROST 字段整合只读映射 CLI 入口

用法:
  python mapper_cli.py --source-file <path> --file-format <xlsx|csv|json> [选项]

输出:
  JSON 格式的结构化映射响应到 stdout 或 --output 指定文件。
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime

# 将同目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bifrost_data_mapper import BifrostDataMapper, SKILL_VERSION, RELEASE_STATUS


def main():
    parser = argparse.ArgumentParser(
        description="BIFROST 字段整合只读映射 CLI"
    )
    parser.add_argument("--source-file", required=True, help="输入数据文件路径")
    parser.add_argument("--file-format", default=None, help="文件格式 (xlsx|csv|json)")
    parser.add_argument("--request-id", default=None, help="外部请求ID")
    parser.add_argument("--source-id", default=None, help="数据源ID")
    parser.add_argument("--source-name", default=None, help="数据源名称")
    parser.add_argument("--declared-source-family", default=None, help="声明的来源族")
    parser.add_argument("--declared-source-type", default=None, help="声明的来源类型")
    parser.add_argument("--mapping-mode", default="zero_shot",
                        choices=["approved_contract", "baseline_assisted", "zero_shot"],
                        help="映射模式")
    parser.add_argument("--semantic-model-version", default="SEM-v1.1.1")
    parser.add_argument("--mapping-rule-version", default=None)
    parser.add_argument("--allowed-domains", nargs="*", default=[])
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--read-only", default="true", help="必须为 true")
    parser.add_argument("--contracts-dir", default=None,
                        help="合同目录路径 (默认: ../references/contracts)")
    parser.add_argument("--output", default=None, help="输出文件路径")

    args = parser.parse_args()

    # 确定合同目录
    if args.contracts_dir:
        contracts_dir = args.contracts_dir
    else:
        contracts_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "references", "contracts"
        )
        contracts_dir = os.path.normpath(contracts_dir)

    # 构建请求
    fmt = args.file_format or os.path.splitext(args.source_file)[1].lstrip(".").lower()
    request = {
        "request_id": args.request_id or f"REQ-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "source_id": args.source_id or "CLI",
        "source_name": args.source_name or os.path.basename(args.source_file),
        "source_file": args.source_file,
        "file_format": fmt,
        "declared_source_family": args.declared_source_family,
        "declared_source_type": args.declared_source_type,
        "mapping_mode": args.mapping_mode,
        "semantic_model_version": args.semantic_model_version,
        "mapping_rule_version": args.mapping_rule_version,
        "allowed_domains": args.allowed_domains,
        "sample_limit": args.sample_limit,
        "read_only": args.read_only.lower() == "true"
    }

    # 执行映射
    mapper = BifrostDataMapper(contracts_dir)
    response = mapper.orchestrate_mapping_run(request)

    # 输出
    output_json = json.dumps(response, ensure_ascii=False, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"结果已写入: {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # 返回码
    if response.get("status") == "blocked":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
