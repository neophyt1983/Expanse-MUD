# Expanse 1.9.7 on Render

**The 1.9.7 character-name update is a code update for the existing 1.9.6 deployment.** It keeps the already imported `Expanse-Wild-Lands-1.9.6.expanse` file and its existing update-template digest. Upload the supplied `github-upload` contents and deploy the latest commit. The creation form now accepts a character's first and last name independently of the login account, and its fields fit narrow dialogs.

This repository runs the Expanse Python engine and browser player. The complete `.expanse` file supplies the authored world: its rooms, characters, creatures, quests, books, media and gameplay settings. Render runs the simulation and game clock; the browser displays the world and sends player actions over a WebSocket.

**The 1.9.6 release requires both the updated server code and Expanse-Wild-Lands-1.9.6.expanse.** Updating only one does not install the complete release. Existing adventures can use the supplied compatibility update while retaining their original save identity; follow **Upgrade an existing adventure** below.

The normal deployment, account setup, play and editing workflows use GitHub, Render and the game in your browser. A terminal is optional.

## Update the existing GitHub repository

1. Download and extract the supplied **server update ZIP** on your computer. The 1.9.7 character-name patch applies to an installed 1.9.6 server; its existing world import and update-template setting stay in use. Use the deployment repository linked to your existing Render service, keeping this server project separate from the desktop/main-line project.
2. In that GitHub repository, select the branch Render deploys. At the repository root, choose **Add file → Upload files**.
3. Open the extracted release's **`github-upload`** folder and upload its contents, preserving their paths. For example, `render_server.py` and `private_game.py` go at the repository root; a file supplied as `engine/starter_safety.py` goes inside `engine/`; files under `server/`, `web/` and `editor/` keep those folders. Upload the contents of `github-upload`, without adding that enclosing folder, the ZIP, or the release-name folder to the repository.
4. Review the files GitHub will replace and commit the update. Keep the other existing engine files: an update package supplies replacements and additions to the existing application. GitHub's browser uploader accepts up to **100 files per upload**; split larger uploads into batches while preserving their paths. Finish all batches before deploying. If the branch requires a pull request, merge it before deploying that branch.
5. Open the existing Render service and choose **Manual Deploy → Deploy latest commit**. Keep its existing persistent disk. Wait for **Live**. For the 1.9.7 character-name patch, reload the game page and create a character with its own name. For a full 1.9.6 installation, continue with the world import or upgrade steps below.

Source code and browser assets belong in this repository. Import the `.expanse` file through the game website. Enter account passwords only in Render's environment settings; keep saves outside GitHub.

Before a code deployment or any Render environment change that restarts the service, every active tester should use **Save & quit**, wait for the saved-game confirmation, then submit or skip the optional questionnaire. Closing a tab or signing out does not publish a checkpoint.

## Render service settings

For an existing service, preserve the linked repository, deployed branch and persistent disk. These are the settings supplied by `render.yaml`:

| Setting | Value |
|---|---|
| Service type / runtime | Web Service / Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `python render_server.py` |
| Health check path | `/healthz` |
| Instances | `1` |
| Supplied service plan | `1c-2g` |
| Persistent disk | `expanse-data`, 1 GB |
| Disk mount path | `/var/data/expanse` |
| `EXPANSE_DATA_DIR` | `/var/data/expanse` |
| Automatic deployment | Off in the supplied Blueprint; deploy manually after all uploads are committed |

Review Render's current price and resource choices before creating or changing a paid service. The simultaneous-game limit below controls how many private game processes may run; it does not add RAM to the service.

### First deployment

