"""调试意图匹配 — 支持多种模糊匹配模式。

支持三种模糊匹配模式：
1. rapidfuzz: 字符串相似度匹配（默认）
2. bm25: PostgreSQL 全文搜索
3. vector: 向量语义相似度搜索

用法：
    python debug_intent.py                    # 默认 rapidfuzz 模式
    python debug_intent.py --mode bm25        # BM25 模式
    python debug_intent.py --mode vector      # 向量模式
"""

from datacloud_knowledge import reset_singleton_service
from pathlib import Path
from dotenv import load_dotenv
import argparse

from sqlalchemy import text

from datacloud_knowledge.intent import (
    Mention,
    SlotResult,
    MatchResult,
    UserNameCache,
    MatchCandidate,
    match_mentions,
    match_mentions_with_search,
    disambiguate,
    create_user_term_name,
    create_term_with_knowledge,
    batch_update_scores,
)

from datacloud_knowledge.knowledge_search.db.connection import get_session
from datacloud_knowledge.query.sql_engine import get_singleton_service


def print_match_result(match_result=None, disambiguation_result=None):
    """格式化打印匹配结果"""

    if match_result:
        print("\n" + "=" * 50)
        print("【精确匹配】")
        print("=" * 50)
        if match_result.exact:
            for mention_text, candidates in match_result.exact.items():
                print(f"\n'{mention_text}' → {len(candidates)} 个候选:")
                for i, c in enumerate(candidates, 1):
                    print(f"  {i}. {c.term_name}")
                    print(f"     ID: {c.term_id}")
                    print(f"     类型: {c.term_type_code}")
                    print(f"     置信度: {c.confidence:.2f}")
                    print(f"     匹配类型: {c.match_type}")
        else:
            print("  无")

        print("\n" + "=" * 50)
        print("【模糊匹配】")
        print("=" * 50)
        if match_result.fuzzy:
            for mention_text, candidates in match_result.fuzzy.items():
                if candidates:
                    print(f"\n'{mention_text}' → {len(candidates)} 个候选:")
                    for i, c in enumerate(candidates, 1):
                        print(
                            f"  {i}. {c.term_name} (相似度: {c.confidence:.0%}, 类型: {c.match_type})"
                        )
                else:
                    print(f"\n'{mention_text}' → 无匹配 (可能需要追问)")

    if disambiguation_result:
        print("\n" + "=" * 50)
        print("【消歧结果】")
        print("=" * 50)

        if disambiguation_result.confirmed:
            print(f"\n✓ 确权术语 ({len(disambiguation_result.confirmed)} 个):")
            for mention_text, c in disambiguation_result.confirmed.items():
                print(f"   - '{mention_text}' → {c.term_name} [{c.term_type_code}]")
        else:
            print("\n✓ 确权术语: 无")

        if disambiguation_result.ambiguous:
            print(f"\n? 歧义术语 ({len(disambiguation_result.ambiguous)} 个):")
            for mention_text, candidates in disambiguation_result.ambiguous.items():
                print(f"   - '{mention_text}' 有 {len(candidates)} 个候选:")
                for i, c in enumerate(candidates[:3], 1):
                    print(f"     {i}. {c.term_name} ({c.confidence:.0%}, {c.match_type})")
        else:
            print("\n? 歧义术语: 无")


def generate_clarification_message(
    confirmed: dict[str, MatchCandidate],
    ambiguous: dict[str, tuple[MatchCandidate, ...]],
    original_query: str,
) -> str:
    """生成追问消息"""

    lines = ["我已理解您的问题，但有几个概念需要您确认：\n"]

    for mention_text, candidates in ambiguous.items():
        if len(candidates) == 0:
            lines.append(f"❓ 「{mention_text}」在术语库中未找到匹配。")
            lines.append(f"   请解释这个词的含义，或指定一个已有的概念。\n")
        elif len(candidates) == 1:
            c = candidates[0]
            lines.append(f"❓ 「{mention_text}」可能指：{c.term_name}")
            lines.append(f"   确认是否正确？(y/n)\n")
        else:
            lines.append(f"❓ 「{mention_text}」有多个可能的含义：")
            for i, c in enumerate(candidates[:5], 1):
                lines.append(f"   {i}. {c.term_name} ({c.confidence:.0%})")
            lines.append(f"   请选择 1-{min(5, len(candidates))}，或输入自定义解释。\n")

    return "\n".join(lines)


