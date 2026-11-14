#!/bin/bash
# Build the live root filesystem and squash it. Runs ON AN aarch64 ARCH LINUX ARM
# SYSTEM (the r8q itself works: native pacstrap, and its package cache saves most
# of the download). build.sh stages everything into $SRC first.
#
#   SRC=/root/alarmiso/src  (staged by build.sh)   W=/root/alarmiso/work
#   FRESH=1      pacstrap a new base even if packages.live is unchanged
#   BASE_ONLY=1  stop after the pacstrap (to start the download early)
#   WITH_WIFI=1  copy THIS system's NetworkManager Wi-Fi profiles into the image.
#                The image then holds Wi-Fi passwords: never publish it.
set -euo pipefail
SRC=${SRC:-/root/alarmiso/src}
W=${W:-/root/alarmiso/work}
R=$W/airootfs
SFS=$W/iso/alarminstall/aarch64/airootfs.sfs
KVER=$(ls "$SRC/modules/usr/lib/modules" 2>/dev/null || true)

log() { echo "== $(date +%T) $*"; }

# The pacstrapped base is cached in $W/base and reused while packages.live is
# unchanged (FRESH=1 forces a new one); each build customises a fresh copy of it.
B=$W/base
PKGSUM=$(sha256sum "$SRC/packages.live" | cut -d' ' -f1)
if [ "${FRESH:-0}" = 1 ] || [ "$(cat "$W/base.packages" 2>/dev/null)" != "$PKGSUM" ]; then
    if mountpoint -q "$B/proc" 2>/dev/null; then umount -R "$B"; fi
    rm -rf "$B" "$W/base.packages"; mkdir -p "$B"
    log "pacstrap ($(grep -cv '^#' "$SRC/packages.live") packages)"
    mapfile -t PKGS < <(grep -v '^#' "$SRC/packages.live" | grep -v '^$')
    # Wi-Fi roaming here resets every TCP connection: retry, partial downloads
    # resume from the cache. -c = use this system's package cache.
    for try in 1 2 3 4 5 6 7 8; do
        if pacstrap -c -C /etc/pacman.conf -M "$B" "${PKGS[@]}" --disable-download-timeout; then break; fi
        [ $try = 8 ] && { log "pacstrap failed 8 times"; exit 1; }
        log "pacstrap failed (try $try), retrying in 10 s"; sleep 10
    done
    echo "$PKGSUM" > "$W/base.packages"
else
    log "reusing the pacstrapped base ($B)"
fi
[ "${BASE_ONLY:-0}" = 1 ] && { log "base only: done"; exit 0; }

# The image step only uses a live system whose build reached the end (see mkimage.sh):
# a build cut short (the phone wedged mid-build once) must not end up in an image.
rm -f "$W/airootfs.done"
rm -rf "$R"
cp -a "$B" "$R"

log "r8q files (services, module blacklists, sysctl, tmpfiles, USB gadget)"
cp -a "$SRC/r8q-rootfs/." "$R/"
log "live-system files"
cp -a "$SRC/airootfs/." "$R/"
chmod 700 "$R/root"

log "kernel modules $KVER"
cp -a "$SRC/modules/." "$R/"
depmod -b "$R" "$KVER"

log "Wi-Fi firmware (QCA6390) from this system"
mkdir -p "$R/usr/lib/firmware/ath11k"
cp -a /usr/lib/firmware/ath11k/QCA6390 "$R/usr/lib/firmware/ath11k/"

rm -f "$R/etc/alarminstall-CONTAINS-WIFI-PASSWORDS"
if [ "${WITH_WIFI:-0}" = 1 ]; then
    log "Wi-Fi profiles from this system (the image now contains Wi-Fi passwords)"
    install -d -m 700 "$R/etc/NetworkManager/system-connections"
    for f in /etc/NetworkManager/system-connections/*.nmconnection; do
        [ -e "$f" ] && install -m 600 "$f" "$R/etc/NetworkManager/system-connections/"
    done
    echo "This image was built with WITH_WIFI=1. Do not publish it." > "$R/etc/alarminstall-CONTAINS-WIFI-PASSWORDS"
fi

log "alarminstall"
rm -rf "$R/opt/alarminstall"; mkdir -p "$R/opt"
cp -a "$SRC/alarminstall" "$R/opt/alarminstall"

log "configuration"
echo root:root | chpasswd -R "$R"
echo 'LANG=C.UTF-8' > "$R/etc/locale.conf"
ln -sf /usr/share/zoneinfo/UTC "$R/etc/localtime"
# Our kernel has no Landlock: pacman's download sandbox must be off.
grep -q '^DisableSandbox' "$R/etc/pacman.conf" || sed -i '/^\[options\]/a DisableSandbox' "$R/etc/pacman.conf"
cp /etc/pacman.d/mirrorlist "$R/etc/pacman.d/mirrorlist"
systemctl --root="$R" enable sshd.service NetworkManager.service systemd-networkd.service systemd-timesyncd.service \
    r8q-usb-gadget.service r8q-touch.service r8q-battery.service r8q-wifi.service \
    r8q-keys.service r8q-keyrepeat.service pacman-init.service
systemctl --root="$R" disable NetworkManager-wait-online.service systemd-networkd-wait-online.service 2>/dev/null || true
# Suspend is a hard reset on this SoC.
systemctl --root="$R" mask sleep.target suspend.target hibernate.target \
    hybrid-sleep.target suspend-then-hibernate.target
rm -f "$R/etc/machine-id"
# pacstrap left a keyring initialised at build time; every copy of the image would
# share its master key. pacman-init.service makes a fresh one at boot.
rm -rf "$R/etc/pacman.d/gnupg"
rm -rf "$R/var/cache/pacman/pkg/"* "$R/var/lib/pacman/sync/"*

log "squashfs"
mkdir -p "$(dirname "$SFS")"
mksquashfs "$R" "$SFS" -noappend -no-xattrs -comp zstd -Xcompression-level 15 -b 1M >/dev/null
ls -la "$SFS"
sync
date +%s > "$W/airootfs.done"
log "done"
