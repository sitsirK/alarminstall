# alarminstall for the Samsung Galaxy S20 FE 5G (r8q)

A bootable image that starts straight into **alarminstall**, this fork of
archinstall, and installs Arch Linux ARM with the r8q kernel onto the phone.

## Using it

Needs a phone that already runs **Mu-Silicium with the SD-card boot option**
([sitsirK/Mu-Silicium](https://github.com/sitsirK/Mu-Silicium), branches
`sd-card-power` + `sd-card-boot-option`) on `BOOT`.

1. Write the image to a microSD card (`dd`), or copy the `.iso` onto a Ventoy card.
2. Reboot, press **Vol-Up** at "[Volume Up] Boot Manager", pick **SD Card**.
3. The installer comes up on the screen: **Vol-Up / Vol-Down** move, **Power** selects.
   From a PC, `ssh root@172.16.42.1` (password `root`) and `tmux attach -t alarminstall`
   gives the same session with a keyboard.

Installing **erases the `userdata` partition** (Android, or a previous Linux) and
reformats `cache` as the EFI system partition. The partition table is not changed.

Test-build defaults: hostname `alarm`, root password `alarm`, user `alarm` / `alarm`.

## What is supported

Choices are marked in the menus: plain = tested on the phone, yellow = untested,
struck through = not supported yet (cannot be selected). The table is
`archinstall/lib/r8q/support.py`.

## Building

`r8q/iso/build.sh all`. The kernel is cross-built on a PC (r8q-arch's kernel
tree); the live system and the image are built on an aarch64 Arch Linux ARM
machine over SSH (the r8q itself works). See the comments at the top of
`build.sh`, `build-airootfs.sh` and `mkimage.sh`.

`WITH_WIFI=1` copies the build machine's Wi-Fi networks into the image, so it
boots online. Such an image contains Wi-Fi passwords: never publish it.
