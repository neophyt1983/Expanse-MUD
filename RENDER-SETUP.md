# Expanse private web engine

This repository runs the Expanse 1.9.1 Python game server and the existing browser player. A fresh deployment opens at sign-in with an empty game shelf. Import a complete desktop-editor .expanse export to play. The server runs the world, simulation and game clock, and the browser displays the map and sends player actions over a WebSocket.

## Put the package in your existing GitHub repository

Use the **Code → HTTPS** clone URL from your private deployment repository. On Bazzite, save the ZIP directly in **/home/dkipple/Games/text-rpg**. These commands put the deployment source in its own checkout beside your existing game. If you have already cloned the deployment repository, use its checkout and start with the unzip command.

```bash
cd /home/dkipple/Games/text-rpg
read -r -p "Paste the HTTPS clone URL from GitHub: " expanse_git_url
git clone "$expanse_git_url" expanse-render-repo
cd expanse-render-repo
unzip /home/dkipple/Games/text-rpg/Expanse-Render-1.9.1.zip
git status --short
git add -- .gitignore .python-version LICENSE RENDER-SETUP.md render.yaml requirements.txt render_server.py private_game.py restore_save.py engine editor server web
git diff --cached --stat
git commit -m "Deploy the private Expanse web engine on Render"
git push -u origin HEAD
```

Run the commands in order. If a clone or checkout fails, stop there. If a file already exists, review the incoming version before replacing it. If your branch requires a pull request, push these changes to a feature branch, merge through GitHub, then select the merged branch in Render. Only server source and browser assets belong in the repository. Game exports, credentials and saves stay outside it.

## Deploy the private test

1. Open the Render dashboard and leave the **Existing Image** form. Select **New → Blueprint**. Choose **GitHub**, then **Connect** beside the private repository you just updated. Grant Render access to that repository if prompted.
2. Choose the branch containing the commit. Leave **Blueprint Path** at **render.yaml**. You should see one Python web service named **expanse-private** with one persistent disk. A second web service, static site, database or Docker image is unnecessary.
3. Set **EXPANSE_OWNER_NAME** to your character's name and **EXPANSE_OWNER_PASSWORD** to a new password of 15–128 characters. Set these only in Render. Additional accounts default to an empty list. The owner account has no expiration unless you enter one.
4. Review the price before selecting **Deploy Blueprint**. The supplied configuration uses one instance with 1 CPU, 2 GB RAM and a 1 GB disk mounted at **/var/data/expanse**. Listed base cost for continuous use is **$25.25/month**, before usage-based charges, taxes or paid workspace fees. There is no paid resource in GitHub itself created by these directions. The 512 MB plan costs $7.25/month with this disk, but local service-plus-game memory reached about 472 MiB with Wild Lands. The supplied plan leaves room for usage that the short test did not exercise.
5. Wait for **Live**, open the service's HTTPS **onrender.com** link, and sign in. The public landing page is visible to anyone with that URL. Game data, play and downloads require a provisioned account. Render supplies HTTPS and the WebSocket uses the same origin and port.
6. Under **Import a game**, choose **Expanse-Wild-Lands-1.9.0.expanse** or another compatible game, then select **Import world**. Select **Play Expanse** beside that world. Create your character, play, and press **Save** or **Saves → Create save** for a named checkpoint.
7. To check your live deployment, record your room, save, walk to a different room, then use **World & saves → Sign out**. Sign back in, open the same game and load the saved character. The saved room should return. Repeat after a Render service restart to check that the deployed disk retains both the imported file and checkpoint.

## Later updates and additional testers

Browser engine updates go through GitHub. For a code-only change, push it to the linked branch, then choose **Manual Deploy → Deploy latest commit** on the existing service. Keep the same persistent disk. Save before restarting the service. Reapplying a Blueprint into a second service creates a separate deployment. Changes to the Blueprint itself can change provisioned resources. Review those changes in Render.

Owners can import more game files through **World & saves**. Importing the identical bytes again reopens the existing library entry. Different game files, including revised versions with the same internal world ID, get independent save storage. The earlier version remains available with its saves. This pilot does not migrate a save between two different game files.

The default configuration provisions only the owner. When you want to add someone, enter **EXPANSE_GUESTS_JSON** as a secret environment variable in Render. Its value is a JSON array of records containing **name**, **password** and an optional **expires_at** timestamp with an explicit offset, such as **2027-01-01T00:00:00Z**. Use real passwords only in the Render dashboard. Account names are unique after normalization and case folding. For the owner, the optional variable is **EXPANSE_OWNER_EXPIRES_AT**. Empty expiration means access continues until removed. Signing in creates a session lasting at most 12 hours and never past the account expiration. Restarting clears browser sessions. Expiring or removing access leaves manual saves in place. No automatic user-data deletion period is configured.

Each account has its own single-player save directory for each imported game. One active play tab is supported across the pilot. A second tester sees a busy message while someone else plays. Closing the play tab releases the seat. Authenticated testers can download imported game files and their own saves. Only the owner can import games. This build does not run multiplayer sessions.

## Export and restore

From **World & saves**, download the **imported world** and **your manual saves**. The world download is the original .expanse file. The save ZIP contains the game's native SQLite and world-state files for your account and the selected version. A save download appears after a manual checkpoint. Close other play tabs before downloading.

For local Bazzite use, import the same game file into Expanse. Quit the game. Restore into an empty save directory for a separate Bazzite installation, or move the existing save directory aside first using your normal backup procedure. From the deployment source checkout run:

```bash
python3 restore_save.py /path/to/Expanse-manual-saves.zip /path/to/game.expanse --save-dir /path/to/separate-expanse-install/save
```

For self-hosting this same web engine, sign in and import the original .expanse first, then stop the web service and restore into an unused account/game save directory:

```bash
python3 restore_save.py /path/to/Expanse-manual-saves.zip /path/to/game.expanse --web-data /path/to/web-data --character "Your Character"
```

The helper verifies the exact world file, checks SQLite integrity and refuses to replace a nonempty save directory.

## Local smoke test

Python 3.12 and the dependencies in requirements.txt are sufficient for this server. Run the commands from this directory on Linux.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export EXPANSE_PUBLIC_URL=http://127.0.0.1:10000 PORT=10000
export EXPANSE_DATA_DIR="$PWD/data"
read -r -p "Private character name: " EXPANSE_OWNER_NAME
read -r -s -p "Private password: " EXPANSE_OWNER_PASSWORD
echo
export EXPANSE_OWNER_NAME EXPANSE_OWNER_PASSWORD
python render_server.py
```

Visit **http://127.0.0.1:10000**. On Render the server binds to **0.0.0.0:$PORT**, uses the Render-provided public URL, and requires the configured disk mount. The health endpoint is **/healthz**. The game process uses a separate authenticated loopback connection. Application access logging is disabled. Render has its own platform and service logs.

The local acceptance run covered sign-in, world import, character creation, travel, atlas, manual save, named checkpoint reload after restart, guest isolation, account expiration, a second game with a matching internal slug, and restoration of an exported save. A real embedded Chromium browser also entered the game and pressed Save. Render deployment, the production TLS connection, persistent disk mounting, physical-device browsers and sustained hosted performance require verification on the live pilot.

Render references: <https://render.com/docs/infrastructure-as-code>, <https://render.com/docs/disks>, <https://render.com/docs/websocket>, <https://render.com/pricing>.
