-- crm_demo.sales_person_kpi_summary definition

-- Drop table

-- DROP TABLE crm_demo.sales_person_kpi_summary;

CREATE TABLE crm_demo.sales_person_kpi_summary (
	id bigserial NOT NULL, -- 主键ID
	user_id varchar(32) NULL DEFAULT NULL::character varying, -- 责任人ID
	emp_no varchar(32) NOT NULL, -- 责任人工号
	"name" varchar(255) NULL DEFAULT NULL::character varying, -- 责任人姓名
	emp_org_id varchar(32) NULL DEFAULT NULL::character varying, -- 责任人组织
	contact_no varchar(255) NOT NULL, -- 合同号
	contact_name varchar(255) NOT NULL, -- 合同名称
	contact_date date NOT NULL, -- 合同时间
	soft_sell varchar(255) NULL DEFAULT NULL::character varying, -- 软销金额
	contact_scale varchar(255) NOT NULL, -- 合同金额
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	kpi_year int4 NULL,
	kpi_sum varchar(10) NULL,
	CONSTRAINT sales_person_kpi_summary_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_person_kpi_summary IS '合同表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.user_id IS '责任人ID';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.emp_no IS '责任人工号';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary."name" IS '责任人姓名';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.emp_org_id IS '责任人组织';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.contact_no IS '合同号';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.contact_name IS '合同名称';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.contact_date IS '合同时间';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.soft_sell IS '软销金额';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.contact_scale IS '合同金额';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_person_kpi_summary.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
