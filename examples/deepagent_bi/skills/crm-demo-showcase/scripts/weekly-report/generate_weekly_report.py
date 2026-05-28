"""周报生成器 — 通过模板填槽随机生成模拟周报文本。

Agent 只需调用 `python generate_weekly_report.py` 即可获得一份完整的周报文本，
内部逻辑 Agent 无感。

Usage:
    python generate_weekly_report.py                    # 默认参数
    python generate_weekly_report.py --output json      # 输出 JSON 格式
    python generate_weekly_report.py --seed 42          # 指定随机种子
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

# ============================================================
# 字段值池 — Mock 数据来源
# ============================================================

_CITIES: dict[str, list[str]] = {
    "北京": ["北京"],
    "上海": ["上海"],
    "广东": ["广州", "深圳", "东莞"],
    "浙江": ["杭州", "宁波"],
    "江苏": ["南京", "苏州"],
    "四川": ["成都"],
    "湖北": ["武汉"],
}

_INDUSTRIES: list[str] = ["金融", "制造", "医疗", "教育", "互联网", "能源", "零售", "物流"]

_SALES_USERS: list[dict[str, str]] = [
    {"code": "0027024630", "name": "黄药师"},
    {"code": "0027024631", "name": "韦小二"},
    {"code": "0027024632", "name": "张三丰"},
    {"code": "0027024633", "name": "李秋水"},
]

_ORGS: list[dict[str, str]] = [
    {"code": "231", "name": "华北-金融组"},
    {"code": "232", "name": "华东-制造组"},
    {"code": "233", "name": "华南-互联网组"},
    {"code": "234", "name": "西南-能源组"},
]

_PRODUCTS: list[dict[str, str]] = [
    {"code": "WHALE_DF", "name": "数据工厂平台"},
    {"code": "WHALE_AI", "name": "AI智能分析套件"},
    {"code": "WHALE_DG", "name": "数据治理工具"},
    {"code": "WHALE_BI", "name": "智能BI平台"},
]

_CUSTOMER_NAME_PREFIXES: list[str] = [
    "北京", "广州", "深圳", "上海", "杭州", "成都", "武汉",
]

_CUSTOMER_NAME_SUFFIXES: list[str] = [
    "国投中债资产管理有限公司",
    "华融资产管理有限公司",
    "招商银行股份有限公司",
    "平安保险集团有限公司",
    "万科企业股份有限公司",
    "腾讯科技有限公司",
    "阿里巴巴网络技术有限公司",
    "华为技术有限公司",
]

_OPPORTUNITY_NAMES: list[str] = [
    "数据工厂-项目",
    "AI智能分析-平台建设",
    "数据治理-咨询项目",
    "智能BI-平台搭建",
    "数据中台-一期项目",
]

_OPPORTUNITY_STATUSES: list[dict[str, str]] = [
    {"code": "1", "name": "线索获取"},
    {"code": "2", "name": "方案交流"},
    {"code": "3", "name": "商务谈判"},
    {"code": "4", "name": "合同签订"},
]

_DOMAINS: list[str] = ["1", "2", "3", "4"]

# ============================================================
# 数据模型
# ============================================================


@dataclass
class CustomerInfo:
    code: str
    name: str
    industry: str
    province: str
    city: str
    domain: str
    sales_code: str
    sales_name: str
    org_code: str
    org_name: str


@dataclass
class OpportunityInfo:
    code: str
    name: str
    industry: str
    domain: str
    customer_code: str
    sales_code: str
    org_code: str
    product_code: str
    status_code: str
    status_name: str
    predict_amount: str
    predict_rate: str
    plan_sign_date: str


@dataclass
class WeeklyReportData:
    visit_date: str
    customer: CustomerInfo
    opportunity: OpportunityInfo


# ============================================================
# 生成逻辑
# ============================================================


def _pick_one[T](items: list[T]) -> T:
    return random.choice(items)


def _generate_customer_code(index: int) -> str:
    return f"CUST{100001 + index:06d}"


def _generate_opportunity_code(index: int) -> str:
    return f"OPP{index:08d}"


def _pick_province_city() -> tuple[str, str]:
    province = _pick_one(list(_CITIES.keys()))
    city = _pick_one(_CITIES[province])
    return province, city


def generate_customer(index: int) -> CustomerInfo:
    sales = _pick_one(_SALES_USERS)
    org = _pick_one(_ORGS)
    province, city = _pick_province_city()
    prefix = _pick_one(_CUSTOMER_NAME_PREFIXES)
    suffix = _pick_one(_CUSTOMER_NAME_SUFFIXES)

    return CustomerInfo(
        code=_generate_customer_code(index),
        name=f"{prefix}{suffix}",
        industry=_pick_one(_INDUSTRIES),
        province=province,
        city=city,
        domain=_pick_one(_DOMAINS),
        sales_code=sales["code"],
        sales_name=sales["name"],
        org_code=org["code"],
        org_name=org["name"],
    )


def generate_opportunity(customer: CustomerInfo, index: int) -> OpportunityInfo:
    product = _pick_one(_PRODUCTS)
    status = _pick_one(_OPPORTUNITY_STATUSES)
    predict_amount = f"{random.randint(10, 80) * 10000:,.2f}"
    predict_rate = f"{random.uniform(5, 50):.2f}%"
    plan_sign_date = (date.today() + timedelta(days=random.randint(30, 180))).isoformat()

    return OpportunityInfo(
        code=_generate_opportunity_code(3000000 + index),
        name=_pick_one(_OPPORTUNITY_NAMES),
        industry=customer.industry,
        domain=customer.domain,
        customer_code=customer.code,
        sales_code=customer.sales_code,
        org_code=customer.org_code,
        product_code=product["code"],
        status_code=status["code"],
        status_name=status["name"],
        predict_amount=predict_amount,
        predict_rate=predict_rate,
        plan_sign_date=plan_sign_date,
    )


def generate_weekly_report(seed: int | None = None) -> WeeklyReportData:
    """生成一份随机周报。"""
    if seed is not None:
        random.seed(seed)

    customer = generate_customer(0)
    opportunity = generate_opportunity(customer, 0)
    today = date.today()
    last_weekday = today - timedelta(days=max(0, today.weekday() - 4))  # 上周五

    return WeeklyReportData(
        visit_date=last_weekday.strftime("%Y年%m月%d日（周%w）".replace("0", "日")
        .replace("1", "一")
        .replace("2", "二")
        .replace("3", "三")
        .replace("4", "四")
        .replace("5", "五")
        .replace("6", "六")
        .replace("7", "日")),
        customer=customer,
        opportunity=opportunity,
    )


# ============================================================
# 模板渲染
# ============================================================


def _render_report(data: WeeklyReportData) -> str:
    c = data.customer
    o = data.opportunity

    return f"""本周工作总结:
