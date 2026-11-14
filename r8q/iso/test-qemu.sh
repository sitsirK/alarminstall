#!/bin/bash
# Boot the alarminstall image under QEMU (aarch64 + edk2) on a PC: GRUB, the ISO
# kernel, the live initramfs, systemd and the installer's start-up all run;
# nothing phone-specific does (alarminstall itself refuses: not an r8q).
#
#   ./test-qemu.sh start [IMAGE]   boot (default: newest out/*.iso), as a USB stick;
#                                  TARGET=1 adds out/qemu/ufs.img as a phone-like disk
#   ./test-qemu.sh shot NAME       screenshot -> out/qemu/NAME.ppm (+ .png if python-pillow)
#   ./test-qemu.sh key KEY...      send keys (QEMU names: up down ret esc a b ...)
#   ./test-qemu.sh type TEXT       type a line of text and Enter
#   ./test-qemu.sh log             the serial console so far
#   ./test-qemu.sh stop
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=$HERE/out/qemu
SOCK=$W/monitor.sock
EDK2=${EDK2:-/usr/share/edk2/aarch64}
mkdir -p "$W"

mon() { python3 - "$SOCK" "$@" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.2); s.recv(65536)
for cmd in sys.argv[2:]:
    s.sendall((cmd + '\n').encode()); time.sleep(0.4)
EOF
}

case "${1:-}" in
start)
    img=${2:-$(ls -t "$HERE"/out/*.iso | head -1)}
    cp "$EDK2/QEMU_VARS.fd" "$W/vars.fd"
    # TARGET=1: out/qemu/ufs.img as a fixed (non-removable) disk with 4096-byte sectors, like the
    # phone's UFS (GPT names apnhlos, cache, userdata) — an install target.
    target=()
    if [ "${TARGET:-0}" = 1 ]; then
        target=(-drive if=none,format=raw,file="$W/ufs.img",id=ufs
                -device usb-storage,drive=ufs,removable=off,logical_block_size=4096,physical_block_size=4096)
    fi
    : > "$W/serial.log"
    setsid qemu-system-aarch64 -M virt,gic-version=3 -cpu cortex-a76 -smp 4 -m 3G \
        -display none -no-reboot \
        -drive if=pflash,format=raw,readonly=on,file="$EDK2/QEMU_EFI.fd" \
        -drive if=pflash,format=raw,file="$W/vars.fd" \
        -device ramfb -device qemu-xhci -device usb-kbd \
        -drive if=none,format=raw,readonly=on,file="$img",id=stick -device usb-storage,drive=stick,removable=on \
        "${target[@]}" \
        -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
        -serial file:"$W/serial.log" -monitor unix:"$SOCK",server,nowait \
        > "$W/qemu.log" 2>&1 < /dev/null &
    echo "started: $img"
    ;;
shot)
    mon "screendump $W/$2.ppm"
    python3 -c "from PIL import Image; Image.open('$W/$2.ppm').save('$W/$2.png')" 2>/dev/null && echo "$W/$2.png" || echo "$W/$2.ppm"
    ;;
key)
    shift; cmds=(); for k in "$@"; do cmds+=("sendkey $k"); done; mon "${cmds[@]}"
    ;;
type)
    # type TEXT: send a line of text (letters, digits, = - _ . / space), then Enter
    shift; cmds=()
    for ((i = 0; i < ${#1}; i++)); do
        c=${1:i:1}
        case "$c" in
            [a-z0-9]) cmds+=("sendkey $c") ;;
            [A-Z]) cmds+=("sendkey shift-${c,,}") ;;
            ' ') cmds+=("sendkey spc") ;; '=') cmds+=("sendkey equal") ;; '-') cmds+=("sendkey minus") ;;
            '_') cmds+=("sendkey shift-minus") ;; '.') cmds+=("sendkey dot") ;; '/') cmds+=("sendkey slash") ;;
        esac
    done
    cmds+=("sendkey ret"); mon "${cmds[@]}"
    ;;
log)
    cat "$W/serial.log"
    ;;
stop)
    mon quit 2>/dev/null || true
    ;;
*)
    sed -n '2,12p' "$0"; exit 1 ;;
esac
