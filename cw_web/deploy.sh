#!/bin/bash
# ============================================
# 定位器网站 - 部署脚本
# 用于将网站部署到云服务器 (8.134.127.141)
# ============================================

set -e  # 遇到错误立即退出

# ==================== 配置 ====================
SERVER_IP="8.134.127.141"
SERVER_USER="root"
SERVER_PASS="123456789zyhZ"
DEPLOY_DIR="/opt/location-server"
LOCAL_DIR="C:/Users/zyh/Desktop/cw_web"
WEB_PORT=3000
TCP_PORT=8080
WS_PORT=8081

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ==================== 检查环境 ====================
echo_info "检查部署环境..."

# 检查 Node.js 是否安装
if ! command -v node &> /dev/null; then
    echo_error "Node.js 未安装，请先在服务器上安装 Node.js"
    echo_info "安装命令: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"
    exit 1
fi

NODE_VERSION=$(node --version)
echo_info "Node.js 版本: $NODE_VERSION"

# 检查 npm 是否安装
if ! command -v npm &> /dev/null; then
    echo_error "npm 未安装"
    exit 1
fi

NPM_VERSION=$(npm --version)
echo_info "npm 版本: $NPM_VERSION"

# ==================== 创建部署目录 ====================
echo_info "创建部署目录..."
ssh -o StrictHostKeyChecking=no $SERVER_USER@$SERVER_IP "mkdir -p $DEPLOY_DIR"

# ==================== 上传文件 ====================
echo_info "上传网站文件到服务器..."
echo_info "从 $LOCAL_DIR 上传到 $SERVER_USER@$SERVER_IP:$DEPLOY_DIR"

# 使用 scp 上传（排除 node_modules）
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows 环境
    echo_warn "检测到 Windows 环境，请手动上传文件"
    echo_info "可以使用以下方式之一："
    echo_info "1. 使用 WinSCP 或 FileZilla 上传"
    echo_info "2. 使用 Git 推送到服务器"
    echo_info "3. 使用压缩包传输"
    echo ""
    echo_info "手动上传步骤："
    echo_info "1. 将 cw_web 文件夹压缩为 cw_web.zip"
    echo_info "2. 上传到服务器: scp cw_web.zip root@$SERVER_IP:/tmp/"
    echo_info "3. 在服务器上解压: unzip /tmp/cw_web.zip -d $DEPLOY_DIR"
else
    # Linux/Mac 环境
    tar -czf /tmp/cw_web.tar.gz -C "$(dirname "$LOCAL_DIR")" "$(basename "$LOCAL_DIR")" --exclude='node_modules'
    scp -o StrictHostKeyChecking=no /tmp/cw_web.tar.gz $SERVER_USER@$SERVER_IP:/tmp/
    ssh $SERVER_USER@$SERVER_IP "cd $DEPLOY_DIR && tar -xzf /tmp/cw_web.tar.gz --strip-components=1 && rm /tmp/cw_web.tar.gz"
    rm /tmp/cw_web.tar.gz
fi

# ==================== 安装依赖 ====================
echo_info "安装 Node.js 依赖..."
ssh $SERVER_USER@$SERVER_IP "cd $DEPLOY_DIR && npm install --production"

# ==================== 配置防火墙 ====================
echo_info "配置防火墙..."
ssh $SERVER_USER@$SERVER_IP "
    if command -v ufw &> /dev/null; then
        echo '使用 ufw 配置防火墙'
        sudo ufw allow $WEB_PORT/tcp comment 'Web 服务器'
        sudo ufw allow $TCP_PORT/tcp comment 'TCP 设备连接'
        sudo ufw allow $WS_PORT/tcp comment 'WebSocket'
        sudo ufw reload
    elif command -v firewall-cmd &> /dev/null; then
        echo '使用 firewalld 配置防火墙'
        sudo firewall-cmd --permanent --add-port=$WEB_PORT/tcp
        sudo firewall-cmd --permanent --add-port=$TCP_PORT/tcp
        sudo firewall-cmd --permanent --add-port=$WS_PORT/tcp
        sudo firewall-cmd --reload
    else
        echo_warn '未检测到防火墙工具，请手动开放端口'
    fi
