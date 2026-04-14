import os
from typing import Any

from pathlib import Path
from pprint import pp

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


from datacloud_analysis.tools.knowledge import (
    disambiguate_candidates,
    search_all_candidates,
    update_term_scores,
)


def print_debug_section(title: str, payload: object) -> None:
    print(f"\n{'=' * 12} {title} {'=' * 12}")
    pp(payload, sort_dicts=False, width=100)


async def main():
    env_path = Path(__file__).resolve().parents[3] / "backend" / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)

    model = os.getenv("DATACLOUD_LLM_MODEL", "openai:kimi-k2.5")
    if not model.startswith("openai:"):
        model = f"openai:{model}"

    llm = init_chat_model(
        model=model,
        api_key=os.getenv("DATACLOUD_LLM_API_KEY"),
        base_url=os.getenv("DATACLOUD_LLM_API_BASE"),
    )

    last_user_msg = "请查询【企业综合分析表】 100条数据。"
    concept_terms = ["经开区", "企业", "综合分析表"]
    user_id = None
    candidates_map = await search_all_candidates(concept_terms, user_id=user_id, top_k=100)
    confirmed_terms, ambiguous_terms = await disambiguate_candidates(
        candidates_map,
        str(last_user_msg),
        llm=llm,
    )
    from datacloud_knowledge.intent import build_shortest_path_tree_with_session
    for item in confirmed_terms:
        tree_result = build_shortest_path_tree_with_session(
            target_term_id=item["term_id"],
            source_term_type_codes=["object"],
            max_depth=4,
        )
        print(tree_result.tree_text)
    print(confirmed_terms)

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
