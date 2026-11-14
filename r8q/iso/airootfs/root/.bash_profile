# On the phone's own screen (tty1) start the installer inside tmux, so it can
# also be reached from a PC: ssh root@172.16.42.1 (password root), then
#     tmux attach -t alarminstall
# SSH logins get a plain shell.
[ -f ~/.bashrc ] && . ~/.bashrc
if [ "$(tty)" = /dev/tty1 ] && [ -z "$TMUX" ]; then
    exec /usr/local/bin/alarminstall-session
fi