def process_user_reply(
    mention_text: str,
    user_input: str,
    candidates: tuple[MatchCandidate, ...],
) -> MatchCandidate | str:
    """处理用户回复"""
    if len(candidates) == 0:
        return user_input

    try:
        choice = int(user_input.strip())
        if 1 <= choice <= len(candidates):
            return candidates[choice - 1]
    except ValueError:
        pass

    if user_input.lower() == "y" and len(candidates) == 1:
        return candidates[0]

    return user_input


def store_clarification_results(
    clarification_results: dict[str, MatchCandidate | str],
    user_id: str,
    session,
) -> list[str]:
    """存储澄清结果"""
    created_name_ids: list[str] = []

    for mention_text, result in clarification_results.items():
        if isinstance(result, MatchCandidate):
            name_id = create_user_term_name(
                name_text=mention_text,
                term_id=result.term_id,
                user_id=user_id,
                session=session,
            )
            created_name_ids.append(name_id)
            print(f"  ✓ 创建用户别名: '{mention_text}' → {result.term_name}")

        else:
            term_id, knowledge_id, name_id = create_term_with_knowledge(
                term_code=f"user_defined_{mention_text}",
                term_name=mention_text,
                term_type_code="USER_DEFINED",
                domain_id="DOMAIN_002",
                knowledge_text=result,
                user_id=user_id,
                session=session,
            )
            print(f"  ✓ 创建新术语: '{mention_text}' (term_id={term_id})")
            print(f"    知识: {result[:50]}...")
            created_name_ids.append(name_id)

    return created_name_ids


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="调试意图匹配")
    parser.add_argument(
        "--mode",
        choices=["rapidfuzz", "bm25", "vector"],
        default="bm25",
        help="模糊匹配模式: rapidfuzz , bm25 (默认), vector",
    )
    parser.add_argument(
        "--query",
        default="帮我看一下经开区内亩产效益最高的10家企业",
        help="测试查询",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)

    # 构造测试数据
    query = args.query
    solt_result = SlotResult(
        mentions=(Mention(text="经开区"), Mention(text="亩产效益"), Mention(text="企业"))
    )
    print("---语义解析---")
    print(solt_result)
    print(f"\n模糊匹配模式: {args.mode}")

    # Step 2: 获取数据库 session + global_name_index
    with get_session() as session:
        # 获取全局术语索引
        query_service = get_singleton_service(n_hops=4, fast=True)
        global_name_index = query_service._build_name_index()

        # Step 3: 术语匹配
        print("\n---Step 2: 术语匹配---")

        # 精确匹配
        exact_result = match_mentions_with_search(
            mentions=solt_result.mentions,
            session=session,
            global_name_index=global_name_index
        )
        # BM25 或向量模式
        embedding_service = None
        if args.mode == "vector":
            try:
                from datacloud_knowledge.query.embedding import get_embedding_service

                embedding_service = get_embedding_service()
                print("已加载 Embedding 服务")
            except ImportError:
                print("警告: Embedding 服务不可用，回退到 bm25 模式")
                args.mode = 'bm25'
                

        fuzzy_result = match_mentions_with_search(
            mentions=solt_result.mentions,
            session=session,
            global_name_index=global_name_index,
            search_mode=args.mode,
            embedding_service=embedding_service,
            top_k=5,
        )

        match_result = MatchResult(
            exact=exact_result,
            fuzzy=fuzzy_result
        )

        print_match_result(match_result)

        # Step 4: 多维消歧
        print("\n---Step 3: 多维消歧---")
        disambiguation_result = disambiguate(match_result, session)
        print_match_result(disambiguation_result=disambiguation_result)

        # 模拟追问流程
        print("\n" + "=" * 50)
        print("【追问澄清】")
        print("=" * 50)

        clarification_msg = generate_clarification_message(
            confirmed=disambiguation_result.confirmed,
            ambiguous=disambiguation_result.ambiguous,
            original_query=query,
        )
        print(clarification_msg)

        # 模拟用户回复
        simulated_replies = {
            "经开区": "北京亦庄经济技术开发区",
            "亩产效益": "## 计算公式\n企业亩产效益 = 企业申报营收 / 企业占地面积（亩）\n",
            "企业": "1",
        }

        print("\n--- 模拟用户回复 ---")

        clarification_results: dict[str, MatchCandidate | str] = {}

        for mention_text, candidates in disambiguation_result.ambiguous.items():
            user_reply = simulated_replies.get(mention_text, "")
            print(f"用户对「{mention_text}」的回复: {user_reply}")

            result = process_user_reply(mention_text, user_reply, candidates)
            clarification_results[mention_text] = result

            if isinstance(result, MatchCandidate):
                print(f"  → 确认: {result.term_name}")
            else:
                print(f"  → 自定义: {result}")

        print("\n--- 澄清结果 ---")
        print(clarification_results)

        USER_ID = "user_001"

        # 存储澄清结果
        print("\n--- 存储澄清结果 ---")
        created_name_ids = store_clarification_results(
            clarification_results=clarification_results,
            user_id=USER_ID,
            session=session,
        )

        # 模拟对话成功
        dialog_success = True

        # score 闭环更新
        print("\n--- Score 闭环更新 ---")
        if created_name_ids:
            from datacloud_knowledge.intent import ScoreUpdateRecord

            records = tuple(
                ScoreUpdateRecord(name_id=nid, success=dialog_success) for nid in created_name_ids
            )
            batch_update_scores(records, session)
            print(f"  ✓ 更新了 {len(created_name_ids)} 条别名记录的 score")
        else:
            print("  无需更新 score（没有新创建的别名）")

        print("\n=== 流程完成 ===")

        # 验证：第二次查询
        print("\n" + "=" * 50)
        print("【验证：第二次查询】")
        print("=" * 50)

        user_cache = UserNameCache()

        print("\n--- 第二次术语匹配 (带用户缓存) ---")

        exact_result_2 = match_mentions_with_search(
            mentions=solt_result.mentions,
            session=session,
            user_id=USER_ID,
            global_name_index=global_name_index,
            user_cache=user_cache
        )
        match_result_2 = MatchResult(exact=exact_result_2, fuzzy={})

        print("\n第二次匹配结果:")
        print_match_result(match_result_2)

        # 验证精确匹配
        print("\n--- 验证结果 ---")
        for mention in solt_result.mentions:
            if mention.text in match_result_2.exact:
                candidates = match_result_2.exact[mention.text]
                if candidates:
                    print(f"✓ '{mention.text}' 第二次精确匹配成功")
                else:
                    print(f"✗ '{mention.text}' 第二次仍未匹配")
            else:
                print(f"✗ '{mention.text}' 不在精确匹配中")

        print("\n--- 验证知识查询 ---")

        # 从第二次匹配结果构建 QueryEntity
        from datacloud_knowledge.query.sql_engine import QueryEntity
        entities: list[QueryEntity] = []
        for mention in solt_result.mentions:
            if mention.text in match_result_2.exact:
                candidates = match_result_2.exact[mention.text]
                if candidates:
                    # 取置信度最高的候选
                    best = candidates[0]
                    entity = QueryEntity(
                        name=best.term_name,
                        node_id=best.term_id,
                        node_type=best.term_type_code,
                        match_score=best.confidence,
                        match_type=best.match_type,
                        matched_text=mention.text,
                    )
                    entities.append(entity)
        print(f"构建了 {len(entities)} 个查询实体")
        # 执行知识子图查询
        subgraphs = query_service._batch_query_subgraphs(
            entities=entities,
            n_hops=4,
            include_knowledge=True,
        )
        print(query_service._format_subgraphs_as_tree_text(subgraphs))

        # 清理测试数据
        print("\n" + "=" * 50)
        print("【清理测试数据】")
        print("=" * 50)

        if created_name_ids:
            session.execute(
                text("DELETE FROM whale_datacloud.term_name WHERE name_id = ANY(:ids)"),
                {"ids": created_name_ids},
            )
            print(f"  ✓ 删除 {len(created_name_ids)} 条 term_name 记录")

        for mention_text, result in clarification_results.items():
            if isinstance(result, str):
                session.execute(
                    text(
                        "DELETE FROM whale_datacloud.term_knowledge WHERE term_id IN "
                        "(SELECT term_id FROM whale_datacloud.term WHERE term_code = :code)"
                    ),
                    {"code": f"user_defined_{mention_text}"},
                )
                session.execute(
                    text("DELETE FROM whale_datacloud.term WHERE term_code = :code"),
                    {"code": f"user_defined_{mention_text}"},
                )
                print(f"  ✓ 删除用户定义术语: {mention_text}")

        user_cache.invalidate(USER_ID)
        print("  ✓ 清除用户缓存")

        print("\n=== 完整验证流程结束 ===")
        reset_singleton_service()


if __name__ == "__main__":
    main()
