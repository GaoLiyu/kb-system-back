-- ============================================================================
-- 操作日志表
-- ============================================================================

-- 创建操作日志表
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

-- 创建索引
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

-- ============================================================================
-- 日志清理（可选）- 保留最近90天的日志
-- ============================================================================

-- 创建清理函数
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

-- 使用方法: SELECT clean_old_audit_logs(90);
