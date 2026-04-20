#!/usr/bin/env python3
# Copy full /tmp/GP_CARD_SN folder from each GP card to PXE /home/qsitoan/April20_unlock

import os
import re
import subprocess
import sys
import time
from datetime import datetime

import pexpect

MAC_FILE = "/project/teto/UNLOCK_GP/RM_MAC.txt"
SSH_PASSWORD = "$pl3nd1D"
FIND_IP = "/usr/local/bin/find_ip"

PXE_USER = "qsitoan"
PXE_IP = "192.168.202.50"
PXE_BASE_DIR = "/home/qsitoan"


def run(cmd):
    try:
        return subprocess.check_output(
            cmd,
            stderr=subprocess.STDOUT,
            shell=True,
            universal_newlines=True
        )
    except subprocess.CalledProcessError as exc:
        return exc.output if exc.output else ""


def get_mac_from_file(filepath):
    with open(filepath, "r") as f:
        return f.read().strip()


def find_ip(mac):
    output = run("%s %s" % (FIND_IP, mac))
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
    if m:
        return m.group(1)
    return None


def exec_rm_cmd(ip, cmd):
    ssh_cmd = [
        "sshpass", "-p", SSH_PASSWORD, "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "root@%s" % ip,
        cmd
    ]

    try:
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        full_output = ""
        for line in proc.stdout:
            full_output += line

        proc.wait()
        return ("Completion Code: Success" in full_output, full_output)

    except Exception as e:
        return (False, "SSH execution failed: %s" % e)


def exec_cmd(ip, cmd):
    ssh_cmd = [
        "sshpass", "-p", SSH_PASSWORD, "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "root@%s" % ip,
        cmd
    ]

    try:
        proc = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        full_output = ""
        for line in proc.stdout:
            full_output += line

        proc.wait()
        return ("Completion Code: Success" in full_output, full_output)

    except Exception as e:
        return (False, "SSH execution failed: %s" % e)


def get_server_slots(manager_info):
    slots = []

    for line in manager_info.splitlines():
        line = line.strip()

        if not line.startswith("|"):
            continue
        if "Port State" in line:
            continue

        parts = [p.strip() for p in line.split("|") if p.strip()]

        if len(parts) < 7:
            continue

        slot = parts[0]
        port_type = parts[3]
        completion_code = parts[6]

        if port_type == "Server" and completion_code == "Success":
            try:
                slots.append(int(slot))
            except ValueError:
                pass

    return slots


def extract_board_serial(output):
    for line in output.splitlines():
        if "Board Serial" in line:
            return line.split(":", 1)[1].strip()
    return None


def get_today_unlock_folder(base_dir):
    folder_name = datetime.now().strftime("%B") + str(datetime.now().day) + "_unlock"
    candidate = os.path.join(base_dir, folder_name)

    if not os.path.exists(candidate):
        os.makedirs(candidate)
        print("[OK] Created today's unlock folder: %s" % candidate)
    else:
        print("[OK] Today's unlock folder already exists: %s" % candidate)

    return candidate


def gp_login(ip, slot):
    print("[STEP] Opening SSH to RM %s for slot %s" % (ip, slot))

    child = pexpect.spawn(
        "sshpass -p '%s' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@%s" % (SSH_PASSWORD, ip),
        encoding="utf-8",
        timeout=60
    )

    child.logfile = sys.stdout

    try:
        child.expect(r"#", timeout=30)
    except Exception:
        print("[FAIL] can't login to RM for slot %s" % slot)
        try:
            child.close()
        except Exception:
            pass
        return None

    print("[STEP] Starting serial session slot %s port 8295" % slot)
    child.sendline("start serial session -i %s -p 8295" % slot)

    time.sleep(2)
    child.sendline("")

    try:
        child.expect(r"root@localhost:.*#", timeout=60)
    except Exception:
        print("[FAIL] can't login to 8295 on slot %s" % slot)
        try:
            child.close()
        except Exception:
            pass
        return None

    print("[OK] Entered GP console for slot %s" % slot)
    return child


def gp_exit(child):
    try:
        child.send("~.")
        child.expect(pexpect.EOF, timeout=10)
    except Exception:
        pass
    try:
        child.close()
    except Exception:
        pass


def gp_check_folder(child, gp_sn, slot):
    folder_path = "/tmp/%s" % gp_sn
    print("[STEP] Checking folder %s" % folder_path)

    child.sendline("ls %s" % folder_path)

    try:
        child.expect(r"root@localhost:.*#", timeout=20)
    except Exception:
        print("[FAIL] can't see slot %s" % slot)
        return False

    output = child.before

    if "No such file" in output:
        print("[FAIL] Folder not found for slot %s (%s)" % (slot, gp_sn))
        return False

    return True


