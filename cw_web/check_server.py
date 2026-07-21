#!/usr/bin/env python3
"""Check server status via SSH."""
import paramiko
import json

HOST = "8.134.127.141"
PORT = 22
USER = "root"
PASS = "123456789zyhZ"

def run_command(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def main():
    print(f"[SSH] 连接到 {HOST} ...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASS)
    print("[SSH] 连接成功")

    # Check PM2
    print("\n[PM2] 进程状态:")
    out, _ = run_command(client, "pm2 list")
    print(out)

    # Check health API
    print("[API] 健康检查:")
    out, _ = run_command(client, "curl -s http://127.0.0.1:3002/cw_dwq/api/health")
    print(out[:300])

    # Check TCP port
    print("\n[端口] 监听检查:")
    out, _ = run_command(client, "ss -tlnp | grep -E '3002|8080|8081'")
    print(out or "无输出")

    # Check nginx config
    print("\n[Nginx] 配置检查:")
    out, _ = run_command(client, "nginx -t 2>&1")
    print(out)

    # Check file sizes
    print("[文件] 已部署文件:")
    out, _ = run_command(client, "ls -la /opt/location-server/public/")
    print(out)

    client.close()
    print("\n[完成] 服务器检查完成")

if __name__ == "__main__":
    main()
