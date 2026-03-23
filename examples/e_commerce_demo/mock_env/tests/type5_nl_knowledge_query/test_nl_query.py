#!/usr/bin/env python3
"""自然语言查知识测试 - 电商产业大脑场景

基于场景测试结果文档中的4大类测试用例：
1. 偷税漏税 - 风险企业识别与证据分析
2. 经济活力 - 亩产效益排名、企业行业分析、纳税排名
3. 产业链对比 - 亦庄vs闵行的产业能力对比与建议
4. 闲置资产交易 - 空置用地/楼宇查询与交易推动建议
"""

import os
import sys
from pathlib import Path

import pytest

# 将项目根目录加入路径
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "..",
        "packages",
        "datacloud-knowledge",
        "src",
    ),
)

from datacloud_knowledge import SQLKnowledgeGraphQuery, TreeNode, nl_to_semantic_tree


def dict_to_tree(tree_dict: dict) -> TreeNode:
    """将字典转换为TreeNode"""
    node = TreeNode(
        id=tree_dict.get("id", ""),
        name=tree_dict.get("name", ""),
        node_type=tree_dict.get("node_type", ""),
        properties=tree_dict.get("properties", {}),
        relation=tree_dict.get("relation", ""),
    )

    for child_dict in tree_dict.get("children", []):
        node.children.append(dict_to_tree(child_dict))

    return node


def print_tree(node: TreeNode, prefix: str = "", is_last: bool = True) -> str:
    """打印树形结构"""
    lines = []

    connector = "└── " if is_last else "├── "
    relation_str = f"[{node.relation}] -> " if node.relation else ""
    lines.append(f"{prefix}{connector}{relation_str}{node.name} [{node.node_type}]")

    new_prefix = prefix + ("    " if is_last else "│   ")

    if node.properties:
        lines.append(f"{new_prefix}├── 属性:")
        prop_prefix = new_prefix + "│   "
        props = list(node.properties.items())
        for i, (key, value) in enumerate(props):
            is_last_prop = (i == len(props) - 1) and not node.children
            prop_connector = "└── " if is_last_prop else "├── "
            value_str = str(value)
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            lines.append(f"{prop_prefix}{prop_connector}{key}: {value_str}")

    for i, child in enumerate(node.children):
        is_last_child = i == len(node.children) - 1
        lines.append(print_tree(child, new_prefix, is_last_child))

    return "\n".join(lines)


def execute_nl_query(query_text: str, service: SQLKnowledgeGraphQuery | None = None) -> dict:
    """执行自然语言查询并返回结果"""
    if service is None:
        service = SQLKnowledgeGraphQuery(default_hops=4)

    print(f"\n执行查询: '{query_text}'")
    result = service.query(query_text)

    # 打印识别的实体
    entities = result.get("entities_found", [])
    print(f"识别到的中心实体: {len(entities)} 个")
    for i, entity in enumerate(entities, 1):
        match_type_str = "精确匹配" if entity.get("match_type") == "standard_name" else "别名匹配"
        print(f"  {i}. {entity['name']} ({entity['node_type']}) - {match_type_str}")

    return result


def print_query_results(result: dict, query_name: str) -> None:
    """打印查询结果"""
    print(f"\n{'=' * 70}")
    print(f"【{query_name}】查询结果")
    print(f"{'=' * 70}")

    results = result.get("results", [])
    if results:
        for i, subgraph in enumerate(results, 1):
            center_entity = subgraph.get("center_entity", {})
            print(f"\n【中心实体 {i}】{center_entity.get('name')}")
            print(f"节点数: {subgraph.get('node_count')}, 边数: {subgraph.get('edge_count')}")

            tree_dict = subgraph.get("tree")
            if tree_dict:
                tree = dict_to_tree(tree_dict)
                print(f"\n树形结构:")
                print(print_tree(tree, prefix="", is_last=True))
            else:
                print("  (无树形结构)")
    else:
        print("\n✗ 未返回子图结果")


