import type { Metadata } from "next";
import Link from "next/link";
import Copy from "@/components/Copy";
import copy from "@/lib/landing/copy.json";
import logos from "@/lib/landing/logos.json";
import s from "./landing.module.css";

// The landing page. Every word comes from lib/landing/copy.json, the text written in the brand page's form;
// the links are fixed here.
const X = "https://x.com/0xSero";
const PLUGIN = "https://github.com/sybil-solutions/omarchy-local-ai";
const INSTALL = `omarchy plugin add ${PLUGIN} --enable`;
const NAV: Record<string, string> = { models: "/models/", hardware: "/hardware/", videos: "#videos", "how it works": "#how", github: PLUGIN, docs: "/docs/", api: "/docs/#api" };
const GROUP_LINK: Record<string, string> = { gpuLogos: "/hardware/", modLogos: "/models/" };

type Logo = { name: string; wordmark: boolean; body: string };
const LOGOS = logos as Record<string, Logo>;

export const metadata: Metadata = {
  title: { absolute: `${copy.word}: ${copy.sHead}` },
  description: copy.sSub ?? undefined,
};

const list = (v: string | null) => String(v ?? "").split(",").map((x) => x.trim()).filter(Boolean);

function XIcon() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" className={s.xicon}>
      <path fill="currentColor" d="M18.24 2.25h3.31l-7.23 8.26 8.5 11.24h-6.66l-5.21-6.82-5.97 6.82H1.67l7.73-8.84L1.25 2.25h6.83l4.71 6.23 5.45-6.23Zm-1.16 17.52h1.83L7.08 4.13H5.12l11.96 15.64Z" />
    </svg>
  );
}

function Play({ big }: { big?: boolean }) {
  return (
    <span className={big ? `${s.play} ${s.playBig}` : s.play} aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M7 4.5v15l13-7.5z" /></svg>
    </span>
  );
}

function BrandLogo({ k }: { k: string }) {
  const L = LOGOS[k];
  if (!L) return null;
  // The Intel and AMD glyphs are wordmarks with empty space above and below, so they are drawn larger and show no name.
  const scale = L.wordmark ? (k === "amd" ? 3.6 : 2.4) : 1;
  return (
    <span className={s.logo} title={L.name}>
      <svg viewBox="0 0 24 24" fill="currentColor" fillRule="evenodd" style={{ height: `${scale}em`, margin: `${-(scale - 1) / 2}em 0` }} dangerouslySetInnerHTML={{ __html: L.body }} />
      {!L.wordmark && <span>{L.name}</span>}
    </span>
  );
}

function Thumb({ title, meta, pos, big }: { title?: string | null; meta?: string | null; pos: string; big?: boolean }) {
  return (
    <a href={X} className={s.thumb} target="_blank" rel="noreferrer">
      <span className={s.frame}>
        <img src="/landing/hands.svg" alt="" style={{ objectPosition: pos }} />
        <Play big={big} />
        {meta && <span className={s.meta}>{meta}</span>}
      </span>
      {title && <span className={s.thumbTitle}>{title}</span>}
    </a>
  );
}

export default function Landing() {
  const groups = ([["gpuTitle", "gpuLogos"], ["harTitle", "harLogos"], ["modTitle", "modLogos"]] as const)
    .map(([t, l]) => ({ title: copy[t], keys: list(copy[l]).filter((k) => LOGOS[k]), href: GROUP_LINK[l] }))
    .filter((g) => g.keys.length);
  const steps = ([["s1t", "s1d"], ["s2t", "s2d"], ["s3t", "s3d"]] as const).map(([t, d]) => [copy[t], copy[d]]);
  const videos = ([["v1t", "v1m", "0% 50%"], ["v2t", "v2m", "50% 50%"], ["v3t", "v3m", "100% 50%"]] as const).map(([t, m, pos]) => ({ title: copy[t], meta: copy[m], pos }));

  return (
    <div className={s.page}>
      <header className={s.nav}>
        <Link href="/" className={s.word}>{copy.word}</Link>
        <nav>
          {list(copy.sNav).map((label) => {
            const href = NAV[label.toLowerCase()] ?? "#";
            return href.startsWith("http") ? <a key={label} href={href}>{label}</a> : <Link key={label} href={href}>{label}</Link>;
          })}
          {copy.sFollow && <a href={X} className={s.btn}><XIcon />{copy.sFollow}</a>}
        </nav>
      </header>

      <section className={s.hero}>
        <h1>{copy.sHead}</h1>
        {copy.sSub && <p>{copy.sSub}</p>}
        <div className={s.cmd}>
          <span className={s.prompt}>$</span>
          <code title={INSTALL}>{copy.sCmd}</code>
          <Copy text={INSTALL} event="install_copied" props={{ from: "landing" }} />
        </div>
      </section>

      <div className={s.art}>
        <img src="/landing/hands.svg" alt="Two hands drawn in dots, reaching for each other" />
        {copy.credit && <span className={s.credit}>{copy.credit}</span>}
      </div>

      <div className={s.demo}><Thumb meta={copy.sDemo} pos="50% 50%" big /></div>

      <section className={s.supported}>
        {copy.supLabel && <div className={s.label}>{copy.supLabel}</div>}
        {groups.map((g) => (
          <div key={g.title ?? g.keys[0]} className={s.group}>
            {g.href ? <Link href={g.href} className={s.groupTitle}>{g.title}</Link> : <span className={s.groupTitle}>{g.title}</span>}
            <div className={s.logos}>{g.keys.map((k) => <BrandLogo key={k} k={k} />)}</div>
          </div>
        ))}
      </section>

      <section id="videos" className={s.section}>
        <div className={s.head}><span className={s.label}>{copy.sWatch}</span><a href={X} className={s.more}>{copy.sWatchLink}</a></div>
        <div className={s.videos}>{videos.map((v) => <Thumb key={v.pos} {...v} />)}</div>
      </section>

      <section id="how" className={s.section}>
        <div className={s.head}><span className={s.label}>{copy.sHow}</span></div>
        <div className={s.steps}>
          {steps.map(([t, d], i) => (
            <div key={i} className={s.step}><span className={s.num}>0{i + 1}</span><h3>{t}</h3><p>{d}</p></div>
          ))}
        </div>
      </section>

      <section className={`${s.section} ${s.follow}`}>
        <div className={s.followText}>
          <span className={s.label}>{copy.sXHead}</span>
          {copy.sXText && <p>{copy.sXText}</p>}
          <a href={X} className={s.btn}><XIcon />{copy.sXBtn}</a>
        </div>
        {[0, 1].map((i) => (
          <a key={i} href={X} className={s.post} target="_blank" rel="noreferrer">
            <span className={s.postHead}><i />{copy.sPostName} <span>{copy.sPostHandle}</span><XIcon /></span>
            <span className={s.line} style={{ width: "90%" }} /><span className={s.line} style={{ width: "64%" }} />
            <span className={s.postMedia}><Play /></span>
          </a>
        ))}
      </section>

      <footer className={s.foot}><a href={X}>{copy.sFooter}</a></footer>
    </div>
  );
}
