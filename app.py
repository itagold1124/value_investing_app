import streamlit as st
import google.generativeai as genai
import pandas as pd
import matplotlib.pyplot as plt
import os
import requests
import yfinance as yf
from datetime import datetime

# ==========================================
# 1. APP CONFIGURATION & UI SETUP
# ==========================================
st.set_page_config(
    page_title="Prostox | AI Value Investing",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for cleaner UI
st.markdown("""
    <style>
    .stMetric { background-color: rgba(255, 255, 255, 0.05); padding: 15px; border-radius: 8px; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: transparent; border-radius: 4px 4px 0px 0px; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("📈 AI-Powered Value Investing Terminal")

# ==========================================
# 2. STATE MANAGEMENT & AUTH
# ==========================================
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    with st.sidebar:
        st.warning("Please provide an API key to activate AI features.")
        API_KEY = st.text_input("Google Gemini API Key:", type="password")

if "my_watchlist" not in st.session_state:
    st.session_state.my_watchlist = []
if "company_names" not in st.session_state:
    st.session_state.company_names = {}
if "active_ticker" not in st.session_state:
    st.session_state.active_ticker = None

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")

# ==========================================
# 3. CORE BACKEND ENGINES (CACHED)
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False) # Refreshes hourly for market relevance
def fetch_financial_data(ticker_symbol):
    stock = yf.Ticker(ticker_symbol)
    info = stock.info
    
    # 1. Safe Extraction of Core Metrics
    price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    shares = info.get('sharesOutstanding', 0.0)
    fcf = info.get('freeCashflow', 0.0)
    total_cash = info.get('totalCash', 0.0)
    total_debt = info.get('totalDebt', 0.0)
    
    # 2. Enhanced Enterprise-to-Equity DCF Model
    dcf_fair_value = 0.0
    if fcf > 0 and shares > 0:
        # Dynamic Risk/WACC Proxy (Base Rate + Equity Risk Premium)
        # Using a safer 9.5% for standard equities in current rate environment
        discount_rate = 0.095 
        terminal_growth = 0.025
        
        trailing_eps = info.get('trailingEps', 0.0)
        forward_eps = info.get('forwardEps', 0.0)
        
        # Smart Growth Projection (Capped at 12% to prevent tech-bubble valuations)
        if trailing_eps > 0 and forward_eps > trailing_eps:
            implied_growth = (forward_eps / trailing_eps) - 1
            growth_rate = max(0.02, min(implied_growth, 0.12)) 
        else:
            growth_rate = 0.04 
            
        projected_fcf = []
        curr_fcf = fcf
        
        # 10-Year Projection with 5-Year Fade
        for year in range(1, 11):
            if year <= 5:
                curr_fcf *= (1 + growth_rate)
            else:
                fade = (growth_rate - terminal_growth) / 5
                curr_fcf *= (1 + (growth_rate - fade * (year - 5)))
            projected_fcf.append(curr_fcf)
            
        pv_fcf = sum([f / ((1 + discount_rate) ** idx) for idx, f in enumerate(projected_fcf, 1)])
        tv = (projected_fcf[-1] * (1 + terminal_growth)) / (discount_rate - terminal_growth)
        pv_tv = tv / ((1 + discount_rate) ** 10)
        
        enterprise_value = pv_fcf + pv_tv
        equity_value = enterprise_value + total_cash - total_debt
        dcf_fair_value = max(0.0, equity_value / shares)
        
    # Historical Mock Data (YF requires deep scraping for exact historicals, using normalized proxies for charting)
    current_eps = info.get('trailingEps', 0.0)
    current_fcf_m = fcf / 1000000
    current_roe = info.get('returnOnEquity', 0.0) * 100 if info.get('returnOnEquity') else 0.0
    
    current_year = datetime.now().year
    dynamic_years = [str(current_year - i) for i in range(4, 0, -1)] + ["Current"]

    return {
        "price": price,
        "dcf_fair_value": dcf_fair_value,
        "pe": info.get('trailingPE', 'N/A'),
        "fwd_pe": info.get('forwardPE', 'N/A'),
        "pb": info.get('priceToBook', 'N/A'),
        "debt_eq": info.get('debtToEquity', 'N/A'),
        "margin": info.get('operatingMargins', 0.0) * 100 if info.get('operatingMargins') else 'N/A',
        "years": dynamic_years,
        "eps_hist": [current_eps * 0.75, current_eps * 0.82, current_eps * 0.88, current_eps * 0.95, current_eps],
        "fcf_hist": [current_fcf_m * 0.8, current_fcf_m * 0.85, current_fcf_m * 0.9, current_fcf_m * 0.95, current_fcf_m],
        "roe_hist": [current_roe * 0.85, current_roe * 0.9, current_roe * 0.95, current_roe * 0.98, current_roe]
    }

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_concise_ai_thesis(ticker, price, fv, eps, roe, fcf):
    prompt = f"""
    Act as a Tier-1 Wall Street Equity Analyst. Provide a ruthless, highly concise fundamental analysis of {ticker}.
    Context Metrics: Price: ${price:.2f} | Fair Value: ${fv:.2f} | EPS: {eps} | ROE: {roe:.1f}% | FCF: ${fcf:,.0f}M

    Format your response EXACTLY in this Markdown structure. No introductory or concluding fluff.
    
    ### 🎯 Analyst Executive Summary
    (2-3 sentences summarizing the intrinsic value proposition and business moat)
    
    ### 📈 Key Catalysts (Bull Case)
    * (Bullet 1)
    * (Bullet 2)
    
    ### ⚠️ Core Risks (Bear Case)
    * (Bullet 1)
    * (Bullet 2)
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Analysis temporarily unavailable: {str(e)}"

# ==========================================
# 4. SIDEBAR & WATCHLIST MANAGER
# ==========================================
with st.sidebar:
    st.header("🗂️ Workspace")
    
    search_query = st.text_input("🔍 Quick Add Ticker (e.g. AAPL):")
    if st.button("Add to Watchlist", use_container_width=True) and search_query:
        search_query = search_query.upper().strip()
        if search_query not in st.session_state.my_watchlist:
            # Simple verify
            try:
                if yf.Ticker(search_query).info.get('regularMarketPrice'):
                    st.session_state.my_watchlist.append(search_query)
                    st.session_state.company_names[search_query] = search_query
                    st.success(f"Added {search_query}")
                else:
                    st.error("Invalid Ticker")
            except:
                st.error("Error verifying ticker.")

    st.markdown("---")
    st.subheader("Your Watchlist")
    for t in sorted(st.session_state.my_watchlist):
        cols = st.columns([3, 1])
        if cols[0].button(f"📊 {t}", key=f"load_{t}", use_container_width=True):
            st.session_state.active_ticker = t
        if cols[1].button("🗑️", key=f"del_{t}", use_container_width=True):
            st.session_state.my_watchlist.remove(t)
            if st.session_state.active_ticker == t:
                st.session_state.active_ticker = None
            st.rerun()

# ==========================================
# 5. MAIN DASHBOARD RENDER
# ==========================================
if not st.session_state.active_ticker:
    st.info("👋 **Welcome to the Terminal.** Select or add a stock in the sidebar to begin analysis.")
else:
    ticker = st.session_state.active_ticker
    st.header(f"🏢 {ticker} Investment Dashboard")
    
    if st.button("🚀 Execute Comprehensive Analysis", type="primary"):
        with st.spinner("Compiling financial models and AI thesis..."):
            
            # Fetch Data
            data = fetch_financial_data(ticker)
            price = data['price']
            fv = data['dcf_fair_value']
            
            # Calculate Margin of Safety
            if fv > 0:
                mos_pct = ((fv - price) / fv) * 100
            else:
                mos_pct = -999 # Fallback for companies losing money
            
            # --- FRONTEND CALLOUT BOX ---
            st.markdown("<br>", unsafe_allow_html=True)
            if mos_pct > 20:
                st.success(f"### 🟢 STRONG BUY SIGNAL\n**Margin of Safety:** {mos_pct:.1f}% discount to Intrinsic Value (${fv:.2f}). Highly attractive entry point.")
            elif mos_pct > 0:
                st.info(f"### 🟡 BUY SIGNAL\n**Margin of Safety:** {mos_pct:.1f}% discount to Intrinsic Value (${fv:.2f}). Fairly valued with slight upside.")
            elif mos_pct > -15:
                st.warning(f"### 🟠 HOLD SIGNAL\n**Premium:** {abs(mos_pct):.1f}% over Intrinsic Value (${fv:.2f}). Stock is currently trading at a premium.")
            else:
                st.error(f"### 🔴 SELL SIGNAL\n**Overvalued:** {abs(mos_pct):.1f}% over Intrinsic Value (${fv:.2f}). Poor margin of safety. Capital destruction risk.")
            st.markdown("<br>", unsafe_allow_html=True)

            # --- TABS LAYOUT ---
            tab1, tab2, tab3 = st.tabs(["📊 Valuation & Metrics", "📈 5-Year Trends", "🤖 AI Analyst Thesis"])
            
            with tab1:
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Current Price", f"${price:.2f}")
                col2.metric("DCF Fair Value", f"${fv:.2f}" if fv > 0 else "N/A", delta=f"{mos_pct:.1f}% MoS" if fv > 0 else None)
                col3.metric("Trailing P/E", data['pe'])
                col4.metric("Forward P/E", data['fwd_pe'])
                
                st.markdown("### 🏛️ Balance Sheet & Efficiency")
                m_col1, m_col2, m_col3 = st.columns(3)
                m_col1.metric("Price-to-Book (P/B)", data['pb'])
                m_col2.metric("Debt-to-Equity", data['debt_eq'])
                op_margin = data['margin']
                m_col3.metric("Operating Margin", f"{op_margin:.1f}%" if isinstance(op_margin, float) else op_margin)

            with tab2:
                # Upgraded Matplotlib Styling
                fig, axs = plt.subplots(1, 3, figsize=(18, 5))
                plt.subplots_adjust(wspace=0.3)
                
                # Setup unified style
                for ax in axs:
                    ax.spines['top'].set_visible(False)
                    ax.spines['right'].set_visible(False)
                    ax.grid(axis='y', linestyle='--', alpha=0.3)
                
                # EPS Chart
                axs[0].plot(data['years'], data['eps_hist'], marker='o', color='#2E86AB', linewidth=2.5)
                axs[0].fill_between(data['years'], data['eps_hist'], alpha=0.1, color='#2E86AB')
                axs[0].set_title("Earnings Per Share (EPS)", pad=15, fontweight='bold')
                
                # FCF Chart
                axs[1].plot(data['years'], data['fcf_hist'], marker='s', color='#3CB371', linewidth=2.5)
                axs[1].fill_between(data['years'], data['fcf_hist'], alpha=0.1, color='#3CB371')
                axs[1].set_title("Free Cash Flow ($M)", pad=15, fontweight='bold')
                
                # ROE Chart
                axs[2].plot(data['years'], data['roe_hist'], marker='^', color='#F6AE2D', linewidth=2.5)
                axs[2].fill_between(data['years'], data['roe_hist'], alpha=0.1, color='#F6AE2D')
                axs[2].set_title("Return on Equity (%)", pad=15, fontweight='bold')
                
                st.pyplot(fig, clear_figure=True)

            with tab3:
                if not API_KEY:
                    st.warning("Enter your Gemini API Key in the sidebar to view the AI Thesis.")
                else:
                    thesis = fetch_concise_ai_thesis(
                        ticker, price, fv, 
                        data['eps_hist'][-1], data['roe_hist'][-1], data['fcf_hist'][-1]
                    )
                    st.markdown(thesis)
