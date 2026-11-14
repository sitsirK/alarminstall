"""
Facts about the phone alarminstall is running on, read from the live system.
"""

from pathlib import Path

# The live medium is mounted here by the image's initramfs.
MEDIUM = Path('/run/alarminstall/medium')
PAYLOAD = MEDIUM / 'alarminstall' / 'r8q'

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