1. In Render, choose **New → Blueprint**, choose **GitHub**, and connect the repository containing the complete server application. Grant access to that repository if prompted.
2. Select its deployment branch and leave **Blueprint Path** as `render.yaml`. The Blueprint defines one Python web service named `expanse-private` and its persistent disk.
3. Set `EXPANSE_OWNER_NAME` to your owner login name and `EXPANSE_OWNER_PASSWORD` to a new password of **15–128 characters**. Additional accounts default to an empty list. The owner has no expiration unless you set one. Character names are chosen separately after signing in.
4. Review the service and disk settings, then deploy. Wait for **Live** and open the service's HTTPS `onrender.com` address.
5. Sign in as the owner. Under **Import a game**, select **Expanse-Wild-Lands-1.9.6.expanse**, then choose **Import world**. Select **Play Expanse** beside that imported entry and create a character.
6. Use **Save** for a checkpoint while continuing to play, or **Saves → Create save** for a named checkpoint. Use **Save & quit** to save, end the play session and answer or skip the questionnaire.

The sign-in page is public. Imported game data, play and downloads require a provisioned account. Render supplies HTTPS; the WebSocket uses the same public origin and port. Imported worlds, manual saves, owner drafts and playtest records live on the configured persistent disk.

## Upgrade an existing adventure to 1.9.6

Keep the original imported entry and its saves. A different `.expanse` file has a different storage identity even when it contains the same internal world name. Opening the new entry starts a separate adventure; it does not move an old save into that entry.

For this release, the new world also contains the authored compatibility update used by the engine when loading supported older adventures:

1. Have all testers **Save & quit**. Download the original imported world and your manual saves from **World & saves** as a backup. Each tester can download their own saves.
2. Upload the 1.9.6 code to the linked GitHub repository and deploy that commit on the existing Render service as described above. Preserve the disk and account names.
3. Sign in as the owner and **import Expanse-Wild-Lands-1.9.6.expanse**. Leave the original imported entry in place. The newly imported entry supplies the update template; you do not need to create a new character in it to upgrade an old adventure.
4. After that import succeeds, open the existing Render service's **Environment** page and add or update:

   | Key | Value |
   |---|---|
   | `EXPANSE_UPDATE_WORLD_SHA256` | `c54c0597825053824ee8bb4cdf9ccc746fbe124eaba353eb3ae294baddcfee9f` |

   This is the **complete SHA-256 of the released Expanse-Wild-Lands-1.9.6.expanse file**. Paste the whole value, not the filename or the shortened identifier shown on the game shelf. The selected file must already be imported before this setting is enabled.

5. Use the dropdown beside **Save only** and choose **Save and deploy** to activate the new value. This restarts the service, so testers must have saved first. **Save only** stores the change for a later deployment; **Restart service** uses the already-deployed environment values.
6. Sign in again. Continue through **Play Expanse on the original imported entry**, then load your existing character or named save. When two entries have the same displayed world name, use the shortened **Game file** identifier on the shelf to distinguish them. Keep using the original entry for that continuing adventure.
7. Check your character, location, inventory and quests, then use **Save** to checkpoint the updated session. Loading the compatibility update does not silently overwrite the existing checkpoint.

For a completely new adventure, play the newly imported 1.9.6 entry instead. Importing identical file bytes again reuses the existing entry. Importing a different file normally creates an independent entry; the explicit update-template setting above is the supported bridge for this release, not a general save transfer between arbitrary worlds.

For later code-only fixes, upload their source changes and use **Manual Deploy → Deploy latest commit**. A later authored-content change also requires its `.expanse` file and the matching compatibility instructions. A revised export has a different digest; retain the pin to the released file until a compatible replacement is intentionally selected.

## Create tester accounts in Render

Accounts are provisioned in the existing service's **Environment** page. There is no in-game account-creation step.

Add the key **`EXPANSE_GUESTS_JSON`**. Its value is **JSON text pasted directly into the Render environment value box**. You do not create or upload a JSON file, and this value does not belong in GitHub.

For example, provision the next two testers as `pretzel99` and `pretzel100`:

```json
[
  {
    "name": "pretzel99",
    "password": "REPLACE_WITH_UNIQUE_SECRET_FOR_PRETZEL99"
  },
  {
    "name": "pretzel100",
    "password": "REPLACE_WITH_UNIQUE_SECRET_FOR_PRETZEL100",
    "expires_at": "2027-12-31T23:59:59Z"
  }
]
```

Replace both placeholder passwords with unique passwords of **15–128 characters** before saving. Keep the JSON quotes and commas. Add further `pretzel<number>` records to the same array, retaining the records for accounts that should continue to have access.

