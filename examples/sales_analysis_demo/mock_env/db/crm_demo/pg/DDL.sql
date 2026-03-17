-- crm_demo.po_organization definition

-- Drop table

-- DROP TABLE crm_demo.po_organization;

CREATE TABLE crm_demo.po_organization (
	org_id int8 NOT NULL, -- 组织ID
	org_code varchar(250) NOT NULL, -- 组织编码
	org_name varchar(100) NOT NULL, -- 组织名称
	org_type varchar(4) NOT NULL DEFAULT '0'::character varying, -- 组织类型(0：内部组织；1：外部组织)
	parent_org_id int8 NOT NULL, -- 父标识，-1代表顶层
	org_level int4 NULL, -- 组织层级(0: 顶级； 1-9往后递增)
	org_index int4 NULL, -- 同层级内排序字段
	create_date timestamp NULL, -- 创建时间
	update_date timestamp NULL, -- 更新时间
	path_code varchar(500) NULL, -- 组织路径
	org_desc varchar(1000) NULL, -- 组织描述
	CONSTRAINT po_organization_pkey PRIMARY KEY (org_id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.po_organization IS '组织信息表';

-- Column comments

COMMENT ON COLUMN crm_demo.po_organization.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.po_organization.org_code IS '组织编码';
COMMENT ON COLUMN crm_demo.po_organization.org_name IS '组织名称';
COMMENT ON COLUMN crm_demo.po_organization.org_type IS '组织类型(0：内部组织；1：外部组织)';
COMMENT ON COLUMN crm_demo.po_organization.parent_org_id IS '父标识，-1代表顶层';
COMMENT ON COLUMN crm_demo.po_organization.org_level IS '组织层级(0: 顶级； 1-9往后递增)';
COMMENT ON COLUMN crm_demo.po_organization.org_index IS '同层级内排序字段';
COMMENT ON COLUMN crm_demo.po_organization.create_date IS '创建时间';
COMMENT ON COLUMN crm_demo.po_organization.update_date IS '更新时间';
COMMENT ON COLUMN crm_demo.po_organization.path_code IS '组织路径';
COMMENT ON COLUMN crm_demo.po_organization.org_desc IS '组织描述';


-- crm_demo.po_users definition

-- Drop table

-- DROP TABLE crm_demo.po_users;

CREATE TABLE crm_demo.po_users (
	user_id int8 NOT NULL, -- 用户唯一标识
	user_name varchar(255) NOT NULL, -- 用户名称
	email varchar(255) NULL, -- 用户邮箱
	phone varchar(255) NULL, -- 用户电话
	user_code varchar(255) NOT NULL, -- 用户登录标识
	pwd varchar(255) NOT NULL, -- 用户密码(md5加密)
	address text NULL, -- 用户地址
	remark varchar(255) NULL, -- 用户备注
	user_eff_date timestamp NULL, -- 预留
	user_exp_date timestamp NULL, -- 用户过期日期
	create_date timestamp NOT NULL, -- 记录创建日期
	update_date timestamp NULL, -- 记录更新日期
	state bpchar(1) NOT NULL DEFAULT 'A'::bpchar, -- 用户状态：A-正常;X-禁用
	state_time timestamp NULL,
	is_locked bpchar(1) NOT NULL, -- 是否锁定，Y-锁定，N-没有锁定，null表示'N'
	last_login_date timestamp NULL, -- 用户最后一次登录时间
	security_question_id int8 NULL, -- 用户忘记密码找回密码问题
	security_answer varchar(120) NULL, -- 用户忘记密码安全提示问题
	thumbnail_uri varchar(400) NULL, -- 用户头像URL地址
	ext_attr varchar(1000) NULL, -- 用户扩展信息
	assistant_id int8 NULL, -- 一个员工对应一个超级助手
	user_number varchar(30) NULL, -- 工号
	station_id int8 NULL, -- 所属驻地
	register_type int2 NULL, -- 注册类型 1-手机号注册
	apple_user_id varchar(255) NULL DEFAULT NULL::character varying, -- 苹果用户ID，用于苹果登录关联
	CONSTRAINT po_users_pkey PRIMARY KEY (user_id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.po_users IS '用户表';

-- Column comments

COMMENT ON COLUMN crm_demo.po_users.user_id IS '用户唯一标识';
COMMENT ON COLUMN crm_demo.po_users.user_name IS '用户名称';
COMMENT ON COLUMN crm_demo.po_users.email IS '用户邮箱';
COMMENT ON COLUMN crm_demo.po_users.phone IS '用户电话';
COMMENT ON COLUMN crm_demo.po_users.user_code IS '用户登录标识';
COMMENT ON COLUMN crm_demo.po_users.pwd IS '用户密码(md5加密)';
COMMENT ON COLUMN crm_demo.po_users.address IS '用户地址';
COMMENT ON COLUMN crm_demo.po_users.remark IS '用户备注';
COMMENT ON COLUMN crm_demo.po_users.user_eff_date IS '预留';
COMMENT ON COLUMN crm_demo.po_users.user_exp_date IS '用户过期日期';
COMMENT ON COLUMN crm_demo.po_users.create_date IS '记录创建日期';
COMMENT ON COLUMN crm_demo.po_users.update_date IS '记录更新日期';
COMMENT ON COLUMN crm_demo.po_users.state IS '用户状态：A-正常;X-禁用';
COMMENT ON COLUMN crm_demo.po_users.is_locked IS '是否锁定，Y-锁定，N-没有锁定，null表示''N''';
COMMENT ON COLUMN crm_demo.po_users.last_login_date IS '用户最后一次登录时间';
COMMENT ON COLUMN crm_demo.po_users.security_question_id IS '用户忘记密码找回密码问题';
COMMENT ON COLUMN crm_demo.po_users.security_answer IS '用户忘记密码安全提示问题';
COMMENT ON COLUMN crm_demo.po_users.thumbnail_uri IS '用户头像URL地址';
COMMENT ON COLUMN crm_demo.po_users.ext_attr IS '用户扩展信息';
COMMENT ON COLUMN crm_demo.po_users.assistant_id IS '一个员工对应一个超级助手';
COMMENT ON COLUMN crm_demo.po_users.user_number IS '工号';
COMMENT ON COLUMN crm_demo.po_users.station_id IS '所属驻地';
COMMENT ON COLUMN crm_demo.po_users.register_type IS '注册类型 1-手机号注册';
COMMENT ON COLUMN crm_demo.po_users.apple_user_id IS '苹果用户ID，用于苹果登录关联';


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


-- crm_demo.po_users_organization definition

-- Drop table

-- DROP TABLE crm_demo.po_users_organization;

CREATE TABLE crm_demo.po_users_organization (
	id int8 NOT NULL, -- 主键
	user_id int8 NOT NULL,
	org_id int8 NOT NULL, -- 组织ID
	position_id int8 NULL, -- 岗位ID
	user_type varchar(50) NULL, -- 用户类型
	CONSTRAINT po_users_organization_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
CREATE INDEX idx_po_users_organization_org_id ON crm_demo.po_users_organization USING btree (org_id) TABLESPACE pg_default;
CREATE INDEX idx_po_users_organization_user_id ON crm_demo.po_users_organization USING btree (user_id) TABLESPACE pg_default;
COMMENT ON TABLE crm_demo.po_users_organization IS '用户组织关联表';

-- Column comments

COMMENT ON COLUMN crm_demo.po_users_organization.id IS '主键';
COMMENT ON COLUMN crm_demo.po_users_organization.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.po_users_organization.position_id IS '岗位ID';
COMMENT ON COLUMN crm_demo.po_users_organization.user_type IS '用户类型';


-- crm_demo.sales_bo_status_change definition

-- Drop table

-- DROP TABLE crm_demo.sales_bo_status_change;

CREATE TABLE crm_demo.sales_bo_status_change (
	id bigserial NOT NULL, -- 主键ID
	bo_id int8 NOT NULL, -- 商机主键ID，关联 sales_business_opportunity.id
	opportunity_id varchar(50) NULL DEFAULT NULL::character varying, -- 商机业务唯一标识，关联 sales_business_opportunity.id
	status_before varchar(64) NULL DEFAULT NULL::character varying, -- 变更前状态
	status_after varchar(64) NOT NULL, -- 变更后状态
	change_remark varchar(512) NULL DEFAULT NULL::character varying, -- 变更说明
	changed_by varchar(100) NOT NULL, -- 变更人
	changed_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 变更时间
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_bo_status_change_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_bo_status_change IS '商机状态变更表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_bo_status_change.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.bo_id IS '商机主键ID，关联 sales_business_opportunity.id';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.opportunity_id IS '商机业务唯一标识，关联 sales_business_opportunity.id';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.status_before IS '变更前状态';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.status_after IS '变更后状态';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.change_remark IS '变更说明';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.changed_by IS '变更人';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.changed_time IS '变更时间';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.is_deleted IS '逻辑删除标识(0:正常,1:删除)';


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


-- crm_demo.sales_emp_attendance definition

-- Drop table

-- DROP TABLE crm_demo.sales_emp_attendance;

CREATE TABLE crm_demo.sales_emp_attendance (
	id bigserial NOT NULL, -- 主键ID
	user_id varchar(32) NULL DEFAULT NULL::character varying, -- 用户id
	emp_no varchar(32) NOT NULL, -- 工号
	attendance_date date NOT NULL, -- 考勤日
	bill_date int4 NOT NULL, -- 账期
	forenoon_status varchar(32) NULL DEFAULT NULL::character varying, -- 上午打卡结果
	afternoon_status varchar(32) NULL DEFAULT NULL::character varying, -- 下午打卡结果
	forenoon_time timestamp NULL, -- 上午实际打卡时间
	afternoon_time timestamp NULL, -- 下午实际打卡时间
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	forenoon_location varchar(1024) NULL DEFAULT NULL::character varying, -- 上午打卡地点
	afternoon_location varchar(1024) NULL DEFAULT NULL::character varying, -- 下午打卡地点
	CONSTRAINT sales_emp_attendance_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_emp_attendance IS '员工考勤表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_emp_attendance.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.user_id IS '用户id';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.emp_no IS '工号';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.attendance_date IS '考勤日';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.bill_date IS '账期';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.forenoon_status IS '上午打卡结果';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.afternoon_status IS '下午打卡结果';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.forenoon_time IS '上午实际打卡时间';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.afternoon_time IS '下午实际打卡时间';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.forenoon_location IS '上午打卡地点';
COMMENT ON COLUMN crm_demo.sales_emp_attendance.afternoon_location IS '下午打卡地点';


-- crm_demo.sales_expense_report definition

-- Drop table

-- DROP TABLE crm_demo.sales_expense_report;

CREATE TABLE crm_demo.sales_expense_report (
	id bigserial NOT NULL, -- 主键ID
	applicant_emp_no varchar(32) NOT NULL, -- 申请人工号
	applicant_name varchar(64) NOT NULL, -- 申请人姓名
	applicant_org_id varchar(32) NOT NULL, -- 申请组织ID
	expense_amount numeric(10, 2) NOT NULL, -- 申请金额（元）
	expense_desc varchar(512) NULL DEFAULT NULL::character varying, -- 申请说明
	related_bo_id varchar(50) NULL DEFAULT NULL::character varying, -- 关联商机ID
	related_customer_id varchar(128) NULL DEFAULT NULL::character varying, -- 关联客户ID
	apply_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 申请时间
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_expense_report_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_expense_report IS '费用报备表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_expense_report.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.applicant_emp_no IS '申请人工号';
COMMENT ON COLUMN crm_demo.sales_expense_report.applicant_name IS '申请人姓名';
COMMENT ON COLUMN crm_demo.sales_expense_report.applicant_org_id IS '申请组织ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.expense_amount IS '申请金额（元）';
COMMENT ON COLUMN crm_demo.sales_expense_report.expense_desc IS '申请说明';
COMMENT ON COLUMN crm_demo.sales_expense_report.related_bo_id IS '关联商机ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.related_customer_id IS '关联客户ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.apply_time IS '申请时间';
COMMENT ON COLUMN crm_demo.sales_expense_report.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_expense_report.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_expense_report.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_expense_report.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_expense_report.is_deleted IS '逻辑删除标识(0:正常,1:删除)';


-- crm_demo.sales_meeting_note definition

-- Drop table

-- DROP TABLE crm_demo.sales_meeting_note;

CREATE TABLE crm_demo.sales_meeting_note (
	id bigserial NOT NULL, -- 主键ID
	meeting_title varchar(255) NOT NULL, -- 会议纪要标题
	meeting_content text NULL, -- 会议内容
	start_time timestamp NOT NULL, -- 发起时间
	related_bo_id varchar(50) NULL DEFAULT NULL::character varying, -- 关联商机ID
	related_customer_id varchar(128) NULL DEFAULT NULL::character varying, -- 关联客户ID
	participant_emp_nos jsonb NULL, -- 会议参与人员工号（多个）
	created_by varchar(100) NOT NULL, -- 会议创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_meeting_note_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_meeting_note IS '会议纪要表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_meeting_note.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_meeting_note.meeting_title IS '会议纪要标题';
COMMENT ON COLUMN crm_demo.sales_meeting_note.meeting_content IS '会议内容';
COMMENT ON COLUMN crm_demo.sales_meeting_note.start_time IS '发起时间';
COMMENT ON COLUMN crm_demo.sales_meeting_note.related_bo_id IS '关联商机ID';
COMMENT ON COLUMN crm_demo.sales_meeting_note.related_customer_id IS '关联客户ID';
COMMENT ON COLUMN crm_demo.sales_meeting_note.participant_emp_nos IS '会议参与人员工号（多个）';
COMMENT ON COLUMN crm_demo.sales_meeting_note.created_by IS '会议创建人';
COMMENT ON COLUMN crm_demo.sales_meeting_note.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_meeting_note.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_meeting_note.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_meeting_note.is_deleted IS '逻辑删除标识(0:正常,1:删除)';


-- crm_demo.sales_org_kpi_completion definition

-- Drop table

-- DROP TABLE crm_demo.sales_org_kpi_completion;

CREATE TABLE crm_demo.sales_org_kpi_completion (
	id bigserial NOT NULL, -- 主键ID
	org_id varchar(32) NOT NULL, -- 组织ID
	org_name varchar(255) NULL DEFAULT NULL::character varying, -- 组织名称
	period_type varchar(16) NOT NULL, -- 账期类型：WEEK-周，MONTH-月
	period_value varchar(32) NOT NULL, -- 账期值：周如2025-W01，月如2025-01
	kpi_year varchar(32) NULL DEFAULT NULL::character varying, -- 对应KPI年度
	completed_amount numeric(20, 2) NULL DEFAULT NULL::numeric, -- 该账期组织汇总完成金额（万元）
	completed_soft_sell numeric(20, 2) NULL DEFAULT NULL::numeric, -- 该账期组织汇总软销金额（万元）
	contract_count int4 NULL, -- 该账期组织签约合同笔数
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_org_kpi_completion_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_org_kpi_completion IS '组织KPI完成统计表（按周/月）';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.org_name IS '组织名称';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.period_type IS '账期类型：WEEK-周，MONTH-月';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.period_value IS '账期值：周如2025-W01，月如2025-01';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.kpi_year IS '对应KPI年度';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.completed_amount IS '该账期组织汇总完成金额（万元）';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.completed_soft_sell IS '该账期组织汇总软销金额（万元）';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.contract_count IS '该账期组织签约合同笔数';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_org_kpi_completion.is_deleted IS '逻辑删除标识(0:正常,1:删除)';


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


-- crm_demo.todo_item_handlers definition

-- Drop table

-- DROP TABLE crm_demo.todo_item_handlers;

CREATE TABLE crm_demo.todo_item_handlers (
	id int8 NOT NULL, -- 关联ID（自增）
	todo_item_id int8 NOT NULL, -- 待办ID
	org_id int8 NOT NULL, -- 组织ID
	handler_id varchar(64) NOT NULL, -- 处理人ID
	assigned_at timestamptz(6) NULL DEFAULT pg_systimestamp(), -- 分配时间
	handled_at timestamptz(6) NULL, -- 处理时间
	handle_comment text NULL, -- 处理意见/备注
	progress_percentage int4 NULL DEFAULT 0 -- 该处理人的处理进度0-100，100时可变为待审核
)
WITH (
	orientation=row,
	compression=no
);
CREATE INDEX idx_todo_handlers_composite ON crm_demo.todo_item_handlers USING btree (handler_id, todo_item_id) TABLESPACE pg_default;
CREATE INDEX idx_todo_handlers_handled_at ON crm_demo.todo_item_handlers USING btree (handled_at DESC) TABLESPACE pg_default WHERE (handled_at IS NOT NULL);
CREATE INDEX idx_todo_handlers_handler_id ON crm_demo.todo_item_handlers USING btree (handler_id) TABLESPACE pg_default;
CREATE INDEX idx_todo_handlers_org_id ON crm_demo.todo_item_handlers USING btree (org_id) TABLESPACE pg_default;
CREATE INDEX idx_todo_handlers_todo_item_id ON crm_demo.todo_item_handlers USING btree (todo_item_id) TABLESPACE pg_default;
COMMENT ON TABLE crm_demo.todo_item_handlers IS '待办处理人关联表';

-- Column comments

COMMENT ON COLUMN crm_demo.todo_item_handlers.id IS '关联ID（自增）';
COMMENT ON COLUMN crm_demo.todo_item_handlers.todo_item_id IS '待办ID';
COMMENT ON COLUMN crm_demo.todo_item_handlers.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.todo_item_handlers.handler_id IS '处理人ID';
COMMENT ON COLUMN crm_demo.todo_item_handlers.assigned_at IS '分配时间';
COMMENT ON COLUMN crm_demo.todo_item_handlers.handled_at IS '处理时间';
COMMENT ON COLUMN crm_demo.todo_item_handlers.handle_comment IS '处理意见/备注';
COMMENT ON COLUMN crm_demo.todo_item_handlers.progress_percentage IS '该处理人的处理进度0-100，100时可变为待审核';


-- crm_demo.todo_items definition

-- Drop table

-- DROP TABLE crm_demo.todo_items;

CREATE TABLE crm_demo.todo_items (
	id int8 NOT NULL, -- 待办ID（自增）
	title varchar(512) NOT NULL, -- 待办标题
	todo_content text NULL, -- 待办内容
	deadline_at timestamptz(6) NULL, -- 截止时间
	todo_priority varchar(64) NULL DEFAULT 'Normal'::character varying, -- 优先级：Low(低)、Normal(普通)、High(高)、Urgent(紧急)
	todo_status varchar(64) NULL DEFAULT 'Pending'::character varying, -- 状态：Pending(待处理)、Approving(待审批)、Rejected(已审批拒绝)、Completed(已完成)、Cancelled(已取消)
	created_by varchar(64) NOT NULL, -- 创建人ID
	promoter varchar(64) NOT NULL, -- 发起人ID
	org_id int8 NOT NULL, -- 组织ID
	handler_id varchar(64) NULL, -- 处理人ID（主处理人）
	created_at timestamptz(6) NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_at timestamptz(6) NULL DEFAULT pg_systimestamp(), -- 更新时间
	completed_at timestamptz(6) NULL, -- 完成时间
	cancelled_at timestamptz(6) NULL, -- 取消时间
	cancelled_reason text NULL, -- 取消原因
	approved_at timestamptz(6) NULL, -- 审批通过时间
	rejected_at timestamptz(6) NULL, -- 审批拒绝时间
	approval_comment text NULL, -- 审批意见
	urgency_level varchar(64) NULL,
	remark varchar(2048) NULL, -- 备注
	meeting_note_id int8 NULL, -- 关联的会议纪要id
	return_reason varchar(5000) NULL, -- 退回理由
	returned_at timestamptz(6) NULL -- 退回时间
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.todo_items IS '待办事项主表';

-- Column comments

COMMENT ON COLUMN crm_demo.todo_items.id IS '待办ID（自增）';
COMMENT ON COLUMN crm_demo.todo_items.title IS '待办标题';
COMMENT ON COLUMN crm_demo.todo_items.todo_content IS '待办内容';
COMMENT ON COLUMN crm_demo.todo_items.deadline_at IS '截止时间';
COMMENT ON COLUMN crm_demo.todo_items.todo_priority IS '优先级：Low(低)、Normal(普通)、High(高)、Urgent(紧急)';
COMMENT ON COLUMN crm_demo.todo_items.todo_status IS '状态：Pending(待处理)、Approving(待审批)、Rejected(已审批拒绝)、Completed(已完成)、Cancelled(已取消)';
COMMENT ON COLUMN crm_demo.todo_items.created_by IS '创建人ID';
COMMENT ON COLUMN crm_demo.todo_items.promoter IS '发起人ID';
COMMENT ON COLUMN crm_demo.todo_items.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.todo_items.handler_id IS '处理人ID（主处理人）';
COMMENT ON COLUMN crm_demo.todo_items.created_at IS '创建时间';
COMMENT ON COLUMN crm_demo.todo_items.updated_at IS '更新时间';
COMMENT ON COLUMN crm_demo.todo_items.completed_at IS '完成时间';
COMMENT ON COLUMN crm_demo.todo_items.cancelled_at IS '取消时间';
COMMENT ON COLUMN crm_demo.todo_items.cancelled_reason IS '取消原因';
COMMENT ON COLUMN crm_demo.todo_items.approved_at IS '审批通过时间';
COMMENT ON COLUMN crm_demo.todo_items.rejected_at IS '审批拒绝时间';
COMMENT ON COLUMN crm_demo.todo_items.approval_comment IS '审批意见';
COMMENT ON COLUMN crm_demo.todo_items.remark IS '备注';
COMMENT ON COLUMN crm_demo.todo_items.meeting_note_id IS '关联的会议纪要id';
COMMENT ON COLUMN crm_demo.todo_items.return_reason IS '退回理由';
COMMENT ON COLUMN crm_demo.todo_items.returned_at IS '退回时间';