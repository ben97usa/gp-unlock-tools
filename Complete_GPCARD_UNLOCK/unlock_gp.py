#!/usr/bin/env python3
import re
import subprocess
import threading
import select
import sys
import time
import os
import shutil

import pexpect

MAC_FILE = "./RM_MAC.txt"
SSH_PASSWORD = "$pl3nd1D"
FIND_IP = "/usr/local/bin/find_ip"
RSCM_SHOW_MANAGER_INFO = "show manager info"
TFTPBOOT_DIRECTORY = "/tftpboot/pxelinux.cfg"
MOS_CUST_IMAGE = "/tftpboot/pxelinux.cfg/t6t_MOS"
MOS_IMAGE = "firmware/t6t/gp/Image_rsa_mos.img"
PUBLIC_KEY = ""

# ---------------------------------------------------
# Utility: run command and capture output
# ---------------------------------------------------
def run(cmd):
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.STDOUT, shell=True, text=True
        )
    except subprocess.CalledProcessError:
        return ""

def get_mac_from_file(filepath):
    with open(filepath, "r") as f:
        mac = f.read().strip()
    return mac

def find_ip(mac):
    output = run(f"{FIND_IP} {mac}")
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
    return m.group(1) if m else None

def conv_mac_format(mac):
    if "MacAddress:" in mac:
        extr_mac = mac.split("MacAddress:")[1].strip()
        return "01-" + extr_mac.replace(":", "-").lower()
    
def check_custom_bootimage(filepath, fielname):
    filepath = os.path.join(filepath, fielname)
    if os.path.isfile(filepath):
        print(f"File '{filepath}' exists.")

        with open(filepath, "r") as f:
            content = f.read()

        if MOS_IMAGE in content:
            print(f"   ✅ Found MOS image reference in '{filepath}'")
        else:
            print(f"   ⚠️  MOS image reference NOT found in '{filepath}'")
            shutil.copy(MOS_CUST_IMAGE, filepath)
            print(f"   → Updated: {filepath} with MOS image reference")
    else:
        print(f"File '{filepath}' does not exist.")
        shutil.copy(MOS_CUST_IMAGE, filepath)
        print(f"Created: {filepath}")

def get_server_slots(rm_manager_info_output):
    server_slots = []

    for line in rm_manager_info_output.splitlines():
        line = line.strip()

        # Skip header / separators
        if not line.startswith("|"):
            continue
        if "Port State" in line:
            continue

        # Split columns
        parts = [p.strip() for p in line.split("|") if p.strip()]

        # Expect at least 6 columns
        if len(parts) < 6:
            continue

        slot = parts[0]
        port_type = parts[3]
        completion_code = parts[6]

        if port_type == "Server" and completion_code == "Success":
            server_slots.append(int(slot))

    return server_slots

def exec_cmd(ip, slot, action, extra=None):
    if action == "vreset":
        cmd = f"set system vreset -i {slot}"
    elif action == "reset":
        cmd = f"set system reset -i {slot}"
    elif action == "gp_info":
        cmd = f"show system info -i {slot} -b 1"
    elif action == "boot_mode":
        cmd = f"set system boot -i {slot} -b 1 -t {extra}"
    else:
        cmd = f'set system cmd -i {slot} -c {extra}'

    ssh_cmd = [
        "sshpass", "-p", SSH_PASSWORD, "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{ip}",
        cmd
    ]

    print(f"Command:", cmd)
    # print("   → Executing command... please wait...(This may take up to 90 seconds depending on RSCM load)")

    try:
        # Use Popen so we don't freeze
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        full_output = ""

        # Stream output line by line
        for line in proc.stdout:
            line = line.rstrip()
            full_output += line + "\n"
            if "Completion Code:" in line:
                print(line)
            if "MacAddress:" in line:
                print(line)

        proc.wait()  # ensure completion

    except Exception as e:
        print(f"   ❌ SSH execution failed: {e}")
        return False

    # Detect completion code
    return "Completion Code: Success" in full_output, full_output

def exec_cmd_with_timeout_and_skip(ip, slot, action, extra, timeout=60):
    """
    Run exec_cmd() with:
      - timeout
      - ability for user to skip to next IP by pressing ENTER.
    """

    result_holder = {"done": False, "success": False}

    def run_cmd():
        ok = exec_cmd(ip, slot, action, extra)
        result_holder["done"] = True
        result_holder["success"] = ok

    # Run SSH command in separate thread
    t = threading.Thread(target=run_cmd)
    t.start()

    print(f"\n→ RM IP: {ip}, SLOT: {slot}, Please ENTER to skip")

    start = time.time()

    # Poll loop
    while time.time() - start < timeout:
        if result_holder["done"]:
            return result_holder["success"]

        # Non-blocking skip input
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            _ = sys.stdin.readline()
            print("⚠️  User requested skip")
            return False

        time.sleep(0.2)

    print(f"⏳ Timeout ({timeout}s)")
    return False

def exec_rm_cmd(ip, cmd, extra=None):

    ssh_cmd = [
        "sshpass", "-p", SSH_PASSWORD, "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{ip}",
        cmd
    ]

    print(f"Command:", ssh_cmd)
    print("   → Executing command... please wait...(This may take up to 90 seconds depending on RSCM load)")

    try:
        # Use Popen so we don't freeze
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        full_output = ""

        # Stream output line by line
        for line in proc.stdout:
            line = line.rstrip()
            full_output += line + "\n"

        proc.wait()  # ensure completion

    except Exception as e:
        print(f"   ❌ SSH execution failed: {e}")
        return False

    # Detect completion code
    return "Completion Code: Success" in full_output, full_output