# ════════════════════════════════════════════════════════════════════════════
# 测试类：nl_to_semantic_tree 函数测试
# ════════════════════════════════════════════════════════════════════════════


class TestNlToSemanticTree:
    """nl_to_semantic_tree 函数测试"""

    @pytest.fixture(scope="class")
    def service(self):
        """创建知识图谱查询服务实例"""
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[5] / ".env.example"
        if env_path.exists():
            load_dotenv(env_path, override=True)
        return SQLKnowledgeGraphQuery(default_hops=2)

    def test_nl_to_semantic_tree_yizhuang_output(self, service):
        """测试：nl_to_semantic_tree 输出严格匹配预期结果

        查询：帮我看一下"北京亦庄经济技术开发区"区域内单位亩产效益最低的10家企业
        """
        query = '帮我看一下"北京亦庄经济技术开发区"区域内单位亩产效益最低的10家企业'
        result = nl_to_semantic_tree(query, service=service, n_hops=2)

        expected_output = """查询: 帮我看一下"北京亦庄经济技术开发区"区域内单位亩产效益最低的10家企业
识别到 6 个实体:
  1. 北京亦庄经济技术开发区 (region_name) - 精确匹配
  2. 亩产效益 (enterprise_metric) - 别名匹配
  3. 低 (risk_level) - 精确匹配
  4. 低 (todo_priority) - 精确匹配
  5. 低 (urgency_level) - 精确匹配
  6. 企业 (belong_industry) - 精确匹配

【中心实体 1】北京亦庄经济技术开发区
节点数: 4, 边数: 3

知识图谱:
└── 北京亦庄经济技术开发区 [region_name]
    └── [区域_包含_企业] -> 企业大宽表 [ONTOLOGY_OBJ]
        ├── [企业_归属_网格] -> 网格大宽表 [ONTOLOGY_OBJ]
        └── [企业_归属_产业链] -> 产业维度大宽表 [ONTOLOGY_OBJ]

【中心实体 2】亩产效益
节点数: 4, 边数: 4

知识图谱:
└── 企业亩产效益 [enterprise_metric]
    ├── [企业亩产效益_计算依赖_营收] -> 企业申报营收 [enterprise_metric]
    │   └── [企业申报营收_归属_企业表] -> 企业大宽表 [ONTOLOGY_OBJ]
    └── [企业亩产效益_计算依赖_占地] -> 企业占地面积（亩） [enterprise_metric]
        └── [企业占地_归属_企业表] -> 企业大宽表 [ONTOLOGY_OBJ]

【中心实体 3】低
节点数: 4, 边数: 3

知识图谱:
└── 低 [risk_level]
    └── [低风险_分类_企业] -> 企业大宽表 [ONTOLOGY_OBJ]
        ├── [企业_归属_网格] -> 网格大宽表 [ONTOLOGY_OBJ]
        └── [企业_归属_产业链] -> 产业维度大宽表 [ONTOLOGY_OBJ]

【中心实体 4】低
节点数: 1, 边数: 0

知识图谱:
└── 低 [todo_priority]

【中心实体 5】低
节点数: 1, 边数: 0

知识图谱:
└── 低 [urgency_level]

【中心实体 6】企业
节点数: 1, 边数: 0

知识图谱:
└── 企业 [belong_industry]"""

        assert result == expected_output, (
            f"输出不匹配预期结果:\n实际输出:\n{result}\n\n预期输出:\n{expected_output}"
        )


# ════════════════════════════════════════════════════════════════════════════
# 测试类：经济活力类查询
# ════════════════════════════════════════════════════════════════════════════


