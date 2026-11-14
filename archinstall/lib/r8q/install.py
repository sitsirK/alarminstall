"""
What alarminstall does to the new system beyond archinstall's own steps, for the
Samsung Galaxy S20 FE 5G (r8q). This is the on-device version of r8q-arch's
scripts/install-arch.sh plus the INSTALLATION.md sections for each option.

The kernel, its modules and the r8q files come from the live medium
(device.PAYLOAD): the same kernel and files the phone was tested with.
"""

import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import override

from archinstall.lib.args import ArchConfig
from archinstall.lib.installer import Installer
from archinstall.lib.log import info, warn
from archinstall.lib.models.device import DiskLayoutConfiguration
from archinstall.lib.r8q import device
from archinstall.lib.r8q.models import R8qBootloader, R8qConfiguration, TouchChip

# Always installed: Wi-Fi (firmware, NetworkManager, setpci for r8q-wifi.service), SSH, filesystems.
BASE_PACKAGES = [
	'base',
	# ALARM's base pulls archlinux-keyring only; its packages are signed with these keys.
	'archlinuxarm-keyring',
	'sudo',
	'nano',
	'less',
	'networkmanager',
	'wireless-regdb',
	'linux-firmware-atheros',
	'pciutils',
	'openssh',
	'dosfstools',
	'e2fsprogs',
]

GPU_PACKAGES = ['mesa', 'vulkan-freedreno', 'linux-firmware-qcom']
CAMERA_PACKAGES = ['libcamera', 'libcamera-tools', 'libcamera-ipa', 'pipewire-libcamera']

ZAP = 'usr/lib/firmware/qcom/sm8250/a650_zap'

SLEEP_TARGETS = ['sleep.target', 'suspend.target', 'hibernate.target', 'hybrid-sleep.target', 'suspend-then-hibernate.target']

LOGIND = """\
# alarminstall (r8q): suspend is a hard reset on this SoC (s2idle), and the
# Power button must not switch the phone off by accident.
[Login]
HandlePowerKey=ignore
HandleSuspendKey=ignore
HandleHibernateKey=ignore
HandleLidSwitch=ignore
IdleAction=ignore
"""

SSHD = """\
# alarminstall (r8q): a phone with no keyboard is reached over SSH.
# Root logs in with a password: change it (passwd), or switch to keys.
PermitRootLogin yes
PasswordAuthentication yes
"""

SWAY_PROFILE = """\
[ -f ~/.bashrc ] && . ~/.bashrc
# alarminstall (r8q): start sway on the tty1 autologin console (ssh sessions are unaffected).
# r8q-gpu.service loads msm after multi-user, so wait for the render node; without
# it sway renders on the CPU (pixman).
if [ -z "$WAYLAND_DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    for i in $(seq 1 30); do [ -e /dev/dri/renderD128 ] && break; [ -e /etc/alarminstall/no-gpu ] && break; sleep 1; done
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    export WLR_DRM_DEVICES=/dev/dri/card0
    if [ -e /dev/dri/renderD128 ]; then
        # Render on the Adreno 650 (turnip), scan out on simpledrm card0.
        export WLR_RENDER_DRM_DEVICE=/dev/dri/renderD128
        export WLR_RENDERER=vulkan
    else
        export WLR_RENDERER=pixman
    fi
    exec sway > /tmp/sway.log 2>&1
fi
"""


class R8qInstaller(Installer):
	"""archinstall's Installer without a kernel package or mkinitcpio: the r8q kernel comes from the medium."""

	def __init__(self, target: Path, disk_config: DiskLayoutConfiguration, packages: list[str], silent: bool = False) -> None:
		super().__init__(target, disk_config, base_packages=list(packages), kernels=['linux-r8q'], silent=silent)
		# The base class adds each kernel as a package to pacstrap; linux-r8q is not one.
		self._base_packages = [p for p in self._base_packages if p != 'linux-r8q']

	@override
	def _get_microcode(self) -> None:
		return None


def base_packages(_r8q: R8qConfiguration) -> list[str]:
	return list(BASE_PACKAGES)


# --- helpers ------------------------------------------------------------------------


def _chroot(inst: Installer, *argv: str) -> None:
	info('r8q (chroot): ' + ' '.join(argv))
	subprocess.run(['arch-chroot', str(inst.target), *argv], check=True)


def _write(inst: Installer, rel: str, text: str, mode: int = 0o644) -> None:
	path = inst.target / rel
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(text)
	path.chmod(mode)


