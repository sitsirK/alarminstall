#!/bin/bash
# Build the alarminstall image for the Samsung Galaxy S20 FE 5G (r8q).
#
# The kernel is cross-built here on the PC; the live root filesystem and the image
# are built on the phone itself (native aarch64 pacstrap, reuses its package
# cache), reached over the USB network link.
#
#   ./build.sh all              everything below, in order
#   ./build.sh initramfs        stage the live /init into the kernel's initramfs dir
#   ./build.sh kernel           build the ISO kernel (Image + modules)
#   ./build.sh stage            collect what the phone needs into out/stage
#   ./build.sh push             copy out/stage to the phone
#   ./build.sh base             only pacstrap the live system's packages on the phone
#   ./build.sh airootfs         build + squash the live system on the phone
#   ./build.sh image            make the bootable image on the phone
#   ./build.sh pull             copy the image back to out/
#
# Env: R8Q (project dir), KSRC, KOUT (ISO kernel build dir), KOUT_MAIN (the
#      installed kernel's build dir, as running on the phone), KDTB (device tree),
#      REPO (r8q-arch checkout), WITH_WIFI=1 (put the phone's Wi-Fi profiles in
#      the image: for private test builds only).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TOP=$(cd "$HERE/../.." && pwd)
R8Q=${R8Q:-/home/sitsirk/r8q-linux}
KSRC=${KSRC:-$R8Q/kernel-work/linux-7.1.2}
KOUT_MAIN=${KOUT_MAIN:-$R8Q/kernel-work/out}
KOUT=${KOUT:-$R8Q/kernel-work/out-iso}
KDTB=${KDTB:-$R8Q/kernel-work/out/arch/arm64/boot/dts/qcom/sm8250-samsung-r8q.dtb}
IRFS=${IRFS:-$R8Q/kernel-work/iso-irfs}
BUSYBOX=${BUSYBOX:-$R8Q/kernel-work/irfs/bin/busybox}
REPO=${REPO:-$R8Q/repo}
PHONE=${PHONE:-$R8Q/tools/r8q.sh}
WITH_WIFI=${WITH_WIFI:-0}
OUT=$HERE/out
STAGE=$OUT/stage
RDIR=/root/alarmiso

log() { echo "== $*"; }

do_initramfs() {
    log "live initramfs -> $IRFS"
    rm -rf "$IRFS"; mkdir -p "$IRFS"/{bin,dev,proc,sys,run,newroot,mnt}
    install -m755 "$BUSYBOX" "$IRFS/bin/busybox"
    install -m755 "$HERE/initramfs/init" "$IRFS/init"
}

do_kernel() {
    log "ISO kernel ($KOUT)"
    make -C "$KSRC" O="$KOUT" ARCH=arm64 LLVM=1 -j"$(nproc)" Image modules
}

# Modules named in a list, plus everything they depend on (from modules.dep).
closure() {
    local depfile=$1; shift
    python3 - "$depfile" "$@" <<'EOF'
import sys, os
dep = {}
for line in open(sys.argv[1]):
    mod, _, rest = line.partition(':')
    dep[mod] = rest.split()
byname = {os.path.basename(m).split('.ko')[0].replace('-', '_'): m for m in dep}
want, seen = [], set()
for n in sys.argv[2:]:
    want.append(byname[n.replace('-', '_')])
while want:
    m = want.pop()
    if m in seen: continue
    seen.add(m); want.extend(dep[m])
print('\n'.join(sorted(seen)))
EOF
}

# stage_modules KOUT LIST DEST: DEST/usr/lib/modules/<kver> = the modules in LIST
# plus their dependencies, DEST/root/ts = the modules in modules.ts (loaded by
# insmod from there, never by udev). The layout the phone runs today.
stage_modules() {
    local kout=$1 list=$2 dest=$3 kver full mdir dst
    kver=$(cat "$kout/include/config/kernel.release")
    full=$OUT/modules-full-$(basename "$kout")
    rm -rf "$full"
    make -C "$KSRC" O="$kout" ARCH=arm64 LLVM=1 INSTALL_MOD_PATH="$full" INSTALL_MOD_STRIP=1 modules_install >/dev/null
    mdir=$full/lib/modules/$kver; dst=$dest/usr/lib/modules/$kver
    mkdir -p "$dst" "$dest/root/ts"
    cp "$mdir"/modules.{order,builtin,builtin.modinfo} "$dst/"
    mapfile -t want < <(grep -v '^#' "$list" | grep -v '^$')
    closure "$mdir/modules.dep" "${want[@]}" | while read -r m; do
        install -D -m644 "$mdir/$m" "$dst/$m"
    done
    while read -r n; do
        [ -z "$n" ] || [ "${n#\#}" != "$n" ] && continue
        f=$(find "$mdir/kernel" -name "$n.ko*" | head -1)
        [ -n "$f" ] || { echo "module $n not built in $kout"; exit 1; }
        install -m644 "$f" "$dest/root/ts/$(basename "${f%.zst}")"
    done < "$HERE/modules.ts"
    echo "   $(basename "$kout"): $(find "$dst" -name '*.ko*' | wc -l) modules in /usr/lib/modules/$kver, $(ls "$dest/root/ts" | wc -l) in /root/ts"
}

