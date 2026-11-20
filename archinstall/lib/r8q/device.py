"""
Facts about the phone alarminstall is running on, read from the live system.
"""

import functools
import re
import subprocess
from pathlib import Path

# The live medium is mounted here by the image's initramfs.
MEDIUM = Path('/run/alarminstall/medium')
PAYLOAD = MEDIUM / 'alarminstall' / 'r8q'

# Samsung's bootloader (XBL) writes its log, including the panel it found, to the
# LOGFS partition (vfat): "dsi_display0=ss_dsi_panel_S6E3FC3_AMS646YD01_FHD".
LOGFS = Path('/dev/disk/by-label/LOGFS')
LOGFS_MNT = Path('/run/alarminstall/logfs')
# The panel the msm-drm display (r8q-arch patches/0012) has a driver for.
PANEL_WITH_DRIVER = 'S6E3FC3'

# GPT partition names on UFS LUN 0. alarminstall writes to these two and nothing else.
ESP_PARTNAME = 'cache'
ROOT_PARTNAME = 'userdata'

TOUCH_STM = Path('/sys/bus/i2c/drivers/fts5cu56a/5-0049')
TOUCH_ZINITIX = Path('/sys/bus/i2c/drivers/Zinitix-TS/5-0020')
BATTERY = Path('/sys/class/power_supply/max170xx_battery')


def is_r8q() -> bool:
	try:
		return b'samsung,r8q' in Path('/proc/device-tree/compatible').read_bytes()
	except OSError:
		return False


def find_partition(partname: str) -> Path | None:
	"""
	The block device of a GPT partition by name, on the phone's internal
	storage only (UFS, non-removable). Never guesses a device letter.
	"""
	for uevent in Path('/sys/class/block').glob('*/uevent'):
		try:
			lines = uevent.read_text().splitlines()
		except OSError:
			continue
		if f'PARTNAME={partname}' not in lines:
			continue
		dev = uevent.parent.name
		if not dev.startswith('sd'):
			continue
		disk = dev.rstrip('0123456789')
		removable = Path(f'/sys/class/block/{disk}/removable')
		if removable.exists() and removable.read_text().strip() == '1':
			continue
		return Path('/dev') / dev
	return None


def partition_size_gib(dev: Path) -> float | None:
	try:
		sectors = int(Path(f'/sys/class/block/{dev.name}/size').read_text())
	except OSError, ValueError:
		return None
	return sectors * 512 / 1024**3


def detected_touch_chip() -> str | None:
	if TOUCH_STM.exists():
		return 'STM FTS5CU56A'
	if TOUCH_ZINITIX.exists():
		return 'Zinitix ZT7650'
	return None


def battery_percent() -> int | None:
	try:
		return int((BATTERY / 'capacity').read_text())
	except OSError, ValueError:
		return None


def charging() -> bool | None:
	try:
		status = Path('/sys/class/power_supply/max77705-charger/status').read_text().strip()
	except OSError:
		return None
	return status == 'Charging'


def wifi_profiles() -> list[Path]:
	return sorted(Path('/etc/NetworkManager/system-connections').glob('*.nmconnection'))


def bundled_kernel_release() -> str:
	"""The version of the tested kernel on the medium (linux-r8q), e.g. 7.3.5."""
	try:
		return (PAYLOAD / 'kernel.release').read_text().strip()
	except OSError:
		return '?'


@functools.cache
def detected_panel() -> str | None:
	"""
	The display panel this phone was built with, from the bootloader's log on LOGFS:
	e.g. 'S6E3FC3_AMS646YD01_FHD'. The r8q shipped with one of three panels (S6E3FC3,
	EA8079B, EA8076A). None if the log cannot be read.
	"""
	if not LOGFS.exists():
		return None
	LOGFS_MNT.mkdir(parents=True, exist_ok=True)
	mounted = subprocess.run(['mount', '-t', 'vfat', '-o', 'ro,nosuid,nodev,noexec', str(LOGFS), str(LOGFS_MNT)], capture_output=True, check=False)
	if mounted.returncode != 0:
		return None
	try:
		found = None
		for log in sorted(LOGFS_MNT.glob('UefiLog*.txt')):
			try:
				matches = re.findall(rb'dsi_display0=ss_dsi_panel_([A-Za-z0-9_]+)', log.read_bytes())
			except OSError:
				continue
			if matches:
				found = matches[-1].decode()
				# UefiLog1.txt is the newest boot; the others are older ones.
				if log.name == 'UefiLog1.txt':
					break
		return found
	finally:
		subprocess.run(['umount', str(LOGFS_MNT)], check=False)


def panel_has_driver(panel: str | None) -> bool | None:
	"""True/False if the panel is known, None if it could not be detected."""
	if panel is None:
		return None
	return panel.upper().startswith(PANEL_WITH_DRIVER)
