-- ============================================================================
-- 数据库初始化脚本 - SQL 版本
-- ============================================================================
-- 执行方式：
-- psql -h 127.0.0.1 -p 54321 -U kb_admin -d real_estate_kb -f init_db.sql
-- ============================================================================

-- ============================================================================
-- 1. 组织/机构表
-- ============================================================================
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    org_code VARCHAR(50) UNIQUE NOT NULL,           -- 机构编码
    org_name VARCHAR(200) NOT NULL,                 -- 机构名称
    parent_id INTEGER REFERENCES organizations(id), -- 上级机构
    level INTEGER DEFAULT 1,                        -- 层级
    sort_order INTEGER DEFAULT 0,                   -- 排序
    status VARCHAR(20) DEFAULT 'active',            -- 状态: active/inactive
    description TEXT,                               -- 描述
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 组织表索引
CREATE INDEX IF NOT EXISTS idx_org_parent ON organizations(parent_id);
CREATE INDEX IF NOT EXISTS idx_org_status ON organizations(status);

-- 插入默认组织
INSERT INTO organizations (org_code, org_name, description)
VALUES ('default', '默认组织', '系统默认组织')
ON CONFLICT (org_code) DO NOTHING;


-- ============================================================================
-- 2. 用户表
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,           -- 用户名
    password_hash VARCHAR(255) NOT NULL,            -- 密码哈希
    real_name VARCHAR(100),                         -- 真实姓名
    email VARCHAR(100),                             -- 邮箱
    phone VARCHAR(20),                              -- 手机号
    avatar VARCHAR(500),                            -- 头像URL
    org_id INTEGER REFERENCES organizations(id),    -- 所属组织
    status VARCHAR(20) DEFAULT 'active',            -- 状态: active/inactive/locked
    last_login_at TIMESTAMP,                        -- 最后登录时间
    last_login_ip VARCHAR(50),                      -- 最后登录IP
    login_fail_count INTEGER DEFAULT 0,             -- 连续登录失败次数
    password_changed_at TIMESTAMP,                  -- 密码修改时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,                             -- 创建人
    remark TEXT                                     -- 备注
);

-- 用户表索引
CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 用户表注释
COMMENT ON TABLE users IS '用户表';
COMMENT ON COLUMN users.username IS '用户名，唯一';
COMMENT ON COLUMN users.password_hash IS '密码哈希，使用bcrypt';
COMMENT ON COLUMN users.status IS '状态：active-正常，inactive-禁用，locked-锁定';


-- ============================================================================
-- 3. 用户角色关联表
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_code VARCHAR(50) NOT NULL,                 -- 角色编码: super_admin/admin/reviewer/editor/viewer
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role_code)
);

-- 用户角色索引
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_code);

-- 用户角色注释
COMMENT ON TABLE user_roles IS '用户角色关联表';
COMMENT ON COLUMN user_roles.role_code IS '角色编码：super_admin/admin/reviewer/editor/viewer';


-- ============================================================================
-- 4. 用户Token表
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,               -- Token哈希
    token_type VARCHAR(20) DEFAULT 'access',        -- Token类型: access/refresh
    device_info VARCHAR(200),                       -- 设备信息
    ip_address VARCHAR(50),                         -- IP地址
    expires_at TIMESTAMP NOT NULL,                  -- 过期时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP                          -- 最后使用时间
);

-- Token表索引
CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_user_tokens_hash ON user_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_user_tokens_expires ON user_tokens(expires_at);

-- 清理过期Token的函数
CREATE OR REPLACE FUNCTION clean_expired_tokens()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_tokens WHERE expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- 5. 业务表 - documents
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(64) UNIQUE NOT NULL,
    filename VARCHAR(255),
    file_path VARCHAR(500),
    file_type VARCHAR(20),
    report_type VARCHAR(50),
    address TEXT,
    area FLOAT,
    case_count INT DEFAULT 0,
    org_id VARCHAR(64),
    create_by VARCHAR(64),
    update_by VARCHAR(64),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- documents 表索引
CREATE INDEX IF NOT EXISTS idx_documents_report_type ON documents(report_type);
CREATE INDEX IF NOT EXISTS idx_documents_org_id ON documents(org_id);
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN(metadata);


-- ============================================================================
-- 6. 业务表 - cases
-- ============================================================================
CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(64) UNIQUE NOT NULL,
    doc_id VARCHAR(64) REFERENCES documents(doc_id) ON DELETE CASCADE,
    report_type VARCHAR(50),
    address TEXT,
    district VARCHAR(100),
    street VARCHAR(100),
    area FLOAT,
    price FLOAT,
    usage VARCHAR(50),
    build_year INT,
    total_floor INT,
    current_floor INT,
    orientation VARCHAR(20),
    decoration VARCHAR(20),
    structure VARCHAR(50),
    org_id VARCHAR(64),
    create_by VARCHAR(64),
    case_data JSONB,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- cases 表索引
CREATE INDEX IF NOT EXISTS idx_cases_doc_id ON cases(doc_id);
CREATE INDEX IF NOT EXISTS idx_cases_district ON cases(district);
CREATE INDEX IF NOT EXISTS idx_cases_usage ON cases(usage);
CREATE INDEX IF NOT EXISTS idx_cases_area ON cases(area);
CREATE INDEX IF NOT EXISTS idx_cases_price ON cases(price);
CREATE INDEX IF NOT EXISTS idx_cases_org_id ON cases(org_id);
CREATE INDEX IF NOT EXISTS idx_cases_case_data ON cases USING GIN(case_data);


