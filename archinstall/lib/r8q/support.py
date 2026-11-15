"""
What is known to work on the Samsung Galaxy S20 FE 5G (r8q), in one place.

Every choice alarminstall offers is in one of three tiers:

- TESTED       works on the phone today.
- UNTESTED     nothing known stops it, but nobody has tried it yet. Selectable,
               marked in yellow.
- UNSUPPORTED  known not to work yet. Shown in red, struck through, with the
               reason, and NOT selectable.

The Linux console on the phone cannot draw struck-through text, so the line is
also red and the reason is always written out. Over SSH (tmux attach) the strike
shows as well.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from textual.markup import escape

from archinstall.tui.menu_item import MenuItem


class Tier(Enum):
	TESTED = 'tested'
	UNTESTED = 'untested'
	UNSUPPORTED = 'unsupported'


@dataclass(frozen=True)
class Support:
	tier: Tier
	note: str = ''  # short: shown on the menu line, which is ~65 columns on the phone
	detail: str = ''  # longer explanation, shown in the preview where there is one

	@property
	def selectable(self) -> bool:
		return self.tier != Tier.UNSUPPORTED

	def label(self, text: str) -> str:
		"""Menu text (Textual markup) for an option with this support level."""
		text = escape(text)
		note = escape(self.note)

		match self.tier:
			case Tier.TESTED:
				return text
			case Tier.UNTESTED:
				return f'{text} [yellow]— {note or "untested"}[/]'
			case Tier.UNSUPPORTED:
				# Red as well as struck: the phone's console drops the strike
				# (and tmux shares one picture between the phone and SSH).
				return f'[red][strike]{text}[/strike] — {note or "not supported yet"}[/red]'


TESTED = Support(Tier.TESTED)
UNTESTED = Support(Tier.UNTESTED)
NOT_TESTED_WAYLAND = Support(Tier.UNTESTED, 'untested', 'A Wayland compositor: it might work, nobody has tried it on this phone yet.')
NO_XORG = Support(
	Tier.UNSUPPORTED,
	'not supported: needs X11',
	'X11 has never been run on this phone. Use Plasma Mobile, GNOME or Sway.',
)


def unsupported(note: str, detail: str = '') -> Support:
	return Support(Tier.UNSUPPORTED, note, detail)


def untested(note: str = 'untested', detail: str = '') -> Support:
	return Support(Tier.UNTESTED, note, detail)


# Desktop / window-manager profiles, by archinstall profile name.
PROFILES: dict[str, Support] = {
	'Plasma Mobile': TESTED,
	'GNOME': TESTED,
	'Sway': TESTED,
	'KDE Plasma': untested('untested (Plasma Mobile is tested)'),
	'Hyprland': NOT_TESTED_WAYLAND,
	'niri': NOT_TESTED_WAYLAND,
	'niri - DankMaterialShell': NOT_TESTED_WAYLAND,
	'Labwc': NOT_TESTED_WAYLAND,
	'River': NOT_TESTED_WAYLAND,
	'Cosmic': NOT_TESTED_WAYLAND,
	'Awesome': NO_XORG,
	'Bspwm': NO_XORG,
	'Budgie': NO_XORG,
	'Cinnamon': NO_XORG,
	'Deepin': NO_XORG,
	'Enlightenment': NO_XORG,
	'i3-wm': NO_XORG,
	'Lxqt': NO_XORG,
	'Mate': NO_XORG,
	'Qtile': NO_XORG,
	'Xfce4': NO_XORG,
	'Xmonad': NO_XORG,
	# top-level profile types
	'Minimal': TESTED,
	'Desktop': TESTED,
	'Server': untested('untested (only sshd is tested)'),
	'Xorg': NO_XORG,
	# servers
	'sshd': TESTED,
}


def profile_support(name: str) -> Support:
	return PROFILES.get(name, UNTESTED)


GREETERS: dict[str, Support] = {
	'sddm': TESTED,
	'gdm': TESTED,
	'lightdm-gtk-greeter': NO_XORG,
	'lightdm-slick-greeter': NO_XORG,
	'ly': untested('untested, needs a keyboard'),
}


def greeter_support(value: str) -> Support:
	return GREETERS.get(value, untested())


# Applications sub-menu, by its menu key.
APPLICATIONS: dict[str, Support] = {
	'bluetooth_config': unsupported('not supported yet', 'Bluetooth (QCA6390) is not brought up yet.'),
	'audio_config': unsupported('not supported yet', 'No sound card yet: speakers and microphones are work in progress.'),
	'print_service_config': untested('untested', 'CUPS does not depend on the phone; network printers might work.'),
	'power_management_config': untested(
		'untested, see preview', 'Changes the CPU frequency policy, which has not been tested with the CPU-wedge bug. Suspend stays disabled whatever it says.'
	),
	'firewall_config': unsupported('not supported: no nftables', 'The r8q kernel has no nftables, which ufw and firewalld need.'),
	'fonts_config': TESTED,
}

SWAP = unsupported('not supported: no zram in kernel', 'The r8q kernel has no zram yet.')

ENCRYPTION = unsupported('not supported yet', 'The r8q kernel has no dm-crypt, and its boot script cannot unlock a disk.')

KERNELS: dict[str, Support] = {
	'linux-r8q': TESTED,
	'linux-aarch64': unsupported('not supported, use linux-r8q'),
	'linux': unsupported('not supported: x86_64 only'),
	'linux-lts': unsupported('not supported: x86_64 only'),
	'linux-zen': unsupported('not supported: x86_64 only'),
	'linux-hardened': unsupported('not supported: x86_64 only'),
	'linux-rt': unsupported('not supported: x86_64 only'),
	'linux-rt-lts': unsupported('not supported: x86_64 only'),
}

ROOT_FILESYSTEMS: dict[str, Support] = {
	'ext4': TESTED,
	'btrfs': unsupported('not supported yet', 'btrfs is a module and the r8q boot script loads none.'),
	'f2fs': unsupported('not supported: not in kernel'),
	'xfs': unsupported('not supported: not in kernel'),
}


def apply_tiers(items: list[MenuItem], support_of: Callable[[MenuItem], Support]) -> list[MenuItem]:
	"""
	Label menu items with their support level, make unsupported ones
	unselectable, and order them tested -> untested -> unsupported (by name
	within a tier). Callers must then build their MenuItemGroup with
	sort_items=False, or the markup would decide the order.
	"""
	rank = {Tier.TESTED: 0, Tier.UNTESTED: 1, Tier.UNSUPPORTED: 2}
	keyed = []
	for item in items:
		support = support_of(item)
		keyed.append((rank[support.tier], item.text.lower(), item))
		item.text = support.label(item.text)
		item.read_only = not support.selectable
	return [item for _, _, item in sorted(keyed, key=lambda k: (k[0], k[1]))]
