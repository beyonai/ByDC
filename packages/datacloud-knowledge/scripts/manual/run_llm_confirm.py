from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.clarification import _confirmed_query_to_paradigm_list
from datacloud_knowledge.intent.llm_confirm import (
    llm_confirm,
    semantic_to_display,
    semantic_to_sql_expr,
)


def main() -> None:

    original_question = "2026年2月各街道的亩产效益、龙头企业数、高风险占比，按亩产降序"
    expanded_query = "亩产效益、龙头企业数、高风险占比"
    recall_context = "== 查询值 ==\n  亩产效益 (select): ['物理网格亩产效益（万元/亩）', '企业总利润（万元）', '企业经济效益等级（高、中、低）', '企业总营收（万元）', '数据来源']\n  亩产 (select): ['物理网格亩产效益（万元/亩）', '企业总营收（万元）', '企业总利润（万元）', '数据来源', '企业数量']\n  亩产效益值 (select): ['物理网格亩产效益（万元/亩）', '企业总利润（万元）', '企业经济效益等级（高、中、低）', '企业总营收（万元）', '企业实际税负率（%）']\n  龙头企业数 (select): ['企业数量', '企业等级', '企业全称', '企业经营状态', '企业总营收（万元）']\n  龙头企业数量 (select): ['企业数量', '企业等级', '企业全称', '企业经营状态', '企业总营收（万元）']\n  高风险占比 (select): ['企业综合风险等级', '数据来源', '企业实际税负率（%）', '企业数量', '企业经济效益等级（高、中、低）']\n  高风险比例 (select): ['企业综合风险等级', '企业实际税负率（%）', '数据来源', '企业数量', '企业经济效益等级（高、中、低）']\n\n== 分组条件 ==\n  街道 (groupBy): ['企业数量', '企业经营状态', '企业详细地址', '所属管理网格名称', '企业等级']\n  街道名称 (groupBy): ['所属管理网格名称', '企业全称', '企业详细地址', '企业所属物理网格名称', '所属管理网格编码']\n  街道办 (groupBy): ['企业数量', '企业详细地址', '企业经营状态', '所属管理网格编码', '企业等级']\n\n== 过滤条件 ==\n  时间 (whereKey): ['分析表更新时间', '分析表创建时间', '统计日期', '数据来源', '企业经营状态']\n  2026年2月 (whereValue): 不参与召回\n  日期 (whereKey): ['统计日期', '分析表更新时间', '分析表创建时间', '数据来源', '企业经营状态']\n  2026年2月 (whereValue): 不参与召回\n  月份 (whereKey): ['统计日期', '分析表创建时间', '分析表更新时间', '数据来源', '行业类型']\n  2026年2月 (whereValue): 不参与召回\n  统计月份 (whereKey): ['统计日期', '数据来源', '分析表创建时间', '分析表更新时间', '企业数量']\n  2026年2月 (whereValue): 不参与召回\n\n== 维度值线索（从短语中识别，辅助理解） ==\n  龙头企业数: \"龙头\" → 链主龙头 (维度=企业等级)（企业等级全部值: ['基础配套', '成长中坚', '核心骨干', '潜力小微', '链主龙头']）\n  龙头企业数量: \"龙头\" → 链主龙头 (维度=企业等级)\n  高风险占比: \"风险\" → 中风险 (维度=企业综合风险等级)（企业综合风险等级全部值: ['中风险', '低风险', '高风险']）\n  高风险占比: \"风险\" → 低风险 (维度=企业综合风险等级)\n  高风险占比: \"风险\" → 高风险 (维度=企业综合风险等级)\n  高风险比例: \"风险\" → 中风险 (维度=企业综合风险等级)\n  高风险比例: \"风险\" → 低风险 (维度=企业综合风险等级)\n  高风险比例: \"风险\" → 高风险 (维度=企业综合风险等级)"
    # import json
    # with open('/home/luoyanzhuo/project/by-datacloud/packages/datacloud-knowledge/scripts/manual/llm_confirm_test_cases.json') as f:
    #     dataset = json.load(f)
    #     for data in dataset:
    #         original_question = data['original_question']
    #         print(f'========{original_question}========')
    #         expanded_query = data['expanded_query']
    #         recall_context = data['recall_context']

    confirmed = llm_confirm(
        original_question=original_question,
        expanded_query=expanded_query,
        recall_context=recall_context,
    )
    if confirmed:
        import json

        print(json.dumps(confirmed.model_dump(), ensure_ascii=False, indent=2))
        print("\n=== 用户确认视图 ===")
        print("\n查询值:")
        for s in confirmed.select:
            display = semantic_to_display(s)
            sql = semantic_to_sql_expr(s)
            print(f"  {s.original_keyword}: {display}")
            print(f"    → SQL: {sql}")
        print("\n分组:")
        for g in confirmed.group_by:
            print(f"  {g.original_keyword or g.field} → {g.field}")
        print("\n过滤:")
        for w in confirmed.where:
            kw = w.original_field_keyword or w.original_value_keyword or w.field
            print(f"  {kw} → {w.field} {w.op} {w.value}")
        print("\n排序:")
        for o in confirmed.order_by:
            print(f"  {o.original_keyword or o.field} → {o.field} {o.direction}")
        if confirmed.clarify_items:
            print("\n⚠️ 需确认:")
            for ci in confirmed.clarify_items:
                src = f"[{ci.source}] " if ci.source else ""
                print(f"  {src}{ci.keyword} → {' / '.join(ci.candidates)}")
                if ci.reason:
                    print(f"    原因: {ci.reason}")

        print("\n表单:")
        form = _confirmed_query_to_paradigm_list(confirmed)
        print(json.dumps(form, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
