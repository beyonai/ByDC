# -*- coding: utf-8 -*-
"""根据 sales_person_kpi_detail 合同表按周/月聚合，生成个人与组织 KPI 完成统计表。当前时间 2026-03-03。"""

import csv
import os
from datetime import datetime, timedelta
from collections import defaultdict

BASE = os.path.join(
    os.path.dirname(__file__), "..", "resource", "data", "crm_demo", "modules", "crm"
)
DETAIL_PATH = os.path.join(BASE, "sales_person_kpi_detail.csv")
USER_COMPLETION_PATH = os.path.join(BASE, "po_users_kpi_completion.csv")
ORG_COMPLETION_PATH = os.path.join(BASE, "sales_org_kpi_completion.csv")


# 金额：合同表里为元，完成表为万元
def to_wan_yuan(s):
    if s is None or (isinstance(s, str) and s.strip() == ""):
        return 0.0
    s = str(s).replace(",", "").strip()
    if not s:
        return 0.0
    try:
        return float(s) / 10000.0
    except ValueError:
        return 0.0


def week_sunday(dt):
    """该周周日日期，period_value 用 YYYY-MM-DD。"""
    # weekday(): Mon=0 .. Sun=6，周日 = 当日 + (6 - weekday) 天
    sunday = dt + timedelta(days=(6 - dt.weekday()))
    return sunday.strftime("%Y-%m-%d")


def main():
    # 个人: (emp_no, period_type, period_value) -> (contract_amount_万, soft_sell_万, count)
    person_agg = defaultdict(lambda: [0.0, 0.0, 0])
    # 组织: (org_id, period_type, period_value) -> (amount_万, soft_sell_万, count)
    org_agg = defaultdict(lambda: [0.0, 0.0, 0])

    with open(DETAIL_PATH, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("is_deleted") == "1":
                continue
            contact_date_s = (row.get("contact_date") or "").strip()
            if not contact_date_s:
                continue
            try:
                dt = datetime.strptime(contact_date_s[:10], "%Y-%m-%d")
            except ValueError:
                continue
            emp_no = (row.get("emp_no") or "").strip()
            emp_org_id = (row.get("emp_org_id") or "").strip()
            if not emp_no:
                continue

            contract_wan = to_wan_yuan(row.get("contact_scale"))
            soft_wan = to_wan_yuan(row.get("soft_sell"))

            pv_week = week_sunday(dt)
            pv_month = dt.strftime("%Y-%m")

            # 个人：周
            key_pw = (emp_no, "WEEK", pv_week)
            person_agg[key_pw][0] += contract_wan
            person_agg[key_pw][1] += soft_wan
            person_agg[key_pw][2] += 1
            # 个人：月
            key_pm = (emp_no, "MONTH", pv_month)
            person_agg[key_pm][0] += contract_wan
            person_agg[key_pm][1] += soft_wan
            person_agg[key_pm][2] += 1

            if emp_org_id:
                key_ow = (emp_org_id, "WEEK", pv_week)
                org_agg[key_ow][0] += contract_wan
                org_agg[key_ow][1] += soft_wan
                org_agg[key_ow][2] += 1
                key_om = (emp_org_id, "MONTH", pv_month)
                org_agg[key_om][0] += contract_wan
                org_agg[key_om][1] += soft_wan
                org_agg[key_om][2] += 1

    # 组织名称：从 sales_org_kpi_summary 或 common 取；此处用简表
    org_names = {
        "6978": "营销一部",
        "6982": "营销十部",
        "706": "云智能业务经营中心",
        "7468": "云业务营销部",
        "6979": "营销二部",
        "6980": "营销六部",
        "6983": "营销五部",
        "6984": "营销九部",
        "6985": "营销八部",
        "6986": "营销七部",
        "6987": "营销四部",
        "6988": "营销三部",
        "7100": "营销十四部",
        "7471": "营销十一部",
        "7472": "营销十五部",
        "7473": "营销十三部",
        "7474": "营销十二部",
    }
    now_ts = "2026-03-03 12:00:00"
    created_by = "system"

    # 写入 po_users_kpi_completion
    user_fieldnames = [
        "id",
        "emp_no",
        "user_id",
        "period_type",
        "period_value",
        "kpi_year",
        "completed_contract_amount",
        "completed_soft_sell",
        "contract_count",
        "created_by",
        "created_time",
        "updated_by",
        "updated_time",
        "is_deleted",
    ]
    person_rows = []
    for (emp_no, period_type, period_value), (contract_wan, soft_wan, cnt) in sorted(
        person_agg.items()
    ):
        year = period_value[:4] if period_value else ""
        person_rows.append(
            {
                "id": "",
                "emp_no": emp_no,
                "user_id": "",
                "period_type": period_type,
                "period_value": period_value,
                "kpi_year": year,
                "completed_contract_amount": f"{contract_wan:.2f}",
                "completed_soft_sell": f"{soft_wan:.2f}",
                "contract_count": str(cnt),
                "created_by": created_by,
                "created_time": now_ts,
                "updated_by": "",
                "updated_time": now_ts,
                "is_deleted": "0",
            }
        )
    for i, row in enumerate(person_rows, start=1):
        row["id"] = str(i)
    with open(USER_COMPLETION_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=user_fieldnames)
        w.writeheader()
        w.writerows(person_rows)
    print(f"Wrote {len(person_rows)} rows to po_users_kpi_completion.csv")

    # 写入 sales_org_kpi_completion
    org_fieldnames = [
        "id",
        "org_id",
        "org_name",
        "period_type",
        "period_value",
        "kpi_year",
        "completed_amount",
        "completed_soft_sell",
        "contract_count",
        "created_by",
        "created_time",
        "updated_by",
        "updated_time",
        "is_deleted",
    ]
    org_rows = []
    for (org_id, period_type, period_value), (amount_wan, soft_wan, cnt) in sorted(org_agg.items()):
        year = period_value[:4] if period_value else ""
        org_rows.append(
            {
                "id": "",
                "org_id": org_id,
                "org_name": org_names.get(org_id, ""),
                "period_type": period_type,
                "period_value": period_value,
                "kpi_year": year,
                "completed_amount": f"{amount_wan:.2f}",
                "completed_soft_sell": f"{soft_wan:.2f}",
                "contract_count": str(cnt),
                "created_by": created_by,
                "created_time": now_ts,
                "updated_by": "",
                "updated_time": now_ts,
                "is_deleted": "0",
            }
        )
    for i, row in enumerate(org_rows, start=1):
        row["id"] = str(i)
    with open(ORG_COMPLETION_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=org_fieldnames)
        w.writeheader()
        w.writerows(org_rows)
    print(f"Wrote {len(org_rows)} rows to sales_org_kpi_completion.csv")


if __name__ == "__main__":
    main()
