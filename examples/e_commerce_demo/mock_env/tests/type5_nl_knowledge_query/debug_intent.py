from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import text

from datacloud_knowledge.intent import (
    Mention,
    SlotResult,
    UserNameCache,
    MatchCandidate,
    match_mentions, 
    disambiguate, 
    create_user_term_name,
    create_term_with_knowledge,
    batch_update_scores)

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
                        print(f"  {i}. {c.term_name} (相似度: {c.confidence:.0%})")
                else:
                    print(f"\n'{mention_text}' → 无匹配 (可能需要追问)")
    
    if disambiguation_result:
        print("\n" + "=" * 50)
        print("【消歧结果】")
        print("=" * 50)
        
        if disambiguation_result.confirmed:
            print(f"\n✓ 确权术语 ({len(disambiguation_result.confirmed)} 个):")
            # 改成 .items() 遍历
            for mention_text, c in disambiguation_result.confirmed.items():
                print(f"   - '{mention_text}' → {c.term_name} [{c.term_type_code}]")
        else:
            print("\n✓ 确权术语: 无")
        
        if disambiguation_result.ambiguous:
            print(f"\n? 歧义术语 ({len(disambiguation_result.ambiguous)} 个):")
            # 改成 .items() 遍历
            for mention_text, candidates in disambiguation_result.ambiguous.items():
                print(f"   - '{mention_text}' 有 {len(candidates)} 个候选:")
                for i, c in enumerate(candidates[:3], 1):  # 只显示前3个
                    print(f"     {i}. {c.term_name} ({c.confidence:.0%})")
        else:
            print("\n? 歧义术语: 无")

def generate_clarification_message(
    confirmed: dict[str, MatchCandidate],
    ambiguous: dict[str, tuple[MatchCandidate, ...]],
    original_query: str,
) -> str:
    """生成追问消息 (算法 D)"""
    
    lines = ["我已理解您的问题，但有几个概念需要您确认：\n"]
    
    for mention_text, candidates in ambiguous.items():
        if len(candidates) == 0:
            # 完全未知
            lines.append(f"❓ 「{mention_text}」在术语库中未找到匹配。")
            lines.append(f"   请解释这个词的含义，或指定一个已有的概念。\n")
        elif len(candidates) == 1:
            # 单候选但置信度不够
            c = candidates[0]
            lines.append(f"❓ 「{mention_text}」可能指：{c.term_name}")
            lines.append(f"   确认是否正确？(y/n)\n")
        else:
            # 多义竞争
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
    """处理用户回复
    
    Returns:
        MatchCandidate: 用户选择的候选
        str: 用户自定义的解释
    """
    if len(candidates) == 0:
        # 完全未知，用户给自定义解释
        return user_input
    
    # 尝试解析用户选择的编号
    try:
        choice = int(user_input.strip())
        if 1 <= choice <= len(candidates):
            return candidates[choice - 1]
    except ValueError:
        pass
    
    # 用户输入 y/n 确认单候选
    if user_input.lower() == 'y' and len(candidates) == 1:
        return candidates[0]
    
    # 用户输入自定义解释
    return user_input

def store_clarification_results(
    clarification_results: dict[str, MatchCandidate | str],
    user_id: str,
    session,
) -> list[str]:
    """存储澄清结果 (算法 D 存储部分)
    
    Returns:
        创建的 name_id 列表，用于后续 score 更新
    """
    created_name_ids: list[str] = []
    
    for mention_text, result in clarification_results.items():
        if isinstance(result, MatchCandidate):
            # 用户选择了已有术语 → 创建用户别名
            name_id = create_user_term_name(
                name_text=mention_text,
                term_id=result.term_id,
                user_id=user_id,
                session=session,
            )
            created_name_ids.append(name_id)
            print(f"  ✓ 创建用户别名: '{mention_text}' → {result.term_name}")
            
        else:
            # 用户自定义解释 → 创建新术语 + 知识
            # 需要 domain_id，从已有术语获取或使用默认值
            term_id, knowledge_id, name_id = create_term_with_knowledge(
                term_code=f"user_defined_{mention_text}",
                term_name=mention_text,
                term_type_code="USER_DEFINED",  # 自定义类型
                domain_id="DOMAIN_002",  # 产业管理领域
                knowledge_text=result,  # 用户给出的解释
                user_id=user_id,
                session=session,
            )
            print(f"  ✓ 创建新术语: '{mention_text}' (term_id={term_id})")
            print(f"    知识: {result[:50]}...")
            # create_term_with_knowledge 内部已创建用户别名
            created_name_ids.append(name_id)
    
    return created_name_ids


