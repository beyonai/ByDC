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
