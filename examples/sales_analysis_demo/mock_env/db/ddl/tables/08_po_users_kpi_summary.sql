-- crm_demo.po_users_kpi_summary definition

-- Drop table

-- DROP TABLE crm_demo.po_users_kpi_summary;

CREATE TABLE crm_demo.po_users_kpi_summary (
	id bigserial NOT NULL, -- 主键ID
	user_id varchar(32) NULL DEFAULT NULL::character varying, -- 责任人id
	emp_no varchar(32) NOT NULL, -- 责任人工号
	kpi_year varchar(32) NULL DEFAULT NULL::character varying, -- kpi年度
	kpi_sum varchar(255) NULL DEFAULT NULL::character varying, -- KPI目标金额
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT po_users_kpi_summary_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.po_users_kpi_summary IS '个人kpi表';

-- Column comments

COMMENT ON COLUMN crm_demo.po_users_kpi_summary.id IS '主键ID';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.user_id IS '责任人id';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.emp_no IS '责任人工号';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.kpi_year IS 'kpi年度';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.kpi_sum IS 'KPI目标金额';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.po_users_kpi_summary.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
