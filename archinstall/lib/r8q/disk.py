"""
Prepare the phone's storage. The partition table is never touched: the two
partitions alarminstall uses are found by GPT name and formatted in place.

  cache    -> FAT32 "R8QESP": the EFI system partition Mu-Silicium boots from
  userdata -> ext4 "archroot": the root filesystem (the kernel's boot script
              finds it by the partition name "userdata")
"""

import subprocess
from pathlib import Path

from archinstall.lib.log import info
from archinstall.lib.r8q import device


class R8qDiskError(Exception):
	pass


def _run(*argv: str) -> None:
	info('r8q: ' + ' '.join(argv))
	result = subprocess.run(argv, capture_output=True, text=True, check=False)
	if result.returncode != 0:
		raise R8qDiskError(f'{" ".join(argv)} failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}')


def _unmount_everything_on(dev: Path) -> None:
	result = subprocess.run(['findmnt', '-rno', 'TARGET', '-S', str(dev)], capture_output=True, text=True, check=False)
	for target in sorted(result.stdout.split(), reverse=True):
		_run('umount', target)


def target_partitions() -> tuple[Path, Path]:
	esp = device.find_partition(device.ESP_PARTNAME)
	root = device.find_partition(device.ROOT_PARTNAME)
	if esp is None or root is None:
		raise R8qDiskError('The "cache" or "userdata" partition was not found on internal storage.')
	if esp.parent != root.parent or esp.name.rstrip('0123456789') != root.name.rstrip('0123456789'):
		raise R8qDiskError(f'"cache" ({esp}) and "userdata" ({root}) are not on the same disk: refusing.')
	return esp, root


def prepare_target(target: Path, root_fs: str = 'ext4') -> None:
	if root_fs != 'ext4':
		raise R8qDiskError(f'Root filesystem {root_fs} is not supported on the r8q yet.')

	esp, root = target_partitions()
	info(f'r8q: ESP = {esp} (cache), root = {root} (userdata)')

	if subprocess.run(['mountpoint', '-q', str(target)], check=False).returncode == 0:
		_run('umount', '-R', str(target))
	for dev in (esp, root):
		_unmount_everything_on(dev)

	_run('wipefs', '--all', str(root))
	_run('mkfs.ext4', '-F', '-L', 'archroot', str(root))
	_run('wipefs', '--all', str(esp))
	# UFS has 4096-byte logical sectors; say so explicitly.
	_run('mkfs.fat', '-F', '32', '-S', '4096', '-n', 'R8QESP', str(esp))

	target.mkdir(parents=True, exist_ok=True)
	_run('mount', str(root), str(target))
	(target / 'boot').mkdir(exist_ok=True)
	_run('mount', str(esp), str(target / 'boot'))
