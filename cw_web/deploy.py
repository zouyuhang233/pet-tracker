#!/usr/bin/env python3
"""Deploy frontend files to cloud server via SFTP."""
import paramiko
import os

HOST = "8.134.127.141"
PORT = 22
USER = "root"
PASS = "123456789zyhZ"
REMOTE_DIR = "/opt/location-server/public"

FILES = [
    ("index.html", "index.html"),
    ("style.css", "style.css"),
    ("app.js", "app.js"),
    ("tcp-test.html", "tcp-test.html"),
]

LOCAL_DIR = r"C:\Users\zyh\Desktop\cw_web\public"

def deploy():
    print(f"[SFTP] 连接到 {HOST}:{PORT} ...")
    transport = paramiko.Transport((HOST, PORT))
    transport.connect(username=USER, password=PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    print("[SFTP] 连接成功")

    # Ensure remote directory exists
    try:
        sftp.stat(REMOTE_DIR)
    except FileNotFoundError:
        print(f"[SFTP] 创建目录: {REMOTE_DIR}")
        sftp.mkdir(REMOTE_DIR)

    for local_name, remote_name in FILES:
        local_path = os.path.join(LOCAL_DIR, local_name)
        remote_path = f"{REMOTE_DIR}/{remote_name}"
        size = os.path.getsize(local_path)
        print(f"[SFTP] 上传 {local_name} ({size:,} bytes) -> {remote_path}")
        sftp.put(local_path, remote_path)
        print(f"[SFTP] ✓ {local_name} 上传完成")

    sftp.close()
    transport.close()
    print("\n[完成] 所有文件部署成功！")
    print(f"  请访问 https://zouyuhang.online/cw_dwq 查看效果")

if __name__ == "__main__":
    deploy()
