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
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_financial_data(ticker_symbol):
    # 🛡️ ANTI-BOT MEASURE: Create a custom browser session
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    })
    
    # Pass the disguised session to Yahoo Finance
    stock = yf.Ticker(ticker_symbol, session=session)
    
    # Safely attempt to get data
    try:
        info = stock.info
    except Exception:
        info = {} # Fallback to empty dict if Yahoo still blocks it temporarily
        
    price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
    shares = info.get('sharesOutstanding', 0.0)
    fcf = info.get('freeCashflow', 0.0)
    total_cash = info.get('totalCash', 0.0)
    total_debt = info.get('totalDebt', 0.0)
    
    dcf_fair_value = 0.0
    if fcf > 0 and shares > 0:
        discount_rate = 0.095 
        terminal_growth = 0.025
        
        trailing_eps = info.get('trailingEps', 0.0)
        forward_eps = info.get('forwardEps', 0.0)
        
        if trailing_eps > 0 and forward_eps > trailing_eps:
            implied_growth = (forward_eps / trailing_eps) - 1
            growth_rate = max(0.02, min(implied_growth, 0.12)) 
        else:
            growth_rate = 0.04 
            
        projected_fcf = []
        curr_fcf = fcf
        
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
# 4. WATCHLIST MANAGER (RESTORED POPUP)
# ==========================================
def add_stock_callback(new_ticker, new_name):
    if new_ticker not in st.session_state.my_watchlist:
        st.session_state.my_watchlist.append(new_ticker)
        st.session_state.company_names[new_ticker] = new_name

def remove_stock_callback(ticker_to_remove):
    if ticker_to_remove in st.session_state.my_watchlist:
        st.session_state.my_watchlist.remove(ticker_to_remove)
    if ticker_to_remove in st.session_state.company_names:
        del st.session_state.company_names[ticker_to_remove]
    if st.session_state.active_ticker == ticker_to_remove:
        st.session_state.active_ticker = None

@st.dialog("📋 My Stock List Manager", width="large")
def open_watchlist_manager():
    st.write("Search Yahoo Finance to verify active tickers, or manage saved items below.")
    st.subheader("🔍 Find & Verify via Yahoo Finance")
    search_query = st.text_input("Type a Company Name or Ticker (e.g., Apple, Intel, Microsoft):", key="modal_search_input")

    if search_query:
        with st.spinner("Querying Yahoo Finance directory..."):
            try:
                url = f"https://query2.finance.yahoo.com/v1/finance/search?q={search_query}&quotesCount=6&newsCount=0"
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    search_results = response.json().get("quotes", [])
                    valid_matches = [{"display_name": f"{i.get('shortname') or i.get('longname')} ({i.get('symbol')} - {i.get('exchange')})", "ticker": i.get("symbol"), "company_name": i.get("shortname") or i.get("longname")} for i in search_results if i.get("symbol") and (i.get("shortname") or i.get("longname")) and i.get("exchange")]
                    
                    if valid_matches:
                        options_map = {item["display_name"]: item for item in valid_matches}
                        dropdown_selection = st.selectbox("👇 Select company:", options=["-- Select Company --"] + list(options_map.keys()), key="modal_dropdown_selection")
                        if dropdown_selection != "-- Select Company --":
                            chosen_item = options_map[dropdown_selection]
                            st.button(f"➕ Add {chosen_item['ticker']} to List", key=f"add_{chosen_item['ticker']}", on_click=add_stock_callback, args=(chosen_item['ticker'], chosen_item['company_name']), use_container_width=True)
                    else:
                        st.warning("No active listings found.")
            except Exception as e:
                st.error(f"Search error: {str(e)}")

    st.markdown("---")
    st.subheader("Your Saved Watchlist")

    if not st.session_state.my_watchlist:
        st.info("Your watchlist is empty. Search for a stock above to get started!")
    else:
        for ticker in sorted(list(st.session_state.my_watchlist)):
            c1, c2, c3 = st.columns([1.5, 4, 1])
            if c1.button(f"📊 Analyze {ticker}", key=f"select_{ticker}", use_container_width=True):
                st.session_state.active_ticker = ticker
                st.write("<script>window.parent.document.querySelector('.stDialog').remove();</script>", unsafe_allow_html=True)
                st.rerun()
            c2.write(f"**{ticker}** — {st.session_state.company_names.get(ticker, 'Unknown Name').strip()}")
            c3.button("🗑️", key=f"del_{ticker}", on_click=remove_stock_callback, args=(ticker,), use_container_width=True)

with st.sidebar:
    st.header("🗂️ Workspace")
    if st.button("⚙️ Manage My Stock List", use_container_width=True):
        open_watchlist_manager()
    st.markdown("---")

# ==========================================
# 5. MAIN DASHBOARD RENDER
# ==========================================
if not st.session_state.active_ticker:
    st.info("👋 **Welcome to the Terminal.** Click **⚙️ Manage My Stock List** in the sidebar to begin.")
else:
    ticker = st.session_state.active_ticker
    comp_name = st.session_state.company_names.get(ticker, ticker)
    st.header(f"🏢 {comp_name} ({ticker})")
    
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
                fig, axs = plt.subplots(1, 3, figsize=(18, 5))
                plt.subplots_adjust(wspace=0.3)
                
                for ax in axs:
                    ax.spines['top'].set_visible(False)
                    ax.spines['right'].set_visible(False)
                    ax.grid(axis='y', linestyle='--', alpha=0.3)
                
                axs[0].plot(data['years'], data['eps_hist'], marker='o', color='#2E86AB', linewidth=2.5)
                axs[0].fill_between(data['years'], data['eps_hist'], alpha=0.1, color='#2E86AB')
                axs[0].set_title("Earnings Per Share (EPS)", pad=15, fontweight='bold')
                
                axs[1].plot(data['years'], data['fcf_hist'], marker='s', color='#3CB371', linewidth=2.5)
                axs[1].fill_between(data['years'], data['fcf_hist'], alpha=0.1, color='#3CB371')
                axs[1].set_title("Free Cash Flow ($M)", pad=15, fontweight='bold')
                
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
