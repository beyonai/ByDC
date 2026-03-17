-- crm_demo.po_users_kpi_completion definition

-- Drop table

-- DROP TABLE crm_demo.po_users_kpi_completion;

CREATE TABLE crm_demo.po_users_kpi_completion (
	id bigserial NOT NULL, -- 主键ID
	emp_no varchar(32) NOT NULL, -- 责任人工号
	user_id varchar(32) NULL DEFAULT NULL::character varying, -- 责任人用户ID
	period_type varchar(16) NOT NULL, -- 账期类型：WEEK-周，MONTH-月
	period_value varchar(32) NOT NULL, -- 账期值：周如2025-W01，月如2025-01
	kpi_year varchar(32) NULL DEFAULT NULL::character varying, -- 对应KPI年度
	completed_contract_amount numeric(20, 2) NULL DEFAULT NULL::numeric, -- 该账期已完成合同金额（万元）
	completed_soft_sell numeric(20, 2) NULL DEFAULT NULL::numeric, -- 该账期已完成软销金额（万元）
	contract_count int4 NULL, -- 该账期签约合同笔数
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT po_users_kpi_completion_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.po_users_kpi_completion IS '个人KPI完成统计表（按周/月）';

-- Column comments

COMMENT ON COLUMN crm_demo.po_users_kpi_completion.id IS '主键ID';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.emp_no IS '责任人工号';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.user_id IS '责任人用户ID';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.period_type IS '账期类型：WEEK-周，MONTH-月';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.period_value IS '账期值：周如2025-W01，月如2025-01';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.kpi_year IS '对应KPI年度';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.completed_contract_amount IS '该账期已完成合同金额（万元）';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.completed_soft_sell IS '该账期已完成软销金额（万元）';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.contract_count IS '该账期签约合同笔数';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.po_users_kpi_completion.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
