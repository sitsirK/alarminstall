# alarminstall for the Samsung Galaxy S20 FE 5G (r8q)

A bootable image that starts straight into **alarminstall**, this fork of
archinstall, and installs Arch Linux ARM with the r8q kernel onto the phone.

## What you need

- A Galaxy S20 FE 5G (Snapdragon 865, codename r8q) with an unlocked bootloader.
- **Mu-Silicium with SD-card support** on `BOOT`: the `r8q` branch of
  [sitsirK/Mu-Silicium](https://github.com/sitsirK/Mu-Silicium/tree/r8q), ready
  to build ([r8q-arch INSTALLATION §0](https://github.com/sitsirK/r8q-arch/blob/main/INSTALLATION.md#0-the-alarminstall-image)).
  It powers the SD slot and adds an "SD Card" boot-menu entry; upstream
  Mu-Silicium does not see the SD card on this phone.
- A microSD card, Wi-Fi, and for typing the Wi-Fi password: a PC with a USB cable.

## Using it

1. Download the `.iso` from
   [r8q-arch's Releases](https://github.com/sitsirK/r8q-arch/releases) and
   check it against `SHA256SUMS`.
2. Write it to a microSD card (`dd`), or copy it onto a Ventoy card (several
   versions side by side are fine).
3. Reboot, press **Vol-Up** at "[Volume Up] Boot Manager", pick **SD Card**.
4. The installer comes up on the screen: **Vol-Up / Vol-Down** move (hold to
   scroll), **Power** selects.

Installing **erases the `userdata` partition** (Android, or a previous Linux) and
reformats `cache` as the EFI system partition. The partition table is not changed.

## Getting online

The installer downloads packages. The phone has no keyboard, so connect from a
PC over USB (it gets an address from the phone; the bar at the bottom of the
screen shows where to connect):

```
ssh root@172.16.42.1                 # password root; the host key changes every boot
nmtui                                # or: nmcli dev wifi connect "NAME" password "PASSWORD"
tmux attach -t alarminstall          # the installer, now with a keyboard
```

If the installer gave up waiting for the network, type `alarminstall` there.
The Wi-Fi network is copied to the installed system. A Linux PC can also share
its own connection over the cable with r8q-arch's
[`scripts/host-tether.sh`](https://github.com/sitsirK/r8q-arch/blob/main/scripts/host-tether.sh).

## After installing

Hostname `alarm`, root password `alarm`, user `alarm` / `alarm` (sudo). With
"SSH over USB" on, root can log in with that password over USB and Wi-Fi:
change both passwords (`passwd`).

## What is supported

Choices are marked in the menus: plain = tested on the phone, yellow = untested,
red and struck through = not supported yet (cannot be selected). The table is
`archinstall/lib/r8q/support.py`.

- **Phone → Display**: *msm-drm* (Linux drives the display: 120 Hz, brightness,
  real screen-off) needs the S6E3FC3 panel; the installer reads which of the
  r8q's three panels yours is from the bootloader's log and picks for you.
  *simpledrm* keeps the picture the bootloader set up (60 Hz, any panel).
- **Kernels → latest kernel** (experimental): at the end of the install the phone
  downloads the newest stable kernel from kernel.org, applies the r8q patches and
  builds it itself (30-60 minutes, needs the network). If a patch no longer
  applies or the build fails, the tested kernel stays. `r8q-kernel-latest` on the
  installed system tries again later; how to roll back is at the top of that script.

## Building

`r8q/iso/build.sh all`. The kernel is cross-built on a PC (r8q-arch's kernel
tree); the live system and the image are built on an aarch64 Arch Linux ARM
machine over SSH (the r8q itself works). See the comments at the top of
`build.sh`, `build-airootfs.sh` and `mkimage.sh`.

`WITH_WIFI=1` copies the build machine's Wi-Fi networks into the image, so it
boots online. Such an image contains Wi-Fi passwords: never publish it.
