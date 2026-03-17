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
