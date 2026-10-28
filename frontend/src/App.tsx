import { useEffect, useState } from 'react';
import { en } from './i18n/en';
import { ur } from './i18n/ur';
import { Workspace } from './Workspace';

type Health = 'checking' | 'healthy' | 'unavailable';

export function App() {
  const [language, setLanguage] = useState<'en' | 'ur'>(() => localStorage.getItem('shiplens-language') === 'ur' ? 'ur' : 'en');
  const [health, setHealth] = useState<Health>('checking');
  const [attempt, setAttempt] = useState(0);
  const t = language === 'ur' ? ur : en;

  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === 'ur' ? 'rtl' : 'ltr';
    localStorage.setItem('shiplens-language', language);
  }, [language]);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    let active = true;
    setHealth('checking');
    fetch('/api/health', { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (!response.ok) throw new Error('Service unavailable');
        const data: unknown = await response.json();
        if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
          throw new Error('Unexpected health response');
        }
        if (active) setHealth('healthy');
      })
      .catch(() => { if (active) setHealth('unavailable'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [attempt]);

  return (
    <>
      <a className="skip-link" href="#main">{t.skip}</a>
      <header className="site-header page-width">
        <a className="brand" href="/" aria-label={t.brand}>
          <span className="brand-mark" aria-hidden="true">S<span /></span>
          <span><strong>{t.brand}</strong><small>{t.brandDescription}</small></span>
        </a>
        <button className="language-button" aria-label={t.switchLabel} onClick={() => setLanguage(language === 'en' ? 'ur' : 'en')}>
          <span aria-hidden="true">◎</span> {t.language}
        </button>
      </header>
      <main id="main" className="page-width">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <span className="phase-label"><span aria-hidden="true" />{t.phase}</span>
            <p className="eyebrow">{t.eyebrow}</p>
            <h1 id="hero-title">{t.headline}</h1>
            <p className="hero-description">{t.description}</p>
          </div>
          <div className="connection-art" aria-hidden="true">
            <div className="orbit orbit-one" /><div className="orbit orbit-two" />
            <span className="node node-a" /><span className="node node-b" /><span className="node node-c" />
            <div className="central-node"><svg viewBox="0 0 48 48" fill="none"><path d="M9 39V18L24 9l15 9v21H9Z" stroke="currentColor" strokeWidth="2.5"/><path d="M19 39V27h10v12M18 19h1m10 0h1" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/></svg></div>
          </div>
        </section>
        <aside className="development-note"><span className="note-icon" aria-hidden="true">i</span><div><strong>{t.development}</strong><p>{t.developmentDetail}</p></div></aside>
        <Workspace t={t.auth} language={language} />
        <section className="roadmap" aria-labelledby="roadmap-title">
          <div className="section-heading"><h2 id="roadmap-title">{t.roadmapTitle}</h2><p>{t.roadmapDescription}</p></div>
          <div className="step-grid">{t.steps.map((step, index) => <article className={`step ${index === 1 ? 'current' : ''}`} key={index}>
            <div className="step-top"><span className="step-number">{step.number}</span><span className="step-status">{step.status}</span></div>
            <h3>{step.title}</h3><p>{step.description}</p>
          </article>)}</div>
        </section>
        <section className="service-card" aria-labelledby="service-title">
          <div><h2 id="service-title">{t.statusTitle}</h2><p>{t.statusDescription}</p></div>
          <div className="service-result"><p role="status" className={`health ${health}`}><span aria-hidden="true" />{t[health]}</p>{health === 'unavailable' && <p className="health-detail">{t.unavailableDetail}</p>}<button className="retry" disabled={health === 'checking'} onClick={() => setAttempt(attempt + 1)}>{t.retry}</button></div>
        </section>
      </main>
      <footer className="page-width"><p>{t.footer}</p><p>{t.footerNote}</p></footer>
    </>
  );
}
