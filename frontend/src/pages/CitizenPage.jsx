import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { getAqiColor, getAqiLabel, getAqiBadgeClass } from '../utils/aqi';
import { postAdvisory, postChatQuery, getWardTrends, getWards, getHotspots } from '../api/client';
import { useTheme } from '../hooks/useTheme';

export default function CitizenPage() {
  const { theme, toggleTheme } = useTheme();
  const [lang, setLang] = useState('en');
  const [fadeKey, setFadeKey] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [wardTrend, setWardTrend] = useState(null);
  const contentRef = useRef(null);

  const [wards, setWards] = useState([]);
  const [selectedWard, setSelectedWard] = useState(null);
  const [hotspot, setHotspot] = useState(null);
  // Ward readings may be returned as floating-point values. AQI is presented
  // and classified as a whole-number CPCB index.
  const rawAqi = Number(selectedWard?.aqi);
  const aqi = Number.isFinite(rawAqi) ? Math.round(rawAqi) : 0;
  const aqiColor = getAqiColor(aqi);

  const [advisoryMsg, setAdvisoryMsg] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getWards().then((wardItems) => {
      if (!mounted) return;
      setWards(wardItems);
      setSelectedWard(null);
      setHotspot(null);
    }).catch(() => { if (mounted) setIsLoading(false); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!selectedWard) {
      setWardTrend(null);
      setAdvisoryMsg(lang === 'en' ? 'Select your ward to receive a live advisory.' : 'लाइव सलाह पाने के लिए अपना वार्ड चुनें।');
      setIsLoading(false);
      return undefined;
    }

    let mounted = true;
    setIsLoading(true);
    
    async function fetchTrend() {
      try {
        if (!selectedWard) return;
        const t = await getWardTrends(selectedWard.name);
        if (mounted) setWardTrend(t);
      } catch {
        // ignore error
      }
    }

    async function fetchAdvisory() {
      try {
        const result = await postAdvisory({
          user_id: 'demo',
          ward: selectedWard.name,
          language: lang,
          forecast_aqi: aqi,
        });
        if (mounted) {
          setAdvisoryMsg(result.message);
          setIsLoading(false);
        }
      } catch (err) {
        if (mounted) {
          console.error('Failed to fetch advisory:', err);
          setIsLoading(false);
          setAdvisoryMsg(lang === 'en' ? 'Live advisory is currently unavailable.' : 'लाइव सलाह अभी उपलब्ध नहीं है।');
        }
      }
    }
    
    // add an artificial delay to make the skeleton visible for the demo if it's too fast
    const t = setTimeout(() => {
      fetchAdvisory();
      fetchTrend();
    }, 0);
    
    return () => { 
      mounted = false; 
      clearTimeout(t);
    };
  }, [lang, selectedWard, aqi]);

  useEffect(() => {
    setMessages([]);
  }, [lang, selectedWard?.name]);

  const handleChatSubmit = async (e) => {
    e?.preventDefault();
    if (!chatInput.trim()) return;
    
    const query = chatInput.trim();
    setChatInput('');
    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setIsTyping(true);
    
    try {
      const response = await postChatQuery({
        query,
        ward: selectedWard?.name,
        language: lang,
        aqi,
        source: hotspot?.source || 'Unknown',
        confidence: (hotspot?.confidence || 0) / 100,
        risk_level: 'Unknown',
        peak_month: wardTrend?.peak_month || 'Unknown',
        weekday_delta: wardTrend?.weekday_vs_weekend_delta || 0.0
      });
      
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: response.answer, 
        citation: response.citations?.map((item) => item.title).join(' · ') || response.citation || 'ClearSkies AQI Monitor'
      }]);
    } catch {
      const fallback = lang === 'en' 
        ? "Unable to connect. Please check the AQI display for current conditions." 
        : "कनेक्ट करने में समस्या हो रही है। कृपया AQI डिस्प्ले देखें।";
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: fallback, 
        citation: '*Source: ClearSkies AQI Monitor*' 
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  // Language switch with fade
  const switchLang = (newLang) => {
    if (newLang === lang) return;
    setFadeKey((k) => k + 1);
    setTimeout(() => {
      setLang(newLang);
      setFadeKey((k) => k + 1);
    }, 150);
  };

  return (
    <div className="citizen-layout">
      {/* Simplified header */}
      <div className="citizen-header">
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none' }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.7 7.7a2.5 2.5 0 1 1 1.8 4.3H2" />
            <path d="M9.6 4.6A2 2 0 1 1 11 8H2" />
            <path d="M12.6 19.4A2 2 0 1 0 14 16H2" />
          </svg>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
            ClearSkies
          </span>
        </Link>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            {theme === 'light' ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2" /><path d="M12 20v2" /><path d="m4.93 4.93 1.41 1.41" /><path d="m17.66 17.66 1.41 1.41" /><path d="M2 12h2" /><path d="M20 12h2" /><path d="m6.34 17.66-1.41 1.41" /><path d="m19.07 4.93-1.41 1.41" /></svg>
            )}
          </button>
          <div className="lang-toggle">
            <button
              className={`lang-option${lang === 'en' ? ' active' : ''}`}
              onClick={() => switchLang('en')}
            >
              English
            </button>
            <button
              className={`lang-option${lang === 'hi' ? ' active' : ''}`}
              onClick={() => switchLang('hi')}
            >
              हिन्दी
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="citizen-content" ref={contentRef}>
        <div
          key={fadeKey}
          className="lang-fade-active"
          style={{ animationDelay: '0ms' }}
        >
          <div className="form-group" style={{ maxWidth: '320px', margin: '0 auto 16px' }}>
            <label className="form-label">{lang === 'en' ? 'Your ward' : 'आपका वार्ड'}</label>
            <select className="form-select" value={selectedWard?.name || ''}
              onChange={(event) => {
                const ward = wards.find((item) => item.name === event.target.value);
                setSelectedWard(ward || null);
                getHotspots().then((items) => setHotspot(items.find((item) => item.zone === ward?.name) || null)).catch(() => setHotspot(null));
              }}>
              <option value="" disabled>{lang === 'en' ? 'Select your ward' : 'अपना वार्ड चुनें'}</option>
              {wards.map((ward) => <option key={ward.name} value={ward.name}>{ward.name}</option>)}
            </select>
          </div>
          {/* Large AQI display */}
          <div className="citizen-aqi-display">
            <div className="citizen-aqi-value" style={{ color: aqiColor === '#FFFF00' ? '#E6E600' : aqiColor }}>
              {aqi || '—'}
            </div>
            <div className="citizen-aqi-label">
              {aqi ? getAqiLabel(aqi) : 'No live reading'}
            </div>
            <div style={{ marginTop: '8px' }}>
              <span className={`aqi-badge ${getAqiBadgeClass(aqi)}`}>
                {selectedWard?.name || 'Loading ward…'}
              </span>
            </div>
          </div>

          {/* Plain language message */}
          <div className="citizen-message">
            {isLoading ? (
              <div style={{ animation: 'pulse 1.5s infinite', background: 'var(--color-bg-tertiary, rgba(128,128,128,0.2))', height: '80px', borderRadius: '8px', opacity: 0.5 }} />
            ) : (
              advisoryMsg
            )}
          </div>

          {/* Vulnerable group tags */}
          <div style={{ marginBottom: '24px' }}>
            <div className="section-title">
              {lang === 'en' ? 'Guidance for Vulnerable Groups' : 'संवेदनशील समूहों के लिए मार्गदर्शन'}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {[
              { icon: '👶', title: lang === 'en' ? 'Children' : 'बच्चे', advice: lang === 'en' ? 'Reduce prolonged outdoor activity when AQI is poor or worse.' : 'AQI खराब या अधिक होने पर लंबे समय तक बाहर न रहें।' },
              { icon: '👴', title: lang === 'en' ? 'Elderly' : 'बुज़ुर्ग', advice: lang === 'en' ? 'Limit exertion outdoors and follow the live advisory.' : 'बाहर मेहनत वाले काम सीमित करें और लाइव सलाह मानें।' },
              { icon: '👷', title: lang === 'en' ? 'Outdoor workers' : 'बाहरी कर्मचारी', advice: lang === 'en' ? 'Use appropriate respiratory protection and take indoor breaks.' : 'उचित मास्क पहनें और अंदर ब्रेक लें।' },
            ].map((group, i) => (
                <div key={i} className="group-tag">
                  <div className="group-tag-icon">{group.icon}</div>
                  <div>
                    <div className="group-tag-title">{group.title}</div>
                    <div className="group-tag-advice">{group.advice}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Ask why button */}
          <button
            className={`citizen-chat-trigger${chatOpen ? ' hidden' : ''}`}
            onClick={() => setChatOpen(true)}
            aria-label={lang === 'en' ? 'Open air-quality assistant' : 'वायु गुणवत्ता सहायक खोलें'}
          >
            {lang === 'en' ? '💬 Ask why the air quality is this way' : '💬 हवा की गुणवत्ता ऐसी क्यों है?'}
          </button>
        </div>
      </div>

      {/* Chatbot slide-up panel */}
      <div className={`chat-panel${chatOpen ? ' open' : ''}`}>
        <div className="chat-panel-header">
          <span className="chat-panel-title">
            {lang === 'en' ? 'Why is the air like this?' : 'हवा ऐसी क्यों है?'}
          </span>
          <button
            onClick={() => setChatOpen(false)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: '1.2rem',
              padding: '4px',
            }}
          >
            ✕
          </button>
        </div>

        <div className="chat-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto', padding: '16px', maxHeight: '400px' }}>
          {messages.map((msg, idx) => (
            <div key={idx} style={{ alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '80%' }}>
              <div className={`chat-message ${msg.role === 'user' ? 'user' : 'assistant'}`}>
                {msg.content}
              </div>
              {msg.role === 'assistant' && msg.citation && (
                <div className="chat-citation" style={{ fontSize: '0.75rem', fontStyle: 'italic', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                  {msg.citation}
                </div>
              )}
            </div>
          ))}
          {isTyping && (
            <div className="typing-indicator">
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
              <div className="typing-dot"></div>
            </div>
          )}
        </div>

        <form className="chat-input-area" onSubmit={handleChatSubmit}>
          <input
            className="chat-input"
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            placeholder={lang === 'en' ? 'Ask a follow-up question...' : 'अनुवर्ती प्रश्न पूछें...'}
          />
          <button type="submit" className="btn-chat-submit">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </form>
      </div>

      {/* Overlay when chat is open */}
      {chatOpen && (
        <div
          onClick={() => setChatOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.3)',
            zIndex: 150,
          }}
        />
      )}
    </div>
  );
}
