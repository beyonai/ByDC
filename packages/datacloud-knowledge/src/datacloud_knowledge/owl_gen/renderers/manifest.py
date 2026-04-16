"""manifest.json 生成。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from datacloud_knowledge.owl_gen.models import OwlGenConfig, Table


def render_manifest(
    config: OwlGenConfig,
    tables: list[Table],
    term_count: int,
    term_type_count: int,
    terms_files: dict[str, tuple[str, int]],
    rel_term_files: dict[str, str],
) -> str:
    """生成 manifest.json 内容。"""
    total_attr_rels = sum(len(t.columns) for t in tables)
    views = config.resolved_views()
    relation_view_count = (
        sum(len(v.object_codes) for v in views) if views else len(config.table_codes)
    )

    steps: list[dict[str, Any]] = [
        {"type": "meta", "file": "meta/domains.owl", "description": "领域定义"},
        {"type": "meta", "file": "meta/library.owl", "description": "本体库定义"},
        {
            "type": "term_types",
            "file": "term_types/term_types.owl",
            "description": "术语类型定义",
            "count": term_type_count,
        },
    ]

    # terms — 每个拆分文件一个 step
    for rel_path, (_content, count) in terms_files.items():
        steps.append(
            {
                "type": "terms",
                "file": rel_path,
                "description": f"术语定义 ({rel_path.rsplit('/', maxsplit=1)[-1]})",
                "count": count,
            }
        )

    # relations — 固定 4 个
    steps.extend(
        [
            {
                "type": "relations",
                "file": "relations/relation_view.owl",
                "description": "视图关系定义",
                "count": relation_view_count,
            },
            {
                "type": "relations",
                "file": "relations/relation_object.owl",
                "description": "对象关系定义",
                "count": len(config.object_relations),
            },
            {
                "type": "relations",
                "file": "relations/relation_attribute.owl",
                "description": "对象属性关系定义",
                "count": total_attr_rels,
            },
            {
                "type": "relations",
                "file": "relations/relation_action.owl",
                "description": "对象动作关系定义",
                "count": len(tables),
            },
        ]
    )

    # relations — term 拆分文件
    for rel_path in rel_term_files:
        steps.append(
            {
                "type": "relations",
                "file": rel_path,
                "description": f"术语值关系 ({rel_path.rsplit('/', maxsplit=1)[-1]})",
            }
        )

    # ontology
    steps.extend(
        [
            {
                "type": "ontology",
                "file": "ontology/dbsources/dbsource.owl",
                "description": "数据源定义",
                "count": 1,
            },
            {
                "type": "ontology",
                "file": "ontology/actions/action.owl",
                "description": "动作定义",
                "count": len(tables),
            },
        ]
    )
    for view in views:
        steps.append(
            {
                "type": "ontology",
                "file": f"ontology/views/{view.view_code}/{view.view_code}_view.owl",
                "description": f"{view.view_name}定义",
                "count": 1,
            }
        )
        steps.append(
            {
                "type": "ontology",
                "file": f"ontology/views/{view.view_code}/{view.view_code}_mapping.owl",
                "description": f"{view.view_name}映射定义",
                "count": len(view.field_mappings),
            }
        )
    for table in tables:
        steps.append(
            {
                "type": "ontology",
                "file": f"ontology/objects/{table.code}/{table.code}_object.owl",
                "description": f"{table.name}对象定义",
                "count": len(table.columns),
            }
        )
        steps.append(
            {
                "type": "ontology",
                "file": f"ontology/objects/{table.code}/{table.code}_mapping.owl",
                "description": f"{table.name}对象映射",
                "count": len(table.columns),
            }
        )

    today = datetime.now(tz=UTC).date()
    manifest = {
        "version": "1.0",
        "package_id": f"ads_owl_{today.strftime('%Y%m%d')}",
        "description": "业务库表 → OWL 导入包（脚本自动生成）",
        "created_at": today.isoformat(),
        "import_steps": steps,
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2)
