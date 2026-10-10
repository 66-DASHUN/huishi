import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

const AnimatePresence = React.Fragment;
const motion = ["span", "div", "p", "section", "form"].reduce((components, tag) => {
  components[tag] = React.forwardRef(({ initial, animate, exit, transition, whileHover, whileTap, viewport, variants, custom, layout, ...props }, ref) =>
    React.createElement(tag, { ...props, ref }),
  );
  return components;
}, {});

const HERO_VIDEO = "/static/media/shouyeshipin-sea.mp4";
const HERO_POSTER = "/static/media/shouyeshipin-poster.jpg";
const CAPABILITIES_VIDEO = "/static/media/huishi-workflow-cloud.mp4";
const CAPABILITIES_POSTER = "/static/media/huishi-workflow-cloud-poster.jpg";
const HOME_PROMPT_DRAFT_KEY = "huishi.home.promptDraft";
const CSRF_TOKEN = window.__HUISHI_CSRF_TOKEN__ || "";
function safeNextUrl(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/workspace";
  return value;
}

const initialSearchParams = new URLSearchParams(window.location.search);
const SERVER_AUTH_INTENT = window.__HUISHI_AUTH_INTENT__ || {};
const INITIAL_AUTH_MODE = ["login", "register"].includes(SERVER_AUTH_INTENT.mode)
  ? SERVER_AUTH_INTENT.mode
  : ["login", "register"].includes(initialSearchParams.get("auth"))
  ? initialSearchParams.get("auth")
  : null;
const NEXT_URL = safeNextUrl(SERVER_AUTH_INTENT.next || initialSearchParams.get("next"));
const NON_JSON_AUTH_ERROR = "请求未成功，请刷新后重试或检查邮件服务配置";
const FADE_MS = 500;
const FADE_OUT_LEAD = 0.55;

function authNextUrl() {
  try {
    if (sessionStorage.getItem(HOME_PROMPT_DRAFT_KEY)) return "/workspace?new=1";
  } catch (error) {
    // Authentication remains usable when storage is unavailable.
  }
  return NEXT_URL;
}

function ArrowUpRight({ className = "h-6 w-6" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 17L17 7" />
      <path d="M7 7h10v10" />
    </svg>
  );
}

function Play({ className = "h-6 w-6" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <polygon points="6 4 20 12 6 20 6 4" />
    </svg>
  );
}