`expires_at` is optional. Omit it for ongoing access, or supply an ISO timestamp with `Z` or an explicit UTC offset. For the owner, the equivalent optional variable is `EXPANSE_OWNER_EXPIRES_AT`. Login names must be unique after normalization and case folding; keep an existing tester's login name stable to preserve the account's save identity.

The account name, such as `pretzel99`, identifies the login and its private saves. In **Create a character**, choose the character's own first name and optional last name. The supported name characters are letters, digits, spaces, hyphens, apostrophes and underscores; the combined normalized name is limited to 61 characters. Each nonempty name field must contain a letter. Separate accounts may use the same character name because their adventures and saves are isolated. Existing characters retain their current names and IDs. Creating another character does not rename an existing one, and creation remains unsaved until the player explicitly saves.

Choose **Save and deploy** from the Render save dropdown to activate the environment changes. All testers must Save & quit first. A service restart clears browser sign-ins, so everyone signs in again using their own name and password. A sign-in lasts at most 12 hours and never beyond the account's expiration; a new sign-in for the same account replaces that account's previous browser session. Removing or expiring an account does not delete its manual saves.

### Simultaneous private games

`EXPANSE_MAX_ACTIVE_GAMES` is optional. The default is **`2`**; accepted values are integers from **`1` through `8`**.

Each active account/world runs in its own private process and uses its own save directory. Two testers can play at the same time without sharing characters, world changes or checkpoints. These are **independent single-player adventures**, not a shared MMO world. One play tab is supported per account/world.

When all configured slots are occupied, another tester receives a capacity message. The service does not disconnect an active player to make room. Players should finish with **Save & quit** and submit or skip the questionnaire so that their slot is released. An ordinary tab close retains an unsaved running adventure for reconnection and can keep a slot occupied. Signing out ends that account's running workers without adding a checkpoint.

Raise the limit only after checking the service's memory and performance with the intended world and number of testers. The accepted maximum is a configuration bound, not a guarantee that the selected Render plan can run eight large worlds.

## Owner editing: draft, validate and export

From **World & saves**, the owner can choose **Edit a draft** beside an imported world. The editor opens a separate persistent draft. Testers do not have editor access, and editing the draft does not modify a running player's session or saved game.

1. Use the structured Creator tools for records such as rooms, NPCs, items and quests. Use **World files** to inspect and edit the world's authored JSON, including world settings, and to upload, replace or download supported media.
2. Save your changes explicitly with **Save draft** or the relevant world-file save control. Text left unsaved in a form is not a saved draft. There is no gameplay autosave as a consequence of editing.
3. Choose **Validate** and resolve reported errors before distributing the world.
4. Choose **Export .expanse**. The browser downloads the complete portable world, including its authored JSON and media; a server filesystem path is not required.
5. Return to **World & saves** and import the exported file to add that playable version. A changed export gets a separate entry and save storage. Updating an existing adventure requires an authored compatible update and the deliberate template selection described above.

World content and gameplay settings belong in the `.expanse` file. The Python engine supplies the mechanics. Keep the exported world as the portable deliverable for authored changes, including encounters, city inhabitants and defenses, institutions, creatures, quests and publications.

## Playtest feedback and owner reports

During play, a short notice explains that the service collects semantic actions, places visited, active-time estimates, injuries and recognized errors. It does not collect raw command arguments, conversation transcripts, passwords or authentication tokens in playtest records.

**Save & quit waits for a successful server checkpoint acknowledgement before ending the socket session.** The confirmation opens **Game saved — session feedback**. If Save fails, the session stays open and the questionnaire does not appear. If the acknowledgement is lost, **Check save status** checks that request; it does not automatically send a second Save.

The optional questionnaire asks for enjoyment, clarity and difficulty ratings, what the player liked or disliked, places avoided, reasons for avoiding them and the next intended goal. Players can send feedback, retry after a feedback error, or skip it. A feedback error does not undo the successful gameplay save. The explicit unsaved `quit`/`leave_no_save` commands do not claim that a checkpoint was saved and do not open the saved-session questionnaire.