def main():
    env_path = Path(__file__).resolve().parents[2] / ".env.example"
    if env_path.exists():
        load_dotenv(env_path, override=True)

    query = "帮我看一下经开区内亩产效益最高的10家企业"
    solt_result = SlotResult(
        mentions=(
            Mention(text='经开区'),
            Mention(text='亩产效益'),
            Mention(text='企业')
        )
    )
    print("---语义解析---")
    print(solt_result)

    # Step 2: 获取数据库 session + global_name_index
    with get_session() as session:
        # 获取全局术语索引（从 SQLKnowledgeGraphQuery）
        query_service = get_singleton_service(
            n_hops=4, fast=True)

        global_name_index = query_service._build_name_index()  # 内部方法
        
        # Step 3: 术语匹配 (算法 B)
        print("\n---Step 2: 术语匹配---")
        match_result = match_mentions(
            mentions=solt_result.mentions,
            session=session,
            global_name_index=global_name_index,
        )
        print_match_result(match_result)

        # Step 4: 多维消歧 (算法 C)
        print("\n---Step 3: 多维消歧---")
        disambiguation_result = disambiguate(match_result, session)

        print_match_result(disambiguation_result=disambiguation_result)

        # 模拟追问流程
        print("\n" + "=" * 50)
        print("【追问澄清】")
        print("=" * 50)
        
        # 生成追问消息
        clarification_msg = generate_clarification_message(
            confirmed=disambiguation_result.confirmed,
            ambiguous=disambiguation_result.ambiguous,
            original_query=query,
        )
        print(clarification_msg)

        # 模拟用户回复（实际场景中是用户输入）
        simulated_replies = {
            '经开区': '北京亦庄经济技术开发区',  # 用户自定义
            '亩产效益': '## 计算公式\n企业亩产效益 = 企业申报营收 / 企业占地面积（亩）\n',                          # 用户自定义解释
            '企业': '1',                     # 用户选择第1个候选
        }

        print("\n--- 模拟用户回复 ---")
        
        clarification_results: dict[str, MatchCandidate | str] = {}
        
        for mention_text, candidates in disambiguation_result.ambiguous.items():
            user_reply = simulated_replies.get(mention_text, '')
            print(f"用户对「{mention_text}」的回复: {user_reply}")
            
            result = process_user_reply(mention_text, user_reply, candidates)
            clarification_results[mention_text] = result
            
            if isinstance(result, MatchCandidate):
                print(f"  → 确认: {result.term_name}")
            else:
                print(f"  → 自定义: {result}")
        
        # 后续可以根据 clarification_results 存储 TermName / TermKnowledge
        print("\n--- 澄清结果 ---")
        print(clarification_results)
    
        USER_ID = "user_001"  # 模拟用户 ID

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
                ScoreUpdateRecord(name_id=nid, success=dialog_success)
                for nid in created_name_ids
            )
            batch_update_scores(records, session)
            print(f"  ✓ 更新了 {len(created_name_ids)} 条别名记录的 score")
        else:
            print("  无需更新 score（没有新创建的别名）")
        
        print("\n=== 流程完成 ===")

        # ============================================
        # 第二次查询：验证用户别名生效
        # ============================================
        print("\n" + "=" * 50)
        print("【验证：第二次查询】")
        print("=" * 50)
        
        # 创建用户缓存
        user_cache = UserNameCache()
        
        # 模拟第二次查询，使用相同的 mentions
        print("\n--- 第二次术语匹配 (带用户缓存) ---")
        match_result_2 = match_mentions(
            mentions=solt_result.mentions,
            session=session,
            user_id=USER_ID,
            global_name_index=global_name_index,
            user_cache=user_cache,
        )
        
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
        for mention_text, result in clarification_results.items():
            if isinstance(result, str):  # 用户自定义
                # 查询该术语的知识
                knowledge_rows = session.execute(text("""
                    SELECT k.desc_summary, k."desc"
                    FROM whale_datacloud.term_knowledge k
                    JOIN whale_datacloud.term t ON k.term_id = t.term_id
                    WHERE t.term_name = :name
                """), {"name": mention_text}).fetchall()
                
                if knowledge_rows:
                    print(f"✓ '{mention_text}' 知识已存储:")
                    print(f"  摘要: {knowledge_rows[0][0][:80]}...")
                else:
                    print(f"✗ '{mention_text}' 知识未找到")
        
        # ============================================
        # 清理测试数据
        # ============================================
        print("\n" + "=" * 50)
        print("【清理测试数据】")
        print("=" * 50)
        
        # 删除创建的 term_name
        if created_name_ids:
            session.execute(
                text("DELETE FROM whale_datacloud.term_name WHERE name_id = ANY(:ids)"),
                {"ids": created_name_ids},
            )
            print(f"  ✓ 删除 {len(created_name_ids)} 条 term_name 记录")
        
        # 删除创建的 term_knowledge 和 term
        for mention_text, result in clarification_results.items():
            if isinstance(result, str):  # 用户自定义的术语
                session.execute(
                    text("DELETE FROM whale_datacloud.term_knowledge WHERE term_id IN "
                        "(SELECT term_id FROM whale_datacloud.term WHERE term_code = :code)"),
                    {"code": f"user_defined_{mention_text}"},
                )
                session.execute(
                    text("DELETE FROM whale_datacloud.term WHERE term_code = :code"),
                    {"code": f"user_defined_{mention_text}"},
                )
                print(f"  ✓ 删除用户定义术语: {mention_text}")
        
        # 清除用户缓存
        user_cache.invalidate(USER_ID)
        print("  ✓ 清除用户缓存")
        
        print("\n=== 完整验证流程结束 ===")


if __name__ == '__main__':
    main()

#     可能的问题：
# 1. MatchCandidate.term_name 字段语义不太对，应该显示术语标准名而不是别名
# 2. '企业' 映射到 "北京法商通企业管理有限公司" 这个企业名，语义上可能不对

# ## 可能需要后续优化的点
# 1. **`MatchCandidate.term_name` 语义问题**
#    当前显示的是 `mention.text`（别名），而不是术语标准名。如果需要显示标准名，需要从 `term` 表查询。
# 2. **'企业' 映射到具体企业名**
#    用户选择的 "北京法商通企业管理有限公司" 是一个具体企业，而不是"企业"这个概念。模糊匹配按 `term_type` 过滤可以改善这个问题（后续优化）。
# 3. **自定义术语的 `term_type_code`**
#    当前用 `USER_DEFINED`，实际应该根据用户意图推断类型（如 `METRIC`、`ENTITY` 等）。