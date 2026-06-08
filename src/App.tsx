import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, LogIn, X } from "lucide-react";
import { useEffect, useState } from "react";

/* ── animation variants ── */
const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
};

/* ── product highlights ── */
const highlights = [
  { icon: "✨", title: "文生图", text: "输入提示词，即刻生成高质量图片" },
  { icon: "📐", title: "多种比例和分辨率", text: "7 种比例 × 3 档分辨率，适配各类创作场景" },
  { icon: "📁", title: "资产管理", text: "收藏、下载、批量操作，生成结果井井有条" },
  { icon: "💎", title: "透明定价", text: "按需充值，无隐藏费用" },
];

/* ── how it works ── */
const steps = [
  { num: "1", title: "输入描述", text: "用自然语言描述你想要的画面" },
  { num: "2", title: "选择参数", text: "挑选比例和分辨率，精确控制输出" },
  { num: "3", title: "获得图片", text: "AI 即刻生成，下载或存入资产库" },
];

/* ── types ── */
type SessionUser = { username: string; role: string; points: number };
type SessionState = { authenticated: boolean; user?: SessionUser };

/* ═══════════════════════════════════════════════════════
   App
   ═══════════════════════════════════════════════════════ */
function App() {
  const [authMode, setAuthMode] = useState<"login" | "register" | null>(null);
  const [session, setSession] = useState<SessionState>({ authenticated: false });

  useEffect(() => {
    let isMounted = true;
    fetch("/api/session")
      .then((r) => (r.ok ? r.json() : { authenticated: false }))
      .then((p: SessionState) => {
        if (isMounted && p.authenticated) setSession(p);
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="app-shell">
      <Nav onAuthOpen={setAuthMode} session={session} />
      <Hero session={session} onAuthOpen={setAuthMode} />
      <Highlights />
      <HowItWorks />
      <Footer />
      <AnimatePresence>
        {authMode ? (
          <AuthModal mode={authMode} onModeChange={setAuthMode} onClose={() => setAuthMode(null)} />
        ) : null}
      </AnimatePresence>
    </main>
  );
}

/* ═══════════════════════════════════════════════════════
   Nav
   ═══════════════════════════════════════════════════════ */
function Nav({
  onAuthOpen,
  session,
}: {
  onAuthOpen: (mode: "login" | "register") => void;
  session: SessionState;
}) {
  return (
    <nav className="nav">
      <a className="brand" href="/" aria-label="绘世首页">
        <span>绘世</span>
      </a>
      <div className="nav-actions">
        {session.authenticated ? (
          <>
            <a className="nav-action" href="/workspace">
              工作台
            </a>
            <a className="nav-action" href="/account">
              账户
            </a>
            <a className="nav-action" href="/pricing">
              充值
            </a>
          </>
        ) : (
          <>
            <button className="nav-action" type="button" onClick={() => onAuthOpen("login")}>
              <LogIn size={16} />
              登录
            </button>
            <button className="nav-register" type="button" onClick={() => onAuthOpen("register")}>
              注册
            </button>
          </>
        )}
      </div>
    </nav>
  );
}

/* ═══════════════════════════════════════════════════════
   Hero
   ═══════════════════════════════════════════════════════ */
function Hero({
  session,
  onAuthOpen,
}: {
  session: SessionState;
  onAuthOpen: (mode: "login" | "register") => void;
}) {
  return (
    <section className="hero">
      <motion.div
        className="hero-inner"
        initial="hidden"
        animate="visible"
        transition={{ staggerChildren: 0.12, delayChildren: 0.1 }}
      >
        <motion.h1 variants={fadeUp}>AI 图像生成</motion.h1>
        <motion.p className="hero-subtitle" variants={fadeUp}>
          输入描述，即刻生成高质量图片
        </motion.p>
        <motion.div className="hero-actions" variants={fadeUp}>
          {session.authenticated ? (
            <a className="primary-button" href="/workspace">
              开始创作
              <ArrowRight size={18} />
            </a>
          ) : (
            <button className="primary-button" type="button" onClick={() => onAuthOpen("login")}>
              开始创作
              <ArrowRight size={18} />
            </button>
          )}
          <a className="ghost-button" href="/pricing">
            充值
          </a>
        </motion.div>
      </motion.div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════
   Highlights
   ═══════════════════════════════════════════════════════ */
function Highlights() {
  return (
    <section className="highlights-section">
      <div className="section-head">
        <h2>核心能力</h2>
      </div>
      <div className="highlights-grid">
        {highlights.map((item) => (
          <article className="highlight-card" key={item.title}>
            <span className="highlight-icon">{item.icon}</span>
            <h3>{item.title}</h3>
            <p>{item.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════
   How It Works
   ═══════════════════════════════════════════════════════ */
function HowItWorks() {
  return (
    <section className="how-section">
      <div className="section-head">
        <h2>三步出图</h2>
      </div>
      <div className="steps-grid">
        {steps.map((step) => (
          <div className="step-card" key={step.num}>
            <span className="step-num">{step.num}</span>
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ═══════════════════════════════════════════════════════
   Footer
   ═══════════════════════════════════════════════════════ */
function Footer() {
  return (
    <footer className="footer">
      <span>&copy; 2026 绘世</span>
    </footer>
  );
}

/* ═══════════════════════════════════════════════════════
   AuthModal
   ═══════════════════════════════════════════════════════ */
function AuthModal({
  mode,
  onModeChange,
  onClose,
}: {
  mode: "login" | "register";
  onModeChange: (mode: "login" | "register") => void;
  onClose: () => void;
}) {
  const isLogin = mode === "login";
  const title = isLogin ? "登录绘世" : "注册绘世";

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="auth-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <motion.section
        className="auth-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.98 }}
        transition={{ duration: 0.24 }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="auth-modal-close" type="button" aria-label="关闭" onClick={onClose}>
          <X size={18} />
        </button>
        <div className="auth-modal-head">
          <span>HUISHI ACCOUNT</span>
          <h2>{title}</h2>
          <p>
            {isLogin
              ? "登录后留在首页，你可以再选择进入工作台或充值。"
              : "创建账号后返回首页，并获得 20 点注册赠送。"}
          </p>
        </div>
        <div className="auth-tabs" role="tablist" aria-label="登录注册切换">
          <button
            type="button"
            className={isLogin ? "active" : ""}
            onClick={() => onModeChange("login")}
          >
            登录
          </button>
          <button
            type="button"
            className={!isLogin ? "active" : ""}
            onClick={() => onModeChange("register")}
          >
            注册账号
          </button>
        </div>
        <form
          className="auth-modal-form"
          aria-label={title}
          action={`${isLogin ? "/login" : "/register"}?next=/`}
          method="post"
        >
          {!isLogin ? (
            <label>
              <span>邮箱</span>
              <input name="email" type="email" autoComplete="email" required />
            </label>
          ) : null}
          <label>
            <span>{isLogin ? "邮箱或管理员账号" : "昵称"}</span>
            <input
              name={isLogin ? "email" : "username"}
              autoComplete={isLogin ? "username" : "nickname"}
              required
            />
          </label>
          <label>
            <span>密码</span>
            <input
              name="password"
              type="password"
              autoComplete={isLogin ? "current-password" : "new-password"}
              minLength={6}
              required
            />
          </label>
          <button type="submit">{isLogin ? "登录" : "注册账号"}</button>
        </form>
        <a
          className="auth-fallback-link"
          href={isLogin ? "/login?next=/" : "/register?next=/"}
        >
          打开完整{isLogin ? "登录" : "注册"}页面
        </a>
      </motion.section>
    </div>
  );
}

export default App;
