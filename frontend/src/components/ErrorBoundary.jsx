import { Component } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

// The difference between one broken table and a white screen.
//
// React unmounts the ENTIRE tree when a render throws and nothing catches it. This app
// had nothing catching it anywhere, so a single `undefined.toFixed()` in one cell of one
// board took down every page — header, nav, footer, the lot — and left a blank white
// screen with no message, no way back, and nothing in front of the user to report.
//
// That is not a hypothetical. Driving the real build in a browser, four different
// missing fields each produced exactly that: root emptied to zero bytes, no visible
// text. The site looked dead when one number was absent.
//
// A boundary cannot stop the throw; it stops it spreading. The broken piece is replaced
// by a panel that says what happened, and everything around it keeps working — which
// also means the person can still reach their account page to cancel, which is the one
// thing that must never be behind a crash.
//
// `resetKey` re-mounts the subtree when it changes: a board that threw on one league's
// data should get another go when the visitor switches league or tab, rather than
// staying broken until a reload.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error, info) {
    // Left as console output on purpose — there is no error-reporting service wired up,
    // and inventing one here would be a silent dependency. This at least means a
    // developer opening the console sees the real stack instead of a blank page.
    console.error("Caught by ErrorBoundary:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    const { label = "This section" } = this.props;
    return (
      <div className="bg-card border border-amber-500/30 rounded-lg p-5" data-testid="error-boundary">
        <div className="flex items-center gap-2 text-amber-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <h3 className="font-head font-semibold text-sm">{label} couldn't be displayed</h3>
        </div>
        <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
          Something in the data behind this panel wasn't what the page expected. The rest
          of the site is unaffected — the numbers themselves are fine, this is a display
          fault at our end.
        </p>
        <button
          onClick={() => this.setState({ error: null })}
          data-testid="error-boundary-retry"
          className="mt-3 inline-flex items-center gap-2 text-xs font-medium px-3 py-2 rounded-md bg-secondary border border-border hover:bg-white/10 transition-colors"
        >
          <RotateCcw className="h-3.5 w-3.5" /> Try again
        </button>
      </div>
    );
  }
}
