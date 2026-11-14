from typing import override

from archinstall.default_profiles.profile import DisplayServerType, GreeterType, Profile, ProfileType


class PlasmaMobileProfile(Profile):
	"""
	KDE Plasma Mobile: the touch shell. Tested on the Samsung Galaxy S20 FE 5G
	(r8q), where alarminstall adds the sddm and PowerDevil configuration it needs.
	"""

	def __init__(self) -> None:
		super().__init__(
			'Plasma Mobile',
			ProfileType.DesktopEnv,
			support_gfx_driver=True,
			display_server=DisplayServerType.Wayland,
		)

	@property
	@override
	def packages(self) -> list[str]:
		return [
			'plasma-mobile',
			'plasma-settings',
			'plasma-keyboard',
			'kscreen',
		]

	@property
	@override
	def default_greeter_type(self) -> GreeterType:
		return GreeterType.Sddm
