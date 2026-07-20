import { CornerDownRight } from "lucide-react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function Login() {
  const handleLogin = () => {
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen relative flex items-center justify-center overflow-hidden">
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url('https://images.pexels.com/photos/1657324/pexels-photo-1657324.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940')" }}
      />
      <div className="absolute inset-0 bg-black/80" />
      <div className="relative z-10 w-full max-w-md mx-6 fade-in">
        <div className="bg-[#0a0a0a]/80 backdrop-blur-xl border border-white/10 rounded-lg p-8">
          <div className="flex items-center gap-2 mb-8">
            <div className="h-9 w-9 rounded-md bg-primary flex items-center justify-center">
              <CornerDownRight className="h-5 w-5 text-black" strokeWidth={2.5} />
            </div>
            <div>
              <p className="font-head font-bold text-lg leading-none tracking-tight">Corner Model</p>
              <p className="font-mono-data text-[10px] text-primary tracking-widest">v2.0 · VALUE ENGINE</p>
            </div>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight mb-3">
            Find corner value<br />before the market moves.
          </h1>
          <p className="text-muted-foreground text-sm mb-8 leading-relaxed">
            Auto-updating Poisson model across 7 leagues. Fair odds, EV%, confidence ratings, and a daily value scanner.
          </p>
          <button
            data-testid="google-login-btn"
            onClick={handleLogin}
            className="w-full flex items-center justify-center gap-3 bg-white text-black font-medium text-sm rounded-md py-3 transition-colors duration-150 hover:bg-zinc-200"
          >
            <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="" className="h-5 w-5" />
            Continue with Google
          </button>
          <div className="mt-6 flex items-center gap-4 text-xs text-muted-foreground font-mono-data">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" /> Strong</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-500" /> Small edge</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-500" /> No edge</span>
          </div>
        </div>
      </div>
    </div>
  );
}
