from datacloud_knowledge.intent.clarification.cartesian import expand_condition_cartesian
from datacloud_knowledge.intent.clarification.models import (
    ConditionTermMapping,
    ConfirmedCondition,
)
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    condition = ConfirmedCondition(
        original_sentence="亩产效益后30%的地块",
        term_mappings=[
            ConditionTermMapping(
                original_term="亩产效益",
                start=0,
                end=4,
                confirmed=None,
                candidates=["物理网格亩产效益", "管理网格亩产效益"],
            ),
            ConditionTermMapping(
                original_term="地块",
                start=9,
                end=11,
                confirmed=None,
                candidates=["物理网格", "管理网格"],
            ),
        ],
    )

    for sentence in expand_condition_cartesian(condition):
        print(sentence)


if __name__ == "__main__":
    main()
