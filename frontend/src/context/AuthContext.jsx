import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setToken } from "@/lib/api";

// Who is signed in, and the Google button that gets them there.
//
// The site is PUBLIC. Nothing here gates anything — signing in adds your starred games
// and your own prices, and every screen works without it. So `user` being null is the
// ordinary state, not a loading failure, and nothing should render a spinner over it.
//
// The client id comes from /api/config at runtime rather than the build, so it is
// configured in exactly one place (the Render environment) and changing it needs no
// rebuild. That is the same lesson JOIN_URL taught: a build-time value can be served
// stale from a cache with nothing reporting why.

const AuthContext = createContext({
  user: null, ready: false, member: false, clientId: "", starred: new Set(),
  starredTeams: new Set(), setStarredTeam: () => {},
  setStarred: () => {}, setMember: () => {}, signOut: () => {}, renderButton: () => {},
});

export const useAuth = () => useContext(AuthContext);

const GSI_SRC = "https://accounts.google.com/gsi/client";

/** Load Google's script once, however many components ask for it. */
let gsiPromise = null;
function loadGsi() {
  if (gsiPromise) return gsiPromise;
  gsiPromise = new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve(window.google);
    const el = document.createElement("script");
    el.src = GSI_SRC;
    el.async = true;
    el.defer = true;
    el.onload = () => (window.google?.accounts?.id ? resolve(window.google) : reject(new Error("gsi missing")));
    el.onerror = () => reject(new Error("gsi blocked"));
    document.head.appendChild(el);
  });
  return gsiPromise;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [clientId, setClientId] = useState("");
  // WHICH FIXTURES ARE ALREADY STARRED, held once for the whole app. Without this every
  // star renders empty on load however many times you have saved the game — you star it,
  // navigate away, come back, and it looks like nothing happened. One fetch, shared,
  // rather than a request per star on every list.
  const [starred, setStarredSet] = useState(() => new Set());
  // Followed teams, held alongside starred fixtures and for the same reason: without it
  // every team star renders empty on load, so following looks like it did nothing.
  const [starredTeams, setStarredTeamsSet] = useState(() => new Set());
  const initialised = useRef(false);

  // Resume an existing session, and pick up the client id. Both failures are silent on
  // purpose: signed out is normal, and a backend that cannot be reached should leave a
  // public site readable rather than blocking it behind a broken sign-in.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const cfg = await api.config();
        if (alive) setClientId(cfg?.google_client_id || "");
      } catch { /* sign-in unavailable; the rest of the site is not */ }
      if (getToken()) {
        try {
          const d = await api.me();
          if (alive) setUser(d?.user || null);
          if (!d?.user) setToken(null);         // expired or revoked — stop sending it
        } catch { setToken(null); }
      }
      if (alive) setReady(true);
    })();
    return () => { alive = false; };
  }, []);

  // Load the starred set whenever we learn who the user is, and clear it on sign-out so
  // the next person to use this browser does not inherit the last one's stars.
  useEffect(() => {
    if (!user) { setStarredSet(new Set()); setStarredTeamsSet(new Set()); return; }
    let alive = true;
    api.favourites()
      .then((d) => alive && setStarredSet(new Set((d.favourites || []).map((f) => f.fixture_id))))
      .catch(() => { /* stars just render empty; nothing else breaks */ });
    api.favouriteTeams()
      .then((d) => alive && setStarredTeamsSet(new Set((d.teams || []).map((t) => t.team_id))))
      .catch(() => { /* same — a failed load leaves stars hollow, not the page broken */ });
    return () => { alive = false; };
  }, [user]);

  // Membership lives on the user record, so unlocking is a local update of the same
  // object the server already returned rather than a second source of truth.
  const setMember = useCallback((on) => {
    setUser((u) => (u ? { ...u, member: on } : u));
  }, []);

  const setStarredTeam = useCallback((teamId, on) => {
    setStarredTeamsSet((prev) => {
      const next = new Set(prev);
      on ? next.add(teamId) : next.delete(teamId);
      return next;
    });
  }, []);

  const setStarred = useCallback((fixtureId, on) => {
    setStarredSet((prev) => {
      const next = new Set(prev);
      on ? next.add(fixtureId) : next.delete(fixtureId);
      return next;
    });
  }, []);

  const onCredential = useCallback(async (resp) => {
    try {
      const d = await api.signInWithGoogle(resp.credential);
      setToken(d.token);
      setUser(d.user);
    } catch (e) {
      // Surfaced rather than swallowed: a sign-in that silently does nothing is the
      // worst version of this, because the user has no idea whether to try again.
      const msg = e?.response?.data?.detail || "Sign-in failed — please try again";
      window.alert(msg);
    }
  }, []);

  /** Draw Google's button into `el`. No-op until the client id has arrived. */
  const renderButton = useCallback(async (el) => {
    if (!el || !clientId) return;
    try {
      const google = await loadGsi();
      if (!initialised.current) {
        google.accounts.id.initialize({ client_id: clientId, callback: onCredential });
        initialised.current = true;
      }
      el.innerHTML = "";
      google.accounts.id.renderButton(el, {
        theme: "filled_black", size: "medium", shape: "pill",
        // "Continue with Google" rather than "Sign in with": first sign-in CREATES the
        // account (see /auth/google), so most people clicking this have no account yet
        // and "sign in" reads as something they are not eligible for. "Continue" is
        // true for both, which is why it is the standard wording for a combined button.
        //
        // On a phone the worded button eats most of a narrow header. The G on its own is
        // universally understood, and the header is not where sign-in gets explained.
        ...(window.matchMedia("(max-width: 639px)").matches
          ? { type: "icon" } : { text: "continue_with" }),
      });
    } catch { /* script blocked; the sign-in button simply does not appear */ }
  }, [clientId, onCredential]);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    try { window.google?.accounts?.id?.disableAutoSelect?.(); } catch { /* ignore */ }
  }, []);

  return (
    <AuthContext.Provider value={{ user, ready, member: !!user?.member, clientId, starred, setStarred, starredTeams, setStarredTeam, setMember, signOut, renderButton }}>
      {children}
    </AuthContext.Provider>
  );
}
