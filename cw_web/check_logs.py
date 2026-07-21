import paramiko, sys

HOST, PORT, USER, PASS = "8.134.127.141", 22, "root", "123456789zyhZ"

def run(ssh, cmd, timeout=15):
    sin, sout, serr = ssh.exec_command(cmd, timeout=timeout)
    return sout.read().decode('utf-8', errors='replace'), serr.read().decode('utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15)

# Check the actual error
out, _ = run(ssh, "pm2 logs location-server --lines 15 --nostream 2>&1")
print("=== Logs ===")
print(out[:2000])

# Check what port is listening
out, _ = run(ssh, "sudo ss -tlnp | grep -E ':(3002|8080|8081)'")
print("=== Ports ===")
print(out)

# Try running directly
out, _ = run(ssh, "cd /opt/location-server && timeout 3 node server.js 2>&1 || true")
print(f"=== Direct run ===\n{out[:1000]}")

ssh.close()