function XIcon({ className = "h-5 w-5" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

function ArrowLeftIcon({ className = "h-4 w-4" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 12H5" />
      <path d="m12 19-7-7 7-7" />
    </svg>
  );
}

function EyeIcon({ className = "h-5 w-5" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon({ className = "h-5 w-5" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m3 3 18 18" />
      <path d="M10.6 10.6A3 3 0 0 0 14 14" />
      <path d="M9.9 4.2A10.7 10.7 0 0 1 12 4.0c6.5 0 10 8 10 8a16.5 16.5 0 0 1-3.1 4.2" />
      <path d="M6.5 6.5C3.6 8.5 2 12 2 12s3.5 8 10 8a10.9 10.9 0 0 0 5.5-1.5" />
    </svg>
  );
}

function PasswordField({ label, name, autoComplete, placeholder, minLength, required }) {
  const [visible, setVisible] = useState(false);

  return (
    <label className="auth-label">
      <span>{label}</span>
      <div className="password-field">
        <input
          name={name}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          minLength={minLength}
          placeholder={placeholder}
          required={required}
          className="auth-input auth-input-password"
        />
        <button
          type="button"
          className="password-toggle"
          aria-label={visible ? "隐藏密码" : "显示密码"}
          aria-pressed={visible ? "true" : "false"}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      </div>
    </label>
  );
}

function MaterialIcon({ path }) {
  return (
    <svg className="capability-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg className="h-7 w-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </svg>
  );
}

function ArchiveIcon() {
  return (
    <svg className="h-7 w-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 7h16" />
      <path d="M5 7l1 13h12l1-13" />
      <path d="M9 11h6" />
      <path d="M8 4h8l1 3H7l1-3Z" />
    </svg>
  );
}

function CanvasIcon() {
  return (
    <svg className="h-7 w-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 3h18v18H3V3z" />
      <path d="M8 17l3-6 4 5 2-3 3 4" />
      <path d="M14 6l4 4" />
    </svg>
  );
}

function PromptsIcon() {
  return (
    <svg className="h-7 w-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" />
      <path d="M8 7h8" />
      <path d="M8 11h6" />
    </svg>
  );
}

function MaterialsIcon() {
  return (
    <svg className="h-7 w-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z" />
      <path d="M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z" />
      <path d="M21 16l-5-5L5 21" />
    </svg>
  );
}

function FadingVideo({ src, poster, className, style, loadDelayMs = 0, loadWhenVisible = false }) {
  const videoRef = useRef(null);
  const animationFrameRef = useRef(0);
  const replayTimerRef = useRef(0);
  const fadingOutRef = useRef(false);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false);
  const [shouldLoad, setShouldLoad] = useState(() => !reducedMotion && !loadDelayMs && !loadWhenVisible);

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!media) return undefined;
    const handleChange = (event) => {
      setReducedMotion(event.matches);
      if (event.matches) setShouldLoad(false);
    };
    media.addEventListener?.("change", handleChange);
    return () => media.removeEventListener?.("change", handleChange);
  }, []);

  useEffect(() => {
    if (reducedMotion) return undefined;
    if (shouldLoad) return undefined;
    const video = videoRef.current;
    if (!video) return undefined;

    let delayTimer = 0;
    let observer = null;
    const load = () => setShouldLoad(true);

    if (loadWhenVisible) {
      observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            load();
            observer?.disconnect();
          }
        },
        { rootMargin: "0px", threshold: 0.15 },
      );
      observer.observe(video);
    } else {
      delayTimer = window.setTimeout(load, Math.max(0, loadDelayMs));
    }

    return () => {
      clearTimeout(delayTimer);
      observer?.disconnect();
    };
  }, [loadDelayMs, loadWhenVisible, reducedMotion, shouldLoad]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !shouldLoad || reducedMotion) return undefined;

    const fadeTo = (target, duration = FADE_MS) => {
      cancelAnimationFrame(animationFrameRef.current);
      const startOpacity = Number.parseFloat(video.style.opacity || "0") || 0;
      const startedAt = performance.now();

      const step = (now) => {
        const progress = Math.min(1, (now - startedAt) / duration);
        video.style.opacity = String(startOpacity + (target - startOpacity) * progress);
        if (progress < 1) animationFrameRef.current = requestAnimationFrame(step);
      };

      animationFrameRef.current = requestAnimationFrame(step);
    };

    const handleLoadedData = () => {
      video.style.opacity = "0";
      video.play().catch(() => {});
      fadeTo(1);
    };

    const handleTimeUpdate = () => {
      const remaining = video.duration - video.currentTime;
      if (!fadingOutRef.current && remaining > 0 && remaining <= FADE_OUT_LEAD) {
        fadingOutRef.current = true;
        fadeTo(0);
      }
    };

    const handleEnded = () => {
      video.style.opacity = "0";
      replayTimerRef.current = window.setTimeout(() => {
        video.currentTime = 0;
        fadingOutRef.current = false;
        video.play().catch(() => {});
        fadeTo(1);
      }, 100);
    };

    video.addEventListener("loadeddata", handleLoadedData);
    video.addEventListener("timeupdate", handleTimeUpdate);
    video.addEventListener("ended", handleEnded);
    if (video.readyState >= 2) handleLoadedData();

    return () => {
      cancelAnimationFrame(animationFrameRef.current);
      clearTimeout(replayTimerRef.current);
      video.removeEventListener("loadeddata", handleLoadedData);
      video.removeEventListener("timeupdate", handleTimeUpdate);
      video.removeEventListener("ended", handleEnded);
    };
  }, [reducedMotion, src, shouldLoad]);

  return (
    <div
      className={`video-poster-frame ${className}`}
      style={{ ...style, backgroundImage: poster ? `url("${poster}")` : undefined }}
      aria-hidden="true"
    >
      <video
        ref={videoRef}
        className="fading-video-element"
        src={shouldLoad && !reducedMotion ? src : undefined}
        poster={poster}
        autoPlay={!reducedMotion}
        muted
        playsInline
        preload={shouldLoad && !reducedMotion ? "auto" : "none"}
        style={{ opacity: 0 }}
        aria-hidden="true"
      />
    </div>
  );
}

