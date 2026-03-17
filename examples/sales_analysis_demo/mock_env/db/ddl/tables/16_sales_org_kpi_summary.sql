-- crm_demo.sales_org_kpi_summary definition

-- Drop table

-- DROP TABLE crm_demo.sales_org_kpi_summary;

CREATE TABLE crm_demo.sales_org_kpi_summary (
	id bigserial NOT NULL, -- 主键ID
	org_id varchar(32) NOT NULL, -- 组织ID
	org_name varchar(255) NULL DEFAULT NULL::character varying, -- 组织名称
	kpi_year int4 NOT NULL, -- kpi年度
	kpi_sum varchar(255) NOT NULL, -- KPI目标
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_org_kpi_summary_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_org_kpi_summary IS '组织KPI目标表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.org_name IS '组织名称';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.kpi_year IS 'kpi年度';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.kpi_sum IS 'KPI目标';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_org_kpi_summary.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
