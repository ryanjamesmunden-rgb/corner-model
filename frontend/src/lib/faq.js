// The questions people actually ask before and after paying.
//
// THE RULE FOR THIS FILE: every answer must be true of the code that implements it. An
// FAQ is the page a sceptical buyer reads most closely and the page a disputing customer
// quotes back at you, so a stale answer here is worse than no answer — "it said I could
// cancel on the site" is a chargeback if the button is not there.
//
// Which means: if you change how cancelling, access or the guarantee work, change this
// too. The answers below are pinned to /account (cancel + resume), billing.py (period-end
// cancellation, grandfathering) and the guarantee text on /join.
//
// It is DATA rather than markup so the same list can be rendered on /join, on /faq, and
// anywhere else, without three copies drifting apart — the same reason shareText.js
// exists.

/**
 * @param price   the headline price, so it is stated in one place
 * @param instant whether checkout grants access immediately (Stripe) or by hand (the
 *                old payment-link fallback). Getting this wrong tells people to wait for
 *                access they already have, or to expect instantly what takes hours.
 * @param support how to reach a person, as a phrase ("email x@y" / "message @z on
 *                Telegram"), or "" when nothing is configured. The refund answer names
 *                it, because "refunded on request" with no address given is the sentence
 *                a disputing customer screenshots.
 */
export const faqSections = ({ price = "£20", instant = true, hasTutorial = false,
                              support = "" } = {}) => [
  {
    title: "Getting started",
    items: [
      {
        q: "Do I need an account?",
        a: `Yes — sign in with Google before you subscribe. It takes a few seconds, and it's
            how you manage or cancel your subscription afterwards. Without an account there'd
            be nowhere for you to do that.`,
      },
      {
        q: "How soon do I get access after paying?",
        a: instant
          ? `Straight away. The members-only screens unlock on your account as soon as the
             payment goes through — you don't need to message anyone or wait to be added.`
          : `Checkout asks for your Telegram username and access is added by hand, so allow
             a few hours.`,
      },
      {
        q: "Can I follow my own team?",
        a: `Yes, and it's worth doing. Tap the bell next to any side and their upcoming
            fixtures collect on your Saved page, so you stop scrolling the board to find
            them. The star next to a fixture does the other half of the job — it keeps one
            game to come back to once the prices are up. There's a quick picker on your
            account page if you'd rather start from the best corner sides.`,
      },
      {
        q: "What's the difference between the free and VIP channels?",
        a: `The free channel carries the shape of what the model is seeing — which teams are
            on a run, which games it likes, and how the previous week's calls landed. VIP
            carries the part you can act on: the lines, the prices and the reasoning, before
            kick-off, plus the members-only screens on this site.`,
      },
    ],
  },
  {
    title: "Cancelling and billing",
    items: [
      {
        q: "How do I cancel?",
        a: `On your account page — "Cancel subscription", then confirm. Two clicks, no email
            required, no waiting on a reply. You can restart from the same place.`,
      },
      {
        q: "Do I lose access the moment I cancel?",
        a: `No. You keep everything until the end of the period you've already paid for, and
            you aren't charged again. Cancelling on day 2 of a month means you still have the
            other 28 days.`,
      },
      {
        q: "Can I change my mind after cancelling?",
        a: `Yes. While the subscription is winding down the same button reads "Resume
            subscription" and puts it straight back.`,
      },
      {
        q: `How much is it?`,
        a: `${price} a month, and it can be stopped at any time from your account.`,
      },
      {
        q: "How do I actually claim the refund?",
        a: `Ask${support ? ` (${support})` : " in the Telegram channel"}, within 14 days
            of the month ending. Cancelling and refunding are separate things: you can
            stop paying yourself on your account page in two clicks, but a month back
            under the guarantee needs a person, because it is measured on how the
            channel's posted picks settled and no button can work that out.`,
      },
      {
        q: "Something has gone wrong — how do I reach a human?",
        a: `${support ? `Please ${support}.` : "The Telegram channel is the way through."}
            Payment taken but no access, locked out of your account, anything the site has
            got stuck on — that is the route, and it is the same one that answers refund
            requests.`,
      },
      {
        q: "Where do I update my card or get an invoice?",
        a: `From your account page — "Update card or view invoices" opens the billing portal.
            Card details are handled entirely by Stripe and never touch this site.`,
      },
    ],
  },
  {
    title: "What you're actually buying",
    items: [
      {
        q: "What's on the site that isn't free?",
        a: `The Corner Streak Finder and the Corner Mismatches screen are members-only.
            The fixture board, best bets, chase board, trends and corner tables are open to
            everyone, so you can see how the model reads a game before you pay for anything.`,
      },
      {
        q: "Which leagues does it cover?",
        a: `28 leagues across 20 countries, from the Premier League and the Championship to
            Eliteserien, the Brazilian Série A and J1. Projections are built from real
            finished matches — the screens say "real games only" because that is what they
            count.`,
      },
      ...(hasTutorial ? [{
        q: "I've subscribed — where do I start?",
        a: `There's a short walkthrough on your account page covering where the value is,
            how to read a streak and what the projections mean. It's the fastest way in;
            the boards make a lot more sense after five minutes of it.`,
      }] : []),
      {
        q: "What is a corner streak?",
        a: `A team that keeps landing the same side of a corner line — say 5 or more team
            corners in each of its last five games. The site shows how long the run is, how
            many of those games actually settled, and what the next fixture projects at.`,
      },
    ],
  },
  {
    title: "The honest bit",
    items: [
      {
        q: "Do you guarantee I'll make money?",
        a: `No, and be careful with anyone who does. The model finds spots where it thinks the
            price is wrong; over enough bets that is an edge, and over a handful it is noise.
            Losing weeks are part of it.`,
      },
      {
        q: "Are the monthly figures on the join page verified by the site?",
        a: `Not yet, and the page says so rather than implying otherwise. Those figures are
            stated — the site's own ledger currently tracks the model's automated selections
            rather than the picks sent to the channel, so it cannot check them for you. Once
            every sent pick is logged and settled here, the record becomes computed from
            results instead of typed.`,
      },
      {
        q: "What's the money-back guarantee?",
        a: `Measured on the picks posted in the channel, flat 1 point per pick, at the odds
            shown when the pick went out. If a month's picks close below 0 points, that
            month's ${price} is refunded on request within 14 days of month end. It covers the
            subscription fee, never betting losses — your own returns depend on your stakes
            and the prices you get.`,
      },
      {
        q: "Is this suitable for everyone?",
        a: `No. It's 18+, and it's a tool for people who already bet, not a reason to start.
            If betting has stopped being fun, stop and talk to someone at BeGambleAware.`,
      },
    ],
  },
];