-- ============================================================================
-- 7. 业务表 - review_tasks
-- ============================================================================
CREATE TABLE IF NOT EXISTS review_tasks (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(64) UNIQUE NOT NULL,
    filename VARCHAR(255),
    file_path VARCHAR(500),
    review_mode VARCHAR(20) DEFAULT 'full',
    status VARCHAR(20) DEFAULT 'pending',
    overall_risk VARCHAR(20),
    issue_count INT DEFAULT 0,
    validation_count INT DEFAULT 0,
    llm_count INT DEFAULT 0,
    org_id VARCHAR(64),
    create_by VARCHAR(64),
    result JSONB,
    error TEXT,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    start_time TIMESTAMP,
    end_time TIMESTAMP
);

-- review_tasks 表索引
CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status);
CREATE INDEX IF NOT EXISTS idx_review_tasks_create_time ON review_tasks(create_time DESC);
CREATE INDEX IF NOT EXISTS idx_review_tasks_org_id ON review_tasks(org_id);
CREATE INDEX IF NOT EXISTS idx_review_tasks_result ON review_tasks USING GIN(result);


-- ============================================================================
-- 8. 操作日志表
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,

    -- 用户信息
    user_id VARCHAR(64),                    -- 操作用户ID
    username VARCHAR(128),                  -- 用户名（冗余存储，方便查询）
    org_id VARCHAR(64),                     -- 组织ID
    org_name VARCHAR(128),                  -- 组织名称

    -- 操作信息
    action VARCHAR(64) NOT NULL,            -- 操作类型: create/read/update/delete/upload/download/export/login/logout
    resource_type VARCHAR(64) NOT NULL,     -- 资源类型: report/case/review_task/user/system
    resource_id VARCHAR(128),               -- 资源ID
    resource_name VARCHAR(256),             -- 资源名称（如文件名）

    -- 请求信息
    method VARCHAR(16),                     -- HTTP方法: GET/POST/PUT/DELETE
    path VARCHAR(512),                      -- 请求路径
    query_params TEXT,                      -- 查询参数（JSON）
    ip_address VARCHAR(64),                 -- 客户端IP
    user_agent VARCHAR(512),                -- User-Agent

    -- 结果信息
    status VARCHAR(16) DEFAULT 'success',   -- 状态: success/failed
    status_code INT,                        -- HTTP状态码
    error_message TEXT,                     -- 错误信息

    -- 详情
    detail JSONB,                           -- 操作详情（JSON格式）

    -- 时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 耗时（毫秒）
    duration_ms INT
);

-- 操作日志表索引
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_org_id ON audit_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_type ON audit_logs(resource_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_status ON audit_logs(status);

-- 复合索引（常用查询场景）
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time ON audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_org_time ON audit_logs(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- 添加注释
COMMENT ON TABLE audit_logs IS '操作日志表';
COMMENT ON COLUMN audit_logs.action IS '操作类型: create/read/update/delete/upload/download/export/login/logout';
COMMENT ON COLUMN audit_logs.resource_type IS '资源类型: report/case/review_task/user/system';
COMMENT ON COLUMN audit_logs.status IS '状态: success/failed';
COMMENT ON COLUMN audit_logs.detail IS '操作详情，JSON格式';

-- 日志清理函数（可选）- 保留最近90天的日志
CREATE OR REPLACE FUNCTION clean_old_audit_logs(days_to_keep INT DEFAULT 90)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    DELETE FROM audit_logs
    WHERE created_at < CURRENT_TIMESTAMP - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- 9. 触发器
-- ============================================================================

-- 更新时间触发器函数
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为用户表添加更新时间触发器
DROP TRIGGER IF EXISTS trigger_users_updated_at ON users;
CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- 为组织表添加更新时间触发器
DROP TRIGGER IF EXISTS trigger_organizations_updated_at ON organizations;
CREATE TRIGGER trigger_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();


-- ============================================================================
-- 10. 创建默认管理员用户
-- ============================================================================
-- 密码: admin123 (bcrypt hash)
-- ⚠️ 注意：生产环境请立即修改密码！
DO $$
DECLARE
    default_org_id INTEGER;
    admin_user_id INTEGER;
BEGIN
    -- 获取默认组织ID
    SELECT id INTO default_org_id FROM organizations WHERE org_code = 'default';

    -- 创建管理员用户（如果不存在）
    INSERT INTO users (username, password_hash, real_name, org_id, status)
    VALUES (
        'admin',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G2D0W3xFfF5k5e',  -- admin123
        '系统管理员',
        default_org_id,
        'active'
    )
    ON CONFLICT (username) DO NOTHING
    RETURNING id INTO admin_user_id;

    -- 如果是新创建的用户，分配超级管理员角色
    IF admin_user_id IS NOT NULL THEN
        INSERT INTO user_roles (user_id, role_code) VALUES (admin_user_id, 'super_admin');
    END IF;
END $$;


-- ============================================================================
-- 验证
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE '=== 数据库初始化完成 ===';
    RAISE NOTICE '用户管理表: organizations, users, user_roles, user_tokens';
    RAISE NOTICE '业务表: documents, cases, review_tasks';
    RAISE NOTICE '操作日志表: audit_logs';
    RAISE NOTICE '默认管理员: admin / admin123';
    RAISE NOTICE '⚠️  请立即修改默认密码！';
END $$;