The owner can open **Playtest reports** from the shelf, or visit **`/playtest`** on the same service. **`/api/playtest/report`** provides the structured report. These routes require the signed-in owner; a tester can submit feedback only for their own saved session.

Reports show actual room changes, visit counts, estimated active and idle time, injuries, deaths, recognized failed actions and interactions with authored sentient NPCs, creatures and monsters. Active time is an estimate from server actions and visible-tab activity, not proof of attention; long unobserved gaps are kept separate. Possible caution or friction appears as an interpretation to review. Unvisited places are not automatically labeled avoided, and the player's direct avoided-place answers remain separate from those interpretations.

Reports cover the last **30 days**. Storage is bounded to **100 sessions per account/world**, **1,500 recent events per session**, **300 detailed places** and **160 interaction targets** per session; retention pruning runs as the private analytics store is opened or new sessions are created. Gameplay checkpoints remain separate. Analytics may be written during play, but it never makes a gameplay Save on the player's behalf. The manual-save download contains gameplay checkpoints, not the analytics database.

## Back up and restore

From **World & saves**, download the **imported world** and **your manual saves**. The world download is the original `.expanse` file for that entry. The save ZIP contains native SQLite and world-state checkpoint files for your account and that imported identity. A save download appears after a manual checkpoint. Finish with Save & quit before downloading.

For an adventure upgraded through a pinned update template, keep both its original imported world and the selected update `.expanse` file with your backups. The original identifies the saved adventure; the update supplies the additional authored content needed to run that updated adventure with the matching engine.

The following restore commands are optional maintenance workflows. Ordinary hosted play, deployment and world import do not require them.

For local Bazzite use, import the same original game file into a compatible Expanse installation and install the matching update template when applicable. Quit the game. Restore into an empty save directory for a separate installation, or move the existing save directory aside using your normal backup procedure. From the deployment source checkout run:

```bash
python3 restore_save.py /path/to/Expanse-manual-saves.zip /path/to/original-game.expanse --save-dir /path/to/separate-expanse-install/save
```

For self-hosting this web engine, sign in and import the original `.expanse` first, plus the selected update file when applicable. Stop the web service and restore into an unused account/game save directory:

```bash
python3 restore_save.py /path/to/Expanse-manual-saves.zip /path/to/original-game.expanse --web-data /path/to/web-data --account "pretzel99"
```

The `--account` value is the Render login name that owns the saves. It may differ from every character's name in the archive. The older `--character` option remains a compatible alias for this same login-account value. The helper verifies the exact original world file, checks SQLite integrity and refuses to replace a nonempty save directory. Restore the matching engine and update-template configuration as well; the helper does not select that template for you.

## Verify the deployed service

After deploying, sign in, enter the intended world entry and check the character's location, inventory and quests. Make a manual checkpoint. Use Save & quit and complete or skip the form, then reopen that same entry and load the checkpoint. Repeat after a Render service restart to verify that the deployed disk retains the imported worlds and saves. With two provisioned testers, check that they can play independently and that neither can open the owner editor or reports.

Local checks cover checkpoint ordering and failure handling, save identity, private-worker isolation and capacity, account authorization, owner drafts, feedback and report access. Verify production HTTPS/WebSockets, disk mounting, sustained resource use and physical-device layout on the live Render service. Structural client checks do not replace a rendered mobile-browser test.

### Optional local smoke test

Python 3.12 and the dependencies in `requirements.txt` are sufficient for this server. Run these commands from the repository directory on Linux:

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

Visit **http://127.0.0.1:10000**. On Render, the server binds to `0.0.0.0:$PORT`, uses the Render-provided public URL and requires the configured persistent disk mount. The health endpoint is `/healthz`. Private game processes use authenticated loopback connections. Application access logging is disabled; Render has its own platform and service logs.

Render references: [Blueprints](https://render.com/docs/infrastructure-as-code), [persistent disks](https://render.com/docs/disks), [WebSockets](https://render.com/docs/websocket), [current pricing](https://render.com/pricing).
