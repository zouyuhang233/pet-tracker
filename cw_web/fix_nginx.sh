#!/bin/bash
# ============================================
# 修复 Nginx 路由冲突问题
# 确保 /cw_dwq 正确指向定位器网站
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "=========================================="
echo "   修复 Nginx /cw_dwq 路由配置"
echo "=========================================="
echo ""

# ==================== 检查部署目录 ====================
DEPLOY_DIR="/opt/location-server"

if [ ! -f "$DEPLOY_DIR/server.js" ]; then
    echo_error "未找到部署目录: $DEPLOY_DIR"
    echo_error "请先上传 cw_web 文件到该目录"
    exit 1
fi

echo_info "找到部署目录: $DEPLOY_DIR"

# ==================== 检查 Node.js 服务 ====================
echo_info "检查 Node.js 服务..."

if pm2 list | grep -q "location-server"; then
    echo_info "location-server 进程存在"
    pm2 restart location-server
    sleep 2
else
    echo_warn "location-server 进程不存在，正在启动..."
    cd $DEPLOY_DIR
    pm2 start server.js --name "location-server"
    pm2 save
    sleep 3
fi

# 检查服务是否正常
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/cw_dwq | grep -q "200"; then
    echo_info "✓ Node.js 服务运行正常 (http://localhost:3000/cw_dwq)"
else
    echo_warn "✗ Node.js 服务可能未正常启动，查看日志："
    pm2 logs location-server --lines 20
fi

# ==================== 修复 Nginx 配置 ====================
echo_info "修复 Nginx 配置..."

NGINX_CONF="/etc/nginx/sites-available/location-server"
NGINX_ENABLED="/etc/nginx/sites-enabled/location-server"

# 备份旧配置
if [ -f "$NGINX_CONF" ]; then
    cp "$NGINX_CONF" "${NGINX_CONF}.bak.$(date +%Y%m%d_%H%M%S)"
    echo_info "已备份旧配置"
fi

# 写入新的 Nginx 配置
sudo tee "$NGINX_CONF" > /dev/null << 'NGINXEOF'
server {
    listen 80;
    listen [::]:80;
    server_name zouyuhang.online www.zouyuhang.online _;

    # ====== 主站 / 定位器子目录 /cw_dwq ======

    # 定位器网站 - 子目录反向代理
    location /cw_dwq/ {
        proxy_pass http://localhost:3000/cw_dwq/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_cache_bypass $http_upgrade;

        # 解决某些环境下的路径问题
        proxy_redirect http://localhost:3000/ /cw_dwq/;
    }

    # WebSocket 子路径反代
    location /cw_dwq/ws {
        proxy_pass http://localhost:8081/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # 根路径重定向到主站（如果有主站的话）
    # 如果没有主站，可以注释掉下面这行，让 /cw_dwq 成为首页
    # return 301 http://zouyuhang.online/cw_dwq/;
}
NGINXEOF

echo_info "Nginx 配置已更新"

# 启用配置
sudo ln -sf "$NGINX_CONF" "$NGINX_ENABLED"

# 禁用 default 配置（防止冲突）
if [ -f "/etc/nginx/sites-enabled/default" ]; then
    echo_warn "禁用 default 配置（防止与主站冲突）..."
    sudo rm -f /etc/nginx/sites-enabled/default
fi

# 测试 Nginx 配置
echo_info "测试 Nginx 配置..."
if sudo nginx -t; then
    echo_info "✓ Nginx 配置语法正确"
else
    echo_error "✗ Nginx 配置有语法错误"
    exit 1
fi

# 重载 Nginx
echo_info "重载 Nginx..."
sudo systemctl reload nginx
echo_info "✓ Nginx 已重载"

# ==================== 验证路由 ====================
echo ""
echo_info "=========================================="
echo_info "验证路由..."
echo_info "=========================================="

# 测试本地访问
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/cw_dwq 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo_info "✓ 本地服务: http://localhost:3000/cw_dwq (HTTP $HTTP_CODE)"
else
    echo_warn "✗ 本地服务异常 (HTTP $HTTP_CODE)"
fi

# 测试 Nginx 反代
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/cw_dwq 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo_info "✓ Nginx 反代: http://localhost/cw_dwq (HTTP $HTTP_CODE)"
else
    echo_warn "✗ Nginx 反代异常 (HTTP $HTTP_CODE)"
    echo_warn "可能原因：Nginx 未运行或配置有误"
fi

# ==================== 配置 HTTPS ====================
echo ""
echo_info "配置 HTTPS 证书..."

if sudo command -v certbot &> /dev/null; then
    echo_info "申请 SSL 证书..."
    sudo certbot --nginx -d zouyuhang.online -d www.zouyuhang.online --non-interactive --agree-tos --email zouyuhang@example.com || {
        echo_warn "自动证书申请失败，请手动执行："
        echo_warn "  sudo certbot --nginx -d zouyuhang.online"
    }
else
    echo_warn "Certbot 未安装，跳过 HTTPS 配置"
    echo_info "安装命令: sudo apt install certbot python3-certbot-nginx -y"
fi

# ==================== 防火墙 ====================
echo ""
echo_info "配置防火墙..."
sudo ufw allow 80/tcp comment 'HTTP' 2>/dev/null || true
sudo ufw allow 443/tcp comment 'HTTPS' 2>/dev/null || true
sudo ufw allow 3000/tcp comment 'Web 服务器' 2>/dev/null || true
sudo ufw allow 8080/tcp comment 'TCP 设备连接' 2>/dev/null || true
sudo ufw allow 22/tcp comment 'SSH' 2>/dev/null || true
sudo ufw reload 2>/dev/null || true

# ==================== 完成 ====================
echo ""
echo_info "=========================================="
echo_info "修复完成！"
echo_info "=========================================="
echo_info "访问地址:"
echo_info "  本地:  http://localhost:3000/cw_dwq"
echo_info "  公网:  http://zouyuhang.online/cw_dwq"
echo_info "  HTTPS: https://zouyuhang.online/cw_dwq"
echo_info ""
echo_info "如果公网仍显示主站内容，请检查："
echo_info "  1. DNS 解析: dig zouyuhang.online"
echo_info "  2. Nginx 状态: sudo systemctl status nginx"
echo_info "  3. 查看错误日志: sudo tail -f /var/log/nginx/error.log"
echo_info "  4. 查看访问日志: sudo tail -f /var/log/nginx/access.log"
echo_info "  5. 查看 Node 日志: pm2 logs location-server"
echo_info "=========================================="