def gp_scp_folder_to_pxe(child, gp_sn, dest_dir, pxe_password):
    src = "/tmp/%s" % gp_sn
    dest = "%s@%s:%s/" % (PXE_USER, PXE_IP, dest_dir)

    cmd = "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r %s %s" % (src, dest)

    print("[STEP] SCP folder from GP to PXE")
    print("[CMD] %s" % cmd)

    child.sendline(cmd)

    while True:
        idx = child.expect(
            [
                r"yes/no",
                r"[Pp]assword:",
                r"root@localhost:.*#",
                pexpect.TIMEOUT,
                pexpect.EOF
            ],
            timeout=180
        )

        if idx == 0:
            print("[INFO] SSH asking yes/no -> sending yes")
            child.sendline("yes")
            continue

        if idx == 1:
            print("[INFO] SCP asking PXE password -> sending password")
            child.sendline(pxe_password)
            continue

        if idx == 2:
            print("[OK] Back to GP prompt after SCP")
            break

        if idx == 3:
            print("[FAIL] SCP timeout for %s" % gp_sn)
            return False

        if idx == 4:
            print("[FAIL] SCP EOF for %s" % gp_sn)
            return False

    copied_path = os.path.join(dest_dir, gp_sn)
    if os.path.isdir(copied_path):
        print("[OK] Verified folder exists on PXE: %s" % copied_path)
        return True

    print("[FAIL] Folder not found on PXE: %s" % copied_path)
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 collect_unlock_pkgs_to_pxe.py <PXE_PASSWORD>")
        sys.exit(1)

    pxe_password = sys.argv[1]

    print("[STEP] Reading RM MAC")
    rack_mac = get_mac_from_file(MAC_FILE)
    print("[INFO] RM MAC = %s" % rack_mac)

    print("[STEP] Finding RM IP")
    rm_ip = find_ip(rack_mac)
    if not rm_ip:
        print("[FAIL] Failed to find RM IP from RM_MAC.txt")
        sys.exit(1)

    print("[OK] RM IP = %s" % rm_ip)

    print("[STEP] Using today's unlock folder on PXE")
    dest_dir = get_today_unlock_folder(PXE_BASE_DIR)
    final_name = os.path.basename(dest_dir)

    print("[OK] PXE destination folder: %s" % dest_dir)
    print("FINAL_UNLOCK_FOLDER_NAME=%s" % final_name)

    print("[STEP] Running show manager info")
    ok, manager_info = exec_rm_cmd(rm_ip, "show manager info")

    if not ok:
        print("[FAIL] Failed to retrieve manager info from RM")
        print(manager_info)
        sys.exit(1)

    slots = get_server_slots(manager_info)
    print("[OK] Server slots to process: %s" % slots)

    if len(slots) == 0:
        print("[FAIL] No valid slots found")
        sys.exit(1)

    successes = []
    failures = []

    total = len(slots)
    current = 0

    for slot in slots:
        current += 1
        print("\n======================================")
        print("[STEP] Processing slot %s (%s/%s)" % (slot, current, total))
        print("======================================")

        fru_cmd = "set system cmd -i %s -c 'fru print 2'" % slot
        print("[STEP] Getting GP serial from FRU")
        ok, fru_output = exec_cmd(rm_ip, fru_cmd)

        if not ok:
            print("[FAIL] FRU command failed on slot %s" % slot)
            failures.append((slot, "FRU command failed"))
            continue

        gp_sn = extract_board_serial(fru_output)
        if not gp_sn:
            print("[FAIL] Could not extract GP serial on slot %s" % slot)
            failures.append((slot, "No GP serial"))
            continue

        print("[OK] GP SN = %s" % gp_sn)

        child = None
        try:
            child = gp_login(rm_ip, slot)
            if child is None:
                failures.append((slot, "can't login to 8295"))
                continue

            if not gp_check_folder(child, gp_sn, slot):
                failures.append((slot, "GP folder not found"))
                continue

            copied_ok = gp_scp_folder_to_pxe(child, gp_sn, dest_dir, pxe_password)
            if copied_ok:
                successes.append((slot, gp_sn))
                print("[OK] Copied folder %s to %s" % (gp_sn, dest_dir))
            else:
                failures.append((slot, "SCP folder failed"))

        except Exception as e:
            print("[FAIL] Exception on slot %s: %s" % (slot, e))
            failures.append((slot, "Exception: %s" % e))

        finally:
            if child is not None:
                gp_exit(child)

    print("\n======================================")
    print("Finished collecting unlock packages to PXE")
    print("Destination folder: %s" % dest_dir)
    print("FINAL_UNLOCK_FOLDER_NAME=%s" % final_name)
    print("======================================")

    print("Successful: %s" % len(successes))
    for slot, sn in successes:
        print("  slot %s: %s" % (slot, sn))

    print("Failed: %s" % len(failures))
    for slot, reason in failures:
        print("  slot %s: %s" % (slot, reason))


if __name__ == "__main__":
    main()