import streamlit as st
import yfinance as yf
import google.generativeai as genai
import pandas as pd
import matplotlib.pyplot as plt
import os

# 1. SETUP PAGE AND AI
st.set_page_config(page_title="Pro Value Investing Assistant", layout="wide")
st.title("📈 Pro Value Investing Platform")

# Look for the hidden key automatically from Streamlit Secrets or Environment Variables
API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    # Fallback to sidebar if secrets aren't set up yet
    API_KEY = st.sidebar.text_input("Enter your Google Gemini API Key:", type="password")

# Safety helper function to clean complex numbers or text from yfinance
def clean_numeric_value(val):
    if val is None:
        return 0.0
    if isinstance(val, pd.Series):
        val = val.iloc[0] if not val.empty else 0.0
    try:
        # If it has a 'real' attribute, it's a complex number; extract just the real part
        if hasattr(val, 'real'):
            val = val.real
        # Check for NaN/Null
        if pd.isnull(val):
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0

if API_KEY:
    genai.configure(api_key=API_KEY)
    
    # User inputs
    tickers_input = st.text_input("Enter Stock Tickers (separated by commas, e.g., FIG, INTC, O):", "FIG")
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]

    # Valuation Strategy Selector
    st.sidebar.subheader("Valuation Strategy")
    valuation_method = st.sidebar.selectbox(
        "Choose Alternative Valuation Formula:",
        ["Benjamin Graham Formula (Mature/Stable)", "Asset-Based Valuation (Distressed/Asset-Heavy)"]
    )

    if st.button("Run Comprehensive Analysis"):
        for ticker in tickers:
            st.markdown(f"## 🏢 Analysis for {ticker}")
            
            with st.spinner(f"Fetching financial history for {ticker}..."):
                try:
                    stock = yf.Ticker(ticker)
                    info = stock.info
                    
                    # Fetch financial statements safely
                    financials = stock.financials 
                    cashflow = stock.cashflow     
                    balance_sheet = stock.balance_sheet 
                    
                    current_price = clean_numeric_value(info.get("currentPrice", info.get("previousClose", 0)))
                    
                    # Target last 5 columns (years)
                    years = financials.columns[:5][::-1] if not financials.empty else []
                    year_labels = [str(col).split('-')[0] for col in years]
                    
                    eps_history = []
                    fcf_history = []
                    roe_history = []

                    # 1. Gather & Clean EPS History
                    for yr in years:
                        raw_eps = financials.loc['Diluted EPS'].get(yr, 0) if 'Diluted EPS' in financials.index else 0
                        eps_history.append(clean_numeric_value(raw_eps))
                    
                    # Calculate 5-year EPS Growth Rate safely
                    if len(eps_history) >= 2 and eps_history[0] > 0:
                        eps_growth_5yr = ((eps_history[-1] / eps_history[0]) ** (1 / len(eps_history)) - 1) * 100
                    else:
                        eps_growth_5yr = clean_numeric_value(info.get("earningsGrowth", 0)) * 100
                    
                    # 2. Gather & Clean FCF History
                    for yr in years:
                        raw_fcf = cashflow.loc['Free Cash Flow'].get(yr, 0) if 'Free Cash Flow' in cashflow.index else 0
                        fcf_history.append(clean_numeric_value(raw_fcf) / 1e6) # Convert to Millions
                        
                    # 3. Gather & Clean ROE History
                    for yr in years:
                        net_inc = financials.loc['Net Income'].get(yr, 0) if 'Net Income' in financials.index else 0
                        equity = balance_sheet.loc['Stockholders Equity'].get(yr, 1) if 'Stockholders Equity' in balance_sheet.index else 1
                        
                        clean_net_inc = clean_numeric_value(net_inc)
                        clean_equity = clean_numeric_value(equity)
                        
                        roe_val = (clean_net_inc / clean_equity) * 100 if clean_equity != 0 else 0
                        roe_history.append(roe_val)

                    # Fill placeholders if history is completely missing from yfinance
                    if not year_labels:
                        year_labels = ["N/A"]
                        eps_history = [0.0]
                        fcf_history = [0.0]
                        roe_history = [0.0]

                    # --- CALCULATE INTRINSIC VALUE ---
                    fair_value = 0.0
                    
                    if "Benjamin Graham" in valuation_method:
                        base_eps = eps_history[-1] if eps_history else clean_numeric_value(info.get("trailingEPS", 1))
                        g = max(0, eps_growth_5yr) 
                        expected_yield = 5.0
                        fair_value = (base_eps * (8.5 + 2 * (g/100)) * 4.4) / expected_yield
                    else:
                        total_assets = clean_numeric_value(info.get("totalAssets", 0))
                        total_liab = clean_numeric_value(info.get("totalLiabilitiesNetMinorityInterest", info.get("totalDebt", 0)))
                        shares_out = clean_numeric_value(info.get("sharesOutstanding", 1))
                        fair_value = (total_assets - total_liab) / shares_out if shares_out else 0
                    
                    # Calculate Discount / Premium
                    if fair_value > 0:
                        diff_pct = ((fair_value - current_price) / fair_value) * 100
                        status_label = "Discount (Margin of Safety)" if diff_pct > 0 else "Premium (Overvalued)"
                        status_val = f"{abs(diff_pct):.1f}%"
                    else:
                        status_label = "Margin"
                        status_val = "N/A"
                        diff_pct = 0.0

                    # --- METRICS CARDS ---
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Calculated Fair Value", f"${fair_value:.2f}", help=f"Based on {valuation_method}")
                    col2.metric("Current Market Price", f"${current_price:.2f}")
                    col3.metric(status_label, status_val, delta=f"{diff_pct:.1f}%" if fair_value > 0 else None)

                    # --- HISTORICAL TREND GRAPHS ---
                    st.markdown("### 📊 5-Year Historical Performance Trends")
                    
                    fig, axs = plt.subplots(1, 3, figsize=(18, 4))
                    
                    # EPS Graph
                    axs[0].plot(year_labels, eps_history, marker='o', color='#1f77b4', linewidth=2)
                    axs[0].set_title(f"5-Year EPS Trend (CAGR: {eps_growth_5yr:.1f}%)")
                    axs[0].grid(True, linestyle='--', alpha=0.5)
                    
                    # ROE Graph
                    axs[1].plot(year_labels, roe_history, marker='s', color='#2ca02c', linewidth=2)
                    axs[1].set_title("5-Year Return on Equity (ROE %)")
                    axs[1].grid(True, linestyle='--', alpha=0.5)
                    
                    # FCF Graph
                    axs[2].plot(year_labels, fcf_history, marker='^', color='#ff7f0e', linewidth=2)
                    axs[2].set_title("5-Year Free Cash Flow ($ Millions)")
                    axs[2].grid(True, linestyle='--', alpha=0.5)
                    
                    st.pyplot(fig)
                    plt.close()

                    # Core Multiples Overview Table
                    metrics_df = pd.DataFrame([{
                        "Ticker": ticker,
                        "P/E Ratio": info.get("trailingPE", "N/A"),
                        "Forward P/E": info.get("forwardPE", "N/A"),
                        "Price-to-Book (P/B)": info.get("priceToBook", "N/A"),
                        "Debt-to-Equity": info.get("debtToEquity", "N/A"),
                        "Current Operating Margin": f"{clean_numeric_value(info.get('operatingMargins', 0))*100:.1f}%" if info.get('operatingMargins') else "N/A"
                    }])
                    st.dataframe(metrics_df.set_index("Ticker"))

                    # --- AI VALUATION CRITIQUE ---
                    st.markdown("### 🤖 Deep Value Thesis & Risk Assessment")
                    prompt = f"""
                    Analyze the intrinsic valuation for {ticker}.
                    - Current Price: ${current_price:.2f}
                    - Calculated Intrinsic Value via {valuation_method}: ${fair_value:.2f}
                    - Historical EPS: {eps_history}
                    - Historical ROE %: {roe_history}
                    - Historical FCF ($M): {fcf_history}
                    
                    Provide a concise breakdown:
                    1. Valuation Validation: Does the historical growth warrant this fair value estimation? Is there an actual margin of safety?
                    2. Capital Efficiency: Critique the 5-year trend in ROE and FCF. Is management compounding or destroying value?
                    3. Ultimate Verdict: Is this a 'Buy under Margin of Safety', a 'Hold', or a value trap?
                    """
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                    st.markdown("---")
                    
                except Exception as e:
                    st.error(f"Error analyzing {ticker}: {str(e)}")
else:
    st.info("Please enter your free Google Gemini API Key in the sidebar to unlock the application.")