do_stage() {
    log "stage -> $STAGE"
    rm -rf "$STAGE"; mkdir -p "$STAGE"

    # The live system: ISO kernel, Wi-Fi modules only.
    install -m644 "$KOUT/arch/arm64/boot/Image" "$STAGE/Image"
    install -m644 "$KDTB" "$STAGE/r8q.dtb"
    stage_modules "$KOUT" "$HERE/modules.lib" "$STAGE/modules"

    # The installed system (alarminstall copies it from the medium's alarminstall/r8q/):
    # the kernel, device tree and module set the phone is running today, plus
    # r8q-arch's rootfs files.
    local p=$STAGE/payload
    mkdir -p "$p"
    install -m644 "$KOUT_MAIN/arch/arm64/boot/Image" "$p/Image"
    install -m644 "$KDTB" "$p/r8q.dtb"
    cp "$KOUT_MAIN/include/config/kernel.release" "$p/kernel.release"
    stage_modules "$KOUT_MAIN" "$HERE/modules.installed" "$OUT/installed-modules"
    tar -C "$OUT/installed-modules" --owner=0 --group=0 -cf "$p/modules.tar" usr root
    cp -a "$REPO/rootfs" "$p/rootfs"

    # r8q files shared with the installed system (one source of truth: r8q-arch).
    local rf=$STAGE/r8q-rootfs
    for f in etc/modprobe.d/r8q-audio-blacklist.conf etc/modprobe.d/r8q-camera-blacklist.conf \
             etc/modprobe.d/r8q-gpu.conf etc/modprobe.d/r8q-wifi-blacklist.conf \
             etc/sysctl.d/50-r8q-printk.conf etc/tmpfiles.d/50-r8q-cpuidle.conf \
             etc/systemd/network/20-usb0.network \
             etc/systemd/system/r8q-usb-gadget.service etc/systemd/system/r8q-wifi.service \
             etc/systemd/system/r8q-battery.service etc/systemd/system/r8q-touch.service \
             usr/local/sbin/r8q-usb-gadget-up.sh; do
        install -D -m"$( [ -x "$REPO/rootfs/$f" ] && echo 755 || echo 644 )" "$REPO/rootfs/$f" "$rf/$f"
    done

    cp -a "$HERE/airootfs" "$STAGE/airootfs"
    cp -a "$HERE/grub" "$STAGE/grub"
    install -m644 "$HERE/packages.live" "$STAGE/"
    install -m755 "$HERE/build-airootfs.sh" "$HERE/mkimage.sh" "$STAGE/"
    mkdir -p "$STAGE/alarminstall"
    tar -C "$TOP" --exclude=__pycache__ -cf - archinstall | tar -C "$STAGE/alarminstall" -xf -
    du -sh "$STAGE"
}

do_push() {
    log "push -> phone:$RDIR/src"
    tar -C "$STAGE" -cf - . | "$PHONE" "rm -rf $RDIR/src && mkdir -p $RDIR/src && tar -C $RDIR/src -xf -"
}

# Long jobs run as transient units on the phone, so a dropped USB link does not
# kill them; output lands in $RDIR/<step>.log.
remote_step() {
    local step=$1 script=$2
    log "$step on the phone (log: $RDIR/$step.log)"
    # PERF=1 (default): every CPU cluster runs the performance governor while the step
    # runs; the previous governors are put back afterwards (a reboot resets them anyway).
    # The leading CPU-wedge theory is a frequency change that never completes, and a build
    # wedged the phone once (2026-11-15).
    "$PHONE" "systemctl reset-failed alarmiso-$step 2>/dev/null
        govs=
        if [ ${PERF:-1} = 1 ]; then
            for p in /sys/devices/system/cpu/cpufreq/policy*; do
                govs=\"\$govs \$p:\$(cat \$p/scaling_governor)\"
                echo performance > \$p/scaling_governor
            done
        fi
        systemd-run --unit=alarmiso-$step --collect --wait --quiet \
            -p StandardOutput=truncate:$RDIR/$step.log -p StandardError=append:$RDIR/$step.log \
            --setenv=WITH_WIFI=$WITH_WIFI --setenv=FRESH=${FRESH:-0} --setenv=BASE_ONLY=${BASE_ONLY:-0} \
            /bin/bash $RDIR/src/$script
        rc=\$?
        for g in \$govs; do echo \${g#*:} > \${g%%:*}/scaling_governor; done
        tail -5 $RDIR/$step.log
        exit \$rc"
}

do_airootfs() { remote_step airootfs build-airootfs.sh; }

# Only the pacstrap (the slow download), e.g. while the kernel still builds.
do_base() {
    log "push package list -> phone:$RDIR/src"
    tar -C "$HERE" -cf - packages.live build-airootfs.sh | "$PHONE" "mkdir -p $RDIR/src && tar -C $RDIR/src -xf -"
    BASE_ONLY=1 remote_step base build-airootfs.sh
}
do_image()    { remote_step image mkimage.sh; }

do_pull() {
    local f; f=$("$PHONE" "ls -t $RDIR/work/alarminstall-r8q-*.iso | head -1")
    log "pull $f"
    mkdir -p "$OUT"
    "$PHONE" "cat $f" > "$OUT/$(basename "$f")"
    ls -la "$OUT/$(basename "$f")"; sha256sum "$OUT/$(basename "$f")"
}

case "${1:-all}" in
    all) do_initramfs; do_kernel; do_stage; do_push; do_airootfs; do_image; do_pull ;;
    initramfs|kernel|stage|push|base|airootfs|image|pull) "do_$1" ;;
    *) sed -n '2,20p' "$0"; exit 1 ;;
esac
