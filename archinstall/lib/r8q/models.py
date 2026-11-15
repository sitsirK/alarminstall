from dataclasses import dataclass
from enum import Enum
from typing import Any, Self, override

from archinstall.lib.models.config import SubConfig, SummaryLevel


class TouchChip(Enum):
	AUTO = 'auto'
	STM = 'stm'
	ZINITIX = 'zinitix'

	def display(self) -> str:
		match self:
			case TouchChip.AUTO:
				return 'Detect at boot (recommended)'
			case TouchChip.STM:
				return 'STM FTS5CU56A'
			case TouchChip.ZINITIX:
				return 'Zinitix ZT7650'


class R8qBootloader(Enum):
	EFISTUB = 'efistub'
	SYSTEMD_BOOT = 'systemd-boot'

	def display(self) -> str:
		match self:
			case R8qBootloader.EFISTUB:
				return 'EFISTUB: the kernel is \\EFI\\BOOT\\BOOTAA64.EFI'
			case R8qBootloader.SYSTEMD_BOOT:
				return 'systemd-boot'


@dataclass
class R8qConfiguration(SubConfig):
	"""Options specific to the Samsung Galaxy S20 FE 5G (r8q)."""

	gpu: bool = True
	touch: TouchChip = TouchChip.AUTO
	camera: bool = False
	usb_ssh: bool = True
	wedge_mitigation: bool = True
	charge_limit: bool = True
	copy_wifi: bool = True
	root_fs: str = 'ext4'
	bootloader: R8qBootloader = R8qBootloader.EFISTUB

	NAME: str = 'Phone (r8q)'

	@override
	def json(self) -> dict[str, Any]:
		return {
			'gpu': self.gpu,
			'touch': self.touch.value,
			'camera': self.camera,
			'usb_ssh': self.usb_ssh,
			'wedge_mitigation': self.wedge_mitigation,
			'charge_limit': self.charge_limit,
			'copy_wifi': self.copy_wifi,
			'root_fs': self.root_fs,
			'bootloader': self.bootloader.value,
		}

	@classmethod
	def parse_arg(cls, arg: dict[str, Any]) -> Self:
		default = cls()
		return cls(
			gpu=arg.get('gpu', default.gpu),
			touch=TouchChip(arg.get('touch', default.touch.value)),
			camera=arg.get('camera', default.camera),
			usb_ssh=arg.get('usb_ssh', default.usb_ssh),
			wedge_mitigation=arg.get('wedge_mitigation', default.wedge_mitigation),
			charge_limit=arg.get('charge_limit', default.charge_limit),
			copy_wifi=arg.get('copy_wifi', default.copy_wifi),
			root_fs=arg.get('root_fs', default.root_fs),
			bootloader=R8qBootloader(arg.get('bootloader', default.bootloader.value)),
		)

	@override
	def summary(self, _level: SummaryLevel = SummaryLevel.BASIC) -> list[str]:
		def yn(v: bool) -> str:
			return 'yes' if v else 'no'

		return [
			f'GPU acceleration: {yn(self.gpu)}',
			f'Touchscreen: {self.touch.display()}',
			f'Camera: {yn(self.camera)}',
			f'SSH over USB: {yn(self.usb_ssh)}',
			f'CPU-wedge mitigation: {yn(self.wedge_mitigation)}',
			f'PC USB port at 700 mA: {yn(self.charge_limit)}',
			f'Copy Wi-Fi networks: {yn(self.copy_wifi)}',
		]
