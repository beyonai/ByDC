from __future__ import annotations
import logging
import os
from typing import Any, Literal
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)
IntentLabel = Literal["react", "chitchat", "clarify"]

_CHITCHAT_TOKENS = frozenset({
    "hi", "hello", "hey", "thanks", "thank you", "你好", "您好", "喂",
    "哈喽", "在吗", "谢谢", "早上好", "中午好", "下午好", "晚上好",
})

class IntentClassifier:
    _llm_quick_disabled: bool = False

    def _is_chitchat(self, text: str) -> bool:
        normalized = " ".join(text.lower().split())
        return normalized in _CHITCHAT_TOKENS

    async def classify(self, user_query: str, state: Any) -> IntentLabel:
        max_len_env = os.getenv("DATACLOUD_INTENT_MAX_LEN", "").strip()
        max_len = int(max_len_env) if max_len_env.isdigit() else 4000
        trimmed_query = user_query
        if len(user_query) > max_len:
            trimmed_query = user_query[:max_len]
            logger.info(
                "[intent_classifier] trim user_query len=%d -> %d",
                len(user_query),
                len(trimmed_query),
            )
        if os.environ.get("DATACLOUD_TRACE_USER_QUERY", "").strip().lower() in ("1", "true", "yes"):
            logger.info(
                "[user_query_trace] IntentClassifier.classify input_len=%d preview=%r",
                len(trimmed_query),
                trimmed_query[:400] + ("..." if len(trimmed_query) > 400 else ""),
            )
        if self._is_chitchat(trimmed_query):
            return "chitchat"
        # 尝试用 llm_quick 分类，失败则 fallback react
        try:
            api_base = os.getenv("DATACLOUD_LLM_QUICK_API_BASE", "")
            api_key = os.getenv("DATACLOUD_LLM_QUICK_API_KEY", "")
            model = os.getenv("DATACLOUD_LLM_QUICK_MODEL", "")
            if self._llm_quick_disabled or not (api_base and api_key and model):
                return "react"
            llm = init_chat_model(
                model=model,
                model_provider="openai",
                api_key=api_key,
                base_url=api_base,
                temperature=0.0,
            )
            prompt = (
                f"请判断用户问题的意图类型，只输出以下之一：react / chitchat / clarify\n"
                f"用户问题：{trimmed_query}"
            )
            resp = await llm.ainvoke([
                SystemMessage(content="你是意图分类专家，只输出 react 或 chitchat 或 clarify，不输出其他内容。"),
                HumanMessage(content=prompt),
            ])
            label = str(resp.content).strip().lower()
            if label in ("react", "chitchat", "clarify"):
                return label  # type: ignore[return-value]
            return "react"
        except Exception as exc:
            msg = str(exc)
            if "invalid_model_name" in msg or "InvalidParameter" in msg:
                self._llm_quick_disabled = True
                logger.warning("IntentClassifier: disable quick model due to error: %s", msg)
            logger.warning("IntentClassifier.classify failed, fallback react: %s", exc)
            return "react"
