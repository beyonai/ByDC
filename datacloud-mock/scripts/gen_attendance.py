# -*- coding: utf-8 -*-
"""生成 2025-01-01 至 2026-03-03 全员考勤数据，含部分员工考勤异常。"""

import csv
import os
import random
from datetime import datetime, timedelta

BASE = os.path.join(os.path.dirname(__file__), "..", "mock-resource", "data", "crm_demo")
COMMON_USERS = os.path.join(BASE, "common", "po_users.csv")
ATTENDANCE_PATH = os.path.join(BASE, "modules", "attendance", "sales_emp_attendance.csv")

START = datetime(2025, 1, 1).date()
END = datetime(2026, 3, 3).date()

# 异常类型：(上午状态, 下午状态, 上午时间是否空, 下午时间是否空, 上午迟到, 下午早退)
ANOMALIES = [
    ("正常", "正常", False, False, False, False),
    ("缺卡", "正常", True, False, False, False),
    ("正常", "缺卡", False, True, False, False),
    ("缺卡", "缺卡", True, True, False, False),
    ("迟到", "正常", False, False, True, False),
    ("正常", "早退", False, False, False, True),
    ("迟到", "早退", False, False, True, True),
]
# 异常类型索引：0=正常, 1=上午缺卡, 2=下午缺卡, 3=全天缺卡, 4=迟到, 5=早退, 6=迟到+早退


def main():
    # 读取 common 下所有人：user_id, emp_no (user_number or user_code)
    employees = []
    with open(COMMON_USERS, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            uid = (row.get("user_id") or "").strip()
            emp_no = (row.get("user_number") or row.get("user_code") or "").strip()
            if not emp_no or not uid:
                continue
            employees.append((uid, emp_no))

    # 工作日列表 2025-01-01 ~ 2026-03-03（周一=0 至 周五=4）
    workdays = []
    d = START
    while d <= END:
        if d.weekday() < 5:
            workdays.append(d)
        d += timedelta(days=1)

    # 指定部分员工作为“有异常”的候选人（约 15%），用 emp_no 的 hash 稳定选取
    anomaly_emp_nos = set()
    n_anomaly = max(3, len(employees) // 7)
    for i, (_, emp_no) in enumerate(employees):
        if i < n_anomaly or (hash(emp_no) % 5 == 0 and len(anomaly_emp_nos) < n_anomaly + 5):
            anomaly_emp_nos.add(emp_no)

    rows = []
    rid = 1
    for uid, emp_no in employees:
        is_anomaly_emp = emp_no in anomaly_emp_nos
        for adate in workdays:
            date_str = adate.strftime("%Y-%m-%d")
            bill_year = str(adate.year)
            # 有异常员工约 6% 概率异常日，其他约 0.5%
            if is_anomaly_emp and random.random() < 0.06:
                idx = random.randint(1, len(ANOMALIES) - 1)
            else:
                idx = 0
                if not is_anomaly_emp and random.random() < 0.005:
                    idx = random.randint(1, min(3, len(ANOMALIES) - 1))

            f_st, a_st, f_empty, a_empty, f_late, a_early = ANOMALIES[idx]
            # 上午打卡时间：正常 08:25-08:55，迟到 09:05-09:45
            if f_empty:
                f_time = ""
            else:
                if f_late:
                    minute = random.randint(5, 45)
                    f_time = f"{date_str} 09:{minute:02d}:00"
                else:
                    minute = random.randint(25, 55)
                    f_time = f"{date_str} 08:{minute:02d}:00"
            # 下午打卡时间：正常 17:30-18:15，早退 16:30-17:15
            if a_empty:
                a_time = ""
            else:
                if a_early:
                    minute = random.randint(30, 75)
                    a_time = (
                        f"{date_str} 16:{minute % 60:02d}:00"
                        if minute < 60
                        else f"{date_str} 17:{(minute - 60):02d}:00"
                    )
                else:
                    minute = random.randint(30, 75)
                    a_time = (
                        f"{date_str} 17:{minute % 60:02d}:00"
                        if minute < 60
                        else f"{date_str} 18:{(minute - 60):02d}:00"
                    )
            created = f_time if f_time else (a_time if a_time else f"{date_str} 09:00:00")
            rows.append(
                {
                    "id": str(rid),
                    "user_id": uid,
                    "emp_no": emp_no,
                    "attendance_date": date_str,
                    "bill_date": bill_year,
                    "forenoon_status": f_st,
                    "afternoon_status": a_st,
                    "forenoon_time": f_time,
                    "afternoon_time": a_time,
                    "created_by": "system",
                    "created_time": created,
                    "updated_by": "",
                    "updated_time": created,
                    "is_deleted": "0",
                    "forenoon_location": "公司" if f_time else "",
                    "afternoon_location": "公司" if a_time else "",
                }
            )
            rid += 1

    fieldnames = [
        "id",
        "user_id",
        "emp_no",
        "attendance_date",
        "bill_date",
        "forenoon_status",
        "afternoon_status",
        "forenoon_time",
        "afternoon_time",
        "created_by",
        "created_time",
        "updated_by",
        "updated_time",
        "is_deleted",
        "forenoon_location",
        "afternoon_location",
    ]
    os.makedirs(os.path.dirname(ATTENDANCE_PATH), exist_ok=True)
    with open(ATTENDANCE_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    anomaly_count = sum(
        1 for r in rows if r["forenoon_status"] != "正常" or r["afternoon_status"] != "正常"
    )
    print(
        f"Wrote {len(rows)} attendance rows ({len(employees)} employees, {len(workdays)} workdays), {anomaly_count} with anomaly."
    )


if __name__ == "__main__":
    random.seed(42)
    main()
