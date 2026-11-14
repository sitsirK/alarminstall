"""
alarminstall menus for the Samsung Galaxy S20 FE 5G (r8q).
"""

from collections.abc import Callable
from typing import override

from archinstall.lib.applications.application_menu import ApplicationMenu
from archinstall.lib.menu.abstract_menu import AbstractSubMenu
from archinstall.lib.menu.helpers import Confirmation, Notify, Selection
from archinstall.lib.models.application import ApplicationConfiguration
from archinstall.lib.models.package_types import FirmwareOptdep
from archinstall.lib.r8q import device
from archinstall.lib.r8q.models import R8qBootloader, R8qConfiguration, TouchChip
from archinstall.lib.r8q.support import (
	APPLICATIONS,
	ENCRYPTION,
	KERNELS,
	ROOT_FILESYSTEMS,
	SWAP,
	TESTED,
	Support,
	apply_tiers,
	unsupported,
	untested,
)
from archinstall.tui.menu_item import MenuItem, MenuItemGroup
from archinstall.tui.result import ResultType


def tiered_item(text: str, value: object, support: Support, preview: str | None = None) -> MenuItem:
	preview = preview or support.detail or None
	return MenuItem(
		support.label(text),
		value=value,
		read_only=not support.selectable,
		preview_action=(lambda _: preview) if preview else None,
	)


async def _yes_no(header: str, preset: bool) -> bool:
	result = await Confirmation(header=header, allow_skip=True, preset=preset).show()
	if result.type_ == ResultType.Selection:
		return result.item() == MenuItem.yes()
	return preset


# --- Phone options -------------------------------------------------------------


class R8qMenu(AbstractSubMenu[R8qConfiguration]):
	def __init__(self, preset: R8qConfiguration | None = None) -> None:
		self._r8q_config = preset or R8qConfiguration()
		self._item_group = MenuItemGroup(self._define_menu_options(), checkmarks=True)
		super().__init__(self._item_group, config=self._r8q_config, allow_reset=False)

	@override
	async def show(self) -> R8qConfiguration | None:
		_ = await super().show()
		return self._r8q_config

	def _define_menu_options(self) -> list[MenuItem]:
		c = self._r8q_config

		def yn(v: object) -> str:
			return 'yes' if v else 'no'

		return [
			MenuItem(
				'GPU acceleration (Adreno 650)',
				value=c.gpu,
				action=lambda p: _yes_no(
					'Install GPU acceleration?\n\n'
					'Yes: mesa + turnip (Vulkan), the msm driver, and the\n'
					'Samsung-signed zap shader copied from THIS phone.\n'
					'No: desktops draw on the CPU, which is slow.\n',
					p,
				),
				preview_action=lambda i: f'GPU acceleration: {yn(i.value)}',
				key='gpu',
			),
			MenuItem(
				'Touchscreen',
				value=c.touch,
				action=select_touch,
				preview_action=_prev_touch,
				key='touch',
			),
			MenuItem(
				'Camera',
				value=c.camera,
				action=lambda p: _yes_no(
					'Install camera support?\n\n'
					'Only the rear telephoto camera (Hi-847) works,\n'
					'through libcamera (plasma-camera on Plasma\n'
					'Mobile). Focus does not move yet.\n',
					p,
				),
				preview_action=lambda i: f'Camera: {yn(i.value)}\n\nRear telephoto only; focus does not move.',
				key='camera',
			),
			MenuItem(
				'SSH over USB',
				value=c.usb_ssh,
				action=lambda p: _yes_no(
					'Bring up the USB network link at boot (phone =\n'
					'172.16.42.1) and let root log in over SSH with a\n'
					'password? This is how you reach a phone with no\n'
					'keyboard. Anyone on USB or your Wi-Fi can try the\n'
					'root password: change it after installing.\n',
					p,
				),
				preview_action=lambda i: f'SSH over USB: {yn(i.value)}\n\nssh root@172.16.42.1',
				key='usb_ssh',
			),
			MenuItem(
				'CPU-wedge mitigation',
				value=c.wedge_mitigation,
				action=lambda p: _yes_no(
					'Disable the deep CPU idle state on every core?\n\n'
					'Every so often a core stops and the phone hangs.\n'
					'This does not fix it, but makes it much rarer.\n'
					'Recommended.\n',
					p,
				),
				preview_action=lambda i: f'Disable deep idle (cpuidle state1): {yn(i.value)}',
				key='wedge_mitigation',
			),
			MenuItem(
				'Charge at 700 mA',
				value=c.charge_limit,
				action=lambda p: _yes_no(
					'Raise the USB charge limit from 500 to 700 mA?\n\n'
					'Mainline cannot detect the charger type, so it\n'
					'stays at 500 mA and a desktop drains the battery\n'
					'even while plugged in. Recommended.\n',
					p,
				),
				preview_action=lambda i: f'USB input limit 700 mA: {yn(i.value)}',
				key='charge_limit',
			),
			MenuItem(
				'Copy Wi-Fi networks',
				value=c.copy_wifi,
				action=lambda p: _yes_no(
					'Copy the Wi-Fi networks this installer knows to the new system?\n',
					p,
				),
				preview_action=_prev_wifi,
				key='copy_wifi',
			),
		]