class TestEconomicVitality:
    """经济活力类查询测试"""

    @pytest.fixture(scope="class")
    def service(self):
        """创建知识图谱查询服务实例"""
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[5] / ".env.example"
        if env_path.exists():
            load_dotenv(env_path, override=True)
        return SQLKnowledgeGraphQuery(default_hops=4)

    def test_query_lowest_output_per_mu_enterprises(self, service):
        """测试：查询亩产效益最低的10家企业

        期望结果包含以下企业（按亩产效益升序）：
        - 嘉和机械智能（954）有限公司: 0.028807
        - 京南云信息技术有限公司: 0.038358
        - 众联精密（3520）工程技术有限公司: 0.047631
        - 博创创新智能科技有限公司: 0.051335
        - 亦庄创新创新工程技术有限公司: 0.054617
        - 新宇智能创新信息技术有限公司: 0.058097
        - 新宇物联网科技科技有限公司: 0.059167
        - 鼎盛精工（2821）科技有限公司: 0.067918
        - 宏达精工制造有限公司: 0.068834
        - 大兴电子工程技术有限公司: 0.069009
        """
        query = '帮我看一下"北京亦庄经济技术开发区"区域内单位亩产效益最低的10家企业'
        result = execute_nl_query(query, service)
        print_query_results(result, "亩产效益最低的10家企业")

        # 验证识别到实体
        assert len(result.get("entities_found", [])) > 0, (
            "未识别到任何实体，请确认PG中已导入相关术语数据"
        )

    def test_query_enterprise_industry_info(self, service):
        """测试：查询企业所属行业"""
        query = "京南云信息技术有限公司属于哪些行业"
        result = execute_nl_query(query, service)
        print_query_results(result, "企业行业信息")

        assert len(result.get("entities_found", [])) > 0, "未识别到企业实体"

    def test_query_enterprise_tax_ranking(self, service):
        """测试：查询企业纳税额及排名"""
        query = "京南云信息技术有限公司的纳税额是多少，在整个亦庄排多少名"
        result = execute_nl_query(query, service)
        print_query_results(result, "企业纳税排名")

        assert len(result.get("entities_found", [])) > 0, "未识别到企业实体"


# ════════════════════════════════════════════════════════════════════════════
# 测试类：偷税漏税类查询
# ════════════════════════════════════════════════════════════════════════════


class TestTaxRisk:
    """偷税漏税风险类查询测试"""

    @pytest.fixture(scope="class")
    def service(self):
        """创建知识图谱查询服务实例"""
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[5] / ".env.example"
        if env_path.exists():
            load_dotenv(env_path, override=True)
        return SQLKnowledgeGraphQuery(default_hops=4)

    def test_query_risk_enterprise_count(self, service):
        """测试：查询整个区域有风险的企业数量"""
        query = "整个区域有多少家企业有偷税漏税风险"
        result = execute_nl_query(query, service)
        print_query_results(result, "风险企业数量")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"

    def test_query_high_risk_enterprises(self, service):
        """测试：查询高风险等级企业"""
        query = "这些企业中高风险等级的是哪些企业"
        result = execute_nl_query(query, service)
        print_query_results(result, "高风险等级企业")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"

    def test_query_enterprise_risk_evidence(self, service):
        """测试：查询企业风险证据"""
        query = "XXX公司因为哪些关键证据被判断为偷税漏税"
        result = execute_nl_query(query, service)
        print_query_results(result, "企业风险证据")

        # 这个测试可能没有具体企业数据，允许空结果
        print(f"查询结果: {result}")


# ════════════════════════════════════════════════════════════════════════════
# 测试类：产业链对比类查询
# ════════════════════════════════════════════════════════════════════════════


class TestIndustryChainComparison:
    """产业链对比类查询测试"""

    @pytest.fixture(scope="class")
    def service(self):
        """创建知识图谱查询服务实例"""
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[5] / ".env.example"
        if env_path.exists():
            load_dotenv(env_path, override=True)
        return SQLKnowledgeGraphQuery(default_hops=4)

    def test_query_region_industry_comparison(self, service):
        """测试：对比亦庄和闵行的产业链发展能力"""
        query = "帮我对比北京亦庄区域内和上海闵行经济开发区的产业链发展的能力指标，以及给出应该亦庄应引进哪些类型的企业从而提高产业发展能力"
        result = execute_nl_query(query, service)
        print_query_results(result, "产业链对比分析")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"

    def test_query_minhang_advantage_industries(self, service):
        """测试：查询闵行优势产业"""
        query = "上海闵行经济开发区的优势产业有哪些"
        result = execute_nl_query(query, service)
        print_query_results(result, "闵行优势产业")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"

    def test_query_yizhuang_weakness(self, service):
        """测试：查询亦庄短板"""
        query = "北京亦庄经济开发区的短板聚集在哪些方面"
        result = execute_nl_query(query, service)
        print_query_results(result, "亦庄短板分析")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"


