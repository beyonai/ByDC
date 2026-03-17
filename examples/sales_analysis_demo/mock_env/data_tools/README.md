# data_tools

This directory stores offline resource build scripts for `mock_env`.

## Scope

- Generate or repair CRM mock CSV data.
- Generate or normalize ontology JSON resources.
- Keep resources under `resource/` consistent.

## Typical order

1. `fix_and_generate_crm_data.py`
2. `gen_attendance.py`
3. `gen_kpi_completion.py`
4. `convert_functions_to_post.py`
5. `fix_camel_and_params.py`
6. `generate_ontology.py`
