import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Check PM2 logs for the error
out, _ = run(ssh, "pm2 logs location-server --lines 30 2>&1")
print("=== PM2 Logs ===")
print(out)

# Check if node_modules exists
out, _ = run(ssh, "ls /opt/location-server/node_modules/express/package.json 2>/dev/null && echo EXPRESS_OK || echo NO_EXPRESS")
print(f"Express: {out.strip()}")

out, _ = run(ssh, "ls /opt/location-server/node_modules/ws/package.json 2>/dev/null && echo WS_OK || echo NO_WS")
print(f"WS: {out.strip()}")

# Try running server manually to see error
out, _ = run(ssh, "cd /opt/location-server && timeout 5 node server.js 2>&1 || true")
print(f"\n=== Manual run output ===\n{out}")

# Check npm install log
out, _ = run(ssh, "cat /tmp/npm_install.log 2>/dev/null | tail -20 || echo no log")
print(f"=== npm log ===\n{out}")

# Check if package.json is valid
out, _ = run(ssh, "cat /opt/location-server/package.json")
print(f"=== package.json ===\n{out}")

ssh.close()
