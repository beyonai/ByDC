"""端到端测试: analyze_query_clarification 全流程。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarification_e2e.py
"""

from __future__ import annotations

import json

from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent import analyze_query_clarification

TEST_CASES = [
    # 0. 泄漏验证 + expr=COUNT(*) 曾导致 tsquery 炸
    "亦庄各类级别企业的分布",
    # 1. order_by 含 ASC/DESC 曾原样进召回
    "查询前3个营收最低的网格",
    # 5. expr=COUNT/SUM/AVG 包裹，需提取内部参数
    "2026年2月荣华、亦庄各街道营业中低风险的龙头、骨干企业的数量、总营收、平均利润",
    # 6. 派生表达式 expr=龙头企业营收/总营收，需拆成两段
    "202602各街道的总营收、龙头企业营收、龙头占比",
    # 13. expr=COUNT(*) + 多指标混合
    "帮我查一下亦庄区域高风险企业总数和龙头企业的企业缴税总数、收入均值",
    # --- 以下用例暂时注释，加速复测 ---
    # "荣华、亦庄、瀛海网格的车流、人流情况如何？",
    # "202602龙头、骨干、中坚企业的数量、营收、利润",
    # "2026年2月荣华、亦庄各街道营收超过5000万且税负率低于6%的龙头、骨干企业数",
    # "202602信息技术、汽车各链的上游、下游的龙头、骨干企业数",
    # "荣华、亦庄、瀛海网格，企业清单，要列出企业效能、企业应收相关信息,特别关注低效益的企业。",
    # "土木工程建筑业 行业，营收排前10的企业有哪些",
    # '查找"荣华街道"管理网格"中效益企业"，"高效益企业"企业清单，展示结果必须包含企业经济效益等级 信息，展示字段尽量多。',
    # "找出亩产效益后3的地块，查询这些地块上的中、低效能的企业清单。",
    # "我要查一下小米公司的的行业和所在的网格！",
    # "帮我查一下亦庄区域高风险企业总数，高风险、高效益中坚企业的收入总额、利润均值",
    # "YZ_G100_1 下有哪些企业？",
    # "2026年2月荣华、亦庄各街道灯光明亮、人流正常企业的营收、利润、税收",
    # "202602高效益、中效益、低效益网格的营收、利润、亩产",
    # "2026年2月荣华、亦庄、瀛海各街道营收超过5000万的龙头、骨干企业的数量、营收、利润",
    # "202602各街道低风险营业中的龙头、骨干、中坚企业的数量、总营收、平均利润",
    # "202602各街道灯光明亮物理网格数、企业数、企业营收",
    # "202602荣华、亦庄、瀛海、台湖、马驹桥各街道的龙头、骨干企业营收",
    # "2026年2月荣华、亦庄、瀛海各街道信息技术、汽车链的龙头、骨干企业数量、总营收、总利润",
]


def main() -> None:
    for query in TEST_CASES:
        print(f"\n{'=' * 80}")
        print(f"INPUT: {query}")
        print(f"{'─' * 80}")
        try:
            result = analyze_query_clarification(query)
            print(f"query: {result.query}")
            print(f"needs_clarification: {result.needs_clarification}")
            if result.form:
                payload = json.loads(result.form)
                print(f"form paradigmList count: {len(payload.get('paradigmList', []))}")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            if result.knowledge:
                payload = json.loads(result.knowledge)
                print(f"knowledge paradigmList count: {len(payload.get('paradigmList', []))}")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            if not result.form and not result.knowledge:
                print("(passthrough - no form or knowledge)")
        except Exception as exc:
            print(f"ERROR: {exc}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    main()