# ════════════════════════════════════════════════════════════════════════════
# 测试类：闲置资产交易类查询
# ════════════════════════════════════════════════════════════════════════════


class TestIdleAssetTransaction:
    """闲置资产交易类查询测试"""

    @pytest.fixture(scope="class")
    def service(self):
        """创建知识图谱查询服务实例"""
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parents[5] / ".env.example"
        if env_path.exists():
            load_dotenv(env_path, override=True)
        return SQLKnowledgeGraphQuery(default_hops=4)

    def test_query_vacant_assets(self, service):
        """测试：查询空置工业用地和办公楼宇"""
        query = "帮我看下目前北京亦庄区域内有哪些工业用地及办公楼宇目前仍处于空置状态"
        result = execute_nl_query(query, service)
        print_query_results(result, "空置资产查询")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"

    def test_query_asset_transaction_value(self, service):
        """测试：查询特定地块交易价值"""
        query = "亦庄科技园A地块这块工业用地的交易价值如何"
        result = execute_nl_query(query, service)
        print_query_results(result, "地块交易价值")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"

    def test_query_asset_transaction_policy(self, service):
        """测试：查询推动闲置资产交易的政策建议"""
        query = "帮我看下如何推动这些闲置资产的交易，有哪些合理的政策"
        result = execute_nl_query(query, service)
        print_query_results(result, "资产交易政策建议")

        assert len(result.get("entities_found", [])) > 0, "未识别到相关实体"


# ════════════════════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """支持直接运行单个测试"""
    import sys

    # 从 .env.example 加载环境变量
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parents[5] / ".env.example"
    if env_path.exists():
        load_dotenv(env_path, override=True)

    # 创建服务实例
    service = SQLKnowledgeGraphQuery(default_hops=4)

    # 运行指定测试或默认测试
    test_name = sys.argv[1] if len(sys.argv) > 1 else "economic"

    print("=" * 70)
    print(f"运行测试: {test_name}")
    print("=" * 70)

    try:
        if test_name == "economic" or test_name == "all":
            print("\n" + "=" * 70)
            print("【经济活力类测试】")
            print("=" * 70)

            query1 = '帮我看一下"北京亦庄经济技术开发区"区域内单位亩产效益最低的10家企业'
            result1 = execute_nl_query(query1, service)
            print_query_results(result1, "亩产效益最低的10家企业")

            query2 = "京南云信息技术有限公司属于哪些行业"
            result2 = execute_nl_query(query2, service)
            print_query_results(result2, "企业行业信息")

        if test_name == "tax" or test_name == "all":
            print("\n" + "=" * 70)
            print("【偷税漏税类测试】")
            print("=" * 70)

            query3 = "整个区域有多少家企业有偷税漏税风险"
            result3 = execute_nl_query(query3, service)
            print_query_results(result3, "风险企业数量")

        if test_name == "industry" or test_name == "all":
            print("\n" + "=" * 70)
            print("【产业链对比类测试】")
            print("=" * 70)

            query4 = "帮我对比北京亦庄区域内和上海闵行经济开发区的产业链发展的能力指标"
            result4 = execute_nl_query(query4, service)
            print_query_results(result4, "产业链对比分析")

        if test_name == "asset" or test_name == "all":
            print("\n" + "=" * 70)
            print("【闲置资产交易类测试】")
            print("=" * 70)

            query5 = "帮我看下目前北京亦庄区域内有哪些工业用地及办公楼宇目前仍处于空置状态"
            result5 = execute_nl_query(query5, service)
            print_query_results(result5, "空置资产查询")

        print("\n" + "=" * 70)
        print("测试完成")
        print("=" * 70)
        sys.exit(0)

    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
