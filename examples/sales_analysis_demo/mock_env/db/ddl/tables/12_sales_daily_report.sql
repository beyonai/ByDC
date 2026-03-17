-- crm_demo.sales_daily_report definition

-- Drop table

-- DROP TABLE crm_demo.sales_daily_report;

CREATE TABLE crm_demo.sales_daily_report (
	id bigserial NOT NULL, -- 主键ID
	report_date date NOT NULL, -- 日报日期
	report_title varchar(128) NOT NULL, -- 日报标题
	report_content jsonb NULL, -- 日报内容(JSON格式，灵活存储)
	report_status int2 NOT NULL DEFAULT 0, -- 日报状态(0: 未反馈, 1:已反馈)
	belong_emp_no varchar(32) NOT NULL, -- 员工工号
	belong_user_name varchar(32) NOT NULL, -- 员工姓名
	belong_emp_org_id varchar(32) NULL DEFAULT NULL::character varying, -- 归属用户所在的组织ID
	created_by varchar(32) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(32) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_daily_report_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_daily_report IS '日报记录表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_daily_report.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_daily_report.report_date IS '日报日期';
COMMENT ON COLUMN crm_demo.sales_daily_report.report_title IS '日报标题';
COMMENT ON COLUMN crm_demo.sales_daily_report.report_content IS '日报内容(JSON格式，灵活存储)';
COMMENT ON COLUMN crm_demo.sales_daily_report.report_status IS '日报状态(0: 未反馈, 1:已反馈)';
COMMENT ON COLUMN crm_demo.sales_daily_report.belong_emp_no IS '员工工号';
COMMENT ON COLUMN crm_demo.sales_daily_report.belong_user_name IS '员工姓名';
COMMENT ON COLUMN crm_demo.sales_daily_report.belong_emp_org_id IS '归属用户所在的组织ID';
COMMENT ON COLUMN crm_demo.sales_daily_report.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_daily_report.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_daily_report.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_daily_report.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_daily_report.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