function BlurText({ text, className, as: Tag = "p" }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  const words = useMemo(() => text.split(" "), [text]);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag ref={ref} className={`${className} ${visible ? "blur-text-visible" : ""}`}>
      {words.map((word, index) => (
        <motion.span
          key={`${word}-${index}`}
          className="hero-word"
          style={{ "--word-index": index }}
          initial={{ filter: "blur(10px)", opacity: 0, y: 50 }}
          animate={
            visible
              ? {
                  filter: ["blur(10px)", "blur(5px)", "blur(0px)"],
                  opacity: [0, 0.5, 1],
                  y: [50, -5, 0],
                }
              : undefined
          }
          transition={{
            duration: 0.7,
            times: [0, 0.5, 1],
            ease: "easeOut",
            delay: (index * 100) / 1000,
          }}
        >
          {word}
        </motion.span>
      ))}
    </Tag>
  );
}

const entrance = {
  initial: { filter: "blur(10px)", opacity: 0, y: 20 },
  animate: { filter: "blur(0px)", opacity: 1, y: 0 },
  transition: { duration: 0.75, ease: "easeOut" },
};

function Navbar({ session, onAuthOpen }) {
  const links = [
    ["#hero", "首页"],
    ["#capabilities", "创作流程"],
    ["/pricing", "积分套餐"],
  ];

  return (
    <nav className="home-nav" aria-label="首页导航">
      <a href="/" aria-label="绘世首页" className="home-brand">
        <span className="home-brand-mark">绘</span>
      </a>
      <div className="home-nav-links">
        {links.map(([href, label]) => (
          <a key={`${href}-${label}`} href={href} className="home-nav-link">
            {label}
          </a>
        ))}
        {session.authenticated ? (
          <a href="/workspace" className="home-nav-action">
            进入工作台
            <ArrowUpRight className="h-4 w-4" />
          </a>
        ) : (
          <>
            <button type="button" onClick={() => onAuthOpen("login")} className="home-nav-login">
              登录
            </button>
            <button type="button" onClick={() => onAuthOpen("register")} className="home-nav-action">
              注册
            </button>
          </>
        )}
      </div>
      <div className="home-nav-mobile">
        {session.authenticated ? (
          <a href="/workspace" className="home-nav-action" aria-label="进入工作台">
            进入
            <ArrowUpRight className="h-4 w-4" />
          </a>
        ) : (
          <button type="button" onClick={() => onAuthOpen("login")} className="home-nav-action">登录</button>
        )}
      </div>
    </nav>
  );
}

