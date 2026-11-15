"""Draft-only geology, weather and population handlers from the desktop Creator.

The app context supplies an isolated draft games directory, never live saves.
"""
import hashlib
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from engine import loader as engine_loader


class SpecializedEditors:
    def _editor_geology(self, slug, body=None):
        """Read or explicitly save only the selected world's geology metadata.

        Browser drafts and validation are read-only; saving never reloads the
        live world or flushes the editor's unrelated staged content.
        """
        game_dir = (self.app.GAMES_DIR / slug).resolve()
        if (not slug or slug in (".", "..") or "/" in slug or "\\" in slug
                or game_dir.parent != self.app.GAMES_DIR.resolve() or not game_dir.is_dir()):
            self._json({"error": "Unknown world."}, 404)
            return
        if body is not None:
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self._json({"error": "Open geology settings from this server."}, 403)
                return
        try:
            with self.app._editors_lock:
                path = game_dir / "metadata.json"
                # Unlike load_metadata, do not silently replace a broken file.
                raw = path.read_bytes() if path.exists() else b""
                meta = json.loads(raw) if path.exists() else {}
                if not isinstance(meta, dict):
                    raise ValueError("World metadata must be a JSON object.")
                json.dumps(meta, allow_nan=False)
                revision = hashlib.sha256(raw).hexdigest()
                from editor.cli import FILE_MAP
                data = {typ: engine_loader.load_json(fname, game_dir)
                        for typ, fname in FILE_MAP.items()}
                if body is None:
                    cfg = meta.get("geology", {"enabled": False, "seed": 17,
                               "faults": [], "volcanoes": [], "basins": []})
                    self._json({"geology": cfg, "geology_json": json.dumps(cfg, indent=2),
                        "configured": "geology" in meta, "revision": revision,
                        "living_world_enabled": bool(meta.get("living_world", False)),
                        "room_ids": [r["id"] for r in data["room"]
                                     if isinstance(r, dict) and isinstance(r.get("id"), str)]})
                    return
                if not isinstance(body, dict) or set(body) - {"geology", "geology_json", "validate_only", "revision"}:
                    raise ValueError("Send only geology (or geology_json), validate_only and revision.")
                if "geology_json" in body:
                    if "geology" in body or not isinstance(body["geology_json"], str):
                        raise ValueError("Send either a geology object or geology_json text, not both.")
                    # Preserve 64-bit seeds exactly through JavaScript clients.
                    cfg = json.loads(body["geology_json"])
                else:
                    cfg = body.get("geology")
                if not isinstance(cfg, dict):
                    raise ValueError("geology must be a JSON object.")
                if set(cfg) - {"enabled", "seed", "faults", "volcanoes", "basins"}:
                    raise ValueError("Geology accepts only enabled, seed, faults, volcanoes and basins.")
                if type(body.get("validate_only", False)) is not bool:
                    raise ValueError("validate_only must be a boolean.")
                candidate = dict(meta, geology=cfg)
                # Reject JSON's non-standard NaN/Infinity before persistence.
                encoded = json.dumps(candidate, indent=2, allow_nan=False) + "\n"
                from engine.geology_events import validate
                issues = validate(data, candidate)
                if issues:
                    self._json({"error": "Geology was not saved. " + "\n".join(issues),
                                "issues": issues}, 400)
                    return
                if body.get("validate_only", False):
                    self._json({"ok": True, "text": "Geology is valid against saved world content. Nothing was saved or applied."})
                    return
                if body.get("revision") != revision:
                    self._json({"error": "World settings changed since this dialog opened. Reload saved geology and review your changes before saving."}, 409)
                    return
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=game_dir,
                                                     prefix=".geology-", suffix=".tmp", delete=False) as out:
                        temporary = Path(out.name)
                        out.write(encoded)
                        out.flush()
                        os.fsync(out.fileno())
                    if path.exists():
                        temporary.chmod(path.stat().st_mode & 0o777)
                    os.replace(temporary, path)
                finally:
                    if temporary is not None and temporary.exists():
                        temporary.unlink()
                self._json({"ok": True, "geology": cfg, "geology_json": json.dumps(cfg, indent=2),
                            "revision": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                            "text": "Geology saved for '" + slug + "'. Export this draft and import its .expanse file to use these settings in a game."})
        except (ValueError, TypeError, KeyError) as exc:
            self._json({"error": str(exc)}, 400)
        except OSError as exc:
            self._json({"error": "Could not save or read geology: " + str(exc)}, 500)

    def _editor_regional_weather(self, slug, body=None):
        """Read or explicitly save only the selected world's regional_weather metadata.

        Browser drafts and validation are read-only; saving never reloads the
        live world or flushes the editor's unrelated staged content.
        """
        game_dir = (self.app.GAMES_DIR / slug).resolve()
        if (not slug or slug in (".", "..") or "/" in slug or "\\" in slug
                or game_dir.parent != self.app.GAMES_DIR.resolve() or not game_dir.is_dir()):
            self._json({"error": "Unknown world."}, 404)
            return
        if body is not None:
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self._json({"error": "Open regional_weather settings from this server."}, 403)
                return
        try:
            with self.app._editors_lock:
                path = game_dir / "metadata.json"
                # Unlike load_metadata, do not silently replace a broken file.
                raw = path.read_bytes() if path.exists() else b""
                meta = json.loads(raw) if path.exists() else {}
                if not isinstance(meta, dict):
                    raise ValueError("World metadata must be a JSON object.")
                json.dumps(meta, allow_nan=False)
                revision = hashlib.sha256(raw).hexdigest()
                from editor.cli import FILE_MAP
                data = {typ: engine_loader.load_json(fname, game_dir)
                        for typ, fname in FILE_MAP.items()}
                if body is None:
                    cfg = meta.get("regional_weather", {"version": 1, "enabled": False, "seed": 17, "regions": []})
                    self._json({"regional_weather": cfg, "regional_weather_json": json.dumps(cfg, indent=2),
                        "configured": "regional_weather" in meta, "revision": revision,
                        "living_world_enabled": bool(meta.get("living_world", False)),
                        "room_ids": [r["id"] for r in data["room"]
                                     if isinstance(r, dict) and isinstance(r.get("id"), str)]})
                    return
                if not isinstance(body, dict) or set(body) - {"regional_weather", "regional_weather_json", "validate_only", "revision"}:
                    raise ValueError("Send only regional_weather (or regional_weather_json), validate_only and revision.")
                if "regional_weather_json" in body:
                    if "regional_weather" in body or not isinstance(body["regional_weather_json"], str):
                        raise ValueError("Send either a regional_weather object or regional_weather_json text, not both.")
                    # Preserve 64-bit seeds exactly through JavaScript clients.
                    cfg = json.loads(body["regional_weather_json"])
                else:
                    cfg = body.get("regional_weather")
                if not isinstance(cfg, dict):
                    raise ValueError("regional_weather must be a JSON object.")
                if set(cfg) - {"version", "enabled", "seed", "regions"}:
                    raise ValueError("Regional weather accepts only version, enabled, seed and regions.")
                if type(body.get("validate_only", False)) is not bool:
                    raise ValueError("validate_only must be a boolean.")
                candidate = dict(meta, regional_weather=cfg)
                # Reject JSON's non-standard NaN/Infinity before persistence.
                encoded = json.dumps(candidate, indent=2, allow_nan=False) + "\n"
                from engine.regional_weather import validate
                issues = validate(data, candidate)
                if issues:
                    self._json({"error": "Regional weather was not saved. " + "\n".join(issues),
                                "issues": issues}, 400)
                    return
                if body.get("validate_only", False):
                    self._json({"ok": True, "text": "Regional weather is valid against saved world content. Nothing was saved or applied."})
                    return
                if body.get("revision") != revision:
                    self._json({"error": "World settings changed since this dialog opened. Reload saved regional_weather and review your changes before saving."}, 409)
                    return
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=game_dir,
                                                     prefix=".regional_weather-", suffix=".tmp", delete=False) as out:
                        temporary = Path(out.name)
                        out.write(encoded)
                        out.flush()
                        os.fsync(out.fileno())
                    if path.exists():
                        temporary.chmod(path.stat().st_mode & 0o777)
                    os.replace(temporary, path)
                finally:
                    if temporary is not None and temporary.exists():
                        temporary.unlink()
                self._json({"ok": True, "regional_weather": cfg, "regional_weather_json": json.dumps(cfg, indent=2),
                            "revision": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                            "text": "Regional weather saved for '" + slug + "'. Export this draft and import its .expanse file to use these settings in a game."})
        except (ValueError, TypeError, KeyError) as exc:
            self._json({"error": str(exc)}, 400)
        except OSError as exc:
            self._json({"error": "Could not save or read regional_weather: " + str(exc)}, 500)

    def _editor_population(self, slug, body=None):
        """Explicit, creator-only preview and staged additive generation.

        No path comes from the request, no live entities are modified, and
        applying a preview never saves unrelated Editor drafts.
        """
        game_dir = (self.app.GAMES_DIR / slug).resolve()
        if (not slug or slug in (".", "..") or "/" in slug or "\\" in slug
                or game_dir.parent != self.app.GAMES_DIR.resolve() or not game_dir.is_dir()):
            self._json({"error": "Unknown world."}, 404)
            return
        if body is not None:
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self._json({"error": "Open population settings from this server."}, 403)
                return
        try:
            from engine import population_content as population
            ed = self.app.get_editor(slug)
            with self.app._editors_lock:
                if body is None:
                    cfg = dict(id="residents_1", seed=17, count=24,
                        preset="humanlike_fictional", age_bins=[dict(row) for row in population.HUMANLIKE_BINS],
                        race="human", species="human",
                        group="", homes=[], learning="home", school_rooms=[],
                        community_learning_rooms=[], leisure_rooms=[], workplaces=[],
                        health={"enabled": False, "preset": "fictional"})
                    meta_path = game_dir / "metadata.json"
                    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                    if not isinstance(meta, dict):
                        raise ValueError("World metadata must be a JSON object.")
                    json.dumps(meta, allow_nan=False)
                    refs = {typ: [{k: row[k] for k in ("id", "name", "life_stages") if k in row}
                                  for row in ed.data.get(typ, []) if isinstance(row, dict)]
                            for typ in ("room", "species", "race", "group")}
                    self._json({"population_json": json.dumps(cfg, indent=2),
                        "references": refs, "living_world_enabled": meta.get("living_world") is True,
                        "manifest": getattr(ed, "population_manifest", {}),
                        "pending": bool(getattr(ed, "population_manifest_dirty", False)),
                        "text": "Draft only. Preview first; Apply stages new definitions. Save draft and Export remain separate."})
                    return
                if not isinstance(body, dict) or set(body) - {"action", "population_json", "preview_token"}:
                    raise ValueError("Send only action, population_json and preview_token.")
                action = body.get("action")
                if action not in ("preview", "apply"):
                    raise ValueError("Choose preview or apply.")
                if not isinstance(body.get("population_json"), str):
                    raise ValueError("population_json must be JSON text.")
                cfg = json.loads(body["population_json"])
                if not isinstance(cfg, dict):
                    raise ValueError("Population configuration must be a JSON object.")
                canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"), allow_nan=False)
                now = time.monotonic()
                for key, entry in list(self.app._population_previews.items()):
                    if now - entry["created"] > 1200:
                        del self.app._population_previews[key]
                principal = "host" if self._local_owner() else self.headers.get("X-Expanse-Player", "")
                def disk_signature():
                    from editor.cli import FILE_MAP
                    digest = hashlib.sha256()
                    for name in sorted(set(FILE_MAP.values()) | {"metadata.json", "population.json"}):
                        path = game_dir / name
                        digest.update(name.encode())
                        digest.update(b"present:" + path.read_bytes() if path.exists() else b"absent")
                    return digest.hexdigest()
                if action == "preview":
                    result = population.preview(ed, cfg)
                    if not result.get("ok"):
                        self._json({"error": "\n".join(result.get("errors", [])) or "Population preview is invalid.",
                                    "issues": result.get("errors", []), "warnings": result.get("warnings", [])}, 400)
                        return
                    # A random handle proves the caller actually previewed this
                    # configuration; deterministic generator tokens stay internal.
                    handle = secrets.token_urlsafe(24)
                    while len(self.app._population_previews) >= 64:
                        del self.app._population_previews[next(iter(self.app._population_previews))]
                    self.app._population_previews[handle] = dict(created=now, slug=slug, principal=principal,
                        editor=ed, config=canonical, token=result["preview_token"],
                        disk_revision=disk_signature(), applied=None)
                    self._json({"ok": True, "preview_token": handle, "no_op": result.get("no_op", False),
                        "summary": result.get("summary", {}), "warnings": result.get("warnings", []),
                        "text": "Preview only. No definitions, files or running characters changed."})
                    return
                entry = self.app._population_previews.get(body.get("preview_token"))
                if (entry is None or entry["slug"] != slug or entry["principal"] != principal
                        or entry["editor"] is not ed or entry["config"] != canonical):
                    self._json({"error": "Preview is missing, expired or does not match this draft. Preview again before applying."}, 409)
                    return
                def staged_signature():
                    return hashlib.sha256(json.dumps([ed.data, getattr(ed, "population_manifest", {})],
                        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
                if entry["applied"] is not None:
                    if entry.get("applied_state") != staged_signature():
                        self._json({"error": "This preview was already applied, but Editor content has since changed or been reverted. Inspect current content and preview again."}, 409)
                    else:
                        self._json(dict(entry["applied"], no_op=True))
                    return
                if entry["disk_revision"] != disk_signature():
                    self._json({"error": "Saved world files changed after this preview. Reload the Editor and preview again before applying."}, 409)
                    return
                try:
                    result = population.install(ed, cfg, expected_preview=entry["token"])
                except population.PopulationError as exc:
                    self._json({"error": str(exc)}, 409)
                    return
                if not result.get("ok"):
                    self._json({"error": "\n".join(result.get("errors", [])) or "Population changed. Preview again.",
                                "issues": result.get("errors", [])}, 409)
                    return
                response = {"ok": True, "installed": result.get("installed", True),
                    "no_op": result.get("no_op", False), "summary": result.get("summary", {}),
                    "text": ("This cohort is already recorded. No definitions were added, repaired or restored. Existing edits and saves remain unchanged."
                             if result.get("no_op") else "Population definitions staged for '" + slug + "'. Review NPC fields, then Save draft and Export. Existing residents and saves were not rebalanced.")}
                entry["applied"] = response
                entry["applied_state"] = staged_signature()
                self._json(response)
        except (ValueError, TypeError, KeyError) as exc:
            self._json({"error": str(exc)}, 400)
        except OSError as exc:
            self._json({"error": "Could not read population content: " + str(exc)}, 500)

