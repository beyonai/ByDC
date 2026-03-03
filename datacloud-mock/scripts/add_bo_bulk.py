# -*- coding: utf-8 -*-
"""追加云智能过去1年商机，使 sales_business_opportunity 中 iwhale_cbm_org_id=6978/706 的商机 >= 100 条"""
import csv
import os
from datetime import datetime, timedelta
import random

BASE = os.path.join(os.path.dirname(__file__), "..", "mock-resource", "data", "crm_demo", "modules", "crm")
PATH = os.path.join(BASE, "sales_business_opportunity.csv")

# 有效负责人（common 中存在的工号与姓名）
OWNERS = [
    ("0027026216", "田刚"),
    ("0027031626", "高炎彬"),
    ("0027029940", "章钱满"),
    ("0027029790", "张恋"),
    ("0027012156", "姜斌"),
    ("0027011799", "杜成鹏"),
]
# 真实客户名（参考现有商机与客户表）
CUSTOMERS = [
    "南京大数据集团", "中国科技大学", "阿里", "南京新工数字科技有限责任公司", "长沙百旺",
    "国防科大电子对抗学院", "徐州大数据局", "广陵新城管委会", "随州水务", "中核汇能",
    "江苏卫生健康学校", "南通大数据局", "江苏满运软件", "江苏省审计厅", "三只松鼠",
    "蚂蚁集团", "常州排水集团", "国防科大", "苏州纪委", "南京中铁信息工程公司",
    "江苏交通控股有限公司", "正大天晴药业集团股份有限公司", "江苏金恒信息科技股份有限公司",
    "江苏省数据集团", "湖南强智科技发展有限公司", "中信泰富特钢集团有限公司", "扬州市大数据集团",
    "无锡职业技术大学", "江苏红网技术股份有限公司", "北京华晟经世信息技术股份有限公司",
    "扬州工业职业技术学院", "南京市江宁区城市数字治理中心", "南京医科大学附属口腔医院",
    "江苏苏豪集团", "南京新工投资集团", "南京医药集团", "南京钢铁股份有限公司",
    "南京公共交通集团有限公司", "南京金斯瑞生物", "合肥工业大学", "中国科学技术大学",
    "常州大数据局", "安庆职业技术学院", "江苏开放大学", "台积电（南京）半导体",
    "南京钢铁集团", "天合光能", "数字江西科技有限公司", "湖南生物机电职业技术学院",
    "泰州大数据局", "盐城城运中心", "江苏银行", "中国移动江苏公司", "南京莱斯信息",
    "江苏电力", "浙江大数据局", "安徽交控集团", "山东政务云", "河南教育厅",
]
CONTENT = ["数据中台", "智慧园区", "BI大屏", "知识库", "智能体", "云迁移", "运维服务", "人力外包", "定制开发", "数据治理"]
STAGES = ["产生采购需求，内部准备", "方案设计，评估与比较", "投标竞争，购买和实施", "立项评估中"]

def main():
    with open(PATH, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames
        rows = list(r)
    next_id = max(int(r["id"]) for r in rows) + 1
    need = 100 - len(rows)
    if need <= 0:
        print("Already >= 100 rows, no add.")
        return
    # 多补几条
    add_n = need + 5
    start = datetime(2025, 3, 1)
    end = datetime(2026, 2, 28)
    for i in range(add_n):
        dt = start + timedelta(days=random.randint(0, (end - start).days))
        date_str = dt.strftime("%Y-%m-%d")
        dt_created = dt.strftime("%Y-%m-%d %H:%M:%S")
        emp_no, emp_name = random.choice(OWNERS)
        org_id = random.choice(["6978", "6978", "6978", "706"])
        depart = "营销一部" if org_id == "6978" else "云智能业务经营中心"
        customer = random.choice(CUSTOMERS)
        content = random.choice(CONTENT)
        # 参考现有格式：南京大数据集团AI中台咨询服务、长沙百旺数据中台
        if random.random() < 0.5:
            bo_name = f"{customer}{content}项目"
        else:
            bo_name = f"{content}-{customer}"
        scale = str(random.randint(5, 200))
        opp_id = dt.strftime("%Y%m%d%H%M%S") + f"{i:03d}"
        stage = random.choice(STAGES)
        row = {
            "id": str(next_id + i),
            "bo_name": bo_name,
            "belong_depart": depart,
            "customer_name": customer,
            "order_date": date_str,
            "bid_opening_time": date_str,
            "iwhale_cbm_emp_no": emp_no,
            "iwhale_cbm_name": emp_name,
            "iwhale_cbm_org_id": org_id,
            "software_income_time": date_str,
            "it_investment_scale": "",
            "win_bid": "0",
            "iwhale_sc_emp_no": "",
            "iwhale_sc_name": "",
            "diliver_content": content,
            "type": random.choice(["直签", "分包"]),
            "performance_type": "科技",
            "early_diliver": str(random.randint(0, 1)),
            "business_opportunity_process": "进行中",
            "contract_scale": scale,
            "software_sale_scale": scale,
            "software_income_scale": scale,
            "order_rate": "0.8",
            "business_opportunity_desc": "",
            "submit_person": emp_name,
            "submit_organization": depart,
            "is_ali_integrated": "0",
            "opportunity_nature": "新增",
            "opportunity_source": "",
            "source_description": "",
            "opportunity_stage": stage,
            "opportunity_id": opp_id,
            "instance_id": "",
            "instance_title": "",
            "prepay_expected_date": "",
            "prepay_expected_amount": "",
            "customer_tax_id": "",
            "created_by": emp_no,
            "created_time": dt_created,
            "updated_by": emp_no,
            "updated_time": dt_created,
            "is_deleted": "0",
        }
        rows.append(row)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    # 同步追加 sales_bo_status_change
    path_status = os.path.join(BASE, "sales_bo_status_change.csv")
    status_rows = []
    with open(path_status, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        status_fieldnames = r.fieldnames
        status_rows = list(r)
    next_sid = max(int(r["id"]) for r in status_rows) + 1
    for i in range(add_n):
        bo_row = rows[-(add_n - i)]
        bid = bo_row["id"]
        opp_id = bo_row["opportunity_id"]
        status = bo_row["business_opportunity_process"]
        changed = bo_row["updated_time"]
        by_ = bo_row["updated_by"]
        status_rows.append({
            "id": str(next_sid + i),
            "bo_id": bid,
            "opportunity_id": opp_id,
            "status_before": "",
            "status_after": status,
            "change_remark": "初始录入/状态同步",
            "changed_by": by_,
            "changed_time": changed,
            "created_by": by_,
            "created_time": changed,
            "updated_by": "",
            "updated_time": changed,
            "is_deleted": "0",
        })
    with open(path_status, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=status_fieldnames)
        w.writeheader()
        w.writerows(status_rows)
    print(f"Added {add_n} rows to sales_business_opportunity (total {len(rows)}), synced sales_bo_status_change.")

if __name__ == "__main__":
    main()
