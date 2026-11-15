#!/bin/bash
# Turn the squashed live system into a bootable image. Runs on aarch64 Arch Linux
# ARM (needs grub, libisoburn, mtools, dosfstools) after build-airootfs.sh.
#
# The result is both:
#   - a hybrid disk image: GPT with an EFI system partition holding GRUB, the
#     kernel and the device tree, so Mu-Silicium's "SD Card" boot option starts it
#     when the image is written straight to a card; and
#   - an ISO9660 image with /boot/grub/grub.cfg, which Ventoy runs as-is.
set -euo pipefail
SRC=${SRC:-/root/alarmiso/src}
W=${W:-/root/alarmiso/work}
I=$W/iso
# An image with Wi-Fi passwords in it (build-airootfs.sh WITH_WIFI=1) says so in its name.
SUFFIX=
[ -e "$W/airootfs/etc/alarminstall-CONTAINS-WIFI-PASSWORDS" ] && SUFFIX=-PRIVATE-wifi
OUT=${OUT:-$W/alarminstall-r8q-$(date +%Y.%m.%d)$SUFFIX.iso}

[ -f "$W/airootfs.done" ] || { echo "the live system's build did not finish (no $W/airootfs.done): run build-airootfs.sh again"; exit 1; }
unsquashfs -s "$I/alarminstall/aarch64/airootfs.sfs" >/dev/null || { echo "airootfs.sfs is not a valid squashfs"; exit 1; }

mkdir -p "$I/boot/grub" "$W/efi"
install -m644 "$SRC/Image" "$I/boot/Image"
install -m644 "$SRC/r8q.dtb" "$I/boot/r8q.dtb"
# A per-build ID, in grub.cfg (kernel command line) and in the image: the live
# /init takes the image whose ID matches (several images on one Ventoy card).
ID=$(date -u +%Y%m%d%H%M%S)
sed "s/@ID@/$ID/" "$SRC/grub/grub.cfg" > "$I/boot/grub/grub.cfg"
# What alarminstall installs: kernel, device tree, modules, r8q files.
rm -rf "$I/alarminstall/r8q"; mkdir -p "$I/alarminstall"
cp -a "$SRC/payload" "$I/alarminstall/r8q"
echo "$ID" > "$I/alarminstall/id"

echo "== GRUB (arm64-efi, standalone)"
grub-mkstandalone -O arm64-efi -o "$W/efi/BOOTAA64.EFI" \
    --modules="part_gpt part_msdos fat iso9660 search search_label search_fs_file linux fdt normal configfile echo test halt smbios" \
    --locales="" --themes="" --fonts="" \
    "boot/grub/grub.cfg=$SRC/grub/embedded.cfg"

# A copy in the ISO filesystem too: Ventoy and other tools look for /EFI/BOOT there.
mkdir -p "$I/EFI/BOOT"; install -m644 "$W/efi/BOOTAA64.EFI" "$I/EFI/BOOT/BOOTAA64.EFI"

echo "== EFI system partition image"
size_kib=$(( ( $(stat -c%s "$I/boot/Image") + $(stat -c%s "$I/boot/r8q.dtb") \
              + $(stat -c%s "$W/efi/BOOTAA64.EFI") ) / 1024 + 4096 ))
rm -f "$W/efiboot.img"
mkfs.fat -C -n ALARMEFI "$W/efiboot.img" "$size_kib" >/dev/null
export MTOOLS_SKIP_CHECK=1
mmd -i "$W/efiboot.img" ::/EFI ::/EFI/BOOT ::/boot ::/boot/grub
mcopy -i "$W/efiboot.img" "$W/efi/BOOTAA64.EFI" ::/EFI/BOOT/BOOTAA64.EFI
mcopy -i "$W/efiboot.img" "$I/boot/Image" "$I/boot/r8q.dtb" ::/boot/
mcopy -i "$W/efiboot.img" "$I/boot/grub/grub.cfg" ::/boot/grub/

echo "== ISO"
rm -f "$OUT"
xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames -joliet -joliet-long -rational-rock \
    -volid ALARMINSTALL -appid "alarminstall for the Samsung Galaxy S20 FE 5G (r8q)" \
    -partition_offset 16 \
    -append_partition 2 C12A7328-F81F-11D2-BA4B-00A0C93EC93B "$W/efiboot.img" \
    -appended_part_as_gpt \
    -eltorito-alt-boot -e --interval:appended_partition_2:all:: -no-emul-boot \
    -no-pad -output "$OUT" "$I" 2>&1 | grep -v '^xorriso : UPDATE' || true
ls -la "$OUT"; sha256sum "$OUT"
