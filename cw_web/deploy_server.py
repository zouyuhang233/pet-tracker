#!/usr/bin/env python3
"""Deploy server.js to cloud server and restart."""
import paramiko
import time

HOST = "8.134.127.141"
PORT = 22
USER = "root"
PASS = "123456789zyhZ"
REMOTE_SERVER = "/opt/location-server/server.js"
LOCAL_SERVER = r"C:\Users\zyh\Desktop\cw_web\server.js"

def deploy():
    print(f"[SSH] 连接到 {HOST} ...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASS)

    # Stop PM2 service
    print("[PM2] 停止 location-server ...")
    stdin, stdout, stderr = client.exec_command("pm2 stop location-server")
    stdout.read()

    # Upload server.js
    print("[SFTP] 上传 server.js ...")
    transport = paramiko.Transport((HOST, PORT))
    transport.connect(username=USER, password=PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    sftp.put(LOCAL_SERVER, REMOTE_SERVER)
    sftp.close()
    transport.close()
    print("[SFTP] ✓ server.js 上传完成")

    # Restart PM2
    print("[PM2] 重启 location-server ...")
    stdin, stdout, stderr = client.exec_command("pm2 restart location-server")
    stdout.read()
    stderr.read()

    # Wait for startup
    time.sleep(3)

    # Check status
    stdin, stdout, stderr = client.exec_command("pm2 list")
    out = stdout.read().decode()
    print("\n[PM2] 进程状态:")
    print(out)

    # Check ports
    stdin, stdout, stderr = client.exec_command("ss -tlnp | grep -E '3002|8080|8081'")
    out = stdout.read().decode()
    print("[端口] 监听检查:")
    print(out or "无输出")

    # Quick health check
    stdin, stdout, stderr = client.exec_command("curl -s http://127.0.0.1:3002/cw_dwq/api/health")
    out = stdout.read().decode()
    print("[API] 健康检查:")
    print(out[:200])

    client.close()
    print("\n[完成] 服务器部署完成！")

if __name__ == "__main__":
    deploy()