"

# ==================== 配置 PM2（可选）====================
echo_info "配置 PM2 进程管理..."
ssh $SERVER_USER@$SERVER_IP "
    if ! command -v pm2 &> /dev/null; then
        echo '安装 PM2...'
        sudo npm install -g pm2
    fi
    
    # 停止旧进程
    pm2 stop location-server || true
    pm2 delete location-server || true
    
    # 启动新进程
    cd $DEPLOY_DIR
    pm2 start server.js --name 'location-server'
    
    # 保存进程列表
    pm2 save
    
    # 设置开机自启
    pm2 startup
"

# ==================== 配置 Nginx（可选）====================
echo_info "配置 Nginx 反向代理..."
ssh $SERVER_USER@$SERVER_IP "
    if command -v nginx &> /dev/null; then
        echo '配置 Nginx...'
        sudo tee /etc/nginx/sites-available/location-server << 'EOF'
server {
    listen 80;
    server_name zouyuhang.omline _;

    location / {
        proxy_pass http://localhost:$WEB_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }

    location /ws {
        proxy_pass http://localhost:$WS_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'Upgrade';
    }
}
EOF
        
        # 启用站点
        sudo ln -sf /etc/nginx/sites-available/location-server /etc/nginx/sites-enabled/
        sudo rm -f /etc/nginx/sites-enabled/default
        
        # 测试并重载 Nginx
        sudo nginx -t && sudo systemctl reload nginx
        
        echo 'Nginx 配置完成'
    else
        echo_warn 'Nginx 未安装，跳过 Nginx 配置'
        echo_info '可以手动安装: sudo apt-get install nginx'
    fi
"

# ==================== 验证部署 ====================
echo_info "验证部署..."
sleep 3

# 检查 Web 服务器
if curl -s -o /dev/null -w "%{http_code}" http://$SERVER_IP:$WEB_PORT | grep -q "200"; then
    echo_info "✓ Web 服务器运行正常 (http://$SERVER_IP:$WEB_PORT)"
else
    echo_warn "✗ Web 服务器可能未启动"
fi

# 检查 TCP 端口
if nc -z -w 2 $SERVER_IP $TCP_PORT 2>/dev/null; then
    echo_info "✓ TCP 端口 $TCP_PORT 已开放"
else
    echo_warn "✗ TCP 端口 $TCP_PORT 可能未开放"
fi

# 检查 WebSocket 端口
if nc -z -w 2 $SERVER_IP $WS_PORT 2>/dev/null; then
    echo_info "✓ WebSocket 端口 $WS_PORT 已开放"
else
    echo_warn "✗ WebSocket 端口 $WS_PORT 可能未开放"
fi

# ==================== 部署完成 ====================
echo ""
echo_info "=========================================="
echo_info "部署完成！"
echo_info "=========================================="
echo_info "Web 访问: http://$SERVER_IP:$WEB_PORT"
echo_info "或域名: http://zouyuhang.omline"
echo_info ""
echo_info "服务管理命令："
echo_info "  查看状态: ssh $SERVER_USER@$SERVER_IP 'pm2 status'"
echo_info "  查看日志: ssh $SERVER_USER@$SERVER_IP 'pm2 logs location-server'"
echo_info "  重启服务: ssh $SERVER_USER@$SERVER_IP 'pm2 restart location-server'"
echo_info "  停止服务: ssh $SERVER_USER@$SERVER_IP 'pm2 stop location-server'"
echo_info ""
echo_info "STOP 配置（可选）："
echo_info "  sudo apt install nginx certbot python3-certbot-nginx"
echo_info "  sudo certbot --nginx -d zouyuhang.omline"
echo_info "=========================================="
