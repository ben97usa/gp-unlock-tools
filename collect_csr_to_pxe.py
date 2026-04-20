#!/usr/bin/env python3
#SCP GP CARD SN FOLDER TO PXE
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
BASE_DIR = "/home/qsitoan"


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


def get_unique_unlock_folder(base_dir, base_name):
    candidate = os.path.join(base_dir, base_name)
    count = 1

    while os.path.exists(candidate):
        count += 1
        candidate = os.path.join(base_dir, "%s_%s" % (base_name, count))

    os.makedirs(candidate)
    return candidate


def gp_login(ip, slot):
    print("Opening SSH to RM %s for slot %s" % (ip, slot))

    child = pexpect.spawn(
        "sshpass -p '%s' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@%s" % (SSH_PASSWORD, ip),
        encoding="utf-8",
        timeout=60
    )

    child.logfile = sys.stdout

    try:
        child.expect(r"#", timeout=30)
    except Exception:
        print("can't login to RM on slot %s" % slot)
        try:
            child.close()
        except Exception:
            pass
        return None

    print("Starting serial session on slot %s port 8295" % slot)
    child.sendline("start serial session -i %s -p 8295" % slot)

    time.sleep(2)
    child.sendline("")

    try:
        child.expect(r"root@localhost:", timeout=60)
    except Exception:
        print("can't login to 8295 on slot %s" % slot)
        try:
            child.close()
        except Exception:
            pass
        return None

    print("Entered GP Console for slot %s" % slot)
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
    print("Checking GP folder: /tmp/%s" % gp_sn)
    child.sendline("ls /tmp/%s" % gp_sn)

    try:
        child.expect(r"root@localhost:", timeout=20)
    except Exception:
        print("can't see slot %s" % slot)
        return False

    output = child.before

    if "No such file" in output:
        print("can't see slot %s" % slot)
        return False

    return True


def gp_scp_folder_to_pxe(child, gp_sn, dest_dir, pxe_password):
    src = "/tmp/%s" % gp_sn
    dest = "%s@%s:%s/" % (PXE_USER, PXE_IP, dest_dir)

    cmd = "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r %s %s" % (src, dest)

    print("Running SCP from GP CARD to PXE")
    print(cmd)

    child.sendline(cmd)

    password_count = 0

    while True:
        idx = child.expect(
            [
                r"yes/no",
                r"[Pp]assword:",
                r"root@localhost:",
                pexpect.TIMEOUT,
                pexpect.EOF
            ],
            timeout=120
        )

        if idx == 0:
            print("SSH asking yes/no, sending yes")
            child.sendline("yes")
            continue

        if idx == 1:
            password_count += 1
            print("SCP asking PXE password, sending password attempt %s" % password_count)
            child.sendline(pxe_password)
            continue

        if idx == 2:
            print("Back to GP prompt after SCP")
            break

        if idx == 3:
            print("SCP timeout for %s" % gp_sn)
            return False

        if idx == 4:
            print("SCP EOF for %s" % gp_sn)
            return False

    copied_path = os.path.join(dest_dir, gp_sn)
    if os.path.isdir(copied_path):
        print("Verified copied folder exists on PXE: %s" % copied_path)
        return True

    print("Copied folder not found on PXE: %s" % copied_path)
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 collect_unlock_pkgs.py <PXE_PASSWORD>")
        sys.exit(1)

    pxe_password = sys.argv[1]

    print("Reading RM MAC from %s" % MAC_FILE)
    rack_mac = get_mac_from_file(MAC_FILE)
    print("Using RM MAC: %s" % rack_mac)

    print("Finding RM IP...")
    rm_ip = find_ip(rack_mac)
    if not rm_ip:
        print("Failed to find RM IP from RM_MAC.txt")
        sys.exit(1)

    print("RM IP: %s" % rm_ip)

    now = datetime.now()
    today_base = now.strftime("%B") + str(now.day) + "_unlock"

    print("Creating destination folder on PXE...")
    dest_dir = get_unique_unlock_folder(BASE_DIR, today_base)
    final_name = os.path.basename(dest_dir)

    print("Ready folder: %s" % dest_dir)
    print("FINAL_UNLOCK_FOLDER_NAME=%s" % final_name)

    print("Running show manager info...")
    ok, manager_info = exec_rm_cmd(rm_ip, "show manager info")
    print("show manager info finished")

    if not ok:
        print("Failed to retrieve manager info from rack manager")
        print(manager_info)
        sys.exit(1)

    slots = get_server_slots(manager_info)
    print("Server slots at %s (%s): %s" % (rack_mac, rm_ip, slots))

    if len(slots) == 0:
        print("No valid slots found from show manager info")
        sys.exit(1)

    successes = []
    failures = []

    total = len(slots)
    index = 0

    for slot in slots:
        index += 1
        print("\n==============================")
        print("[%s/%s] Processing slot %s" % (index, total, slot))
        print("==============================")

        fru_cmd = "set system cmd -i %s -c 'fru print 2'" % slot
        print("Running FRU command on slot %s" % slot)
        ok, fru_output = exec_cmd(rm_ip, fru_cmd)

        if not ok:
            print("FRU command failed for slot %s" % slot)
            print(fru_output)
            failures.append((slot, "FRU command failed"))
            continue

        gp_sn = extract_board_serial(fru_output)
        if not gp_sn:
            print("Could not extract serial for slot %s" % slot)
            print(fru_output)
            failures.append((slot, "No serial"))
            continue

        print("GP SN: %s" % gp_sn)

        child = None
        try:
            child = gp_login(rm_ip, slot)
            if child is None:
                failures.append((slot, "can't login to 8295"))
                continue

            folder_exists = gp_check_folder(child, gp_sn, slot)
            if not folder_exists:
                failures.append((slot, "can't see slot %s" % slot))
                continue

            copied_ok = gp_scp_folder_to_pxe(child, gp_sn, dest_dir, pxe_password)
            if copied_ok:
                successes.append((slot, gp_sn))
                print("Copied %s to %s" % (gp_sn, dest_dir))
            else:
                failures.append((slot, "SCP failed for %s" % gp_sn))

        except Exception as e:
            print("Exception on slot %s: %s" % (slot, e))
            failures.append((slot, "Exception: %s" % e))

        finally:
            if child is not None:
                gp_exit(child)

    print("\nFinished collecting unlock packages")
    print("Destination folder: %s" % dest_dir)
    print("FINAL_UNLOCK_FOLDER_NAME=%s" % final_name)

    print("Successful: %s" % len(successes))
    for slot, sn in successes:
        print("  slot %s: %s" % (slot, sn))

    print("Failed: %s" % len(failures))
    for slot, reason in failures:
        print("  slot %s: %s" % (slot, reason))


if __name__ == "__main__":
    main()