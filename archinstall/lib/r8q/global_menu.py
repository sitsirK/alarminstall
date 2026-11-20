"""
The alarminstall main menu: archinstall's, with the r8q's answers filled in and
every choice labelled with how well it is supported on the phone.
"""

import re
from pathlib import Path
from typing import override

from archinstall.lib.args import ArchConfig
from archinstall.lib.global_menu import GlobalMenu
from archinstall.lib.menu.helpers import Notify, Selection
from archinstall.lib.models.authentication import AuthenticationConfiguration
from archinstall.lib.models.bootloader import Bootloader, BootloaderConfiguration
from archinstall.lib.models.device import DiskLayoutConfiguration, DiskLayoutType
from archinstall.lib.models.network import NetworkConfiguration, NicType
from archinstall.lib.models.users import Password, User
from archinstall.lib.r8q import device, menu
from archinstall.lib.r8q.models import R8qBootloader, R8qConfiguration
from archinstall.lib.r8q.support import KERNEL_LABELS, LATEST_KERNEL, SWAP
from archinstall.tui.menu_item import MenuItem, MenuItemGroup
from archinstall.tui.result import ResultType

TARGET = Path('/mnt/archinstall')
MIRRORLIST = Path('/etc/pacman.d/mirrorlist')

# Test-build defaults (the user asked for these): root / alarm, user alarm / alarm.
DEFAULT_HOSTNAME = 'alarm'
DEFAULT_USER = 'alarm'
DEFAULT_PASSWORD = 'alarm'

MIN_BATTERY = 20


def default_auth() -> AuthenticationConfiguration:
	return AuthenticationConfiguration(
		root_enc_password=Password(plaintext=DEFAULT_PASSWORD),
		users=[User(DEFAULT_USER, Password(plaintext=DEFAULT_PASSWORD), sudo=True)],
	)


def disk_layout() -> DiskLayoutConfiguration:
	# Pre-mounted: archinstall never partitions or formats anything itself.
	# alarminstall formats cache + userdata and mounts them at TARGET first.
	return DiskLayoutConfiguration(config_type=DiskLayoutType.Pre_mount, mountpoint=TARGET)


def apply_defaults(config: ArchConfig) -> None:
	"""Fill in the r8q's answers before the menu shows them."""
	config.r8q_config = config.r8q_config or R8qConfiguration(display=menu.default_display())
	config.disk_config = disk_layout()
	# linux-r8q (the tested kernel on the medium) unless the EXPERIMENTAL latest kernel was picked.
	config.kernels = [LATEST_KERNEL] if config.kernels and LATEST_KERNEL in config.kernels else ['linux-r8q']
	config.swap = None
	config.bootloader_config = BootloaderConfiguration(Bootloader.Efistub, uki=False, removable=True)
	if config.hostname in ('archlinux', '', None):
		config.hostname = DEFAULT_HOSTNAME
	config.auth_config = config.auth_config or default_auth()
	config.network_config = config.network_config or NetworkConfiguration(NicType.NM)


