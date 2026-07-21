import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# 1. 当前 Nginx 加载了哪些配置文件
out, _ = run(ssh, "cat /etc/nginx/nginx.conf")
print("=== nginx.conf ===")
print(out)

# 2. conf.d 目录下有哪些文件
out, _ = run(ssh, "ls -la /etc/nginx/conf.d/")
print("=== conf.d/ ===")
print(out)

# 3. 读取 ridge-guardian.conf（当前生效的配置）
out, _ = run(ssh, "cat /etc/nginx/conf.d/ridge-guardian.conf")
print("=== ridge-guardian.conf ===")
print(out)

# 4. 读取 ridge.conf
out, _ = run(ssh, "cat /etc/nginx/conf.d/ridge.conf")
print("=== ridge.conf ===")
print(out)

# 5. 还有没有 default.d
out, _ = run(ssh, "ls -la /etc/nginx/default.d/ 2>/dev/null; cat /etc/nginx/default.d/*.conf 2>/dev/null || echo 'no default.d'")
print("=== default.d ===")
print(out)

# 6. 看所有包含 zouyuhang 的配置
out, _ = run(ssh, "grep -rn 'zouyuhang' /etc/nginx/ 2>/dev/null")
print("=== all zouyuhang refs ===")
print(out)

# 7. 看 Node.js 服务在哪些端口
out, _ = run(ssh, "sudo ss -tlnp | grep node")
print("=== node ports ===")
print(out)

# 8. 本地测试 /cw_dwq 和 /
out, _ = run(ssh, "curl -s -o /dev/null -w 'HTTP %{http_code} -> ' http://localhost/cw_dwq; curl -s http://localhost/cw_dwq | head -5")
print("=== test /cw_dwq via nginx ===")
print(out)

out, _ = run(ssh, "curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost/")
print("=== test / via nginx ===")
print(out)

ssh.close()
