# Play Expanse in a PC terminal

The Windows 11 and Linux terminal editions play Founding Cities with keyboard commands. They include the runtime, worlds and player guides for offline play. Choose your platform on the [downloads page](https://expansemmo.com/downloads/index.html).

## Windows 11

Download `Expanse-Windows-11-Console-1.10.0.zip` on a 64-bit Intel or AMD PC. Extract the whole ZIP into a folder, then open `Install-Expanse-Console.cmd`.

To play, paste this path into File Explorer’s address bar and press Enter: `%LOCALAPPDATA%\Expanse-Console-Client\Run-Expanse-Console.cmd`.

You can also open the installed folder and run the launcher in Command Prompt or PowerShell. Windows Terminal is optional. In PowerShell, use `.\Run-Expanse-Console.cmd` from that folder.

## Linux and Bazzite

Download `Expanse-Linux-Console-1.10.0.run` on a 64-bit Intel or AMD PC. Use a distribution with glibc 2.28 or later and Bash, tar, gzip and sha256sum. Open a terminal in your downloads folder and run:

`bash Expanse-Linux-Console-1.10.0.run`

To play, run:

`"${XDG_DATA_HOME:-$HOME/.local/share}/Expanse-Console-Client/Run-Expanse-Console.sh"`

## Play and save offline

At the launcher menu, press Enter or choose 1 for offline single player. Founding Cities 1.10.0 is the default world. If you have an existing RC4 character, choose **Continue RC4** when offered or add `--world rc4` to the launcher command. Add `--world legacy` to the launcher command to use Wild Lands 1.9.16. During play, type `/menu` for terminal actions or `/wiki` for the player guide. Color appears in supported interactive terminals. The same commands work in plain text. Set the `NO_COLOR` environment variable to disable color.

Type `save` to keep your progress or `save and quit` to save and leave. A plain `quit` discards changes since your last save. The terminal and graphical editions keep separate saves.

Back up `%LOCALAPPDATA%\Expanse-Console` on Windows. On Linux, back up `~/.local/share/Expanse-Console`, or `Expanse-Console` inside your configured `XDG_DATA_HOME` directory. Run the launcher with `--data-dir PATH` to use another data folder.

## Sign in or join a host

Choose 2 or add `--online` to the launcher command to sign in to your personal online world. To use a compatible server of your choice, add `--online HTTPS_ORIGIN`, replacing `HTTPS_ORIGIN` with its secure web address. The official hosted game keeps each account’s world separate.

Choose 3 to join a private host and paste the host’s secure invite when prompted. The command-line form is `--connect INVITE`. Treat the invite as private. For either online mode you need a reachable host. Run the launcher with `--help` for its full list of options.

[Founding Cities play guide](founding-cities.html) · [Back to the wiki](index.html)