def _put(inst: Installer, rel: str, mode: int | None = None) -> None:
	"""Copy one file from the r8q rootfs overlay on the medium to the same path on the target."""
	src = device.PAYLOAD / 'rootfs' / rel
	dst = inst.target / rel
	dst.parent.mkdir(parents=True, exist_ok=True)
	shutil.copyfile(src, dst)
	dst.chmod(mode if mode is not None else (0o755 if src.stat().st_mode & 0o111 else 0o644))


def _enable(inst: Installer, *units: str) -> None:
	_chroot(inst, 'systemctl', 'enable', *units)


def _first_user(config: ArchConfig) -> str | None:
	if config.auth_config and config.auth_config.users:
		return config.auth_config.users[0].username
	return None


def profile_names(config: ArchConfig) -> list[str]:
	profile = config.profile_config.profile if config.profile_config else None
	if profile is None:
		return []
	return profile.current_selection_names() or [profile.name]


def _pacman_conf(inst: Installer, gpu: bool) -> None:
	conf = inst.target / 'etc/pacman.conf'
	lines = conf.read_text().splitlines()
	extra = []
	if not any(line.strip() == 'DisableSandbox' for line in lines):
		extra += [
			'# alarminstall (r8q): the r8q kernel has no Landlock, so pacman cannot sandbox downloads.',
			'DisableSandbox',
		]
	extra += [
		'# The kernel is linux-r8q from alarminstall, not the generic Arch Linux ARM kernel.',
		'IgnorePkg = linux-aarch64',
	]
	if gpu:
		extra += [
			'# The GPU needs the Samsung-signed zap shader copied from this phone; an upgrade',
			'# of linux-firmware-qcom would replace it and break the GPU.',
			f'NoUpgrade = {ZAP}.mbn {ZAP}.mbn.zst',
		]
	out = []
	for line in lines:
		out.append(line)
		if line.strip() == '[options]':
			out.extend(extra)
	conf.write_text('\n'.join(out) + '\n')


# --- steps -------------------------------------------------------------------------


FSTAB = """\
# alarminstall (r8q). The kernel's boot script mounts "userdata" as / by itself;
# systemd remounts by these labels. Device names (sdaNN) are not used: they can change.
LABEL=archroot  /      ext4  rw,relatime  0 1
# The ESP: kernel and r8q.dtb. nofail: a problem here must not stop the boot.
LABEL=R8QESP    /boot  vfat  rw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=ascii,shortname=mixed,utf8,errors=remount-ro,nofail  0 2
"""


def write_fstab(inst: Installer) -> None:
	"""archinstall's pre-mounted mode writes device paths (/dev/sdb2): replace them with labels."""
	_write(inst, 'etc/fstab', FSTAB)


def install_kernel(inst: Installer, r8q: R8qConfiguration) -> None:
	"""The r8q kernel, its device tree and its (pruned) module tree, from the medium."""
	boot = inst.target / 'boot'
	image = device.PAYLOAD / 'Image'
	dtb = device.PAYLOAD / 'r8q.dtb'

	# The kernel's built-in command line says dtb=r8q.dtb: the device tree must be at the
	# root of the ESP, next to whatever starts the kernel. Without it the phone does not boot.
	shutil.copyfile(dtb, boot / 'r8q.dtb')

	match r8q.bootloader:
		case R8qBootloader.EFISTUB:
			(boot / 'EFI/BOOT').mkdir(parents=True, exist_ok=True)
			shutil.copyfile(image, boot / 'EFI/BOOT/BOOTAA64.EFI')
		case R8qBootloader.SYSTEMD_BOOT:
			shutil.copyfile(image, boot / 'Image')
			_chroot(inst, 'bootctl', '--esp-path=/boot', '--no-variables', 'install')
			_write(inst, 'boot/loader/loader.conf', 'default r8q.conf\ntimeout 3\n')
			_write(inst, 'boot/loader/entries/r8q.conf', 'title   Arch Linux ARM (r8q)\nlinux   /Image\n')

	info('r8q: kernel modules')
	with tarfile.open(device.PAYLOAD / 'modules.tar') as tar:
		tar.extractall(inst.target, filter='fully_trusted')
	kver = (device.PAYLOAD / 'kernel.release').read_text().strip()
	_chroot(inst, 'depmod', kver)


