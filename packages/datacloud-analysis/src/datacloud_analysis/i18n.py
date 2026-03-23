from typing import List


SUPPORTED_LOCALES = ["en_US", "zh_CN"]


def get_supported_locales() -> List[str]:
    return SUPPORTED_LOCALES.copy()


def get_system_prompt(locale: str) -> str:
    if locale == "en_US":
        return (
            "You are a data analysis assistant for DataCloud. "
            "Help users analyze data, answer questions, and provide insights."
        )
    return (
        "你是一个数据分析助手，帮助用户分析数据、回答问题并提供洞察。"
    )