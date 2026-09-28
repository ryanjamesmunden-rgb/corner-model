#!/usr/bin/env bash
# Install what render_story.mjs needs: a browser, and ffmpeg for the animation.
#
# WHY THIS IS A FILE. It was thirty lines of inline bash in one workflow step, and a second
# step now needs the same thing — the locked-in post draws a picture too, and it runs after
# the freeze rather than alongside the daily draft. Copying the block would give two
# installers to keep in step, and the one that fell behind would fail as a missing picture
# rather than as an error, which is precisely how the ffmpeg problem below went unnoticed.
#
# IT NEVER FAILS THE JOB. Every path exits 0. The picture is decoration: a post that goes
# out as text is a post, and a job that dies installing a browser costs the day for the sake
# of a graphic. What it does instead is SAY what it managed, on stdout and through
# ::warning::, so a silent fallback cannot happen.
#
# ffmpeg IS NOT ON THE RUNNER, and was assumed to be. `command -v ffmpeg` failed silently,
# the `&&` short-circuited with no output at all, and the job fell through to the still
# while reporting success. The outcome is now logged either way.
#
# IDEMPOTENT, because both callers may run in the same job. npm and apt-get both no-op on
# an already-satisfied install, and playwright's own cache check is the fast path.
#
# It prints one of `video`, `image` or `none` on the last line: what the caller can expect
# to be able to render.
set -uo pipefail

PW_VERSION="${PW_VERSION:-1.49.1}"

have() { command -v "$1" >/dev/null 2>&1; }

if ! npm ls "playwright@${PW_VERSION}" >/dev/null 2>&1; then
  npm i --no-save "playwright@${PW_VERSION}" >/dev/null 2>&1 || {
    echo "::warning::could not install playwright — no picture today"
    echo "none"; exit 0
  }
fi

# PLAYWRIGHT_BROWSERS_PATH is preset on this image, so an already-present chromium is a
# no-op here rather than a second 150MB download.
npx playwright install chromium >/dev/null 2>&1 || {
  echo "::warning::could not install chromium — no picture today"
  echo "none"; exit 0
}

if ! have ffmpeg; then
  echo "installing ffmpeg"
  sudo apt-get update -qq >/dev/null 2>&1 \
    && sudo apt-get install -y --no-install-recommends ffmpeg >/dev/null 2>&1 \
    || echo "::warning::could not install ffmpeg"
fi

if have ffmpeg; then
  echo "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1)"
  echo "video"
else
  # A still is most of the value and none of the encoding risk.
  echo "::warning::no ffmpeg — the animation cannot be encoded, a still will be used"
  echo "image"
fi