function Hero({ session, onAuthOpen }) {
  const [prompt, setPrompt] = useState("");
  const [promptError, setPromptError] = useState(false);

  const handlePromptSubmit = (event) => {
    event.preventDefault();
    const value = prompt.trim();
    if (!value) {
      setPromptError(true);
      return;
    }
    try {
      sessionStorage.setItem(HOME_PROMPT_DRAFT_KEY, value);
    } catch (error) {
      // Navigation remains available when storage is unavailable.
    }
    if (session.authenticated) {
      window.location.assign("/workspace?new=1");
      return;
    }
    onAuthOpen("login");
  };

  return (
    <section id="hero" className="home-section home-hero">
      <FadingVideo
        src={HERO_VIDEO}
        poster={HERO_POSTER}
        className="home-video home-hero-video"
      />
      <div className="hero-layout">
        <div className="hero-copy">
          <motion.div
            className="hero-kicker"
            initial={entrance.initial}
            animate={entrance.animate}
            transition={{ ...entrance.transition, delay: 0.4 }}
          >
            <span aria-hidden="true" />
            <span>绘世 AI 视觉创作空间</span>
          </motion.div>

          <BlurText text="绘梦造世" as="h1" className="hero-title" />

          <motion.p
            className="hero-subtitle"
            initial={entrance.initial}
            animate={entrance.animate}
            transition={{ ...entrance.transition, delay: 0.8 }}
          >
            让灵感在无限画布中持续显形
          </motion.p>

          <motion.form
            className={`hero-prompt-entry liquid-glass-strong ${promptError ? "is-error" : ""}`}
            initial={entrance.initial}
            animate={entrance.animate}
            transition={{ ...entrance.transition, delay: 1.1 }}
            onSubmit={handlePromptSubmit}
          >
            <input
              value={prompt}
              onChange={(event) => {
                setPrompt(event.target.value);
                if (event.target.value.trim()) setPromptError(false);
              }}
              placeholder="描述你想创造的世界"
              aria-label="描述你想创造的世界"
              aria-invalid={promptError ? "true" : "false"}
              maxLength={1000}
            />
            <button type="submit">
              开始创作
              <ArrowUpRight className="h-5 w-5" />
            </button>
          </motion.form>
          <div className="hero-prompt-tags" aria-label="创作能力">
            <span className="liquid-glass">多图参考</span>
            <span className="liquid-glass">提示词优化</span>
            <span className="liquid-glass">无限画布</span>
          </div>
          {session.authenticated ? (
            <motion.div className="hero-utility-items hero-auth-quick-links" initial={entrance.initial} animate={entrance.animate} transition={{ ...entrance.transition, delay: 1.3 }}>
              {/* 指向主站 /canvas，而不是画布应用的地址：那张卡此前直接跳到
                  画布应用的落地页（另一个域名+端口），用户点一下整页就离开了绘世，
                  观感上像外挂；而 /canvas 会用 iframe 内嵌，地址栏始终是绘世。 */}
              <StatCard key="canvas" href="/canvas" icon={<CanvasIcon />} value="画布" label="我的画布" />
              <StatCard key="prompts" href="/prompts" icon={<PromptsIcon />} value="词库" label="提示词库" />
              <StatCard key="assets" href="/assets" icon={<MaterialsIcon />} value="素材" label="我的素材" />
            </motion.div>
          ) : null}
        </div>

        <motion.div
          className="hero-flowline"
          initial={entrance.initial}
          animate={entrance.animate}
          transition={{ ...entrance.transition, delay: 1.4 }}
        >
          <div className="hero-flowline-copy">
            从灵感到成片 创作过程始终在场
          </div>
          <div className="hero-flowline-steps">
            {[
              "灵感",
              "参考",
              "生成",
              "整理",
              "复用",
            ].map((name) => (
              <span key={name}>
                {name}
              </span>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function StatCard({ href, icon, value, label, onClick }) {
  const handleClick = (event) => {
    if (!onClick) return;
    event.preventDefault();
    onClick();
  };

  return (
    <a href={href} onClick={handleClick} className="utility-entry">
      <span className="utility-icon">{icon}</span>
      <span className="utility-copy">
        <strong>{value}</strong>
        <span>{label}</span>
      </span>
      <ArrowUpRight className="utility-arrow" />
    </a>
  );
}

const capabilityCards = [
  {
    title: "灵感显形",
    text: "一句话与多图参考即可得到可用的起点",
    tags: ["提示词库", "多图参考", "生成"],
    path: "M5 21q-.825 0-1.412-.587T3 19V5q0-.825.588-1.412T5 3h14q.825 0 1.413.588T21 5v14q0 .825-.587 1.413T19 21H5Zm1-4h12l-3.75-5-3 4L9 13l-3 4Z",
  },
  {
    title: "意象共生",
    text: "在同一块画布里让多个想法互相生长",
    tags: ["无限画布", "编辑图片", "再次生成"],
    path: "M4 6.47 5.76 10H20v8H4V6.47M22 4h-4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-1.99.89-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4Z",
  },
  {
    title: "世界延展",
    text: "从单张画面走向可持续的完整世界",
    tags: ["资产库", "提示词复用", "参数复用"],
    path: "M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1Zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7Z",
  },
];

function Capabilities() {
  return (
    <section id="capabilities" className="home-section workflow-section">
      <FadingVideo src={CAPABILITIES_VIDEO} poster={CAPABILITIES_POSTER} loadWhenVisible className="home-video workflow-video" />
      <div className="workflow-layout">
        <header className="workflow-heading">
          <p>创作流程</p>
          <h2>从灵感的轮廓<br />到世界的细节</h2>
          <span>参考与生成在同一处生长</span>
        </header>

        <div className="capability-rail">
          {capabilityCards.map((card, index) => (
            <article key={card.title} className="capability-item">
              <div className="capability-meta">
                <span className="capability-index">0{index + 1}</span>
                <MaterialIcon path={card.path} />
              </div>
              <h3>{card.title}</h3>
              <p>{card.text}</p>
              <div className="capability-tags" aria-label={`${card.title}能力`}>
                  {card.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                  ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

async function postAuthForm(url, formData) {
  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "fetch",
        "X-CSRF-Token": CSRF_TOKEN,
      },
    });
    const payload = await response.json().catch(() => null);
    if (!payload) {
      return { ok: false, error: NON_JSON_AUTH_ERROR };
    }
    if (!response.ok || !payload.ok) {
      return { ok: false, error: payload.error || NON_JSON_AUTH_ERROR };
    }
    return payload;
  } catch {
    return { ok: false, error: NON_JSON_AUTH_ERROR };
  }
}

function AuthModal({ mode, onModeChange, onClose }) {
  const isLogin = mode === "login";
  const title = isLogin ? "登录绘世" : "注册绘世";
  const dialogRef = useRef(null);
  const restoreFocusRef = useRef(document.activeElement);
  const onCloseRef = useRef(onClose);
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerStep, setRegisterStep] = useState("email");
  const [notice, setNotice] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  onCloseRef.current = onClose;

  useEffect(() => {
    const dialog = dialogRef.current;
    const focusableSelector = 'button:not([disabled]), a[href], input:not([type="hidden"]):not([disabled])';
    const focusableElements = () => Array.from(dialog?.querySelectorAll(focusableSelector) || []);
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (event.key === "Tab") {
        const elements = focusableElements();
        if (!elements.length) return;
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        } else if (!dialog?.contains(document.activeElement)) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    const initialFocus = dialog?.querySelector('[data-autofocus="true"]') || focusableElements()[0];
    initialFocus?.focus();
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      restoreFocusRef.current?.focus?.();
    };
  }, []);

  useEffect(() => {
    setNotice(null);
    setIsSubmitting(false);
    if (mode === "register") setRegisterStep("email");
  }, [mode]);

  const handleLoginSubmit = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    setNotice(null);
    const nextUrl = authNextUrl();
    const payload = await postAuthForm(`/login?next=${encodeURIComponent(nextUrl)}`, new FormData(event.currentTarget));
    setIsSubmitting(false);
    if (payload.ok) {
      window.location.assign(payload.next || nextUrl);
      return;
    }
    setNotice({ type: "error", text: payload.error || "账号或密码错误" });
  };

  const handleSendCode = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    setNotice(null);
    const formData = new FormData(event.currentTarget);
    formData.set("next", authNextUrl());
    const email = String(formData.get("email") || "").trim().toLowerCase();
    const payload = await postAuthForm("/register/send-code", formData);
    setIsSubmitting(false);
    if (payload.ok) {
      setRegisterEmail(email);
      setRegisterStep("details");
      setNotice({ type: "success", text: payload.message || "验证码已发送，请查看邮箱" });
      return;
    }
    setNotice({ type: "error", text: payload.error || "验证码发送失败" });
  };

  const handleRegisterSubmit = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    setNotice(null);
    const formData = new FormData(event.currentTarget);
    formData.set("email", registerEmail);
    const nextUrl = authNextUrl();
    const payload = await postAuthForm(`/register?next=${encodeURIComponent(nextUrl)}`, formData);
    setIsSubmitting(false);
    if (payload.ok) {
      window.location.assign(payload.next || nextUrl);
      return;
    }
    setNotice({ type: "error", text: payload.error || "注册失败，请检查信息" });
  };

  return (
    <div className="auth-backdrop" role="presentation" onMouseDown={onClose}>
      <motion.section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="auth-dialog"
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.98 }}
        transition={{ duration: 0.24 }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button type="button" aria-label="关闭" onClick={onClose} className="auth-close">
          <XIcon className="h-4 w-4" />
        </button>

        <div>
          <span className="auth-caption">绘世账号</span>
          <h2 className="auth-title">{title}</h2>
        </div>

        <div className="auth-tabs">
          <button type="button" data-autofocus={isLogin ? "true" : undefined} className={`auth-tab ${isLogin ? "is-active" : ""}`} onClick={() => onModeChange("login")}>
            登录
          </button>
          <button type="button" data-autofocus={!isLogin ? "true" : undefined} className={`auth-tab ${!isLogin ? "is-active" : ""}`} onClick={() => onModeChange("register")}>
            注册账号
          </button>
        </div>

        {notice ? (
          <div className={`auth-notice ${notice.type}`} role={notice.type === "error" ? "alert" : "status"} aria-live="polite">
            {notice.text}
          </div>
        ) : null}

        {isLogin ? (
          <form key="login-form" aria-label={title} aria-busy={isSubmitting ? "true" : "false"} data-auth-state={notice?.type === "error" ? "error" : isSubmitting ? "loading" : "idle"} className="auth-form" onSubmit={handleLoginSubmit}>
            <input type="hidden" name="csrf_token" value={CSRF_TOKEN} />
            <label className="auth-label">
              <span>邮箱或用户名</span>
              <input name="email" autoComplete="username" placeholder="请输入邮箱或用户名" required className="auth-input" />
            </label>
            <PasswordField label="密码" name="password" autoComplete="current-password" minLength={6} placeholder="请输入密码" required />
            <a className="auth-link" href="/forgot-password">
              忘记密码？
            </a>
            <button type="submit" disabled={isSubmitting} className="auth-submit">
              {isSubmitting ? "登录中..." : "登录"}
            </button>
          </form>
        ) : registerStep === "email" ? (
          <form key="register-email-form" aria-label={title} aria-busy={isSubmitting ? "true" : "false"} data-auth-state={notice?.type === "error" ? "error" : isSubmitting ? "loading" : "idle"} className="auth-form" onSubmit={handleSendCode}>
            <input type="hidden" name="csrf_token" value={CSRF_TOKEN} />
            <input type="hidden" name="next" value={NEXT_URL} />
            <label className="auth-label">
              <span>邮箱</span>
              <input name="email" type="email" autoComplete="email" value={registerEmail} onChange={(event) => setRegisterEmail(event.target.value)} placeholder="用于接收验证码" required className="auth-input" />
            </label>
            <button type="submit" disabled={isSubmitting} className="auth-submit">
              {isSubmitting ? "发送中..." : "获取验证码"}
            </button>
          </form>
        ) : (
          <form key="register-details-form" aria-label={title} aria-busy={isSubmitting ? "true" : "false"} data-auth-state={notice?.type === "error" ? "error" : isSubmitting ? "loading" : "idle"} className="auth-form" onSubmit={handleRegisterSubmit}>
            <input type="hidden" name="csrf_token" value={CSRF_TOKEN} />
            <div className="auth-email-summary">
              <span>{registerEmail}</span>
              <button type="button" onClick={() => { setNotice(null); setRegisterStep("email"); }}>
                <ArrowLeftIcon className="h-3.5 w-3.5" />
                修改邮箱
              </button>
            </div>
            <label className="auth-label">
              <span>邮箱验证码</span>
              <input name="email_code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" required className="auth-input" />
            </label>
            <label className="auth-label">
              <span>昵称</span>
              <input name="username" autoComplete="nickname" required className="auth-input" />
            </label>
            <PasswordField label="密码" name="password" autoComplete="new-password" minLength={6} required />
            <label className="auth-label">
              <span>邀请码</span>
              <input name="invite_code" autoComplete="off" className="auth-input" />
            </label>
            <button type="submit" disabled={isSubmitting} className="auth-submit">
              {isSubmitting ? "注册中..." : "注册账号"}
            </button>
          </form>
        )}
      </motion.section>
    </div>
  );
}

function App() {
  const [authMode, setAuthMode] = useState(INITIAL_AUTH_MODE);
  const [session, setSession] = useState({ authenticated: false });

  useEffect(() => {
    let isMounted = true;
    fetch("/api/session")
      .then((response) => (response.ok ? response.json() : { authenticated: false }))
      .then((payload) => {
        if (isMounted) setSession(payload.authenticated ? payload : { authenticated: false });
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="home-shell">
      <Navbar session={session} onAuthOpen={setAuthMode} />
      <Hero session={session} onAuthOpen={setAuthMode} />
      <Capabilities />
      <AnimatePresence>
        {authMode ? <AuthModal mode={authMode} onModeChange={setAuthMode} onClose={() => setAuthMode(null)} /> : null}
      </AnimatePresence>
    </main>
  );
}

window.FadingVideo = FadingVideo;
window.BlurText = BlurText;
window.HuishiLanding = App;

createRoot(document.getElementById("root")).render(<App />);
