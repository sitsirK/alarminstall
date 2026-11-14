"""
alarminstall: archinstall for the Samsung Galaxy S20 FE 5G (r8q).

Upstream code checks `active()` at the few places where the phone needs a
different answer; everything else lives in this package.
"""

_state = {'active': False}


def activate() -> None:
	_state['active'] = True


def active() -> bool:
	return _state['active']
