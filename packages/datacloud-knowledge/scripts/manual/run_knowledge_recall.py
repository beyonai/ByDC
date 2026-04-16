from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.paradigm_builder import build_paradigm_resolution_state
from datacloud_knowledge.intent.llm_confirm import _format_recall_context

def main():

    query = "查询前3个营收最低的网格"
    structured_query={'查询目标': ['营收', '网格营收', '营业收入', '营业额', '收入'], '分组条件': ['网格', '网格名称', '网格编号', '网格ID'], '过滤条件': {}, '排序目标': ['营收'], '统计函数': []}

    state = build_paradigm_resolution_state(
        original_question=query,
        structured_query=structured_query,
    )

    items = getattr(state, "items", [])
    dim_hints = getattr(state, "dimension_value_hints", None)
    recall_context = _format_recall_context(items, dimension_value_hints=dim_hints)

    print(recall_context)

if __name__ == '__main__':
    main()