def copy_zap_shader(inst: Installer) -> None:
	"""Samsung's TrustZone only accepts Samsung's signed zap shader: copy it from this phone."""
	apnhlos = Path('/dev/disk/by-partlabel/apnhlos')
	mnt = Path('/run/alarminstall/apnhlos')
	mnt.mkdir(parents=True, exist_ok=True)
	subprocess.run(['mount', '-o', 'ro', str(apnhlos), str(mnt)], check=True)
	try:
		src = mnt / 'image'
		dst = inst.target / 'usr/lib/firmware/qcom/sm8250'
		dst.mkdir(parents=True, exist_ok=True)
		# the .mdt is renamed to .mbn; the .bNN segments keep their names
		shutil.copyfile(src / 'a650_zap.mdt', dst / 'a650_zap.mbn')
		for seg in sorted(src.glob('a650_zap.b[0-9][0-9]')):
			shutil.copyfile(seg, dst / seg.name)
		(dst / 'a650_zap.mbn.zst').unlink(missing_ok=True)
	finally:
		subprocess.run(['umount', str(mnt)], check=False)


def install_r8q_system(inst: Installer, config: ArchConfig, r8q: R8qConfiguration) -> None:
	names = profile_names(config)
	user = _first_user(config)
	info(f'r8q: system setup (profiles: {", ".join(names) or "none"}; user: {user})')

	# Always: module blacklists (cold-plugging the wrong module hard-resets the SoC),
	# quiet console (boot time), Wi-Fi, touch, battery, journald.
	for rel in (
		'etc/modprobe.d/r8q-audio-blacklist.conf',
		'etc/modprobe.d/r8q-camera-blacklist.conf',
		'etc/modprobe.d/r8q-gpu.conf',
		'etc/modprobe.d/r8q-wifi-blacklist.conf',
		'etc/sysctl.d/50-r8q-printk.conf',
		'etc/systemd/journald.conf.d/r8q-sync.conf',
		'etc/NetworkManager/conf.d/10-r8q.conf',
		'etc/systemd/system/r8q-touch.service',
		'etc/systemd/system/r8q-battery.service',
		'etc/systemd/system/r8q-wifi.service',
	):
		_put(inst, rel)
	(inst.target / 'var/log/journal').mkdir(parents=True, exist_ok=True)
	# NetworkManager runs with dns=none (usb0 belongs to networkd).
	(inst.target / 'etc/resolv.conf').unlink(missing_ok=True)
	_write(inst, 'etc/resolv.conf', 'nameserver 1.1.1.1\nnameserver 9.9.9.9\n')
	_write(inst, 'etc/systemd/logind.conf.d/50-r8q.conf', LOGIND)
	_chroot(inst, 'systemctl', 'mask', *SLEEP_TARGETS)
	_enable(inst, 'r8q-touch.service', 'r8q-battery.service', 'r8q-wifi.service', 'NetworkManager.service')
	_chroot(inst, 'systemctl', 'disable', 'NetworkManager-wait-online.service')

	if not r8q.charge_limit:
		_write(inst, 'etc/systemd/system/r8q-battery.service.d/no-charge-limit.conf', '[Service]\nExecStartPost=\n')

	match r8q.touch:
		case TouchChip.AUTO:
			pass
		case TouchChip.STM | TouchChip.ZINITIX:
			module = 'fts5cu56a' if r8q.touch == TouchChip.STM else 'zinitix'
			_write(
				inst,
				'etc/systemd/system/r8q-touch.service.d/chip.conf',
				'[Service]\nExecStart=\n'
				'ExecStart=/usr/bin/insmod /root/ts/gpi.ko\n'
				'ExecStart=/usr/bin/insmod /root/ts/i2c-qcom-geni.ko r8q_force_fifo=1\n'
				"ExecStart=/bin/sh -c 'sleep 2'\n"
				f'ExecStart=/usr/bin/insmod /root/ts/{module}.ko\n',
			)

	if r8q.wedge_mitigation:
		_put(inst, 'etc/tmpfiles.d/50-r8q-cpuidle.conf')

	if r8q.usb_ssh:
		_put(inst, 'etc/systemd/network/20-usb0.network')
		_put(inst, 'etc/systemd/system/r8q-usb-gadget.service')
		_put(inst, 'usr/local/sbin/r8q-usb-gadget-up.sh', 0o755)
		_write(inst, 'etc/ssh/sshd_config.d/50-r8q.conf', SSHD)
		_enable(inst, 'r8q-usb-gadget.service', 'systemd-networkd.service', 'systemd-networkd.socket', 'sshd.service')
		_chroot(inst, 'systemctl', 'disable', 'systemd-networkd-wait-online.service')

	if r8q.copy_wifi and device.wifi_profiles():
		dst = inst.target / 'etc/NetworkManager/system-connections'
		dst.mkdir(parents=True, exist_ok=True)
		dst.chmod(0o700)
		for profile in device.wifi_profiles():
			shutil.copyfile(profile, dst / profile.name)
			(dst / profile.name).chmod(0o600)

	if r8q.gpu:
		inst.add_additional_packages(GPU_PACKAGES)
		copy_zap_shader(inst)
		_put(inst, 'etc/systemd/system/r8q-gpu.service')
		_enable(inst, 'r8q-gpu.service')
	else:
		_write(inst, 'etc/alarminstall/no-gpu', 'GPU acceleration was not installed.\n')

	if r8q.camera:
		inst.add_additional_packages(CAMERA_PACKAGES + (['plasma-camera'] if 'Plasma Mobile' in names else []))
		_put(inst, 'etc/systemd/system/r8q-camera.service')
		_put(inst, 'etc/udev/rules.d/70-r8q-camera.rules')
		_put(inst, 'etc/wireplumber/wireplumber.conf.d/50-r8q-camera.conf')
		_put(inst, 'usr/local/bin/r8q-cam', 0o755)
		_enable(inst, 'r8q-camera.service')
		if user:
			_chroot(inst, 'gpasswd', '-a', user, 'video')

	profile = config.profile_config.profile if config.profile_config else None
	_desktop(inst, names, bool(profile and profile.is_desktop_profile()), user, r8q)
	_pacman_conf(inst, r8q.gpu)

	# ALARM tarball artifact, harmless to repeat: / and /usr must belong to root.
	_chroot(inst, 'chown', 'root:root', '/', '/usr')
	_chroot(inst, 'chmod', '755', '/')


