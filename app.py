import streamlit as st
import google.generativeai as genai
import pandas as pd
import matplotlib.pyplot as plt
import os
import json

# 1. SETUP PAGE AND AI
st.set_page_config(page_title="AI Value Investing Platform", layout="wide")
st.title("📈 AI-Powered Value Investing Platform")

# Fetch key from Streamlit Cloud Secrets or local environment variables
API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    API_KEY = st.sidebar.text_input("Enter your Google Gemini API Key:", type="password")

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # Initialize the watchlist and company names map in memory if they don't exist yet
    if "my_watchlist" not in st.session_state:
        st.session_state.my_watchlist = ["FIG", "INTC", "GOOG", "KO"]
    
    if "company_names" not in st.session_state:
        st.session_state.company_names = {
            "FIG": "Fortress Investment Group",
            "INTC": "Intel Corporation",
            "GOOG": "Alphabet Inc.",
            "KO": "The Coca-Cola Company"
        }
        
    if "ticker_search" not in st.session_state:
        st.session_state.ticker_search = "FIG"

    # --- SIDEBAR: SYSTEM CONTROLS ---
    st.sidebar.subheader("Valuation Strategy")
    valuation_method = st.sidebar.selectbox(
        "Choose Alternative Valuation Formula:",
        ["DCF + RDCF Combined Analysis", "Benjamin Graham Formula (Mature/Stable)", "Asset-Based Valuation (Distressed/Asset-Heavy)"]
    )

    # --- THE CENTRAL POPUP WINDOW FUNCTION ---
    @st.dialog("📋 My Stock List Manager", width="large")
    def open_watchlist_manager():
        st.write("Manage your custom watchlist. Add new stocks, check their full names, or remove tickers below.")
        
        # 1. Add new ticker section
        col_a, col_b = st.columns([3, 1])
        new_ticker = col_a.text_input("➕ Add Ticker Symbol:", "").strip().upper()
        
        if col_b.button("Save Stock", use_container_width=True) and new_ticker:
            if new_ticker not in st.session_state.my_watchlist:
                with st.spinner(f"Resolving name for {new_ticker}..."):
                    try:
                        name_prompt = f"What is the official corporate name for stock ticker symbol {new_ticker}? Return ONLY the short clean company name, nothing else."
                        name_res = model.generate_content(name_prompt).text.strip()
                        st.session_state.company_names[new_ticker] = name_res
                    except:
                        st.session_state.company_names[new_ticker] = "Unknown Company"
                        
                st.session_state.my_watchlist.append(new_ticker)
                st.success(f"Added {new_ticker}!")
                st.rerun()

        st.markdown("---")
        st.subheader("Your Saved Watchlist")

        # 2. Display and Edit/Delete existing entries
        if not st.session_state.my_watchlist:
            st.info("Your watchlist is currently empty.")
        else:
            for ticker in sorted(st.session_state.my_watchlist):
                c1, c2, c3 = st.columns([1, 4, 1])
                # Clickable symbol button to choose it instantly
                if c1.button(f"🔍 {ticker}", key=f"select_{ticker}", use_container_width=True):
                    st.session_state.ticker_search = ticker
                    st.rerun()
                
                # Display the resolved company name
                c2.write(f"**{st.session_state.company_names.get(ticker, 'Loading name...')}**")
                
                # Delete button
                if c3.button("🗑️", key=f"del_{ticker}", use_container_width=True):
                    st.session_state.my_watchlist.remove(ticker)
                    if ticker in st.session_state.company_names:
                        del st.session_state.company_names[ticker]
                    st.rerun()

    # --- SIDEBAR TRIGGER BUTTON ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("📋 Workspace")
    if st.sidebar.button("⚙️ Manage My Stock List", use_container_width=True):
        open_watchlist_manager()
    st.sidebar.markdown("---")

    # Main search field (wired directly to our picker selection)
    tickers_input = st.text_input(
        "Enter Stock Tickers to Analyze (separated by commas if entering multiples manually):", 
        st.session_state.ticker_search
    )
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

    if st.button("Run Comprehensive Analysis"):
        for ticker in tickers:
            # Look up clean company name to show in title banner
            comp_name = st.session_state.company_names.get(ticker, ticker)
            st.markdown(f"## 🏢 {comp_name} ({ticker})")
            
            with st.spinner(f"AI is gathering 5-year financial history for {ticker}..."):
                try:
                    data_prompt = f"""
                    You are an expert financial database. Fetch the current stock price and last 5 years of historical financial data for the ticker symbol {ticker}.
                    Provide the data in a strict, valid JSON format. Do not write any markdown code blocks or introduction text, just the raw JSON.
                    
                    JSON Structure:
                    {{
                        "currentPrice": 0.0,
                        "years": ["2021", "2022", "2023", "2024", "2025"],
                        "eps_history": [0.0, 0.0, 0.0, 0.0, 0.0],
                        "fcf_history_millions": [0.0, 0.0, 0.0, 0.0, 0.0],
                        "roe_history_pct": [0.0, 0.0, 0.0, 0.0, 0.0],
                        "pe_ratio": "N/A",
                        "forward_pe": "N/A",
                        "pb_ratio": "N/A",
                        "debt_to_equity": "N/A",
                        "operating_margin_pct": "N/A",
                        "total_assets": 0.0,
                        "total_liabilities": 0.0,
                        "shares_outstanding": 1.0,
                        "eps_growth_5yr_pct": 5.0,
                        "dcf_fair_value": 0.0,
                        "rdcf_implied_growth_pct": 0.0
                    }}
                    For dcf_fair_value, calculate a standard 10-year DCF using a conservative 9% discount rate and a 2.5% terminal growth rate.
                    For rdcf_implied_growth_pct, calculate the free cash flow growth rate the market is currently implying based on the current market price.
                    Estimate values accurately based on the company's annual financial filings if needed.
                    """
                    
                    response = model.generate_content(data_prompt)
                    clean_text = response.text.strip().replace("```json", "").replace("```", "")
                    financial_data = json.loads(clean_text)
                    
                    current_price = float(financial_data.get("currentPrice", 0.0))
                    year_labels = financial_data.get("years", ["2021", "2022", "2023", "2024", "2025"])
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
                        expected_yield = 5.0
                        fair_value = (base_eps * (8.5 + 2 * (g/100)) * 4.4) / expected_yield
                    else:
                        total_assets = float(financial_data.get("total_assets", 0.0))
                        total_liab = float(financial_data.get("total_liabilities", 0.0))
                        shares_out = float(financial_data.get("shares_outstanding", 1.0))
                        fair_value = (total_assets - total_liab) / shares_out if shares_out else 0.0
                    
                    if fair_value > 0:
                        diff_pct = ((fair_value - current_price) / fair_value) * 100
                        status_label = "Margin of Safety (Discount)" if diff_pct > 0 else "Premium (Overvalued)"
                        status_val = f"{abs(diff_pct):.1f}%"
                    else:
                        status_label = "Margin"
                        status_val = "N/A"
                        diff_pct = 0.0

                    if "DCF + RDCF" in valuation_method:
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("DCF Fair Value", f"${fair_value:.2f}")
                        col2.metric("RDCF Implied Growth", rdcf_growth, help="The growth rate the current stock price assumes")
                        col3.metric("Current Market Price", f"${current_price:.2f}")
                        col4.metric(status_label, status_val, delta=f"{diff_pct:.1f}%" if fair_value > 0 else None)
                    else:
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Calculated Fair Value", f"${fair_value:.2f}", help=f"Based on {valuation_method}")
                        col2.metric("Current Market Price", f"${current_price:.2f}")
                        col3.metric(status_label, status_val, delta=f"{diff_pct:.1f}%" if fair_value > 0 else None)

                    st.markdown("### 📊 5-Year Historical Performance Trends")
                    fig, axs = plt.subplots(1, 3, figsize=(18, 4))
                    
                    axs[0].plot(year_labels, eps_history, marker='o', color='#1f77b4', linewidth=2)
                    axs[0].set_title(f"5-Year EPS Trend (CAGR: {eps_growth_5yr:.1f}%)")
                    axs[0].grid(True, linestyle='--', alpha=0.5)
                    
                    axs[1].plot(year_labels, roe_history, marker='s', color='#2ca02c', linewidth=2)
                    axs[1].set_title("5-Year Return on Equity (ROE %)")
                    axs[1].grid(True, linestyle='--', alpha=0.5)
                    
                    axs[2].plot(year_labels, fcf_history, marker='^', color='#ff7f0e', linewidth=2)
                    axs[2].set_title("5-Year Free Cash Flow ($ Millions)")
                    axs[2].grid(True, linestyle='--', alpha=0.5)
                    
                    st.pyplot(fig)
                    plt.close()

                    metrics_df = pd.DataFrame([{
                        "Ticker": ticker,
                        "P/E Ratio": financial_data.get("pe_ratio", "N/A"),
                        "Forward P/E": financial_data.get("forward_pe", "N/A"),
                        "Price-to-Book (P/B)": financial_data.get("pb_ratio", "N/A"),
                        "Debt-to-Equity": financial_data.get("debt_to_equity", "N/A"),
                        "Current Operating Margin": financial_data.get("operating_margin_pct", "N/A")
                    }])
                    st.dataframe(metrics_df.set_index("Ticker"))

                    st.markdown("### 🤖 Deep Value Thesis & Risk Assessment")
                    analysis_prompt = f"""
                    Analyze the intrinsic valuation for {ticker} based on these values:
                    - Current Price: ${current_price:.2f}
                    - DCF Intrinsic Value: ${fair_value:.2f}
                    - RDCF Implied Market Growth Rate: {rdcf_growth}
                    - Historical EPS: {eps_history}
                    - Historical ROE %: {roe_history}
                    - Historical FCF ($M): {fcf_history}
                    
                    Provide a concise value investing breakdown covering valuation validation, management capital efficiency, and a final buy/hold/sell verdict.
                    """
                    response_analysis = model.generate_content(analysis_prompt)
                    st.markdown(response_analysis.text)
                    st.markdown("---")
                    
                except Exception as e:
                    st.error(f"Error evaluating {ticker}: {str(e)}")
else:
    st.info("Please enter your free Google Gemini API Key to unlock the application.")
