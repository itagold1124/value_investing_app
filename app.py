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
            
            with st.spinner(f"AI is gathering 5-year financial history for {ticker}..."):
                try:
                    # Leverage Gemini to fetch structured historical financial data securely
                    model = genai.GenerativeModel("gemini-2.5-flash")
                    
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
                        "eps_growth_5yr_pct": 5.0
                    }}
                    Estimate values accurately based on the company's annual financial filings if needed.
                    """
                    
                    response = model.generate_content(data_prompt)
                    
                    # Clean response text if model wrapped it in markdown code blocks
                    clean_text = response.text.strip().replace("```json", "").replace("```", "")
                    financial_data = json.loads(clean_text)
                    
                    # Extract variables safely from the AI output
                    current_price = float(financial_data.get("currentPrice", 0.0))
                    year_labels = financial_data.get("years", ["2021", "2022", "2023", "2024", "2025"])
                    eps_history = [float(x) for x in financial_data.get("eps_history", [0.0]*5)]
                    fcf_history = [float(x) for x in financial_data.get("fcf_history_millions", [0.0]*5)]
                    roe_history = [float(x) for x in financial_data.get("roe_history_pct", [0.0]*5)]
                    eps_growth_5yr = float(financial_data.get("eps_growth_5yr_pct", 5.0))
                    
                    # --- CALCULATE INTRINSIC VALUE ---
                    fair_value = 0.0
                    if "Benjamin Graham" in valuation_method:
                        base_eps = eps_history[-1] if eps_history else 1.0
                        g = max(0.0, eps_growth_5yr)
                        expected_yield = 5.0
                        fair_value = (base_eps * (8.5 + 2 * (g/100)) * 4.4) / expected_yield
                    else:
                        total_assets = float(financial_data.get("total_assets", 0.0))
                        total_liab = float(financial_data.get("total_liabilities", 0.0))
                        shares_out = float(financial_data.get("shares_outstanding", 1.0))
                        fair_value = (total_assets - total_liab) / shares_out if shares_out else 0.0
                    
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

                    # Core Multiples Overview Table
                    metrics_df = pd.DataFrame([{
                        "Ticker": ticker,
                        "P/E Ratio": financial_data.get("pe_ratio", "N/A"),
                        "Forward P/E": financial_data.get("forward_pe", "N/A"),
                        "Price-to-Book (P/B)": financial_data.get("pb_ratio", "N/A"),
                        "Debt-to-Equity": financial_data.get("debt_to_equity", "N/A"),
                        "Current Operating Margin": financial_data.get("operating_margin_pct", "N/A")
                    }])
                    st.dataframe(metrics_df.set_index("Ticker"))

                    # --- AI VALUATION CRITIQUE ---
                    st.markdown("### 🤖 Deep Value Thesis & Risk Assessment")
                    analysis_prompt = f"""
                    Analyze the intrinsic valuation for {ticker} based on these values:
                    - Current Price: ${current_price:.2f}
                    - Calculated Intrinsic Value via {valuation_method}: ${fair_value:.2f}
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
