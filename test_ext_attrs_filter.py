"""测试 ext_attrs 过滤功能"""

import sys

sys.path.insert(0, "D:/data/code/baiying/by-datacloud/packages/datacloud-platform/src")
sys.path.insert(0, "D:/data/code/baiying/by-datacloud/packages/datacloud-data/src")

from datacloud_platform.platform import DatacloudPlatform
from datacloud_platform.backends.presets import create_composite_backend

backend = create_composite_backend("D:/data/code/baiying/byclaw-all/byclaw-data/.by/datacloud")
platform = DatacloudPlatform(backend)

# 模拟 RPC 调用参数
params = {
    "keywords": ["byDC"],
    "searchLevel": "1",
    "kb_id": "78",
    "kb_file_path": "/Product/byDC.md",
}

print("=" * 80)
print("测试 1: 查询 byDC 术语，不带过滤条件")
print("=" * 80)

result1 = platform.search_terms("1", keyword="byDC", top_k=10)
items1 = result1.items if hasattr(result1, "items") else result1.get("items", [])

for idx, item in enumerate(items1):
    term_name = item.term_name if hasattr(item, "term_name") else item.get("term_name")
    term_id = item.term_id if hasattr(item, "term_id") else item.get("term_id")

    detail = platform.get_term_detail("1", library_id="1", term_id=term_id)
    ext_attrs = None
    if detail:
        ext_attrs = detail.ext_attrs if hasattr(detail, "ext_attrs") else detail.get("ext_attrs")

    print(f"{idx + 1}. term_name={term_name}, term_id={term_id}")
    print(f"   ext_attrs={ext_attrs}")

print("\n" + "=" * 80)
print("测试 2: 模拟 RPC handler 逻辑，带 ext_attrs 过滤")
print("=" * 80)

filter_kb_id = params.get("kb_id")
filter_kb_file_path = params.get("kb_file_path")

print(f"过滤条件: kb_id={filter_kb_id}, kb_file_path={filter_kb_file_path}")

for keyword in params["keywords"]:
    search_result = platform.search_terms("1", keyword=keyword, top_k=10)
    result_items = (
        search_result.items
        if hasattr(search_result, "items")
        else search_result.get("items", [])
    )

    print(f"\n搜索关键词: {keyword}, 找到 {len(result_items)} 个结果")

    matched_count = 0
    for item in result_items:
        term_id = item.term_id if hasattr(item, "term_id") else item.get("term_id")
        term_name = item.term_name if hasattr(item, "term_name") else item.get("term_name")

        detail = platform.get_term_detail("1", library_id="1", term_id=term_id)
        ext_attrs = None
        if detail:
            ext_attrs = detail.ext_attrs if hasattr(detail, "ext_attrs") else detail.get("ext_attrs")

        # 应用过滤逻辑
        if filter_kb_id or filter_kb_file_path:
            if not ext_attrs or not isinstance(ext_attrs, dict):
                print(f"  - 跳过 {term_name} (无 ext_attrs)")
                continue

            if filter_kb_id:
                term_kb_id = ext_attrs.get("kb_id")
                if str(term_kb_id) != str(filter_kb_id):
                    print(f"  - 跳过 {term_name} (kb_id={term_kb_id} != {filter_kb_id})")
                    continue

            if filter_kb_file_path:
                term_kb_file_path = ext_attrs.get("kb_file_path")
                if term_kb_file_path != filter_kb_file_path:
                    print(
                        f"  - 跳过 {term_name} (kb_file_path={term_kb_file_path} != {filter_kb_file_path})"
                    )
                    continue

        matched_count += 1
        print(f"  ✓ 匹配 {term_name} (term_id={term_id})")
        print(f"    ext_attrs={ext_attrs}")

    print(f"\n过滤后匹配数量: {matched_count}")
