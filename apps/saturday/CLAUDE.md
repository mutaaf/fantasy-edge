# saturday

College football for Apple Vision Pro. See `PLAN.md` for scope and phases, `docs/design-brief.md` for the initial views.

## Rules
- **Stdlib only, Python 3.11+.** No third-party dependencies.
- **Never write credentials into the repo.** `CFBD_API_KEY` and `ESPN_API_KEY` live in the environment.
- **Raw captures in `data/capture/` are ESPN's bytes, gzipped, never edited.** Test fixtures are derived from them by script.
- **Scoreboard requests need `groups=80`.** Without it ESPN serves a curated subset, not the FBS slate.
- **An id is only unique inside its source.** Key on `(source, id)`, because ESPN and CFBD ids collide.
- **A college overtime game has no "End of Game" play.** Wake Forest–Purdue (401858224, 2OT) ends on "Rushing Touchdown" in period 6. Decide whether a game is complete from the header status (`STATUS_FINAL`), never from the last play's text, which is what fantasy-edge's `capture_is_complete` does.
- **Every analysis carries a non-empty caveat.** Report the caveat with the number.
- **Never hand-edit `project.pbxproj`.** It is generated.
