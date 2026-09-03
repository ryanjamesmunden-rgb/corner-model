// Turning whatever YouTube link you pasted into something embeddable.
//
// The URL is set once, by hand, in an environment variable — which means it will be
// whatever form the browser happened to be showing: a watch?v= link, a youtu.be share
// link, a /live/ link, or the embed URL already. Accepting one shape and silently
// rendering nothing for the others is the kind of bug that looks like "the video is
// broken" and is actually "you pasted the wrong flavour of the same link".
//
// nocookie.com on purpose: it is YouTube's privacy-enhanced host, which does not set
// tracking cookies until someone actually plays the video. On a page that people reach
// straight after paying, that is worth the zero effort it costs.

const ID = /^[\w-]{11}$/;

/** The 11-character video id from any YouTube URL shape, or "" if it isn't one. */
export const youtubeId = (url) => {
  const raw = String(url || "").trim();
  if (!raw) return "";
  if (ID.test(raw)) return raw;                    // already just an id
  let u;
  try {
    u = new URL(raw.startsWith("http") ? raw : `https://${raw}`);
  } catch {
    return "";
  }
  const host = u.hostname.replace(/^www\./, "");
  if (host === "youtu.be") return ID.test(u.pathname.slice(1)) ? u.pathname.slice(1) : "";
  if (!/(^|\.)youtube(-nocookie)?\.com$/.test(host)) return "";
  const v = u.searchParams.get("v");
  if (v && ID.test(v)) return v;
  // /embed/<id>, /live/<id>, /shorts/<id>, /v/<id>
  const m = u.pathname.match(/^\/(embed|live|shorts|v)\/([\w-]{11})/);
  return m ? m[2] : "";
};

/**
 * The embed URL for a video, or "" when the link is unusable.
 *
 * Returning "" rather than a broken iframe matters: the caller renders nothing at all,
 * so a site with no tutorial configured looks finished rather than showing an empty
 * black box where a video should be. Same rule the sign-in button follows.
 */
export const youtubeEmbed = (url, { autoplay = false } = {}) => {
  const id = youtubeId(url);
  if (!id) return "";
  const params = new URLSearchParams({ rel: "0", modestbranding: "1" });
  if (autoplay) params.set("autoplay", "1");
  return `https://www.youtube-nocookie.com/embed/${id}?${params}`;
};
