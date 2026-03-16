# -*- coding: utf-8 -*-
"""
任务1：数据修正与商机状态变更表生成
- 从 common 构建有效用户/组织集合
- 修正 CRM 表中不在 common 的用户/组织引用
- 生成 sales_bo_status_change.csv
"""

import csv
import os
from datetime import datetime

BASE = os.path.join(os.path.dirname(__file__), "..", "mock-resource", "data", "crm_demo")
COMMON = os.path.join(BASE, "common")
CRM = os.path.join(BASE, "modules", "crm")
DOC_DIR = os.path.join(CRM, "数据生成说明")


def load_common():
    """加载 common 下用户与组织，返回有效集合及默认值"""
    valid_user_numbers = set()
    user_number_to_name = {}
    valid_user_ids = set()
    with open(os.path.join(COMMON, "po_users.csv"), "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            uid = row.get("user_id", "").strip()
            unum = row.get("user_number", "").strip()
            uname = row.get("user_name", "").strip()
            if uid:
                valid_user_ids.add(uid)
            if unum:
                valid_user_numbers.add(unum)
                user_number_to_name[unum] = uname
            # user_code 也视为可用的“工号”来源
            ucode = row.get("user_code", "").strip()
            if ucode and ucode not in valid_user_numbers:
                valid_user_numbers.add(ucode)
                if ucode not in user_number_to_name and uname:
                    user_number_to_name[ucode] = uname
    valid_org_ids = set()
    with open(os.path.join(COMMON, "po_organization.csv"), "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            oid = row.get("org_id", "").strip()
            if oid:
                valid_org_ids.add(oid)
    default_emp = next(iter(valid_user_numbers), "")
    default_org = next(iter(valid_org_ids), "")
    return {
        "valid_user_numbers": valid_user_numbers,
        "valid_org_ids": valid_org_ids,
        "valid_user_ids": valid_user_ids,
        "user_number_to_name": user_number_to_name,
        "default_emp_no": default_emp,
        "default_org_id": default_org,
    }


def fix_csv_bo(path, ctx):
    """修正商机表：iwhale_cbm_emp_no, iwhale_cbm_org_id"""
    rows = []
    changes = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        for row in r:
            emp = (row.get("iwhale_cbm_emp_no") or "").strip()
            org = (row.get("iwhale_cbm_org_id") or "").strip()
            if emp and emp not in ctx["valid_user_numbers"]:
                row["iwhale_cbm_emp_no"] = ctx["default_emp_no"]
                row["iwhale_cbm_name"] = ctx["user_number_to_name"].get(
                    ctx["default_emp_no"], row.get("iwhale_cbm_name", "")
                )
                changes.append(("iwhale_cbm_emp_no", emp, ctx["default_emp_no"]))
            if org and org not in ctx["valid_org_ids"]:
                row["iwhale_cbm_org_id"] = ctx["default_org_id"]
                changes.append(("iwhale_cbm_org_id", org, ctx["default_org_id"]))
            rows.append(row)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return changes


def fix_csv_kpi_detail(path, ctx):
    """修正合同表：emp_no, emp_org_id"""
    rows = []
    changes = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        for row in r:
            emp = (row.get("emp_no") or "").strip()
            org = (row.get("emp_org_id") or "").strip()
            if emp and emp not in ctx["valid_user_numbers"]:
                row["emp_no"] = ctx["default_emp_no"]
                row["name"] = ctx["user_number_to_name"].get(
                    ctx["default_emp_no"], row.get("name", "")
                )
                changes.append(("emp_no", emp, ctx["default_emp_no"]))
            if org and org not in ctx["valid_org_ids"]:
                row["emp_org_id"] = ctx["default_org_id"]
                changes.append(("emp_org_id", org, ctx["default_org_id"]))
            rows.append(row)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return changes


def fix_csv_customer(path, ctx):
    """修正客户表：iwhale_cbm_emp_no, iwhale_cbm_org_id"""
    rows = []
    changes = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        for row in r:
            emp = (row.get("iwhale_cbm_emp_no") or "").strip()
            org = (row.get("iwhale_cbm_org_id") or "").strip()
            if emp and emp not in ctx["valid_user_numbers"]:
                row["iwhale_cbm_emp_no"] = ctx["default_emp_no"]
                row["iwhale_cbm_name"] = ctx["user_number_to_name"].get(
                    ctx["default_emp_no"], row.get("iwhale_cbm_name", "")
                )
                changes.append(("iwhale_cbm_emp_no", emp, ctx["default_emp_no"]))
            if org and org not in ctx["valid_org_ids"]:
                row["iwhale_cbm_org_id"] = ctx["default_org_id"]
                changes.append(("iwhale_cbm_org_id", org, ctx["default_org_id"]))
            rows.append(row)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return changes


def fix_csv_kpi_summary(path, ctx):
    """修正个人KPI：emp_no, emp_org_id(若有), user_id"""
    rows = []
    changes = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        for row in r:
            emp = (row.get("emp_no") or "").strip()
            org = (row.get("emp_org_id") or "").strip() if "emp_org_id" in row else ""
            if emp and emp not in ctx["valid_user_numbers"]:
                row["emp_no"] = ctx["default_emp_no"]
                changes.append(("emp_no", emp, ctx["default_emp_no"]))
            if org and org not in ctx["valid_org_ids"]:
                row["emp_org_id"] = ctx["default_org_id"]
                changes.append(("emp_org_id", org, ctx["default_org_id"]))
            rows.append(row)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return changes


def fix_csv_org_kpi_summary(path, ctx):
    """修正组织KPI：org_id"""
    rows = []
    changes = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        for row in r:
            org = (row.get("org_id") or "").strip()
            if org and org not in ctx["valid_org_ids"]:
                row["org_id"] = ctx["default_org_id"]
                oname = row.get("org_name")
                if oname:
                    row["org_name"] = "营销一部"  # 与 6978 对应，简单写
                changes.append(("org_id", org, ctx["default_org_id"]))
            rows.append(row)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return changes


def generate_bo_status_change(path_bo, path_out, ctx):
    """根据商机表生成 sales_bo_status_change.csv"""
    bos = []
    with open(path_bo, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            bos.append(row)
    out_rows = []
    for i, bo in enumerate(bos):
        bo_id = bo.get("id", "")
        opp_id = bo.get("opportunity_id", "")
        status = (bo.get("business_opportunity_process") or "进行中").strip()
        created = (bo.get("created_time") or "").strip()[:19]
        updated = (bo.get("updated_time") or "").strip()[:19]
        changed_by = (
            bo.get("updated_by") or bo.get("iwhale_cbm_emp_no") or ctx["default_emp_no"]
        ).strip()
        if not bo_id:
            continue
        # 每条商机至少 1 条：初始 -> 当前状态
        changed_time = updated if updated else created
        if not changed_time:
            changed_time = "2025-12-03 17:28:13"
        out_rows.append(
            {
                "id": str(i + 1),
                "bo_id": str(bo_id),
                "opportunity_id": opp_id or "",
                "status_before": "",
                "status_after": status,
                "change_remark": "初始录入/状态同步",
                "changed_by": changed_by,
                "changed_time": changed_time,
                "created_by": changed_by,
                "created_time": changed_time,
                "updated_by": "",
                "updated_time": changed_time,
                "is_deleted": "0",
            }
        )
    fieldnames = [
        "id",
        "bo_id",
        "opportunity_id",
        "status_before",
        "status_after",
        "change_remark",
        "changed_by",
        "changed_time",
        "created_by",
        "created_time",
        "updated_by",
        "updated_time",
        "is_deleted",
    ]
    os.makedirs(os.path.dirname(path_out), exist_ok=True)
    with open(path_out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    return len(out_rows)


def main():
    ctx = load_common()
    all_changes = {}
    # 1) 商机
    p = os.path.join(CRM, "sales_business_opportunity.csv")
    if os.path.isfile(p):
        all_changes["sales_business_opportunity"] = fix_csv_bo(p, ctx)
    # 2) 合同
    p = os.path.join(CRM, "sales_person_kpi_detail.csv")
    if os.path.isfile(p):
        all_changes["sales_person_kpi_detail"] = fix_csv_kpi_detail(p, ctx)
    # 3) 客户
    p = os.path.join(CRM, "sales_customer.csv")
    if os.path.isfile(p):
        all_changes["sales_customer"] = fix_csv_customer(p, ctx)
    # 4) 个人KPI
    p = os.path.join(CRM, "sales_person_kpi_summary.csv")
    if os.path.isfile(p):
        all_changes["sales_person_kpi_summary"] = fix_csv_kpi_summary(p, ctx)
    # 5) 组织KPI
    p = os.path.join(CRM, "sales_org_kpi_summary.csv")
    if os.path.isfile(p):
        all_changes["sales_org_kpi_summary"] = fix_csv_org_kpi_summary(p, ctx)
    # 6) 生成商机状态变更表
    path_bo = os.path.join(CRM, "sales_business_opportunity.csv")
    path_status = os.path.join(CRM, "sales_bo_status_change.csv")
    n_status = generate_bo_status_change(path_bo, path_status, ctx)
    # 7) 写说明文档
    os.makedirs(DOC_DIR, exist_ok=True)
    doc = []
    doc.append("# 01-数据修正与商机状态变更")
    doc.append("")
    doc.append("## 1. 修正说明")
    doc.append(
        "- 基准：common 下 po_users（user_id、user_number/user_code）、po_organization（org_id）为有效集合。"
    )
    doc.append(
        "- 将 CRM 表中引用到的、不在上述集合中的用户工号替换为第一个有效 user_number；组织 ID 替换为第一个有效 org_id。"
    )
    doc.append("")
    doc.append("## 2. 各表修正情况")
    for table, changes in all_changes.items():
        doc.append(f"### {table}")
        if not changes:
            doc.append("- 无需修正。")
        else:
            seen = set()
            for field, old_v, new_v in changes:
                k = (field, old_v, new_v)
                if k in seen:
                    continue
                seen.add(k)
                doc.append(f"- `{field}`: 将不在 common 中的值 `{old_v}` 修正为 `{new_v}`。")
        doc.append("")
    doc.append("## 3. 商机状态变更表生成规则")
    doc.append(
        "- 依据：修正后的 sales_business_opportunity 的 id、opportunity_id、business_opportunity_process、created_time/updated_time。"
    )
    doc.append(
        "- 每条商机生成 1 条状态变更记录：status_after = 当前商机状态，status_before 为空，change_remark 为「初始录入/状态同步」。"
    )
    doc.append(f"- 输出：sales_bo_status_change.csv，共 {n_status} 条。")
    with open(os.path.join(DOC_DIR, "01-数据修正与商机状态变更.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(doc))
    print("Done: fixes applied, sales_bo_status_change.csv and 01 doc written.")


if __name__ == "__main__":
    main()
