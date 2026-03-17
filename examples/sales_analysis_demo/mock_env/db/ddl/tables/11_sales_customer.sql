-- crm_demo.sales_customer definition

-- Drop table

-- DROP TABLE crm_demo.sales_customer;

CREATE TABLE crm_demo.sales_customer (
	id bigserial NOT NULL, -- 主键ID
	customer_name varchar(64) NOT NULL, -- 客户名称
	belong_depart varchar(32) NOT NULL, -- 所属营销部
	"type" varchar(32) NOT NULL, -- 客户类别：新增
	build_content varchar(32) NULL DEFAULT NULL::character varying, -- 建设类容
	iwhale_cbm_emp_no varchar(32) NOT NULL, -- 客户维护人工号
	iwhale_cbm_name varchar(32) NOT NULL, -- 客户维护人名称
	iwhale_cbm_org_id varchar(32) NULL DEFAULT NULL::character varying, -- 客户维护人组织
	belong_industry varchar(32) NULL DEFAULT NULL::character varying, -- 所属行业
	it_investment_scale varchar(32) NULL DEFAULT NULL::character varying, -- 客户IT投资规模（万元）
	data_year int4 NOT NULL, -- 数据年份，如：2024
	software_sale_scale varchar(32) NULL DEFAULT NULL::character varying, -- 软销规模（万元）
	next_year_predict_scale varchar(32) NULL DEFAULT NULL::character varying, -- 明年预计软销规模
	contract_scale varchar(32) NULL DEFAULT NULL::character varying, -- 合同额（万元）
	process varchar(32) NULL DEFAULT NULL::character varying, -- 目前进展
	main_business varchar(255) NULL DEFAULT NULL::character varying, -- 主营业务
	submit_person varchar(32) NULL DEFAULT NULL::character varying, -- 提交人
	submit_organization varchar(32) NULL DEFAULT NULL::character varying, -- 提交组织
	business_opportunity_process varchar(32) NULL DEFAULT NULL::character varying, -- 商机进展
	customer_tax_id varchar(128) NULL DEFAULT NULL::character varying, -- 客户纳税号
	instance_id varchar(128) NULL DEFAULT NULL::character varying, -- 实例ID
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_customer_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_customer IS '客户表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_customer.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_customer.customer_name IS '客户名称';
COMMENT ON COLUMN crm_demo.sales_customer.belong_depart IS '所属营销部';
COMMENT ON COLUMN crm_demo.sales_customer."type" IS '客户类别：新增';
COMMENT ON COLUMN crm_demo.sales_customer.build_content IS '建设类容';
COMMENT ON COLUMN crm_demo.sales_customer.iwhale_cbm_emp_no IS '客户维护人工号';
COMMENT ON COLUMN crm_demo.sales_customer.iwhale_cbm_name IS '客户维护人名称';
COMMENT ON COLUMN crm_demo.sales_customer.iwhale_cbm_org_id IS '客户维护人组织';
COMMENT ON COLUMN crm_demo.sales_customer.belong_industry IS '所属行业';
COMMENT ON COLUMN crm_demo.sales_customer.it_investment_scale IS '客户IT投资规模（万元）';
COMMENT ON COLUMN crm_demo.sales_customer.data_year IS '数据年份，如：2024';
COMMENT ON COLUMN crm_demo.sales_customer.software_sale_scale IS '软销规模（万元）';
COMMENT ON COLUMN crm_demo.sales_customer.next_year_predict_scale IS '明年预计软销规模';
COMMENT ON COLUMN crm_demo.sales_customer.contract_scale IS '合同额（万元）';
COMMENT ON COLUMN crm_demo.sales_customer.process IS '目前进展';
COMMENT ON COLUMN crm_demo.sales_customer.main_business IS '主营业务';
COMMENT ON COLUMN crm_demo.sales_customer.submit_person IS '提交人';
COMMENT ON COLUMN crm_demo.sales_customer.submit_organization IS '提交组织';
COMMENT ON COLUMN crm_demo.sales_customer.business_opportunity_process IS '商机进展';
COMMENT ON COLUMN crm_demo.sales_customer.customer_tax_id IS '客户纳税号';
COMMENT ON COLUMN crm_demo.sales_customer.instance_id IS '实例ID';
COMMENT ON COLUMN crm_demo.sales_customer.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_customer.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_customer.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_customer.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_customer.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