一、拜访概况
● 拜访时间：{data.visit_date}
● 拜访客户：{c.name}
● 拜访人员：{c.sales_name}（所属销售用户编码：{c.sales_code}）
● 所属组织：{c.org_name}（组织编码：{c.org_code}）
● 拜访目的：初步对接客户数据管理相关需求，挖掘业务合作机会，推进线索转化
二、客户基础信息
字段名称
具体内容
客户编码
{c.code}
客户名称
{c.name}
所属行业
{c.industry}
所属省份
{c.province}
所属城市
{c.city}
所属领域
{c.domain}
所属销售
{c.sales_name}（编码：{c.sales_code}）
所属组织
{c.org_name}（编码：{c.org_code}）

三、商机详情
本次拜访成功挖掘有效商机，具体信息如下：
字段名称
具体内容
商机编码
{o.code}
商机名称
{o.name}
所属行业
{o.industry}
所属领域
{o.domain}
所属客户编码
{o.customer_code}
所属销售用户编码
{o.sales_code}（对接人：{c.sales_name}）
所属组织编码
{o.org_code}
所属产品编码
{o.product_code}
商机状态
{o.status_code}（{o.status_name}）
预测金额
{o.predict_amount} 元
预测成功率
{o.predict_rate}
计划签约日期
{o.plan_sign_date}
其他说明
目前客户已确认初步需求方向，暂未达成签约金额共识，无签约失败原因及成功总结

四、拜访成果与后续计划
1. 拜访成果：明确客户在数据工厂建设方面的核心需求，成功录入有效线索商机，客户表达了进一步沟通的意愿，为后续方案交流奠定基础。
2. 后续行动：
    ○ 本周内完成《数据工厂解决方案》初稿编制，针对{c.industry}行业数据管理痛点优化方案细节；
    ○ 预约近期与客户进行二次沟通，开展方案交流（推进商机状态至 "2 方案交流"）；
    ○ 同步协调产品部门，准备相关产品的功能演示材料，提升客户认可度；
    ○ 持续跟进客户需求变化，更新预测成功率及相关商机信息，确保按计划推进签约进程。
备注:
-
本周完成工作:
同上
下周工作计划:
同上
需协调和帮助的:
-
图片:
-
附件:
-"""


def _to_dict(data: WeeklyReportData) -> dict[str, Any]:
    c = data.customer
    o = data.opportunity
    return {
        "visit_date": data.visit_date,
        "customer": {
            "code": c.code,
            "name": c.name,
            "industry": c.industry,
            "province": c.province,
            "city": c.city,
            "domain": c.domain,
            "sales_code": c.sales_code,
            "sales_name": c.sales_name,
            "org_code": c.org_code,
            "org_name": c.org_name,
        },
        "opportunity": {
            "code": o.code,
            "name": o.name,
            "industry": o.industry,
            "domain": o.domain,
            "customer_code": o.customer_code,
            "sales_code": o.sales_code,
            "org_code": o.org_code,
            "product_code": o.product_code,
            "status_code": o.status_code,
            "status_name": o.status_name,
            "predict_amount": o.predict_amount,
            "predict_rate": o.predict_rate,
            "plan_sign_date": o.plan_sign_date,
        },
    }


def main() -> None:
    output_format = "text"
    seed: int | None = None

    # 简单参数解析
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--output" and i + 1 < len(args):
            output_format = args[i + 1]
            i += 2
        elif args[i] == "--seed" and i + 1 < len(args):
            seed = int(args[i + 1])
            i += 2
        else:
            i += 1

    data = generate_weekly_report(seed=seed)

    if output_format == "json":
        print(json.dumps(_to_dict(data), ensure_ascii=False, indent=2))
    else:
        print(_render_report(data))


if __name__ == "__main__":
    main()
