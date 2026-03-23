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
        "调用search_knowledge，再调用data_query，最后回答用户问题。"
    )