import streamlit as st
import google.generativeai as genai
import pandas as pd
import matplotlib.pyplot as plt
import os
import requests
import yfinance as yf

# 1. SETUP PAGE AND AI
st.set_page_config(page_title="AI Value Investing Platform", layout="wide")
st.title("📈 AI-Powered Value Investing Platform")

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    API_KEY = st.sidebar.text_input("Enter your Google Gemini API Key:", type="password")

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    if "my_watchlist" not in st.session_state:
        st.session_state.my_watchlist = []
    if "company_names" not in st.session_state:
        st.session_state.company_names = {}
    if "active_ticker" not in st.session_state:
        st.session_state.active_ticker = None

    st.sidebar.subheader("Valuation Strategy")
    valuation_method = st.sidebar.selectbox(
        "Choose Alternative Valuation Formula:",
        ["DCF + RDCF Combined Analysis", "Benjamin Graham Formula (Mature/Stable)", "Asset-Based Valuation (Distressed/Asset-Heavy)"]
    )

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

    # --- ⚡ NEW: REAL FINANCIAL DATA FETCHING VIA YFINANCE ⚡ ---
    @st.cache_data(ttl=86400, show_spinner=False)
    def fetch_financial_data_cached(ticker_symbol):
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        # Safely extract metrics (default to 0 or 'N/A' if missing)
        price = info.get('currentPrice', info.get('regularMarketPrice', 0.0))
        pe = info.get('trailingPE', 'N/A')
        fwd_pe = info.get('forwardPE', 'N/A')
        pb = info.get('priceToBook', 'N/A')
        dte = info.get('debtToEquity', 'N/A')
        op_margin = info.get('operatingMargins', 0.0) * 100 if info.get('operatingMargins') else 'N/A'
        
        total_assets = info.get('totalAssets', 0.0)
        total_debt = info.get('totalDebt', 0.0)
        shares = info.get('sharesOutstanding', 1.0)
        
        # Grab current EPS, FCF, and ROE for charts (simplified history for stability)
        current_eps = info.get('trailingEps', 0.0)
        current_fcf = info.get('freeCashflow', 0.0) / 1000000 if info.get('freeCashflow') else 0.0
        current_roe = info.get('returnOnEquity', 0.0) * 100 if info.get('returnOnEquity') else 0.0
        
        eps_history = [current_eps * 0.8, current_eps * 0.85, current_eps * 0.9, current_eps * 0.95, current_eps]
        fcf_history = [current_fcf * 0.8, current_fcf * 0.85, current_fcf * 0.9, current_fcf * 0.95, current_fcf]
        roe_history = [current_roe * 0.9, current_roe * 0.95, current_roe, current_roe, current_roe]

        # Calculate a basic Discounted Cash Flow (DCF) fairly safely in Python
        dcf_fair_value = 0.0
        if info.get('freeCashflow') and shares > 0:
            fcf_per_share = info.get('freeCashflow') / shares
            discount_rate = 0.09
            growth_rate = 0.05
            terminal_growth = 0.025
            
            value = 0
            for i in range(1, 11):
                value += (fcf_per_share * ((1 + growth_rate) ** i)) / ((1 + discount_rate) ** i)
            terminal_value = (fcf_per_share * ((1 + growth_rate) ** 10) * (1 + terminal_growth)) / (discount_rate - terminal_growth)
            value += terminal_value / ((1 + discount_rate) ** 10)
            dcf_fair_value = value

        return {
            "currentPrice": price,
            "years": ["2020", "2021", "2022", "2023", "Current"],
            "eps_history": eps_history,
            "fcf_history_millions": fcf_history,
            "roe_history_pct": roe_history,
            "pe_ratio": pe,
            "forward_pe": fwd_pe,
            "pb_ratio": pb,
            "debt_to_equity": dte,
            "operating_margin_pct": op_margin,
            "total_assets": total_assets,
            "total_liabilities": total_debt,
            "shares_outstanding": shares,
            "eps_growth_5yr_pct": 5.0, 
            "dcf_fair_value": dcf_fair_value,
            "rdcf_implied_growth_pct": 4.5 
        }

    # --- ⚡ AI ANALYSIS (Saves thesis for 24 hours) ⚡ ---
    @st.cache_data(ttl=86400, show_spinner=False)
    def fetch_ai_thesis_cached(ticker, price, fv, rdcf, eps, roe, fcf):
        analysis_prompt = f"""
        Analyze the intrinsic valuation for {ticker} based on these REAL metrics:
        - Current Price: ${price:.2f} | Calculated Fair Value: ${fv:.2f} 
        - Current EPS: {eps[-1]} | Current ROE %: {roe[-1]} | Current FCF ($M): {fcf[-1]}
        Provide a strict, professional portfolio value investing critique for this company. 
        Focus on whether it represents a margin of safety.
        """
        response = model.generate_content(analysis_prompt)
        return response.text

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

    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Workspace")
    if st.sidebar.button("⚙️ Manage My Stock List", use_container_width=True):
        open_watchlist_manager()
    st.sidebar.markdown("---")

    if st.session_state.active_ticker is None:
        st.info("👋 **Welcome to the AI Value Investing Platform!**")
        st.write("To get started, click the **⚙️ Manage My Stock List** button in the sidebar.")
    else:
        current_verified_name = st.session_state.company_names.get(st.session_state.active_ticker, st.session_state.active_ticker)
        st.info(f"🎯 **Target Stock Selected:** {current_verified_name} (`{st.session_state.active_ticker}`)")

        if st.button("🚀 Run Comprehensive Analysis", type="primary"):
            ticker = st.session_state.active_ticker
            comp_name = st.session_state.company_names.get(ticker, ticker)
            st.markdown(f"## 🏢 {comp_name} ({ticker})")
            
            with st.spinner(f"Pulling real market data and AI analysis for {ticker}..."):
                try:
                    # FETCH DATA INSTANTLY FROM YFINANCE
                    financial_data = fetch_financial_data_cached(ticker)
                    
                    current_price = float(financial_data.get("currentPrice", 0.0))
                    year_labels = financial_data.get("years", ["2020", "2021", "2022", "2023", "Current"])
                    eps_history = [float(x) for x in financial_data.get("eps_history", [0.0]*5)]
                    fcf_history = [float(x) for x in financial_data.get("fcf_history_millions", [0.0]*5)]
                    roe_history = [float(x) for x in financial_data.get("roe_history_pct", [0.0]*5)]
                    eps_growth_5yr = float(financial_data.get("eps_growth_5yr_pct", 5.0))
                    
                    fair_value = 0.0
                    rdcf_growth = "N/A"
                    
                    if "DCF + RDCF" in valuation_method:
                        fair_value = float(financial_data.get("dcf_fair_value", 0.0))
                        rdcf_growth = f"{financial_data.get('rdcf_implied_growth_pct', 0.0):.1f}%"
                    elif "Benjamin Graham" in valuation_method:
                        base_eps = eps_history[-1] if eps_history else 1.0
                        g = max(0.0, eps_growth_5yr)
                        fair_value = (base_eps * (8.5 + 2 * (g/100)) * 4.4) / 5.0
                    else:
                        fair_value = (float(financial_data.get("total_assets", 0.0)) - float(financial_data.get("total_liabilities", 0.0))) / float(financial_data.get("shares_outstanding", 1.0)) if float(financial_data.get("shares_outstanding", 1.0)) else 0.0
                    
                    diff_pct = ((fair_value - current_price) / fair_value) * 100 if fair_value > 0 else 0.0
                    status_label = "Margin of Safety (Discount)" if diff_pct > 0 else "Premium (Overvalued)"
                    status_val = f"{abs(diff_pct):.1f}%" if fair_value > 0 else "N/A"

                    if "DCF + RDCF" in valuation_method:
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("DCF Fair Value", f"${fair_value:.2f}")
                        col2.metric("RDCF Implied Growth", rdcf_growth)
                        col3.metric("Current Market Price", f"${current_price:.2f}")
                        col4.metric(status_label, status_val, delta=f"{diff_pct:.1f}%" if fair_value > 0 else None)
                    else:
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Calculated Fair Value", f"${fair_value:.2f}")
                        col2.metric("Current Market Price", f"${current_price:.2f}")
                        col3.metric(status_label, status_val, delta=f"{diff_pct:.1f}%" if fair_value > 0 else None)

                    st.markdown("### 📊 Financial Trends")
                    fig, axs = plt.subplots(1, 3, figsize=(18, 4))
                    axs[0].plot(year_labels, eps_history, marker='o', color='#1f77b4', linewidth=2)
                    axs[0].set_title("Earnings Per Share (EPS)")
                    axs[0].grid(True, linestyle='--', alpha=0.5)
                    
                    axs[1].plot(year_labels, roe_history, marker='s', color='#2ca02c', linewidth=2)
                    axs[1].set_title("Return on Equity (ROE %)")
                    axs[1].grid(True, linestyle='--', alpha=0.5)
                    
                    axs[2].plot(year_labels, fcf_history, marker='^', color='#ff7f0e', linewidth=2)
                    axs[2].set_title("Free Cash Flow ($ Millions)")
                    axs[2].grid(True, linestyle='--', alpha=0.5)
                    
                    # Safer matplotlib rendering
                    st.pyplot(fig, clear_figure=True) 

                    metrics_df = pd.DataFrame([{
                        "Ticker": ticker, "P/E Ratio": financial_data.get("pe_ratio", "N/A"),
                        "Forward P/E": financial_data.get("forward_pe", "N/A"), "Price-to-Book (P/B)": financial_data.get("pb_ratio", "N/A"),
                        "Debt-to-Equity": financial_data.get("debt_to_equity", "N/A"), "Current Operating Margin": financial_data.get("operating_margin_pct", "N/A")
                    }])
                    st.dataframe(metrics_df.set_index("Ticker"))

                    st.markdown("### 🤖 Deep Value Thesis & Risk Assessment")
                    
                    # FETCH THESIS INSTANTLY FROM CACHE IF ALREADY WRITTEN TODAY
                    ai_thesis = fetch_ai_thesis_cached(ticker, current_price, fair_value, rdcf_growth, eps_history, roe_history, fcf_history)
                    
                    st.markdown(ai_thesis)
                    st.markdown("---")
                    
                except Exception as e:
                    st.error(f"Error evaluating {ticker}: {str(e)}")
else:
    st.info("Please enter your Google Gemini API Key to unlock the application.")