def _prev_touch(item: MenuItem) -> str:
	chip: TouchChip = item.value
	found = device.detected_touch_chip() or 'none detected'
	return f'Touchscreen: {chip.display()}\n\nThis phone answers as: {found}'


def _prev_wifi(item: MenuItem) -> str:
	names = [p.stem for p in device.wifi_profiles()]
	text = f'Copy Wi-Fi networks: {"yes" if item.value else "no"}\n\n'
	return text + ('\n'.join(f'- {n}' for n in names) if names else 'The installer knows no Wi-Fi network.')


async def select_touch(preset: TouchChip) -> TouchChip:
	found = device.detected_touch_chip()
	items = [MenuItem(t.display(), value=t) for t in TouchChip]
	group = MenuItemGroup(items, sort_items=False)
	group.set_focus_by_value(preset)

	header = 'The r8q is built with one of two touch controllers.\n'
	header += f'This phone answers as: {found}\n' if found else 'No touch controller answered on this boot.\n'

	result = await Selection[TouchChip](group, header=header, allow_skip=True).show()
	return result.get_value() if result.type_ == ResultType.Selection else preset


# --- Tiered replacements for archinstall's own choices --------------------------


async def select_kernel(_preset: list[str] | None = None) -> list[str]:
	items = [tiered_item(name, name, support) for name, support in KERNELS.items()]
	group = MenuItemGroup(items, sort_items=False)
	group.set_selected_by_value(['linux-r8q'])
	group.set_focus_by_value('linux-r8q')

	result = await Selection[str](
		group,
		header='Only linux-r8q (mainline 7.1.2 + r8q patches)\nboots this phone.\n',
		allow_skip=True,
		multi=True,
		preview_location='bottom',
	).show()

	if result.type_ == ResultType.Selection and result.get_values():
		return result.get_values()
	return ['linux-r8q']


BOOTLOADER_NOTE = unsupported(
	'not supported: kernel misses r8q.dtb',
	'The r8q kernel loads r8q.dtb from the volume it was started from. GRUB,\nLimine and rEFInd load it from memory, so it finds none and stops.',
)


