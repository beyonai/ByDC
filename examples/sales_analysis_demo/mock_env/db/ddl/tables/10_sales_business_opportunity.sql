-- crm_demo.sales_business_opportunity definition

-- Drop table

-- DROP TABLE crm_demo.sales_business_opportunity;

CREATE TABLE crm_demo.sales_business_opportunity (
	id bigserial NOT NULL, -- 主键ID
	bo_name varchar(64) NOT NULL, -- 商机名称
	belong_depart varchar(32) NULL DEFAULT NULL::character varying, -- 所属营销部
	customer_name varchar(64) NOT NULL, -- 客户名称
	order_date date NULL, -- 落单时间
	bid_opening_time date NULL, -- 主标开标时间
	iwhale_cbm_emp_no varchar(32) NOT NULL, -- 商机负责人工号
	iwhale_cbm_name varchar(32) NOT NULL, -- 商机负责人名称
	iwhale_cbm_org_id varchar(32) NULL DEFAULT NULL::character varying, -- 商机负责人组织
	software_income_time date NULL, -- 软收计入时间
	it_investment_scale varchar(32) NOT NULL, -- 客户IT投资规模（万元）
	win_bid int2 NOT NULL, -- 是否中标：1为中标，0为未中标
	iwhale_sc_emp_no varchar(32) NULL DEFAULT NULL::character varying, -- 支撑sc工号
	iwhale_sc_name varchar(32) NULL DEFAULT NULL::character varying, -- 浩鲸sc名称
	diliver_content varchar(32) NULL DEFAULT NULL::character varying, -- 合同交付内容
	"type" varchar(32) NULL DEFAULT NULL::character varying, -- 商机类型
	performance_type varchar(32) NULL DEFAULT NULL::character varying, -- 业绩类型
	early_diliver int2 NULL, -- 是否提前交付：1为提前，0为未提前
	business_opportunity_process varchar(32) NOT NULL, -- 商机状态
	contract_scale varchar(32) NULL DEFAULT NULL::character varying, -- 合同额（万）
	software_sale_scale varchar(32) NULL DEFAULT NULL::character varying, -- 软销规模（万元）
	software_income_scale varchar(32) NULL DEFAULT NULL::character varying, -- 软收计入规模（万元）
	order_rate varchar(32) NOT NULL, -- 落单几率
	business_opportunity_desc varchar(32) NULL DEFAULT NULL::character varying, -- 商机具体进展描述
	submit_person varchar(32) NULL DEFAULT NULL::character varying, -- 提交人
	submit_organization varchar(32) NULL DEFAULT NULL::character varying, -- 提交组织
	is_ali_integrated bool NULL DEFAULT false, -- 是否集成阿里产品: 0-否, 1-是
	opportunity_nature varchar(32) NULL DEFAULT NULL::character varying, -- 商机性质：新增
	opportunity_source varchar(100) NULL DEFAULT NULL::character varying, -- 商机来源
	source_description varchar(255) NULL DEFAULT NULL::character varying, -- 来源说明
	opportunity_stage varchar(100) NULL DEFAULT NULL::character varying, -- 商机进展：初步接触
	opportunity_id varchar(50) NULL DEFAULT NULL::character varying, -- 商机ID, 业务唯一标识
	instance_id varchar(50) NULL DEFAULT NULL::character varying, -- 实例ID
	instance_title varchar(200) NULL DEFAULT NULL::character varying, -- 实例标题
	prepay_expected_date date NULL, -- 预测回款时间【预付款】
	prepay_expected_amount varchar(20) NULL DEFAULT NULL::character varying, -- 预测回款金额【预付款】(万元)
	customer_tax_id varchar(128) NULL DEFAULT NULL::character varying, -- 客户纳税号
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_business_opportunity_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_business_opportunity IS '商机表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_business_opportunity.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.bo_name IS '商机名称';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.belong_depart IS '所属营销部';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.customer_name IS '客户名称';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.order_date IS '落单时间';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.bid_opening_time IS '主标开标时间';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.iwhale_cbm_emp_no IS '商机负责人工号';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.iwhale_cbm_name IS '商机负责人名称';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.iwhale_cbm_org_id IS '商机负责人组织';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.software_income_time IS '软收计入时间';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.it_investment_scale IS '客户IT投资规模（万元）';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.win_bid IS '是否中标：1为中标，0为未中标';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.iwhale_sc_emp_no IS '支撑sc工号';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.iwhale_sc_name IS '浩鲸sc名称';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.diliver_content IS '合同交付内容';
COMMENT ON COLUMN crm_demo.sales_business_opportunity."type" IS '商机类型';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.performance_type IS '业绩类型';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.early_diliver IS '是否提前交付：1为提前，0为未提前';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.business_opportunity_process IS '商机状态';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.contract_scale IS '合同额（万）';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.software_sale_scale IS '软销规模（万元）';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.software_income_scale IS '软收计入规模（万元）';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.order_rate IS '落单几率';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.business_opportunity_desc IS '商机具体进展描述';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.submit_person IS '提交人';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.submit_organization IS '提交组织';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.is_ali_integrated IS '是否集成阿里产品: 0-否, 1-是';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.opportunity_nature IS '商机性质：新增';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.opportunity_source IS '商机来源';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.source_description IS '来源说明';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.opportunity_stage IS '商机进展：初步接触';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.opportunity_id IS '商机ID, 业务唯一标识';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.instance_id IS '实例ID';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.instance_title IS '实例标题';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.prepay_expected_date IS '预测回款时间【预付款】';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.prepay_expected_amount IS '预测回款金额【预付款】(万元)';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.customer_tax_id IS '客户纳税号';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_business_opportunity.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
