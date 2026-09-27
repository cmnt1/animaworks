# Use Case: Research, Investigation, and Analysis

This use case automates information gathering and analysis, including web search, market research, competitive analysis, and report creation.

---

## Problems This Can Solve

- Information gathering takes too long
- You want to regularly check competitor activity but don't have the bandwidth
- Compiling collected information into reports is tedious
- You want to track mentions of your company on social media
- You want to automate periodic market data collection and analysis

---

## Pattern 1: Information Gathering via Web Search

### What It Does
Performs web searches on a specified topic, then summarizes, organizes, and reports the results.

### Workflow
1. Receive a research topic from a human
2. Collect information using multiple search queries
3. Organize and summarize the collected information
4. Report with sources cited

### Example Uses
- "Research the latest trends in the ○○ industry" → Summarize key articles and report
- "Research the technology called ○○" → Compile an overview, pros, cons, and adoption examples
- "Research company ○○" → Organize company overview, latest news, and reputation

### Key Points
- Always include information sources (URLs)
- Clearly mark unverifiable information as "unconfirmed"
- Cross-check multiple sources to ensure reliability

---

## Pattern 2: Regular Competitor and Market Monitoring

### What It Does
Regularly checks competitor and market developments and reports any changes.

### Workflow
1. Runs on a regular schedule (e.g., every Monday)
2. Collects information on pre-configured monitoring targets:
   - Competitors' new services and press releases
   - Industry news
   - Relevant regulatory and legal changes
3. Extracts the diff from the previous check
4. Reports a summary if there are changes

### Example Uses
- "Competitor A has released a new feature. Overview: ○○"
- "A new regulatory proposal has been announced in the ○○ industry"
- "A new research report useful for estimating market share has been published"

---

## Pattern 3: Social Media and Media Monitoring

### What It Does
Regularly searches for mentions of your company and products on social media and news sites to gauge reputation.

### Workflow
1. Regularly search social media and news sites
2. Collect mentions using company name, product name, and related keywords
3. Classify mentions as positive, negative, or neutral
4. Report notable posts and trends

### Example Uses
- "This week there were 15 mentions of the company: 10 positive, 2 negative, 3 neutral"
- "An influential user posted a favorable review of our product"
- "Negative reviews are on the rise. The main complaints are ○○"

### Cautions
- Report social media posts with full context (do not cherry-pick fragments)
- Immediately notify a human if a post with reputational risk is detected

---

## Pattern 4: Data Collection and Periodic Reports

### What It Does
Periodically collects public or market data and automatically generates analytical reports.

### Workflow
1. Fetch data from data sources on a regular schedule
2. Analyze changes over time
3. Detect anomalies and trend shifts
4. Generate reports including charts and tables

### Example Uses
- Daily reports on exchange rates, stock prices, and cryptocurrency prices
- Weekly analysis of your service's usage statistics
- Estimating market vitality from industry job posting trends

---

## Pattern 5: Deep-Dive Research and Due Diligence

### What It Does
Conducts multi-faceted, in-depth research on a specific company, individual, or technology.

### Workflow
1. Confirm the research target and purpose
2. Collect information from web searches, public databases, news archives, etc.
3. Categorize and organize the collected information:
   - Basic information (founding year, location, business description, etc.)
   - Financial information (if publicly available)
   - Reputation and reviews
   - Risk information
4. Report as a structured report

### Example Uses
- Company research for potential M&A targets
- Credit checks on new business partners (based on public information)
- Evaluating whether to adopt new technology (pros, cons, costs, examples)

---

## Pattern 6: Regular Regulatory and Compliance Checks

### What It Does
Regularly checks for changes in laws and regulations relevant to your business.

### Workflow
1. Search for relevant laws and regulations on a regular schedule (e.g., weekly)
2. Detect changes in new laws, regulations, and guidelines
3. Assess the impact on your business
4. If there is an impact, compile details and report

### Example Uses
- "An amendment to the Personal Information Protection Act has been proposed. Impact on our service: ○○"
- "A new guideline has been issued by an industry association"
- "Related regulations have been tightened in ○○ (country). Impact level: Medium"

---

## Configuration Tips

### Minimal Configuration (1 Anima)
- A single instance receives and executes research requests
- Operates on an ad-hoc basis with human instructions
- Can also handle periodic monitoring

### Recommended Configuration (2–3 Anima)
- **Research role**: Executes research requests and deep-dive investigations
- **Monitoring role**: Handles regular market, social media, and regulatory monitoring
- **Analysis role**: Analyzes collected data and generates reports

### Tips for Improving Research Quality
- Always evaluate the reliability of information sources
- Cross-check with multiple sources
- Clearly distinguish between "confirmed facts" and "speculation"
- Include dates for older information
- Accumulate research results as knowledge and leverage them in future work