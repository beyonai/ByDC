from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.natquery import expand_query
from datacloud_knowledge.intent.types import StreamEvent, StreamEventKind

_last_thinking = ""


def print_event(event: StreamEvent) -> None:
    global _last_thinking
    if event.kind == StreamEventKind.THINKING:
        delta = event.content.removeprefix(_last_thinking)
        if delta:
            print(delta, end="", flush=True)
        _last_thinking = event.content


def main():
    query_list = [
        # # 0. 泄漏验证：用户没说具体级别，LLM 不应脑补出龙头/骨干/中型/小微
        # "亦庄各类级别企业的分布",
        # 1. 简单查询：无展开，纯过滤+排序
        "查询前3个营收最低的网格",
        # # 2. 具体值进 where/group_by，不展开进 select
        # "荣华、亦庄、瀛海网格的车流、人流情况如何？",
        # # 3. 笛卡尔展开：3类别×3指标=9短语
        # "202602龙头、骨干、中坚企业的数量、营收、利润",
        # # 4. 展开 + 具体值进 where + 过滤条件
        # "2026年2月荣华、亦庄各街道营收超过5000万且税负率低于6%的龙头、骨干企业数",
        # # 5. 展开 + 多层过滤（经营状态+风险等级+地域）
        # "2026年2月荣华、亦庄各街道营业中低风险的龙头、骨干企业的数量、总营收、平均利润",
        # # 6. 派生计算：占比
        # "202602各街道的总营收、龙头企业营收、龙头占比",
        # # 7. 三层笛卡尔：产业链×上下游×企业类型
        # "202602信息技术、汽车各链的上游、下游的龙头、骨干企业数",
        # # 8-22. 全量用例
        # "荣华、亦庄、瀛海网格，企业清单，要列出企业效能、企业应收相关信息,特别关注低效益的企业。",
        # "土木工程建筑业 行业，营收排前10的企业有哪些",
        # '查找"荣华街道"管理网格"中效益企业"，"高效益企业"企业清单，展示结果必须包含企业经济效益等级 信息，展示字段尽量多。',
        # "找出亩产效益后3的地块，查询这些地块上的中、低效能的企业清单。",
        # "我要查一下小米公司的的行业和所在的网格！",
        # "帮我查一下亦庄区域高风险企业总数和龙头企业的企业缴税总数、收入均值",
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

    for query in query_list:
        natquery = expand_query(query, on_event=print_event)

        if natquery:
            print(natquery.model_dump())
        else:
            print("LLM解析失败")

        print("\n")
        print("=" * 10)
        print("\n")


if __name__ == "__main__":
    main()