def extract_board_serial(output):
    for line in output.splitlines():
        if "Board Serial" in line:
            return line.split(":")[1].strip()
    return None

def gp_ping_ok(child, ip):
    child.sendline(f"ping -c 1 -W 1 {ip}")
    # Wait for the prompt again
    child.expect(r"root@localhost:")
    output = child.before  # everything before the prompt
    # Check if '1 packets transmitted, 1 received' is in output
    return "1 packets received" in output

def gp_collect_keys(child, GP_SN):
    KEYS_EXTRACTION_CMDS = [
        f"mkdir /tmp/{GP_SN}",
        f"cd /tmp/{GP_SN}",
        f"cerberus_utility exportcsr {GP_SN}.CSR",
        "ovb_lock token token.bin",
        "cerberus_utility getcertchain 0"
    ]

    for cmd in KEYS_EXTRACTION_CMDS:
        child.sendline(cmd)
        child.expect(r"root@localhost:", timeout=30)
        output = child.before.splitlines()[1:]
        print("\n".join(output))

def gp_login(ip, slot):
    child = pexpect.spawn(
        f"sshpass -p '$pl3nd1D' ssh -o StrictHostKeyChecking=no root@{ip}",
        encoding="utf-8",
        timeout=30
    )

    # Debug output (VERY helpful)
    child.logfile = sys.stdout

    # Wait for initial shell prompt
    child.expect(r"#")

    # Start serial session
    child.sendline(f"start serial session -i {slot} -p 8295")

    # 🔥 KEY FIX: don't expect wrong prompt
    # Wait for either:
    # - GP prompt
    # - or still shell (fallback)
    child.sendline("")  
    child.expect(r"root@localhost:", timeout=30)

    print("Entered GP Console")
    return child

def gp_exit(child):
    # Exit safely
    print("Exiting both GP card & RSCM")
    child.send("~.")
    child.expect(pexpect.EOF)
    child.close()

def gp_disable_firewall(child, ip, slot, public_key):
    print("Disable Firewall")
    # Example commands inside GP
    # child.sendline("disable firewall")
    # child.expect(r"GP>")
    FIREWALL_DISABLE_CMDS = [
        "setenforce 0",
        "mkdir -p /run/ssh/keys/root",
        f'printf "%s\n" "{public_key}" > /run/ssh/keys/root/authorized_keys',
        "chmod 644 /run/ssh/keys/root/*",
        "ov-firewall --disable"
    ]
    
    for cmd in FIREWALL_DISABLE_CMDS:
        child.sendline(cmd)
        child.expect(r"root@localhost:", timeout=30)
        output = child.before.splitlines()[1:]
        print("\n".join(output))
    

    if gp_ping_ok(child, "10.0.3.254"):
        print("Ping successful")
    else:
        print("Ping failed!")

def main():
    rm_mac = get_mac_from_file(MAC_FILE)
    ip = find_ip(rm_mac)
    cmd_succeed, rm_manager_info = exec_rm_cmd(ip, RSCM_SHOW_MANAGER_INFO)

    # cmd_succeed = True                          # Delete later
    # rm_manager_info = "TESTING"                 # Delete later

    if cmd_succeed:
        with open("/project/teto/UNLOCK_GP/id_rsa.pub", "r") as f:
            PUBLIC_KEY = f.read().strip()

        # print(PUBLIC_KEY)
        print(rm_manager_info)
        slots = get_server_slots(rm_manager_info)             # Uncomment later
        # slots = [14]                             # Delete later
        print("Sever slots at", rm_mac, "(", ip, ") :", slots)
        gp_mac_list = ""
        custom_boot = ""
        server_list = []
        failed_list = []

        for slot in slots:
            print("\n=== Processing slot", slot, "===")
            success, output = exec_cmd(ip, slot, "gp_info", None)
            if not success:
                print(f"Failed to get GP info for slot {slot} at {ip}")
                failed_list.append(slot)
            else:
                server_list.append(slot)
                for line in output.splitlines():
                    if "MacAddress:" in line:
                        gp_mac_list += line + "\n"
                        custom_boot += conv_mac_format(line) + "\n"

        print("\n=== All GP info collected ===")
        print(custom_boot)
        print(server_list)

        for bootimage in custom_boot.splitlines():
            check_custom_bootimage(TFTPBOOT_DIRECTORY, bootimage)
        
        for server in server_list:
            success, output = exec_cmd(ip, server, "boot_mode", "2")
            if not success:
                print(f"Failed to change Boot mode to PXE: slot{server}")
                failed_list.append(server)

            success, output = exec_cmd(ip, server, "reset", None)
            if not success:
                print(f"Failed to DC cycle slot {server}")
                failed_list.append(server)

        for server in server_list:
            print("\n=== Processing slot", server, "===")
            success, gp_fru_output = exec_cmd(ip, server, "cmd", "fru print 2")
            if success:
                GP_SN = extract_board_serial(gp_fru_output)
                print(GP_SN)

            gp_child = gp_login(ip, server)
            gp_disable_firewall(gp_child, ip, server, PUBLIC_KEY)
            gp_collect_keys(gp_child, GP_SN)
            gp_exit(gp_child)
            print("\n=== Completed slot", server, "===")
        
        print("\n=== Completed with all GPs ===")
        print("\nFailed slots:", failed_list)

    else:
        print("Failed to get manager info from RM at", rm_mac, "-", ip)
        return
    
if __name__ == "__main__":
    main()