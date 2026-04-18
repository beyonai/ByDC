from dotenv import load_dotenv

load_dotenv()

import json

from datacloud_knowledge.intent.clarification.api import format_clarification_query


def main() -> None:
    query = "查询前3个营收最低的网格"
    structured_query = {
        "select": ["企业营收", "企业利润"],
        "filters": [{"field": "行业", "op": "eq", "value": "制造业"}],
        "order_by": [{"field": "营收", "direction": "DESC"}],
        "complex_conditions": ["亩产效益后30%的地块"],
    }
    form = json.dumps(
        {
            "paradigmList": [
                {
                    "paradigmId": "1",
                    "paradigmName": "查询值",
                    "paradigmResult": [
                        {"kid": 1, "choiceKeyword": "企业总营收（万元）"},
                        {"kid": 2, "choiceKeyword": "企业总利润（万元）"},
                    ],
                },
                {
                    "paradigmId": "2",
                    "paradigmName": "分组条件",
                    "paradigmResult": [],
                },
                {
                    "paradigmId": "3",
                    "paradigmName": "过滤条件",
                    "paradigmResult": [
                        {
                            "kid": 1,
                            "ktype": "complexCondition",
                            "keyword": "亩产效益后30%的地块",
                            "choiceKeyword": "物理网格亩产效益后30%的地块",
                        }
                    ],
                },
                {
                    "paradigmId": "4",
                    "paradigmName": "排序目标",
                    "paradigmResult": [{"kid": 1, "choiceKeyword": "企业总营收（万元）"}],
                },
                {"paradigmId": "5", "paradigmName": "统计函数", "paradigmResult": []},
            ]
        },
        ensure_ascii=False,
    )
    knowledge = json.dumps(
        {
            "path_mapping": {"1": "select.0", "2": "select.1", "o1": "order_by.0.field"},
            "confirmed_conditions": [],
            "mode": "query",
        },
        ensure_ascii=False,
    )

    resolved = format_clarification_query(
        query=query,
        structured_query=structured_query,
        form=form,
        knowledge=knowledge,
    )
    print(json.dumps(resolved, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