def _desktop(inst: Installer, names: list[str], desktop: bool, user: str | None, r8q: R8qConfiguration) -> None:
	if 'Plasma Mobile' in names or 'KDE Plasma' in names:
		# PowerDevil must never suspend (hard reset), the battery gauge can read "critical"
		# while the pack is fine, and a lock screen without a keyboard locks you out.
		for f in ('powerdevilrc', 'powermanagementprofilesrc', 'kscreenlockerrc'):
			_put(inst, f'etc/xdg/{f}')
		session = 'plasma-mobile.desktop' if 'Plasma Mobile' in names else 'plasma.desktop'
		sddm = (device.PAYLOAD / 'rootfs/etc/sddm.conf.d/10-r8q.conf').read_text()
		sddm = sddm.replace('User=alarm', f'User={user or "root"}').replace('Session=plasma-mobile.desktop', f'Session={session}')
		_write(inst, 'etc/sddm.conf.d/10-r8q.conf', sddm)
		if r8q.gpu:
			# KWin picks its render device once: sddm must start after the GPU is up.
			_put(inst, 'etc/systemd/system/sddm.service.d/r8q-after-gpu.conf')

	if 'GNOME' in names:
		for rel in ('etc/dconf/profile/user', 'etc/dconf/db/local.d/00-r8q-power', 'etc/dconf/db/local.d/locks/00-r8q-power'):
			_put(inst, rel)
		_chroot(inst, 'dconf', 'update')
		gdm = (device.PAYLOAD / 'rootfs/etc/gdm/custom.conf').read_text().replace('AutomaticLogin=alarm', f'AutomaticLogin={user or "root"}')
		_write(inst, 'etc/gdm/custom.conf', gdm)
		if r8q.gpu:
			_put(inst, 'etc/udev/rules.d/61-mutter-primary-gpu.rules')
			_put(inst, 'etc/systemd/system/gdm.service.d/r8q-after-gpu.conf')

	if 'Sway' in names and user:
		_write(
			inst,
			'etc/systemd/system/getty@tty1.service.d/autologin.conf',
			f'[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin {user} --noclear %I 38400 linux\n',
		)
		home = inst.target / 'home' / user
		(home / '.bash_profile').write_text(SWAY_PROFILE)
		_chroot(inst, 'chown', f'{user}:{user}', f'/home/{user}/.bash_profile')
	elif not desktop:
		# No display manager: a root console on the phone's screen, as r8q-arch does.
		_put(inst, 'etc/systemd/system/getty@tty1.service.d/autologin.conf')
	elif not any(n in names for n in ('Plasma Mobile', 'KDE Plasma', 'GNOME')):
		warn(f'r8q: no r8q configuration for {names}: untested, the session may not start')
