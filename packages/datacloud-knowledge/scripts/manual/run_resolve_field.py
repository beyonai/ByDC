from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.provider import resolve_field_aliases


def main():
    field_terms = []
    scope_code = 'scene_crm_comprehensive_analysis'
    user_id = 'adminvip'
    value_terms = ['华为技术有限公司', '中国工商银行股份有限公司北京分行', '江苏省大数据管理中心']
    language = 'zh_CN'
    result = resolve_field_aliases(
        terms=field_terms,
        scope_code=scope_code,
        user_id=user_id,
        resolve_values=bool(value_terms),
        value_terms=value_terms,
        language=language,
    )
    unresolved = list(result.unresolved) + list(result.ambiguous.keys())
    return result.resolved, unresolved

if __name__ == '__main__':
    print(main())
