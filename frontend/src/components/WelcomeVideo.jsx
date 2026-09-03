import { PlayCircle } from "lucide-react";
import { youtubeEmbed } from "@/lib/youtube";

// "How to use the site and find value", shown the moment someone's payment clears.
//
// This is the highest-leverage minute of the whole subscription. Someone who has just
// paid is at peak intent and has never seen the boards; if the first screen is a table
// of lambdas with no explanation, the second thing they do is wonder what they bought.
// A short video here is worth more than any amount of tooltip copy later.
//
// It renders NOTHING when no URL is configured, rather than an empty player. A site with
// the tutorial not yet set up should look finished, not broken — the same rule the
// sign-in button follows when the Google client id is missing.
//
// The iframe is not lazy-loaded on the post-checkout view on purpose: it is the point of
// that view. Elsewhere it loads lazily so it does not cost people who came to check a
// price.
export default function WelcomeVideo({ url, title = "How to use the site", subtitle, prominent = false }) {
  const src = youtubeEmbed(url);
  if (!src) return null;

  return (
    <section
      data-testid="welcome-video"
      className={`rounded-lg border ${prominent
        ? "border-primary/40 bg-primary/[0.04]"
        : "border-border bg-card"} p-4`}
    >
      <div className="flex items-center gap-2 mb-1">
        <PlayCircle className={`h-4 w-4 ${prominent ? "text-primary" : "text-muted-foreground"}`} />
        <h2 className="font-head font-semibold">{title}</h2>
      </div>
      {subtitle && <p className="text-sm text-muted-foreground mb-3">{subtitle}</p>}

      {/* 16:9 without aspect-ratio support worries: padding-top is the reliable trick and
          costs nothing. The iframe fills the box on every width, which matters because
          most people will open this on a phone. */}
      <div className="relative w-full overflow-hidden rounded-md bg-black" style={{ paddingTop: "56.25%" }}>
        <iframe
          src={src}
          title={title}
          loading={prominent ? "eager" : "lazy"}
          className="absolute inset-0 h-full w-full"
          frameBorder="0"
          allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    </section>
  );
}