class R8qGlobalMenu(GlobalMenu):
	@override
	def _get_menu_options(self) -> list[MenuItem]:
		items = super()._get_menu_options()
		by_key = {i.key: i for i in items if i.key}

		phone = MenuItem(
			text='Phone (Galaxy S20 FE 5G)',
			action=lambda p: menu.R8qMenu(p).show(),
			value=R8qConfiguration(),
			preview_action=self._prev_r8q,
			key='r8q_config',
		)
		items.insert(items.index(by_key['mirror_config']), phone)

		m = by_key['mirror_config']
		m.text = 'Mirrors (Arch Linux ARM)'
		m.action = self._select_alarm_mirrors
		m.preview_action = self._prev_alarm_mirrors

		d = by_key['disk_config']
		d.value = disk_layout()
		d.action = self._select_disk
		d.preview_action = self._prev_r8q_disk

		s = by_key['swap']
		s.text = SWAP.label('Swap')
		s.value = None
		s.action = menu.select_swap
		s.preview_action = lambda _: SWAP.note

		b = by_key['bootloader_config']
		b.action = self._select_r8q_bootloader
		b.preview_action = self._prev_r8q_bootloader

		k = by_key['kernels']
		k.value = ['linux-r8q']
		k.action = menu.select_kernel
		k.preview_action = self._prev_r8q_kernel

		f = by_key['firmware_optdeps']
		f.action = menu.select_firmware_optdeps

		by_key['hostname'].value = DEFAULT_HOSTNAME
		by_key['auth_config'].value = default_auth()
		by_key['app_config'].action = menu.select_applications
		by_key['network_config'].value = NetworkConfiguration(NicType.NM)
		return items

	# --- phone ---------------------------------------------------------------

	def _prev_r8q(self, item: MenuItem) -> str | None:
		config: R8qConfiguration | None = item.value
		if config is None:
			return None
		text = '\n'.join(config.summary())
		touch = device.detected_touch_chip()
		battery = device.battery_percent()
		text += f'\n\nThis phone: touch = {touch or "not detected"}'
		if battery is not None:
			text += f', battery {battery}%'
			if device.charging():
				text += ' (charging)'
		return text

	def _prev_r8q_kernel(self, item: MenuItem) -> str | None:
		kernels: list[str] = item.value or ['linux-r8q']
		tested = f'linux-r8q: mainline {device.bundled_kernel_release()} + r8q patches (tested)'
		if LATEST_KERNEL in kernels:
			return (
				f'Kernel: {KERNEL_LABELS[LATEST_KERNEL]} (EXPERIMENTAL)\n\n'
				'The newest kernel.org release, patched and built on the\n'
				'phone at the end of the install (30-60 min). If that fails:\n' + tested
			)
		return f'Kernel: {tested}'

	# --- disk ----------------------------------------------------------------

	async def _select_disk(self, _preset: DiskLayoutConfiguration | None) -> DiskLayoutConfiguration:
		r8q: R8qConfiguration = self._item_group.find_by_key('r8q_config').value
		r8q.root_fs = await menu.select_root_fs(r8q.root_fs)
		return disk_layout()

	def _prev_r8q_disk(self, _item: MenuItem) -> str:
		esp = device.find_partition(device.ESP_PARTNAME)
		root = device.find_partition(device.ROOT_PARTNAME)

		def size(p: Path | None) -> str:
			gib = device.partition_size_gib(p) if p else None
			if gib is None:
				return '?'
			return f'{gib * 1024:.0f} MiB' if gib < 2 else f'{gib:.1f} GiB'

		r8q: R8qConfiguration = self._item_group.find_by_key('r8q_config').value
		return (
			'Fixed layout: the partition table is NOT changed.\n\n'
			f'ESP:  "cache"    {esp or "NOT FOUND"} ({size(esp)})\n'
			'      -> FAT32, label R8QESP, mounted at /boot\n'
			f'Root: "userdata" {root or "NOT FOUND"} ({size(root)})\n'
			f'      -> {r8q.root_fs if r8q else "ext4"}, label archroot\n\n'
			'EVERYTHING ON userdata IS ERASED (Android data or a previous Linux).\n'
			'Nothing else on the phone is touched.'
		)

	# --- bootloader ----------------------------------------------------------

	async def _select_r8q_bootloader(self, preset: BootloaderConfiguration | None) -> BootloaderConfiguration:
		current = R8qBootloader.SYSTEMD_BOOT if preset and preset.bootloader == Bootloader.Systemd else R8qBootloader.EFISTUB
		chosen = await menu.select_bootloader(current)
		r8q: R8qConfiguration = self._item_group.find_by_key('r8q_config').value
		r8q.bootloader = chosen
		loader = Bootloader.Systemd if chosen == R8qBootloader.SYSTEMD_BOOT else Bootloader.Efistub
		return BootloaderConfiguration(loader, uki=False, removable=True)

	def _prev_r8q_bootloader(self, item: MenuItem) -> str | None:
		config: BootloaderConfiguration | None = item.value
		if not config:
			return None
		if config.bootloader == Bootloader.Systemd:
			return 'systemd-boot, installed to \\EFI\\BOOT\\BOOTAA64.EFI\n(untested on this phone)'
		return 'EFISTUB: the kernel itself is \\EFI\\BOOT\\BOOTAA64.EFI on the ESP\n(how the phone boots today)'

	# --- mirrors -------------------------------------------------------------

	@staticmethod
	def _mirror_lines() -> list[tuple[str, bool]]:
		servers = []
		try:
			for line in MIRRORLIST.read_text().splitlines():
				if m := re.match(r'^\s*(#)?\s*Server\s*=\s*(\S+)', line):
					servers.append((m.group(2), m.group(1) is None))
		except OSError:
			pass
		return servers

	async def _select_alarm_mirrors(self, _preset: object) -> None:
		servers = self._mirror_lines()
		if not servers:
			await Notify(f'{MIRRORLIST} lists no servers.').show()
			return

		items = [MenuItem(url, value=url) for url, _ in servers]
		group = MenuItemGroup(items, sort_items=False)
		group.set_selected_by_value([url for url, on in servers if on])
		result = await Selection[str](
			group,
			header='Arch Linux ARM mirrors, tried in this order.\n'
			'mirror.archlinuxarm.org redirects by location\n'
			'and can stall: a fixed mirror near you is safer.\n',
			multi=True,
			allow_skip=True,
		).show()

		if result.type_ == ResultType.Selection and result.get_values():
			chosen = result.get_values()
			text = MIRRORLIST.read_text()
			out = []
			for line in text.splitlines():
				if m := re.match(r'^\s*(#)?\s*Server\s*=\s*(\S+)', line):
					out.append(('' if m.group(2) in chosen else '# ') + f'Server = {m.group(2)}')
				else:
					out.append(line)
			MIRRORLIST.write_text('\n'.join(out) + '\n')
		return

	def _prev_alarm_mirrors(self, _item: MenuItem) -> str:
		on = [url for url, enabled in self._mirror_lines() if enabled]
		return 'Mirrors in use:\n' + ('\n'.join(on) if on else '(none)')

	# --- validation ----------------------------------------------------------

	@override
	def _validate_bootloader(self) -> str | None:
		if device.find_partition(device.ESP_PARTNAME) is None:
			return 'The "cache" partition (ESP) was not found: is this a Galaxy S20 FE 5G?'
		if device.find_partition(device.ROOT_PARTNAME) is None:
			return 'The "userdata" partition was not found: is this a Galaxy S20 FE 5G?'
		battery = device.battery_percent()
		if battery is not None and battery < MIN_BATTERY and not device.charging():
			return f'Battery at {battery}%: charge to at least {MIN_BATTERY}% (or plug in) before installing'
		return None

	@override
	def _get_install_warnings(self) -> list[str]:
		warnings = super()._get_install_warnings()
		warnings.append('Everything on the "userdata" partition will be erased.')
		if (battery := device.battery_percent()) is not None and battery < 50:
			warnings.append(f'Battery at {battery}%: keep the phone plugged in.')
		return warnings