async def select_bootloader(preset: R8qBootloader) -> R8qBootloader:
	items = [
		tiered_item(R8qBootloader.EFISTUB.display(), R8qBootloader.EFISTUB, TESTED),
		tiered_item(
			R8qBootloader.SYSTEMD_BOOT.display(),
			R8qBootloader.SYSTEMD_BOOT,
			untested('untested', 'Starts the kernel from the ESP, so r8q.dtb is found. Nobody has tried it.'),
		),
		tiered_item('Grub', 'grub', BOOTLOADER_NOTE),
		tiered_item('Limine', 'limine', BOOTLOADER_NOTE),
		tiered_item('Refind', 'refind', BOOTLOADER_NOTE),
		tiered_item('Unified kernel image', 'uki', unsupported('not supported', 'The r8q kernel already carries its initramfs and command line.')),
		tiered_item('No bootloader', 'none', unsupported('not supported: would not boot')),
	]
	group = MenuItemGroup(items, sort_items=False)
	group.set_focus_by_value(preset)

	header = "The phone's UEFI starts \\EFI\\BOOT\\BOOTAA64.EFI.\nIt cannot store boot entries, so the bootloader\nalways goes to that fallback path.\n"
	result = await Selection[object](group, header=header, allow_skip=True, preview_location='bottom').show()

	if result.type_ == ResultType.Selection and isinstance(result.get_value(), R8qBootloader):
		return result.get_value()
	return preset


async def select_swap(_preset: object = None) -> None:
	await Notify(f'Swap on zram\n\n{SWAP.note}').show()
	return


async def select_root_fs(preset: str) -> str:
	items = [tiered_item(name, name, support) for name, support in ROOT_FILESYSTEMS.items()]
	items.append(tiered_item('Disk encryption (LUKS)', 'luks', ENCRYPTION))
	group = MenuItemGroup(items, sort_items=False)
	group.set_focus_by_value(preset)
	result = await Selection[str](group, header='Filesystem for the root partition (userdata)\n', allow_skip=True, preview_location='bottom').show()
	return result.get_value() if result.type_ == ResultType.Selection else preset


FIRMWARE: dict[FirmwareOptdep, Support] = {
	FirmwareOptdep.QCOM: untested('added with GPU acceleration'),
}


async def select_firmware_optdeps(preset: list[str] | None = None) -> list[str]:
	preset = preset or []
	items = [MenuItem(f'{f.value} ({f.description()})', value=f.value) for f in FirmwareOptdep]
	items = apply_tiers(items, lambda i: FIRMWARE.get(FirmwareOptdep(i.value), untested('not used by this phone')))
	group = MenuItemGroup(items, sort_items=False)
	group.set_selected_by_value(preset)

	header = (
		'Needed firmware is added for you: atheros (Wi-Fi),\n'
		'qcom (with GPU acceleration).\n'
		'WARNING: the GPU needs a Samsung-signed a650_zap.mbn\n'
		"that replaces linux-firmware-qcom's. A pacman\n"
		'NoUpgrade rule protects it: keep that rule.\n'
	)
	result = await Selection[str](group, header=header, allow_skip=True, allow_reset=True, multi=True, preview_location='bottom').show()

	match result.type_:
		case ResultType.Selection:
			return result.get_values()
		case ResultType.Reset:
			return []
		case _:
			return preset


def _with_detail(preview: Callable[[MenuItem], str | None] | None, detail: str) -> Callable[[MenuItem], str]:
	def show(item: MenuItem) -> str:
		current = preview(item) if preview else None
		return f'{current}\n\n{detail}' if current else detail

	return show


class R8qApplicationMenu(ApplicationMenu):
	"""archinstall's application menu with the r8q support levels applied."""

	@override
	def _define_menu_options(self) -> list[MenuItem]:
		items = super()._define_menu_options()
		for item in items:
			if item.key and (support := APPLICATIONS.get(item.key)):
				item.text = support.label(item.text)
				if not support.selectable:
					item.read_only = True
					item.value = None
				if support.detail:
					item.preview_action = _with_detail(item.preview_action, support.detail)
			if item.key == 'power_management_config':
				item.enabled = True
		return items


async def select_applications(preset: ApplicationConfiguration | None) -> ApplicationConfiguration | None:
	return await R8qApplicationMenu(preset).show()
