# Account photos

The profile pictures for X and Telegram, drawn from `frontend/public/favicon.svg` rather
than redrawn beside it. `mark.html` holds the geometry; `render.cjs` renders it.

## What goes where

| File | Where |
|---|---|
| `corner-model-x-avatar-400.png` | X / Twitter account photo (400×400) |
| `corner-model-telegram-loop.mp4` | Telegram profile or channel photo, animated (800×800, 4s) |
| `corner-model-loop.gif` | the same loop as a GIF (480×480), for anywhere that wants one |
| `corner-model-avatar-1000.png` | the static mark at 1000×1000, for anything else |
| `x-header-3-0.png` | X header (1500×500) |
| `relaunch-card-3-0.png` | square relaunch card (1080×1080), for posting |

## Why 3.0 and not 7.0

**There are two lineages, and only one of them is this one.** The original project was a
spreadsheet, and it reached 6.0 on its own count before it stopped — the old black-circle
logo reads `THE CORNER MODEL [6.0]`. The website restarted the count: 1.0, then 2.0, and
this is 3.0. So 3.0 is a step up, not a step back, and anyone reading it against the
spreadsheet's 6.0 is comparing two different things.

Worth knowing because the mistake is easy to make from the artwork alone: the only
surviving picture of the old project carries a HIGHER number than the current one.

## Why the version is not on the avatar

It is on the header and on the card, where text is read at size, and nowhere near the
32px circle. The old logo put the whole wordmark inside the avatar, and at 32px — a reply
row, a member list — it collapses into a dark smudge with a grey band across it. The mark
is still a corner and a ball at that size. Render `legib.html` beside the old file to see
the two columns side by side.

The old file has a second avatar problem: it is a JPG on a white grid background with the
black circle inscribed in the square, so a platform's circular crop leaves a white halo
around it on any dark timeline.

**Telegram's animated photo takes the MP4, not the GIF.** Setting a profile or channel
photo, Telegram accepts a video and will not take a GIF file — upload it the way you'd
upload a video and it offers a square crop and a cover frame. The GIF is here because a
GIF is the right file in other places (a pinned message, a post, a reply), not because
Telegram will take it as the photo.

## Why the animation rests

The last quarter of the loop is **still**, and that still frame is byte-identical to
`corner-model-x-avatar-400.png`. This is the point of the thing rather than a detail of
it: a profile photo is seen paused far more often than playing — a thumbnail in a member
list, an author line, a notification — so the state it spends most of its time in has to
be the logo. An animation that never settles has no resting state, and the account then
has no fixed mark at all.

What moves: light travels up the corner arc, the ball answers it once, everything stops.
The ball lifts four pixels. At the 32px an avatar is actually read at, more than that
reads as a wobble rather than as motion.

## Why it is scaled up from the favicon

`favicon.svg` keeps the mark at about 57% of the frame, because Android masks icons to a
circle and crops roughly 10% per edge. Every platform here masks to a circle too — but a
circle crops the **corners**, and this mark's furthest point (the wedge's bottom-left
tip) sits 204px from centre against a 256px radius at the SVG's own scale. There is room,
and an avatar needs it: it is read smaller than a favicon ever is. The render scales by
1.12, taking that tip to 228 — 28px of clearance, so nothing clips on any of them.

## Redrawing them

```
cd brand && node render.cjs          # writes avatar-{400,1000}.png and frames/
```

then the two encodes — the MP4 needs `yuv420p` and even dimensions or some Telegram
clients refuse the file outright:

```
ffmpeg -y -framerate 30 -i frames/f%04d.png -c:v libx264 -pix_fmt yuv420p \
  -profile:v high -crf 18 -an -movflags +faststart -vf scale=800:800 \
  corner-model-telegram-loop.mp4

ffmpeg -y -framerate 30 -i frames/f%04d.png -vf \
  "fps=20,scale=480:480:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3" \
  -loop 0 corner-model-loop.gif
```

The GIF's palette is built from the whole clip, not per frame; built per frame the cyan
shifts as the sweep passes over it.

**The loop seam is checked, not assumed.** `md5sum frames/f0000.png frames/f0119.png`
must match. Frame 120 would be frame 0 again, which is why the renderer walks `i/N` and
never reaches 1.0 — a loop that renders both ends shows a stutter every pass, and on a
profile photo that plays forever it is the only thing anyone notices.
