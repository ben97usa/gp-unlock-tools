#!/usr/bin/env python3
# Apply signed_token.bin from PXE to each GP card and unlock it

import os
import re
import subprocess
import sys
import time

import pexpect

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAC_FILE = os.path.join(BASE_DIR, "RM_MAC.txt")

SSH_PASSWORD = "$pl3nd1D"
FIND_IP = "/usr/local/bin/find_ip"

PXE_USER = "qsitoan"
PXE_IP = "192.168.202.50"
PXE_SIGNED_BASE = "/home/RMA_GPCARD/signed_token"
PXE_PASSWORD = "QSI@qmf54321"


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


def gp_login(ip, slot):
    print("[STEP] Trying to open SSH to RM %s for slot %s" % (ip, slot))

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

    print("[STEP] Trying to start serial session on slot %s port 8295" % slot)
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
        print("[STEP] Exiting GP console / RM session")
        child.send("~.")
        child.expect(pexpect.EOF, timeout=10)
    except Exception:
        pass
    try:
        child.close()
    except Exception:
        pass


def gp_run_cmd(child, cmd, timeout=60, print_output=True):
    print("[CMD] %s" % cmd)
    child.sendline(cmd)
    child.expect(r"root@localhost:.*#", timeout=timeout)
    output = child.before

    if print_output:
        print("----- OUTPUT START -----")
        print(output.strip())
        print("----- OUTPUT END -------")

    return output


def gp_pwd(child):
    print("[STEP] Checking current folder on GP")
    output = gp_run_cmd(child, "pwd", timeout=20, print_output=True)
    return output


def gp_prepare_tmp(child):
    print("[STEP] Making sure /tmp is writable and removing old signed_token.bin if exists")
    gp_run_cmd(child, "rm -f /tmp/signed_token.bin", timeout=20, print_output=True)


def gp_check_signed_token_on_pxe(gp_sn):
    pxe_file = os.path.join(PXE_SIGNED_BASE, gp_sn, "signed_token.bin")
    print("[STEP] Checking signed token on PXE: %s" % pxe_file)

    if os.path.isfile(pxe_file):
        print("[OK] Found signed_token.bin for %s on PXE" % gp_sn)
        return True

    print("[FAIL] signed_token.bin not found on PXE for %s" % gp_sn)
    return False


def gp_copy_signed_token_from_pxe(child, gp_sn):
    cmd = "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null qsitoan@%s:%s/%s/signed_token.bin /tmp/signed_token.bin" % (
        PXE_IP, PXE_SIGNED_BASE, gp_sn
    )

    print("[STEP] Copying signed_token.bin from PXE to GP")
    print("[INFO] GP SN compare matched: %s" % gp_sn)
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
            print("[INFO] SCP asking PXE password -> sending PXE password")
            child.sendline(PXE_PASSWORD)
            continue

        if idx == 2:
            print("[OK] Back to GP prompt after SCP")
            break

        if idx == 3:
            print("[FAIL] SCP timeout while copying signed_token.bin for %s" % gp_sn)
            return False

        if idx == 4:
            print("[FAIL] SCP EOF while copying signed_token.bin for %s" % gp_sn)
            return False

    output = gp_run_cmd(child, "ls -l /tmp/signed_token.bin", timeout=20, print_output=True)
    if "No such file" in output:
        print("[FAIL] /tmp/signed_token.bin not found after SCP")
        return False

    print("[OK] signed_token.bin copied to GP successfully")
    return True


def gp_get_policy(child):
    print("[STEP] Running ovb_lock policy get /tmp/policy.bin")
    output = gp_run_cmd(child, "ovb_lock policy get /tmp/policy.bin", timeout=60, print_output=True)
    return output


def gp_policy_is_success(output):
    return "Policy=0x2" in output


def gp_unlock(child):
    print("[STEP] Policy is not 0x2, trying unlock command")
    output = gp_run_cmd(child, "ovb_lock policy set /tmp/signed_token.bin", timeout=120, print_output=True)
    return output


