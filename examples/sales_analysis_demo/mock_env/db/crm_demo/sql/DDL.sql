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
CREATE INDEX idx_po_users_organization_org_id ON crm_demo.po_users_organization (org_id);
CREATE INDEX idx_po_users_organization_user_id ON crm_demo.po_users_organization (user_id);
COMMENT ON TABLE crm_demo.po_users_organization IS '用户组织关联表';

-- Column comments

COMMENT ON COLUMN crm_demo.po_users_organization.id IS '主键';
COMMENT ON COLUMN crm_demo.po_users_organization.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.po_users_organization.position_id IS '岗位ID';
COMMENT ON COLUMN crm_demo.po_users_organization.user_type IS '用户类型';


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
	CONSTRAINT po_users_pkey PRIMARY KEY (user_id),
	CONSTRAINT uk_users_apple_user_id UNIQUE (apple_user_id)
)
WITH (
	orientation=row,
	compression=no
);
CREATE INDEX idx_assistant_id ON crm_demo.po_users (assistant_id);
CREATE INDEX idx_state_create_date_desc ON crm_demo.po_users (state,create_date DESC);
CREATE INDEX idx_users_apple_user_id ON crm_demo.po_users (apple_user_id);
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

-- "crm_demo".todo_item_handlers definition

-- Drop table

-- DROP TABLE "crm_demo".todo_item_handlers;

CREATE TABLE "crm_demo".todo_item_handlers (
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
COMMENT ON TABLE "crm_demo".todo_item_handlers IS '待办处理人关联表';

-- Column comments

COMMENT ON COLUMN "crm_demo".todo_item_handlers.id IS '关联ID（自增）';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.todo_item_id IS '待办ID';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.org_id IS '组织ID';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.handler_id IS '处理人ID';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.assigned_at IS '分配时间';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.handled_at IS '处理时间';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.handle_comment IS '处理意见/备注';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.progress_percentage IS '该处理人的处理进度0-100，100时可变为待审核';


-- "crm_demo".todo_items definition

-- Drop table

-- DROP TABLE "crm_demo".todo_items;

CREATE TABLE "crm_demo".todo_items (
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
COMMENT ON TABLE "crm_demo".todo_items IS '待办事项主表';

-- Column comments

COMMENT ON COLUMN "crm_demo".todo_items.id IS '待办ID（自增）';
COMMENT ON COLUMN "crm_demo".todo_items.title IS '待办标题';
COMMENT ON COLUMN "crm_demo".todo_items.todo_content IS '待办内容';
COMMENT ON COLUMN "crm_demo".todo_items.deadline_at IS '截止时间';
COMMENT ON COLUMN "crm_demo".todo_items.todo_priority IS '优先级：Low(低)、Normal(普通)、High(高)、Urgent(紧急)';
COMMENT ON COLUMN "crm_demo".todo_items.todo_status IS '状态：Pending(待处理)、Approving(待审批)、Rejected(已审批拒绝)、Completed(已完成)、Cancelled(已取消)';
COMMENT ON COLUMN "crm_demo".todo_items.created_by IS '创建人ID';
COMMENT ON COLUMN "crm_demo".todo_items.promoter IS '发起人ID';
COMMENT ON COLUMN "crm_demo".todo_items.org_id IS '组织ID';
COMMENT ON COLUMN "crm_demo".todo_items.handler_id IS '处理人ID（主处理人）';
COMMENT ON COLUMN "crm_demo".todo_items.created_at IS '创建时间';
COMMENT ON COLUMN "crm_demo".todo_items.updated_at IS '更新时间';
COMMENT ON COLUMN "crm_demo".todo_items.completed_at IS '完成时间';
COMMENT ON COLUMN "crm_demo".todo_items.cancelled_at IS '取消时间';
COMMENT ON COLUMN "crm_demo".todo_items.cancelled_reason IS '取消原因';
COMMENT ON COLUMN "crm_demo".todo_items.approved_at IS '审批通过时间';
COMMENT ON COLUMN "crm_demo".todo_items.rejected_at IS '审批拒绝时间';
COMMENT ON COLUMN "crm_demo".todo_items.approval_comment IS '审批意见';
COMMENT ON COLUMN "crm_demo".todo_items.remark IS '备注';
COMMENT ON COLUMN "crm_demo".todo_items.meeting_note_id IS '关联的会议纪要id';
COMMENT ON COLUMN "crm_demo".todo_items.return_reason IS '退回理由';
COMMENT ON COLUMN "crm_demo".todo_items.returned_at IS '退回时间';


CREATE TABLE sales_expense_report (
  id BIGSERIAL PRIMARY KEY,
  applicant_emp_no VARCHAR(32) NOT NULL,
  applicant_name VARCHAR(64) NOT NULL,
  applicant_org_id VARCHAR(32) NOT NULL,
  expense_amount NUMERIC(10,2) NOT NULL,
  expense_desc VARCHAR(512) DEFAULT NULL,
  related_bo_id VARCHAR(50) DEFAULT NULL,
  related_customer_id VARCHAR(128) DEFAULT NULL,
  apply_time TIMESTAMP NOT NULL DEFAULT NULL,
  created_by VARCHAR(100) NOT NULL,
  created_time TIMESTAMP NOT NULL DEFAULT NULL,
  updated_by VARCHAR(100) DEFAULT NULL,
  updated_time TIMESTAMP DEFAULT NULL,
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  -- 新增审核相关字段（行内仅定义字段，注释单独写）
  approval_status VARCHAR(20) DEFAULT 'PENDING',
  approval_comment VARCHAR(1024) DEFAULT NULL,
  approved_at TIMESTAMP DEFAULT NULL
);

-- 表注释
COMMENT ON TABLE sales_expense_report IS '费用报备表';

-- 字段注释（逐个声明）
COMMENT ON COLUMN sales_expense_report.id IS '主键ID';
COMMENT ON COLUMN sales_expense_report.applicant_emp_no IS '申请人工号';
COMMENT ON COLUMN sales_expense_report.applicant_name IS '申请人姓名';
COMMENT ON COLUMN sales_expense_report.applicant_org_id IS '申请组织ID';
COMMENT ON COLUMN sales_expense_report.expense_amount IS '申请金额（元）';
COMMENT ON COLUMN sales_expense_report.expense_desc IS '申请说明';
COMMENT ON COLUMN sales_expense_report.related_bo_id IS '关联商机ID';
COMMENT ON COLUMN sales_expense_report.related_customer_id IS '关联客户ID';
COMMENT ON COLUMN sales_expense_report.apply_time IS '申请时间';
COMMENT ON COLUMN sales_expense_report.created_by IS '创建人';
COMMENT ON COLUMN sales_expense_report.created_time IS '创建时间';
COMMENT ON COLUMN sales_expense_report.updated_by IS '更新人';
COMMENT ON COLUMN sales_expense_report.updated_time IS '更新时间';
COMMENT ON COLUMN sales_expense_report.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
-- 新增字段的注释
COMMENT ON COLUMN sales_expense_report.approval_status IS '审核状态（PENDING:待审核,APPROVED:已通过,REJECTED:已驳回）';
COMMENT ON COLUMN sales_expense_report.approval_comment IS '审核意见';
COMMENT ON COLUMN sales_expense_report.approved_at IS '审批时间';