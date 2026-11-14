"""
alarminstall: install Arch Linux ARM on the Samsung Galaxy S20 FE 5G (r8q).

archinstall's guided flow with the phone's answers: a fixed disk layout on the
existing "cache" and "userdata" partitions (the partition table is never
touched), the r8q kernel from the live medium, and the phone's own setup.
"""

import os
import subprocess
import sys
import time

from archinstall.lib import r8q
from archinstall.lib.applications.application_handler import ApplicationHandler
from archinstall.lib.args import ArchConfigHandler
from archinstall.lib.authentication.authentication_handler import AuthenticationHandler
from archinstall.lib.configuration import confirm_config
from archinstall.lib.general.general_menu import PostInstallationAction, select_post_installation
from archinstall.lib.log import error, info, logger
from archinstall.lib.menu.util import delayed_warning
from archinstall.lib.models.users import User
from archinstall.lib.network.network_handler import install_network_config
from archinstall.lib.profile.profiles_handler import profile_handler
from archinstall.lib.r8q import device
from archinstall.lib.r8q.disk import prepare_target
from archinstall.lib.r8q.global_menu import TARGET, R8qGlobalMenu, apply_defaults
from archinstall.lib.r8q.install import R8qInstaller, base_packages, install_kernel, install_r8q_system
from archinstall.lib.r8q.models import R8qConfiguration
from archinstall.lib.translationhandler import tr
from archinstall.tui.components import tui

TITLE = 'alarminstall — Arch Linux ARM for the Samsung Galaxy S20 FE 5G (r8q)'


def wait_for_keyring() -> None:
	"""The live system initialises its pacman keyring at boot (pacman-init.service)."""
	for _ in range(120):
		state = subprocess.run(['systemctl', 'show', '-P', 'ActiveState', 'pacman-init.service'], capture_output=True, text=True, check=False).stdout.strip()
		if state in ('active', 'failed', 'inactive'):
			return
		time.sleep(1)


def show_menu(handler: ArchConfigHandler) -> None:
	menu = R8qGlobalMenu(handler.config, None, handler.args.skip_boot, advanced=handler.args.advanced, title=TITLE)
	if tui.run(menu) is None:
		sys.exit(0)


def perform_installation(handler: ArchConfigHandler) -> None:
	start_time = time.monotonic()
	config = handler.config
	r8q_config: R8qConfiguration = config.r8q_config
	assert config.disk_config

	info("alarminstall: preparing the phone's storage")
	prepare_target(TARGET, r8q_config.root_fs)

	with R8qInstaller(TARGET, config.disk_config, base_packages(r8q_config), silent=handler.args.silent) as installation:
		# ALARM has no archlinux-keyring-wkd-sync: skip that wait (it would never end).
		installation.sanity_check(handler.args.skip_ntp, skip_wkd=True)
		wait_for_keyring()

		installation.minimal_installation(
			optional_repositories=[],
			mkinitcpio=False,
			hostname=config.hostname,
			locale_config=config.locale_config,
			pacman_config=config.pacman_config,
		)

		install_kernel(installation, r8q_config)

		if config.network_config:
			install_network_config(config.network_config, installation, config.profile_config)

		users = None
		if config.auth_config and config.auth_config.users:
			users = config.auth_config.users
			installation.create_users(users)
			AuthenticationHandler().setup_auth(installation, config.auth_config, config.hostname)

		if app_config := config.app_config:
			ApplicationHandler().install_applications(installation, app_config)

		if profile_config := config.profile_config:
			profile_handler.install_profile_config(installation, profile_config)

		if config.packages and config.packages[0] != '':
			installation.add_additional_packages(config.packages)

		if config.firmware_optdeps:
			installation.add_additional_packages(config.firmware_optdeps)

		if timezone := config.timezone:
			installation.set_timezone(timezone)

		if config.ntp:
			installation.activate_time_synchronization()

		if config.auth_config and config.auth_config.root_enc_password:
			installation.set_user_password(User('root', config.auth_config.root_enc_password, False))

		if (profile_config := config.profile_config) and profile_config.profile:
			profile_config.profile.post_install(installation)
			if users:
				profile_config.profile.provision(installation, users)

		install_r8q_system(installation, config, r8q_config)

		if services := config.services:
			installation.enable_service(services)

		installation.genfstab()

		# Keep a copy of the install log on the new system.
		if logger.path.exists():
			(TARGET / 'var/log/alarminstall.log').write_bytes(logger.path.read_bytes())

		if not handler.args.silent:
			elapsed = time.monotonic() - start_time
			action: PostInstallationAction = tui.run(lambda: select_post_installation(elapsed))
			match action:
				case PostInstallationAction.REBOOT:
					os.system('sync; umount -R /mnt/archinstall; reboot')
				case PostInstallationAction.CHROOT:
					try:
						installation.drop_to_shell()
					except Exception:
						pass
				case PostInstallationAction.EXIT:
					pass


def main(handler: ArchConfigHandler | None = None) -> None:
	r8q.activate()
	if handler is None:
		handler = ArchConfigHandler()

	if not device.is_r8q() and not os.environ.get('ALARMINSTALL_ANY_DEVICE'):
		error('alarminstall is for the Samsung Galaxy S20 FE 5G (r8q), and this is not one.')
		sys.exit(1)

	apply_defaults(handler.config)

	if not handler.args.silent:
		show_menu(handler)

	handler.config.write_debug()
	handler.config.save()

	if handler.args.dry_run:
		return None

	if not handler.args.silent:
		if not tui.run(lambda: confirm_config(handler.config)):
			return main(handler)

		if not delayed_warning(tr('Erasing "userdata" and "cache" in ')):
			return main(handler)

	perform_installation(handler)
	return None
