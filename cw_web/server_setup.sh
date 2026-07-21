#!/bin/bash
# ============================================
# 定位器网站 - 服务器一键部署脚本
# 使用方法：在服务器上执行 bash server_setup.sh
# ============================================

set -e

echo "=========================================="
echo "   定位器网站 - 服务器部署脚本"
echo "   访问地址: https://zouyuhang.online/cw_dwq"
echo "=========================================="
echo ""

# ==================== 配置 ====================
DEPLOY_DIR="/opt/location-server"
WEB_PORT=3000
TCP_PORT=8080
WS_PORT=8081

# 颜色输出
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

# ==================== 检查 Node.js ====================
echo_info "检查 Node.js 环境..."

if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo_info "Node.js 已安装: $NODE_VERSION"
else
    echo_warn "Node.js 未安装，正在安装..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
    echo_info "Node.js 安装完成: $(node --version)"
fi

if command -v npm &> /dev/null; then
    echo_info "npm 版本: $(npm --version)"
else
    echo_error "npm 未安装，请手动安装"
    exit 1
fi

# ==================== 安装 PM2 ====================
echo_info "检查 PM2..."
if ! command -v pm2 &> /dev/null; then
    echo_info "安装 PM2 进程管理..."
    sudo npm install -g pm2
else
    echo_info "PM2 已安装: $(pm2 --version)"
fi

# ==================== 创建部署目录 ====================
echo_info "创建部署目录: $DEPLOY_DIR"
sudo mkdir -p $DEPLOY_DIR
sudo chown -R $USER:$USER $DEPLOY_DIR

# ==================== 上传文件提示 ====================
echo ""
echo_warn "请将 cw_web 文件夹上传到服务器"
echo_warn "推荐方式："
echo ""
echo_info "方式一（推荐）：在本地 PowerShell 执行："
echo_info "  scp -r C:\\Users\\zyh\\Desktop\\cw_web root@8.134.127.141:$DEPLOY_DIR"
echo ""
echo_info "方式二：使用宝塔面板文件管理上传到 $DEPLOY_DIR"
echo ""
echo_info "方式三：使用 FTP 工具（FileZilla）上传"
echo ""

# 检查是否已有文件
if [ -f "$DEPLOY_DIR/package.json" ]; then
    echo_info "检测到已有文件，继续部署..."
else
    echo_warn "等待文件上传..."
    echo_warn "上传完成后请重新运行此脚本"
    read -p "按 Enter 继续..."
fi

# ==================== 安装依赖 ====================
echo_info "安装 Node.js 依赖..."
cd $DEPLOY_DIR
npm install --production

# ==================== 停止旧进程 ====================
echo_info "停止旧进程..."
pm2 stop location-server 2>/dev/null || true
pm2 delete location-server 2>/dev/null || true

# ==================== 启动服务 ====================
echo_info "启动服务..."
cd $DEPLOY_DIR
pm2 start server.js --name "location-server"
pm2 save
pm2 startup

echo_info "服务已启动！"
sleep 2
pm2 status
pm2 logs location-server --lines 20

# ==================== 配置防火墙 ====================
echo_info "配置防火墙..."
sudo ufw allow $WEB_PORT/tcp comment 'Web 服务器' 2>/dev/null || true
sudo ufw allow $TCP_PORT/tcp comment 'TCP 设备连接' 2>/dev/null || true
sudo ufw allow 80/tcp comment 'HTTP' 2>/dev/null || true
sudo ufw allow 443/tcp comment 'HTTPS' 2>/dev/null || true
sudo ufw reload 2>/dev/null || true

# ==================== 配置 Nginx ====================
echo_info "配置 Nginx..."

# 检查是否已有 nginx 配置
NGINX_CONF="/etc/nginx/sites-available/location-server"
NGINX_ENABLED="/etc/nginx/sites-enabled/location-server"

if [ -f "$NGINX_CONF" ]; then
    echo_info "Nginx 配置已存在，更新配置..."
    sudo cp "$DEPLOY_DIR/nginx-cw_dwq.conf" "$NGINX_CONF"
else
    echo_info "创建 Nginx 配置..."
    sudo cp "$DEPLOY_DIR/nginx-cw_dwq.conf" "$NGINX_CONF"
    sudo ln -sf "$NGINX_CONF" "$NGINX_ENABLED"
    sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
fi

# 测试并重载 Nginx
echo_info "重载 Nginx..."
sudo nginx -t && sudo systemctl reload nginx
echo_info "Nginx 配置完成"

# ==================== 配置 HTTPS（Let's Encrypt） ====================
echo ""
echo_info "配置 HTTPS 证书..."
echo_info "域名: zouyuhang.online"

if sudo command -v certbot &> /dev/null; then
    echo_info "Certbot 已安装"
else
    echo_info "安装 Certbot..."
    sudo apt install certbot python3-certbot-nginx -y
fi

echo_info "申请 SSL 证书（需要域名已解析到本服务器）..."
sudo certbot --nginx -d zouyuhang.online -d www.zouyuhang.online --non-interactive --agree-tos --email zouyuhang@example.com || {
    echo_warn "自动证书申请失败，请手动执行："
    echo_warn "  sudo certbot --nginx -d zouyuhang.online"
}

# ==================== 验证部署 ====================
echo ""
echo_info "=========================================="
echo_info "部署完成！"
echo_info "=========================================="
echo_info "Web 访问: https://zouyuhang.online/cw_dwq"
echo_info "本地访问: http://localhost:$WEB_PORT/cw_dwq"
echo_info ""
echo_info "服务管理命令："
echo_info "  查看状态: pm2 status"
echo_info "  查看日志: pm2 logs location-server"
echo_info "  重启服务: pm2 restart location-server"
echo_info "  停止服务: pm2 stop location-server"
echo_info ""
echo_info "Nginx 配置: $NGINX_CONF"
echo_info "部署目录: $DEPLOY_DIR"
echo_info "=========================================="

# 等待服务启动后测试
sleep 3
if curl -s -o /dev/null -w "%{http_code}" http://localhost:$WEB_PORT/cw_dwq | grep -q "200"; then
    echo_info "✓ 本地服务运行正常"
else
    echo_warn "✗ 本地服务可能未启动，请检查日志"
fi

echo ""
echo_info "如果无法通过域名访问，请检查："
echo_info "1. DNS 解析: zouyuhang.online → $TCP_PORT" 
echo_info "2. 防火墙: sudo ufw status"
echo_info "3. Nginx: sudo systemctl status nginx"
echo_info "4. 日志: pm2 logs location-server"