def main():
    print("==================================================")
    print(" APPLY SIGNED TOKEN TO GP CARD FROM PXE ")
    print("==================================================")

    print("[STEP] Reading RM MAC")
    rack_mac = get_mac_from_file(MAC_FILE)
    print("[INFO] RM MAC = %s" % rack_mac)

    print("[STEP] Finding RM IP")
    rm_ip = find_ip(rack_mac)
    if not rm_ip:
        print("[FAIL] Failed to find RM IP from RM_MAC.txt")
        sys.exit(1)

    print("[OK] RM IP = %s" % rm_ip)

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

        print("\n==================================================")
        print("[STEP] Processing slot %s (%s/%s)" % (slot, current, total))
        print("==================================================")

        print("[STEP] Getting GP_CARD_SN from FRU")
        fru_cmd = "set system cmd -i %s -c 'fru print 2'" % slot
        ok, fru_output = exec_cmd(rm_ip, fru_cmd)

        if not ok:
            print("[FAIL] FRU command failed on slot %s" % slot)
            failures.append((slot, "FRU command failed"))
            continue

        gp_sn = extract_board_serial(fru_output)
        if not gp_sn:
            print("[FAIL] Could not extract GP_CARD_SN on slot %s" % slot)
            failures.append((slot, "No GP_CARD_SN"))
            continue

        print("[OK] GP_CARD_SN from slot %s = %s" % (slot, gp_sn))

        if not gp_check_signed_token_on_pxe(gp_sn):
            failures.append((slot, "signed_token.bin not found on PXE for %s" % gp_sn))
            continue

        child = None
        try:
            child = gp_login(rm_ip, slot)
            if child is None:
                failures.append((slot, "can't login to 8295"))
                continue

            gp_pwd(child)

            print("[STEP] Checking GP folder /tmp/%s" % gp_sn)
            output = gp_run_cmd(child, "ls -ld /tmp/%s" % gp_sn, timeout=20, print_output=True)
            if "No such file" in output:
                print("[FAIL] /tmp/%s not found on GP" % gp_sn)
                failures.append((slot, "/tmp/%s not found" % gp_sn))
                continue

            print("[OK] GP current SN matches target signed_token folder: %s" % gp_sn)

            gp_prepare_tmp(child)

            copied_ok = gp_copy_signed_token_from_pxe(child, gp_sn)
            if not copied_ok:
                failures.append((slot, "Failed to copy signed_token.bin"))
                continue

            print("[STEP] Checking policy before unlock")
            policy_before = gp_get_policy(child)

            if gp_policy_is_success(policy_before):
                print("[OK] Policy=0x2")
                print("[SUCCESS] successfully unlock GP CARD %s on slot %s" % (gp_sn, slot))
                successes.append((slot, gp_sn, "already Policy=0x2"))
                continue

            print("[INFO] Policy is NOT 0x2, unlock is required")
            gp_unlock(child)

            print("[STEP] Verifying policy after unlock")
            policy_after = gp_get_policy(child)

            if gp_policy_is_success(policy_after):
                print("[SUCCESS] successfully unlock GP CARD %s on slot %s" % (gp_sn, slot))
                successes.append((slot, gp_sn, "unlock success"))
            else:
                print("[FAIL] Failed to unlock GP CARD %s on slot %s" % (gp_sn, slot))
                failures.append((slot, "unlock failed for %s" % gp_sn))

        except Exception as e:
            print("[FAIL] Exception on slot %s: %s" % (slot, e))
            failures.append((slot, "Exception: %s" % e))

        finally:
            if child is not None:
                gp_exit(child)

    print("\n==================================================")
    print(" FINAL REPORT ")
    print("==================================================")

    print("Successful: %s" % len(successes))
    for slot, gp_sn, msg in successes:
        print("  slot %s : %s : %s" % (slot, gp_sn, msg))

    print("Failed: %s" % len(failures))
    for slot, reason in failures:
        print("  slot %s : %s" % (slot, reason))


if __name__ == "__main__":
    main()