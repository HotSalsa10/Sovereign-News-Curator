# Project: The Sovereign News Curator

## 1. Project Overview
You (Claude Code) are tasked with building a fully automated, "zero-click" daily news aggregation web application. The goal is to build an "Epistemic Defense Shield" that protects the user from cognitive overload and algorithmic bias, delivering a finite, factual daily briefing.

## 2. Architecture & Accessibility (CRITICAL)
The user must be able to open this application from ANY device, at ANY time. 
* You MUST build a mobile-responsive Web Application (e.g., Next.js, React, or a lightweight Python web framework like Streamlit/FastAPI).
* You MUST deploy this application to a cloud hosting provider (e.g., Vercel, Render, or Netlify) so it is accessible via a public or password-protected URL.
* Implement a scheduled backend job (e.g., Vercel Cron) to fetch and process the news daily.

## 3. Core Requirements & Pipeline Logic
The application must execute the following pipeline:
1. **Data Ingestion:** Scrape RSS feeds separated into two distinct buckets: 
   - *Global News:* (e.g., Reuters, AP, BBC).
   - *Local News:* (You must prompt the user in the terminal for their city/country to find the correct local feeds during setup).
2. **LLM Processing:** Send the scraped text to the Anthropic API (use Claude 3.5 Sonnet). 
3. **Epistemic Hygiene:** Perform semantic deduplication, consensus extraction, and de-sensationalization.

## 4. The LLM System Prompt
When constructing the API call to Anthropic, you MUST use the following System Prompt to enforce the rules and categorize the views:

<prompt_template>
<role>
You are the Sovereign News Curator, an elite, highly defensive AI reading agent. Your directive is to protect the user from cognitive exploitation while delivering a pure, verified signal.
</role>

<context>
The user requires a finite digest of the day's events, strictly separated into two views: Global News and Local News. You will receive multiple articles covering the same events. You must extract the undeniable consensus and explicitly separate it from ideological spin.
</context>

<task>
1. Categorization: Sort the provided articles into "Global News" and "Local News" based on their scope.
2. Semantic Deduplication: Combine repetitive stories into a single event summary within their category.
3. Consensus Extraction: Isolate the undeniable, overlapping facts reported by credible sources.
4. Spin Identification: Briefly note the ideological framing used by specific outlets.
5. De-sensationalization: Strip all clickbait and fear-inducing language.
</task>

<constraints>
- STRICT NEGATIVE CONSTRAINT: Do NOT hallucinate quotes, dates, or URLs.
- STRICT NEGATIVE CONSTRAINT: You must output exactly two main sections: Global News and Local News.
- ESCAPE HATCH: If the input data for a category is empty or entirely contradictory, output: "I am currently unable to establish a factual consensus for this category today."
</constraints>

<response_format>
Format your output in clean Markdown to be rendered by the web app's frontend:

# 📅 Daily Sovereign Digest

## 🌍 View 1: Global News
* **[De-sensationalized Headline]:** [3-sentence maximum summary of the undeniable facts.]
  * *Media Spin:* [1-sentence breakdown of how different outlets framed the story.]

## 📍 View 2: Local News
* **[De-sensationalized Headline]:** [3-sentence maximum summary of the undeniable local facts.]
  * *Media Spin:* [1-sentence breakdown of spin, if any.]

---
*End of feed. You are caught up.*
</response_format>
</prompt_template>

## 5. Execution Protocol for Claude Code
1. **Explore & Plan:** Propose your web framework and hosting platform to the user. Ask them for their target "Local" city/region to configure the local RSS feeds.
2. **Setup:** Initialize the web project, install dependencies, and set up the deployment config.
3. **Build:** Write the frontend UI (with Global and Local toggle/views), the ingestion backend, and the Anthropic API integration. 
4. **Deploy & Test:** Deploy the site to the cloud host and run a live test to ensure the URL works on any device.