"""Fill TODO sections in all company wiki pages with real content.

Preserves frontmatter and AUTOGEN signal_history sections.
Updates last_updated to today.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parents[1] / "wiki" / "companies" / "public"
TODAY = str(date.today())

# ── Content database ──────────────────────────────────────────────────────────
# Keys are ticker symbols. Each entry has:
#   position: str  (≤80 words, no promotional language)
#   bull: list[str]  (3 bullets)
#   bear: list[str]  (3 bullets)
#   priced_in: str
#   watch: list[str]

CONTENT: dict[str, dict] = {

    # ── AI Infrastructure ─────────────────────────────────────────────────────

    "NVDA": {
        "position": "NVIDIA designs GPUs that have become the dominant compute substrate for AI training and inference. Its CUDA software ecosystem creates switching costs that have kept hyperscalers, labs, and enterprises on its hardware despite growing competition. Data center revenue now exceeds gaming. The H100/H200/Blackwell product line is the primary bottleneck in global AI buildout.",
        "bull": [
            "Demand for GPU compute continues to outpace supply, giving NVIDIA pricing power across its entire data center stack.",
            "The CUDA ecosystem — 4M+ developers — creates compounding lock-in that AMD and Intel have not been able to meaningfully erode despite years of investment.",
            "Sovereign AI programs (governments building national AI infrastructure) represent a new, durable demand vector outside the hyperscaler cycle.",
        ],
        "bear": [
            "Hyperscalers (Google TPU, Amazon Trainium, Microsoft Maia) are developing custom silicon specifically to reduce NVDA dependency for inference workloads.",
            "Export controls on A100/H100 class chips to China removed a meaningful revenue segment and create a ceiling on addressable market.",
            "At current revenue multiples, any slowdown in AI capex — driven by rising energy costs, regulatory friction, or model efficiency improvements — would compress the multiple significantly.",
        ],
        "priced_in": "Sustained GPU supply shortage through 2025–2026, continued hyperscaler capex growth, and CUDA ecosystem moat. Market is not pricing in meaningful share loss to custom silicon or a capex pause.",
        "watch": [
            "Hyperscaler custom silicon adoption rate — any public disclosure of TPU/Trainium/Maia replacing H100 at scale.",
            "Blackwell yield and supply ramp — any delay signals production risk.",
            "US export control expansion — further restrictions on lower-end chips (H20) would reduce China revenue.",
        ],
    },

    "AMD": {
        "position": "AMD designs CPUs and GPUs competing directly with Intel and NVIDIA. Its EPYC server CPU line has taken meaningful market share from Intel in data center. Its Instinct MI-series GPUs are the primary alternative to NVIDIA for AI training, though the ROCm software stack remains a competitive disadvantage. Fabless — manufactured at TSMC.",
        "bull": [
            "EPYC CPU market share gains in server continue; Intel's process execution issues create a sustained window for AMD to grow data center CPU revenue.",
            "MI300X GPU adoption is accelerating among cloud providers seeking to diversify away from NVIDIA supply constraints.",
            "AMD's acquisition of Xilinx added an FPGA/adaptive compute portfolio relevant to AI inference at the edge.",
        ],
        "bear": [
            "ROCm software ecosystem is years behind CUDA — most AI researchers default to NVIDIA, making AMD's GPU wins concentrated in a small set of cost-sensitive workloads.",
            "Custom silicon from hyperscalers (Trainium, TPU) targets the same cost-optimization market that AMD's MI-series competes in.",
            "CPU market share gains may plateau as Intel stabilizes its process roadmap with TSMC partnerships.",
        ],
        "priced_in": "Continued EPYC server CPU share gains and MI300X ramp as a credible NVIDIA alternative. Significant upside requires ROCm adoption inflecting.",
        "watch": [
            "MI300X/MI350 design wins at hyperscalers — any announced commitment beyond Microsoft Azure.",
            "ROCm developer adoption metrics — GitHub activity, PyTorch/JAX compatibility updates.",
            "Intel Granite Rapids execution — a recovery narrows AMD's CPU window.",
        ],
    },

    "AVGO": {
        "position": "Broadcom is a diversified semiconductor and infrastructure software company. Its networking ASICs (Tomahawk, Jericho) are central to AI data center fabric. It also develops custom AI accelerators (XPUs) for Google (TPU) and Meta. The VMware acquisition adds a large enterprise software revenue stream. Revenue is split roughly 60% semiconductor, 40% software post-VMware.",
        "bull": [
            "Custom XPU deals with Google and Meta create a durable, high-margin revenue stream tied directly to hyperscaler AI capex — without competing with NVIDIA.",
            "VMware integration is progressing; subscription conversion of perpetual licenses should expand recurring revenue and margin.",
            "AI networking (400G/800G switches, optical interconnects) is growing faster than overall semiconductor markets as GPU clusters scale.",
        ],
        "bear": [
            "VMware integration risk — enterprise customer pushback on subscription pricing changes could slow conversion and elevate churn.",
            "Custom XPU revenue is highly concentrated in two customers (Google, Meta); loss of either would materially impair the AI silicon segment.",
            "Networking ASIC competition is intensifying from Marvell and in-house designs by hyperscalers.",
        ],
        "priced_in": "VMware integration executing smoothly and XPU pipeline expanding beyond two anchor customers. Custom silicon TAM growth priced in at current levels.",
        "watch": [
            "Third XPU customer announcement — any hyperscaler beyond Google and Meta.",
            "VMware subscription conversion rate in quarterly earnings commentary.",
            "400G/800G switch ASP and volume trends vs. Marvell.",
        ],
    },

    "INTC": {
        "position": "Intel designs and manufactures CPUs, GPUs, and networking silicon. Its foundry business (Intel Foundry Services) is a strategic pivot to compete with TSMC and Samsung. It has lost significant data center CPU share to AMD and GPU share to NVIDIA. The 18A process node is the key technology milestone to restore manufacturing leadership.",
        "bull": [
            "If 18A process achieves yields competitive with TSMC N2, Intel becomes the only western advanced foundry — a strategic asset for governments seeking supply chain independence.",
            "Xeon data center CPU base remains large; even modest share stabilization generates significant free cash flow.",
            "US CHIPS Act subsidies reduce the capital intensity of the foundry buildout.",
        ],
        "bear": [
            "18A process has faced repeated delays; every delay cedes another generation of manufacturing leadership to TSMC.",
            "Gaudi AI GPU has not gained meaningful traction against NVIDIA H100/H200 — software and ecosystem gaps are significant.",
            "Foundry customer pipeline remains thin; without external customers, IFS cannot achieve the scale economics needed to be cost-competitive.",
        ],
        "priced_in": "18A process achieving risk production on schedule. Market has already discounted significant foundry execution risk — upside requires external customer wins.",
        "watch": [
            "18A risk production yield — any public disclosure or customer tape-out announcement.",
            "IFS external customer wins beyond Amazon (who have one design in process).",
            "Xeon market share in quarterly server CPU shipment data (IDC/Mercury Research).",
        ],
    },

    "MSFT": {
        "position": "Microsoft operates Azure (cloud infrastructure), productivity software (Office 365, Teams), and enterprise applications (Dynamics, LinkedIn). Its OpenAI partnership gives it preferential access to GPT-4 class models, deployed via Azure OpenAI Service and embedded in Copilot across its product suite. Azure is the second-largest cloud by revenue behind AWS.",
        "bull": [
            "Copilot monetization across 400M+ Office users represents the largest potential AI revenue upsell of any software company.",
            "Azure AI services are growing faster than the broader Azure business, suggesting AI is expanding the cloud TAM rather than cannibalizing existing workloads.",
            "Enterprise software lock-in (Office, Teams, Dynamics) creates a stable monetization floor that buffers execution risk in AI.",
        ],
        "bear": [
            "OpenAI exclusivity is not guaranteed — the partnership structure allows OpenAI to pursue other cloud providers after certain conditions, and OpenAI's own compute buildout could reduce Azure dependency.",
            "Copilot pricing ($30/seat/month) is high enough that enterprise adoption is slower than initial forecasts suggested.",
            "Azure market share gains vs. AWS have stalled; Google Cloud is the faster-growing competitor in AI workloads.",
        ],
        "priced_in": "Copilot achieving broad enterprise adoption and Azure AI revenue sustaining 30%+ growth. Significant multiple compression if Copilot penetration disappoints.",
        "watch": [
            "Copilot seat count disclosures in earnings — any quantification of paying Copilot users vs. free trials.",
            "Azure AI revenue as percentage of total Azure — directional trend vs. Google Cloud.",
            "OpenAI governance and exclusivity terms — any renegotiation or competitive opening.",
        ],
    },

    "GOOGL": {
        "position": "Alphabet operates Google Search, YouTube, Google Cloud (GCP), and develops AI through DeepMind and Google Brain (now Google DeepMind). It is the largest digital advertising platform globally. GCP is the third-largest cloud. Its TPU infrastructure gives it a proprietary AI compute advantage for internal workloads. Gemini is its flagship LLM family.",
        "bull": [
            "Search remains the highest-intent advertising channel with no credible displacement yet — AI Overviews appear to be expanding session depth rather than cannibalizing click revenue.",
            "GCP is gaining enterprise AI workload share; TPU availability and Vertex AI tooling are competitive differentiators for customers who want non-NVIDIA infrastructure.",
            "DeepMind's research output (AlphaFold, Gemini) gives Google a talent and IP advantage that compounds over time.",
        ],
        "bear": [
            "AI-native search competitors (Perplexity, ChatGPT search) could erode query volume at the margin, particularly for informational queries where ads monetize best.",
            "EU regulatory pressure on Search, Android, and ad tech could impose structural remedies that impair margin in the highest-profit segments.",
            "GCP trails AWS and Azure in enterprise contract size and global infrastructure footprint.",
        ],
        "priced_in": "Search revenue resilience through AI transition and GCP sustaining 25%+ growth. Risk scenario is Search query volume declining faster than new AI monetization scales.",
        "watch": [
            "Search query volume trends — any disclosure of AI Overview impact on paid click-through rates.",
            "GCP revenue growth rate vs. Azure and AWS in quarterly earnings.",
            "EU DMA enforcement actions — any forced changes to Search or Android distribution.",
        ],
    },

    "AMZN": {
        "position": "Amazon operates e-commerce, AWS (cloud infrastructure), advertising, and logistics. AWS is the largest cloud platform globally with 30%+ market share. It develops custom AI chips (Trainium for training, Inferentia for inference) to reduce NVIDIA dependency. Its advertising segment is the third-largest digital ad business. AWS generates the majority of operating income.",
        "bull": [
            "AWS AI services (Bedrock, SageMaker) are growing faster than core AWS, and Trainium chip adoption reduces per-unit compute cost — enabling margin expansion as AI workloads scale.",
            "Advertising revenue is growing at 20%+ with high margins, becoming a third major profit engine alongside AWS and retail.",
            "Logistics network investments are now generating returns — same-day delivery capability creates a durable retail moat.",
        ],
        "bear": [
            "AWS market share has been slowly eroding as Azure and GCP grow faster; enterprise AI workloads skew toward Azure (OpenAI) and GCP (Gemini).",
            "Retail segment faces margin pressure from increased competition (Temu, Shein) and continued logistics cost inflation.",
            "Trainium adoption outside of Amazon's own workloads is limited — external customer wins are necessary to justify the chip investment.",
        ],
        "priced_in": "AWS reaccelerating to 20%+ growth and advertising continuing at current trajectory. Market prices in Trainium as a cost-savings tool, not a revenue driver.",
        "watch": [
            "AWS revenue growth rate — any reacceleration above 20% signals enterprise workload return.",
            "Trainium external customer wins — any hyperscaler or large enterprise adoption beyond Amazon.",
            "Retail operating margin — recovery toward pre-COVID levels would be significant.",
        ],
    },

    "META": {
        "position": "Meta Platforms operates Facebook, Instagram, WhatsApp, and Threads. It is the second-largest digital advertising platform. It spends more on AI capex per revenue dollar than any other hyperscaler — primarily to improve ad targeting and recommendation systems. Its open-source Llama models are widely adopted. Reality Labs (VR/AR) remains a significant operating loss.",
        "bull": [
            "AI-driven ad targeting improvements are measurably increasing advertiser ROI, supporting pricing power in a competitive market.",
            "Llama open-source strategy builds ecosystem goodwill and attracts developer talent without cannibalizing core revenue.",
            "WhatsApp monetization in emerging markets (business messaging, payments) is early-stage with large optionality.",
        ],
        "bear": [
            "Reality Labs has consumed $50B+ in cumulative losses with no clear path to profitability — investor tolerance for this drag is a risk.",
            "European regulatory risk is highest among US tech; GDPR enforcement and DSA compliance costs could structurally impair EU ad revenue.",
            "Teen and young adult engagement trends on Facebook are negative; Instagram and Threads must compensate.",
        ],
        "priced_in": "AI ad efficiency gains sustaining 15-20% revenue growth and Reality Labs losses stabilizing. Market is not pricing in a regulatory structural remedy in Europe.",
        "watch": [
            "Reality Labs quarterly loss — any inflection (positive or negative) vs. $4B/quarter run rate.",
            "EU DMA enforcement — any fine or behavioral remedy related to ad targeting.",
            "Instagram Reels vs. TikTok engagement metrics — third-party data from Sensor Tower, Data.ai.",
        ],
    },

    "TSM": {
        "position": "Taiwan Semiconductor Manufacturing Company is the world's leading contract chip manufacturer, producing chips for NVIDIA, AMD, Apple, and most advanced semiconductor designs. Its N3 and N2 process nodes are 1-2 generations ahead of Samsung and Intel Foundry. Its geographic concentration in Taiwan is a significant geopolitical risk factor.",
        "bull": [
            "AI chip demand (NVIDIA, AMD, custom XPUs) requires advanced nodes that only TSMC can produce at scale — driving premium pricing and capacity pre-commitments from major customers.",
            "Arizona and Japan fab expansions reduce geopolitical risk premium and qualify TSMC for US CHIPS Act subsidies.",
            "N2 process node is on track with strong early yield reports — sustaining the technology leadership gap vs. competitors.",
        ],
        "bear": [
            "Taiwan invasion scenario, however low probability, represents an existential risk that no hedging strategy fully addresses.",
            "Arizona fab costs are materially higher than Taiwan — US-produced chips carry a cost premium that customers will resist.",
            "A global capex pause (if AI spending decelerates) would hit TSMC with high operating leverage given its fixed cost base.",
        ],
        "priced_in": "Continued AI chip demand growth and N2 ramp on schedule. Geopolitical risk is partially but not fully priced — market assigns a discount vs. pure-play logic.",
        "watch": [
            "CoWoS advanced packaging capacity — bottleneck for HBM-enabled AI chips (H100/H200/GB200).",
            "Arizona fab yield and cost structure — any disclosure of US vs. Taiwan cost differential.",
            "China revenue percentage — exposure to export control escalation.",
        ],
    },

    "ASML": {
        "position": "ASML holds a monopoly on extreme ultraviolet (EUV) lithography machines, required to manufacture chips at 7nm and below. Every advanced chip — NVIDIA, AMD, Apple, Intel — is produced on equipment ASML makes. Its next-generation High-NA EUV system is required for 2nm-class nodes. Dutch export controls restrict EUV sales to China.",
        "bull": [
            "No credible alternative to EUV exists — ASML's monopoly is protected by 30 years of accumulated R&D, supply chain complexity, and customer co-development relationships.",
            "High-NA EUV demand from TSMC, Samsung, and Intel Foundry for 2nm nodes creates a multi-year equipment upgrade cycle.",
            "Installed base of 300+ EUV systems generates a growing, high-margin service and upgrade revenue stream.",
        ],
        "bear": [
            "China export controls cut off ASML's fastest-growing market — DUV (older generation) machines are also increasingly restricted.",
            "Semiconductor capex is cyclical; equipment orders correlate with fab utilization, which can swing significantly in a downturn.",
            "High-NA EUV has a very small initial customer base — adoption delays at any one customer materially impacts near-term revenue.",
        ],
        "priced_in": "High-NA EUV ramp on TSMC's 2nm schedule and continued AI-driven fab investment. China revenue loss is priced in at current levels.",
        "watch": [
            "High-NA EUV first commercial shipment and yield at TSMC/Intel.",
            "Dutch export control expansion to DUV systems — any tightening reduces China system revenue.",
            "TSMC N2 production ramp timeline — delays push out ASML equipment demand.",
        ],
    },

    "AMAT": {
        "position": "Applied Materials supplies equipment for depositing, etching, and inspecting semiconductor films. It is the largest semiconductor equipment company by revenue. Its tools are used at every node from mature processes to leading-edge 2nm. AI-driven demand for advanced memory (HBM) and logic chips is a primary growth driver. Revenue is split roughly 75% semiconductor, 15% display, 10% services.",
        "bull": [
            "HBM memory production requires more deposition steps per layer than standard DRAM, creating a structural uplift in Applied Materials equipment intensity per wafer.",
            "Gate-all-around (GAA) transistor architecture at 2nm requires new deposition processes where Applied has strong IP.",
            "Services and spare parts (25%+ of revenue) provide a recurring base that smooths capex cycle volatility.",
        ],
        "bear": [
            "Semiconductor equipment is among the most cyclical capital goods — a utilization downturn causes rapid order cancellations.",
            "China revenue (25%+ of total) is at risk from expanding US export controls on advanced equipment.",
            "ASML EUV dominates the narrative but Applied's tools are commoditized in older process steps where competition is intense.",
        ],
        "priced_in": "HBM capacity build and leading-edge logic capex sustaining above-trend spending. China restriction risk partially priced.",
        "watch": [
            "China revenue trend — any acceleration in export control enforcement.",
            "HBM layer count per die — each additional layer increases Applied equipment intensity.",
            "Semiconductor fab utilization rates — leading indicator for new equipment orders.",
        ],
    },

    "LRCX": {
        "position": "Lam Research specializes in etch and deposition equipment critical for 3D NAND flash memory and advanced logic chips. It holds strong market share in atomic layer etch and deposition, processes that become more important as chip geometries shrink. Memory (NAND, DRAM) represents roughly 45% of revenue, making it highly sensitive to memory investment cycles.",
        "bull": [
            "3D NAND layer count increases (200+ layers) require proportionally more Lam etch steps per wafer — volume recovery drives outsized revenue leverage.",
            "Advanced logic (gate-all-around at 2nm) increases etch process complexity where Lam holds strong IP positions.",
            "Memory capex is recovering from a cyclical trough — Micron, Samsung, and SK Hynix are all guiding higher investment.",
        ],
        "bear": [
            "Memory is the most cyclical semiconductor segment; oversupply can emerge quickly, causing sharp equipment spending cuts.",
            "China customer concentration — restrictions on advanced equipment exports have already impacted Lam's China revenue.",
            "NAND pricing is volatile; low NAND prices reduce customer incentive to expand capacity.",
        ],
        "priced_in": "Memory capex recovery continuing through 2025-2026 and logic etch share gains. Cyclical trough is fully priced.",
        "watch": [
            "NAND contract pricing — sustained price recovery is necessary for capacity investment to continue.",
            "Customer capex guidance from Micron, Samsung, SK Hynix — leading indicator for Lam orders.",
            "Export control expansion to additional Lam tools or additional Chinese customers.",
        ],
    },

    "KLAC": {
        "position": "KLA Corporation makes process control and inspection equipment — tools that detect defects during chip manufacturing. Process control spending is less cyclical than deposition/etch because fabs must inspect wafers regardless of utilization. KLA holds 50%+ market share in wafer inspection and metrology. Revenues correlate with wafer starts, not just new fab construction.",
        "bull": [
            "Process control intensity (spend as % of total equipment) increases at each new process node — advanced logic and HBM require more inspection steps per wafer.",
            "Recurring revenue from installed base services provides a stable revenue floor through equipment cycles.",
            "AI-driven demand for defect-free chips increases quality requirements, supporting higher inspection spending per wafer.",
        ],
        "bear": [
            "China revenue restriction risk is lower for KLA than peers (less advanced tools) but not zero — export controls are expanding.",
            "At 50%+ market share, organic growth is bounded by overall wafer start growth rather than share gains.",
            "Valuation premium vs. peers requires sustained above-market growth that may compress in a capex slowdown.",
        ],
        "priced_in": "Process control intensity continuing to increase and KLA maintaining dominant market share. Counter-cyclical positioning partially priced in premium multiple.",
        "watch": [
            "Process control as % of total equipment spend in customer capex budgets.",
            "New product cycle — EUV-specific metrology tools for High-NA process qualification.",
            "China wafer start volumes — proxy for KLA's China service revenue.",
        ],
    },

    "MU": {
        "position": "Micron Technology designs and manufactures DRAM and NAND flash memory. It is the only US-based advanced memory manufacturer. Its HBM3E product is shipping to NVIDIA for use in H100/H200 AI accelerators. Memory is one of the most cyclical semiconductor segments, with pricing driven by supply/demand balance across a small number of global producers.",
        "bull": [
            "HBM content per AI server is growing — each GB200 NVL72 system requires orders of magnitude more HBM than a traditional server, creating a structural demand uplift.",
            "As the only US HBM supplier, Micron benefits from supply chain security mandates from US government and allied nations.",
            "DRAM pricing is recovering — supply discipline from Samsung and SK Hynix is supporting ASP recovery.",
        ],
        "bear": [
            "Memory pricing is famously volatile — oversupply can emerge within 12-18 months if Samsung breaks ranks and floods the market.",
            "HBM capacity is constrained by CoWoS packaging at TSMC — Micron cannot ship more HBM than TSMC can package.",
            "China is Micron's largest market and has been subject to regulatory retaliation — any expansion of Chinese government restrictions would be material.",
        ],
        "priced_in": "HBM demand sustaining through 2025-2026 and DRAM pricing recovery continuing. Market is not pricing in a Samsung-led oversupply event.",
        "watch": [
            "Samsung DRAM/HBM capex — any increase signals supply addition that would compress pricing.",
            "HBM CoWoS packaging allocation at TSMC — determines Micron's near-term HBM shipment ceiling.",
            "China market access — any regulatory action beyond the 2023 Fujian cybersecurity review.",
        ],
    },

    "ANET": {
        "position": "Arista Networks makes Ethernet switches for data centers and cloud environments. Its EOS operating system is deployed across hyperscaler AI clusters and enterprise networks. AI GPU clusters require ultra-low-latency, high-bandwidth switching fabrics (400G/800G) where Arista competes with NVIDIA (InfiniBand) and Cisco. Hyperscalers represent 40%+ of revenue.",
        "bull": [
            "AI cluster networking is shifting from InfiniBand to Ethernet at scale — Arista's Ultra Ethernet Consortium membership and 800G product line positions it to capture this transition.",
            "Enterprise campus and WAN modernization is a second growth vector largely independent of AI spending.",
            "EOS software differentiation (single operating system across all hardware) reduces customer operational complexity vs. Cisco.",
        ],
        "bear": [
            "Hyperscaler concentration (Microsoft, Meta, Google represent large % of revenue) means spending decisions by two or three customers drive results.",
            "NVIDIA InfiniBand retains technical advantages for tightly coupled AI training workloads — Ethernet's total cost of ownership advantage doesn't apply to all use cases.",
            "Cisco is investing aggressively in AI networking; its scale and enterprise relationships could erode Arista's campus share.",
        ],
        "priced_in": "Hyperscaler AI networking capex continuing at current pace and Ethernet displacing InfiniBand. Significant multiple compression if AI capex pauses.",
        "watch": [
            "400G/800G port shipment volumes and pricing — ASP trend vs. volume growth.",
            "Ethernet vs. InfiniBand adoption data from hyperscaler earnings calls.",
            "Microsoft capex guidance — Arista's largest individual customer.",
        ],
    },

    "CSCO": {
        "position": "Cisco Systems is the dominant enterprise networking vendor, selling switches, routers, firewalls, and collaboration software (Webex). Its data center switching business competes with Arista. The Splunk acquisition added a large observability and security data platform. Revenue mix is shifting toward software and subscription, with hardware declining as a percentage.",
        "bull": [
            "Splunk integration adds a high-margin, recurring revenue software business that improves Cisco's revenue quality and reduces hardware cyclicality.",
            "AI networking demand (400G switches for GPU clusters) is incremental to Cisco's existing enterprise switching business.",
            "Large installed base in enterprise and government creates renewal and upgrade revenue that competitors cannot easily displace.",
        ],
        "bear": [
            "Arista is winning data center switching share — Cisco's NX-OS vs. EOS comparison is consistently unfavorable in competitive evaluations.",
            "Splunk integration execution risk is high; large software acquisitions frequently underperform synergy targets.",
            "Core enterprise networking growth is slow; the hardware business is in secular decline as software-defined networking matures.",
        ],
        "priced_in": "Splunk integration delivering promised synergies and AI networking offsetting hardware declines. Market expects margin improvement from software mix shift.",
        "watch": [
            "Splunk ARR growth and customer retention post-acquisition.",
            "Data center switching market share — Arista vs. Cisco quarterly shipment data.",
            "Product revenue vs. software/services revenue split — pace of mix shift.",
        ],
    },

    "MRVL": {
        "position": "Marvell Technology designs custom silicon (XPUs) for hyperscalers, networking semiconductors, and optical interconnect components. It has custom AI accelerator design wins at Amazon (Trainium) and Google (TPU). Its electro-optics portfolio serves the optical interconnect market that is growing with AI cluster density. Revenue is split across cloud, enterprise, telecom, and auto.",
        "bull": [
            "Custom XPU design wins (Amazon, Google) are multi-year, sticky revenue streams with high switching costs — each win takes 3-4 years to ramp.",
            "Optical interconnect (PAM4, coherent DSP) is a structural growth market as AI data centers require more bandwidth per rack.",
            "Cloud end-market concentration (60%+ of revenue) aligns Marvell directly with the fastest-growing capex category.",
        ],
        "bear": [
            "Telecom segment has been in a prolonged downturn — excess inventory at carriers continues to weigh on results.",
            "Custom silicon pipeline is opaque — losing one anchor customer (Amazon, Google) would materially impair revenue.",
            "Marvell competes with Broadcom in several product lines; Broadcom's scale and customer relationships are formidable.",
        ],
        "priced_in": "XPU pipeline expanding beyond two anchor customers and electro-optics growing with AI buildout. Telecom recovery is not in consensus.",
        "watch": [
            "Third XPU customer announcement — Microsoft or Meta would validate pipeline growth.",
            "Telecom segment inventory correction — when carriers resume normal ordering.",
            "Optical interconnect ASP and volume vs. Coherent and II-VI competitors.",
        ],
    },

    "DELL": {
        "position": "Dell Technologies sells AI-optimized servers (PowerEdge), storage, PCs, and enterprise services. Its AI server backlog reached $4B+ as hyperscalers and enterprises ordered NVIDIA GPU-based systems. Dell acts as an integrator — assembling NVIDIA GPUs, TSMC-manufactured components, and Micron memory into server systems. It does not design chips.",
        "bull": [
            "Enterprise AI server demand is in early innings — most enterprises have not yet deployed GPU infrastructure, representing a multi-year upgrade cycle.",
            "Dell's direct sales force and global services organization give it distribution advantages for enterprise customers over hyperscaler-only alternatives.",
            "Storage business (PowerStore, APEX) benefits from AI-generated data volumes requiring new storage infrastructure.",
        ],
        "bear": [
            "As an integrator, Dell's margins on AI servers are thin — NVIDIA captures most of the value, leaving Dell with assembly and logistics margin.",
            "PC segment is in a prolonged downturn; any delay in the AI PC upgrade cycle extends the drag on consumer and commercial PC revenue.",
            "AI server backlog can evaporate quickly if customer priorities shift — backlogs reflect orders, not commitments.",
        ],
        "priced_in": "AI server backlog converting to revenue and enterprise AI deployment accelerating. PC recovery cycle not yet in consensus.",
        "watch": [
            "AI server backlog and order rate each quarter — the leading indicator of future revenue.",
            "ISG (Infrastructure Solutions Group) gross margin — monitors whether NVIDIA pricing is compressing Dell's economics.",
            "PC shipment volumes and ASP — Windows 11 AI PC cycle timing.",
        ],
    },

    "HPE": {
        "position": "Hewlett Packard Enterprise sells servers, storage, networking (Aruba), and the GreenLake hybrid cloud platform. Its AI server portfolio (ProLiant with NVIDIA H100/H200) competes with Dell. Cray supercomputer heritage gives it positioning in national lab and government AI deployments. Revenue is split across servers, storage, networking, and services.",
        "bull": [
            "GreenLake as-a-service model converts upfront hardware revenue into recurring subscription — improving revenue quality if adoption scales.",
            "Aruba networking is a credible alternative to Cisco in enterprise campus — a growing installed base with software attach.",
            "Government and national lab AI clusters (Frontier, Aurora) give HPE high-profile reference architectures.",
        ],
        "bear": [
            "AI server margins are thin for the same reasons as Dell — HPE is an integrator competing on price and services rather than silicon differentiation.",
            "GreenLake adoption is slower than guided — customers are not converting traditional CapEx purchases to subscription at the expected rate.",
            "HPE's scale is significantly smaller than Dell, limiting its ability to negotiate with NVIDIA on GPU allocation.",
        ],
        "priced_in": "GreenLake subscription conversion accelerating and AI server backlog converting to revenue. Government supercomputer wins are already known.",
        "watch": [
            "GreenLake ARR and contract value — quarterly disclosure of subscription bookings.",
            "AI server gross margin — any improvement signals better NVIDIA terms or richer services attach.",
            "Aruba market share vs. Cisco in enterprise campus switching.",
        ],
    },

    "IBM": {
        "position": "IBM provides hybrid cloud infrastructure (Red Hat OpenShift), enterprise software, consulting, and the Watsonx AI platform. Red Hat is the primary growth driver, providing enterprise Linux and Kubernetes. IBM's consulting arm (IBM Consulting) deploys AI solutions for large enterprises. Its mainframe business (Z-series) generates stable, high-margin revenue from financial services customers.",
        "bull": [
            "Red Hat OpenShift is the enterprise Kubernetes standard — AI workload orchestration at scale runs on OpenShift in most large enterprises.",
            "Watsonx is positioned for regulated industries (financial services, healthcare, government) where proprietary model deployment and data sovereignty matter.",
            "Mainframe Z-series upgrade cycle (z17 expected) drives predictable high-margin hardware revenue.",
        ],
        "bear": [
            "Consulting revenue growth is slowing as enterprise IT budgets tighten and clients prioritize AI tooling over traditional consulting engagements.",
            "Watsonx market penetration is modest vs. Microsoft Azure OpenAI and Google Vertex AI — IBM's enterprise relationships help but don't guarantee AI platform wins.",
            "Divestiture of legacy infrastructure services (Kyndryl spinoff) removed scale but the remaining portfolio still has low-growth segments.",
        ],
        "priced_in": "Red Hat sustaining 10%+ growth and Watsonx gaining enterprise AI platform traction. Mainframe cycle is consensus.",
        "watch": [
            "Red Hat revenue growth rate — deceleration below 10% would be a significant negative signal.",
            "Watsonx deal size and enterprise customer count — any quantification of AI platform wins.",
            "Consulting revenue backlog — leading indicator of professional services demand.",
        ],
    },

    "ORCL": {
        "position": "Oracle sells enterprise databases (Oracle DB), cloud infrastructure (OCI), and business applications (ERP, HCM, SCM). Its OpenAI partnership to provide GPU compute on OCI is a significant catalyst. OCI is growing faster than Azure/AWS/GCP from a smaller base. Its Autonomous Database and cloud ERP suite are the primary competitive moats.",
        "bull": [
            "OCI GPU cluster wins (OpenAI, Elon Musk's xAI) validate OCI's networking and compute performance at scale — differentiating it from AWS/Azure on GPU cluster latency.",
            "Oracle Database installed base (virtually every large enterprise) creates a migration pathway to Oracle Cloud that competitors cannot easily replicate.",
            "Healthcare vertical (Cerner acquisition) adds a large EHR installed base with multi-year migration upside.",
        ],
        "bear": [
            "OCI is still subscale vs. AWS and Azure — global region count and enterprise sales coverage lag significantly.",
            "Cerner integration has been slower and more expensive than anticipated — EHR modernization is complex.",
            "Database on-premise revenue is in long-term decline as customers migrate to cloud-native alternatives.",
        ],
        "priced_in": "OCI sustaining 40%+ growth and OpenAI/xAI GPU wins converting to durable cloud revenue. Cerner synergies not yet in consensus.",
        "watch": [
            "OCI revenue growth rate — whether 40%+ growth is sustainable as the base grows.",
            "GPU cluster bookings — any additional hyperscale AI lab wins beyond OpenAI and xAI.",
            "Remaining performance obligations (RPO) — backlog metric that signals future OCI revenue.",
        ],
    },

    "PLTR": {
        "position": "Palantir builds AI and data integration platforms for government intelligence agencies (Gotham) and commercial enterprises (Foundry, AIP). Its AIP platform layers LLMs onto enterprise data with strict access controls — targeting regulated industries. US government contracts (DoD, intelligence community) represent roughly 55% of revenue, with commercial growing faster.",
        "bull": [
            "AIP bootcamp model is converting commercial enterprise prospects at an accelerating rate — a differentiated go-to-market that bypasses traditional enterprise sales cycles.",
            "US government AI spending is growing — DoD AI contracts and classified work are durable revenue with high barriers to competitive displacement.",
            "Data moat: Gotham models trained on classified government data are irreplaceable — no competitor can replicate this without the same access.",
        ],
        "bear": [
            "Commercial revenue outside the US remains small — international commercial expansion has been slower than management guided.",
            "Valuation implies very high growth expectations; any deceleration in AIP commercial bookings would compress the multiple significantly.",
            "Government contracts are subject to budget cycles and political risk — a continuing resolution or defense budget cut could slow new awards.",
        ],
        "priced_in": "AIP commercial adoption inflecting and US government AI spending growing. International commercial growth not yet in consensus — represents optionality.",
        "watch": [
            "US commercial revenue growth rate — AIP bootcamp conversion to signed contracts.",
            "Government TCV (total contract value) of new awards — directional trend in DoD/IC spending.",
            "International commercial revenue — any inflection beyond current low single-digit percentage of total.",
        ],
    },

    "CDNS": {
        "position": "Cadence Design Systems provides electronic design automation (EDA) software and hardware used to design chips. Its tools are used to design virtually every advanced semiconductor — AI chips, mobile SoCs, networking ASICs. EDA is a duopoly with Synopsys. AI chip design complexity is increasing EDA tool intensity per design. Revenue is predominantly subscription-based.",
        "bull": [
            "AI chip design complexity (chiplets, advanced packaging, high layer count) increases simulation and verification time — more Cadence tool hours per tapeout.",
            "AI-in-EDA: Cadence's Cerebrus and Veridify use ML to optimize chip layouts, creating a new premium product tier.",
            "Subscription revenue model provides high visibility and low churn — over 90% of revenue is recurring.",
        ],
        "bear": [
            "EDA is a duopoly but Synopsys is acquiring Ansys — the combined entity would have simulation capabilities that challenge Cadence in multi-physics analysis.",
            "China export controls restrict Cadence from selling its most advanced EDA tools to Chinese chip designers.",
            "Customer concentration: a slowdown in chip design activity (if AI chip spending decelerates) directly impacts tool utilization and renewal rates.",
        ],
        "priced_in": "AI chip design activity sustaining high EDA utilization and Cadence's AI-in-EDA products gaining adoption. Synopsys-Ansys competitive threat partially priced.",
        "watch": [
            "Synopsys-Ansys merger completion and integration — combined simulation and EDA capability.",
            "China revenue — any additional tool restriction.",
            "AI chip design starts — any data on NVIDIA, AMD, custom ASIC tapeout volumes.",
        ],
    },

    "SNPS": {
        "position": "Synopsys provides EDA software for chip design, silicon IP (standard cells, interface IP), and software security testing tools. Its acquisition of Ansys (simulation software) is pending regulatory approval — the combined entity would be the largest EDA and simulation company. Like Cadence, it benefits from AI chip design complexity. Revenue is largely subscription-based.",
        "bull": [
            "If the Ansys acquisition closes, Synopsys becomes the only vendor offering end-to-end chip design (EDA) and system-level simulation — a significant competitive moat.",
            "Silicon IP (DesignWare) is used in nearly every advanced chip for interfaces (PCIe, USB, DDR) — a recurring royalty-like revenue stream.",
            "Software security testing (Black Duck, Coverity) is a distinct, growing business benefiting from supply chain security requirements.",
        ],
        "bear": [
            "Ansys acquisition faces regulatory scrutiny in multiple jurisdictions — the UK CMA has raised concerns, creating deal uncertainty.",
            "If Ansys is blocked, Synopsys loses the primary strategic rationale for its current valuation premium.",
            "China revenue restriction risk is similar to Cadence — advanced EDA tools are increasingly restricted.",
        ],
        "priced_in": "Ansys acquisition closing and synergies materializing. Significant re-rating risk if the deal is blocked.",
        "watch": [
            "Ansys regulatory approval timeline — UK CMA, EU, and any other jurisdiction review.",
            "China EDA tool restriction expansion.",
            "Software security (Black Duck) ARR growth — diversification from core EDA.",
        ],
    },

    "TXN": {
        "position": "Texas Instruments designs and manufactures analog and embedded processors, serving industrial, automotive, personal electronics, and communications markets. It owns its manufacturing (not fabless), giving it control over cost and capacity. TI is the largest analog semiconductor company. AI is not a primary near-term driver — industrial and automotive end markets are the focus.",
        "bull": [
            "Industrial and automotive analog content per system is growing — EV powertrains, ADAS sensors, and factory automation all require more TI chips.",
            "Owned manufacturing gives TI cost advantages in analog production that fabless competitors cannot easily replicate.",
            "Cycle recovery: industrial inventory correction that began in 2023 is working through the channel — order recovery should follow.",
        ],
        "bear": [
            "Industrial end market recovery is slower than expected — customers continue to draw down elevated inventory rather than placing new orders.",
            "Capex-heavy owned manufacturing model is a disadvantage in downturns — fixed costs are high relative to peers.",
            "China automotive and industrial exposure is significant — geopolitical or tariff escalation would impact demand.",
        ],
        "priced_in": "Industrial cycle recovery in 2025 and automotive electrification content growth. Extended inventory correction is the bear case that would disappoint consensus.",
        "watch": [
            "Industrial lead times and order patterns — any recovery from low single-digit book-to-bill.",
            "Automotive production volumes — ADAS content growth is volume-dependent.",
            "China industrial and automotive orders — geopolitical risk proxy.",
        ],
    },

    "CRWD": {
        "position": "CrowdStrike operates the Falcon cybersecurity platform — a cloud-native endpoint detection and response (EDR) and extended detection and response (XDR) solution. Its agent-based architecture collects telemetry from endpoints and uses AI to detect threats. It is the market share leader in EDR. The July 2024 global IT outage from a faulty content update was a reputational and legal risk.",
        "bull": [
            "Platform consolidation: CrowdStrike's strategy of adding modules (identity protection, cloud security, SIEM) to Falcon is winning against point-solution vendors in enterprise deals.",
            "Federal government is a large and growing customer — FedRAMP authorization and CISA endorsements create durable government revenue.",
            "AI-native threat detection (Charlotte AI) is a genuine capability advantage — the volume of telemetry CrowdStrike collects trains models that competitors cannot replicate.",
        ],
        "bear": [
            "The July 2024 outage impacted 8.5M Windows devices globally — legal liability, customer churn risk, and reputational damage are still being quantified.",
            "Competition from Microsoft Defender (bundled with M365) is intensifying — Microsoft is good enough for many enterprises at zero marginal cost.",
            "Growth expectations are high — any deceleration in ARR growth would compress a premium multiple.",
        ],
        "priced_in": "July 2024 outage having minimal long-term customer impact and ARR growth sustaining above 25%. Microsoft Defender competitive risk is partially priced.",
        "watch": [
            "Net new ARR each quarter — the primary growth metric, and whether the outage caused structural churn.",
            "Legal liability from the July 2024 outage — any class action settlement or regulatory fine.",
            "Module attach rate — how many Falcon modules per customer, directional trend.",
        ],
    },

    "VRT": {
        "position": "Vertiv Holdings manufactures power and thermal management infrastructure for data centers — UPS systems, power distribution units, cooling (liquid and air), and monitoring software. Its products are required in every data center. AI data centers with dense GPU clusters consume dramatically more power per rack, driving demand for liquid cooling and higher-capacity power systems.",
        "bull": [
            "AI GPU rack density (40-100kW per rack vs. 8-12kW traditional) requires liquid cooling infrastructure where Vertiv holds leading market share.",
            "Data center power infrastructure has 18-24 month lead times — orders placed now represent future revenue with high visibility.",
            "Hyperscalers, colocation providers, and enterprises are all building data center capacity simultaneously — creating broad demand across all customer segments.",
        ],
        "bear": [
            "Execution risk at scale — Vertiv is growing rapidly and supply chain complexity is high for custom thermal and power systems.",
            "Margin pressure: raw material costs (copper, steel) are volatile and Vertiv's ability to pass costs through depends on contract structure.",
            "Any deceleration in data center construction would flow directly to Vertiv orders with a short lag.",
        ],
        "priced_in": "AI data center buildout sustaining through 2026-2027 and liquid cooling becoming the dominant thermal solution. Order backlog provides near-term revenue visibility.",
        "watch": [
            "Order backlog and book-to-bill — leading indicator of future revenue.",
            "Liquid cooling as percentage of thermal revenue — directional shift from air to liquid.",
            "Data center construction starts — building permit data and hyperscaler capex guidance.",
        ],
    },

    # ── Space & Defense ───────────────────────────────────────────────────────

    "LMT": {
        "position": "Lockheed Martin is the largest US defense contractor by revenue. Its primary programs are the F-35 fighter (the largest defense program in history), missile defense systems (PAC-3, THAAD), and space systems (GPS III, Orion). Revenue is 97% US government. Production ramp challenges on the F-35 and missile programs are an ongoing operational focus.",
        "bull": [
            "European NATO members increasing defense budgets to 2%+ GDP creates a sustained F-35 and missile system export pipeline.",
            "Hypersonic weapon programs (HALO, LRHW) position Lockheed for the next generation of precision strike, a growing budget priority.",
            "F-35 sustainment revenue (spare parts, training, software upgrades) grows as the fleet size increases — long-duration recurring revenue.",
        ],
        "bear": [
            "F-35 production rate has repeatedly underperformed targets — unit cost remains elevated relative to initial program estimates.",
            "Concentration in the F-35 program means any cancellation, reduction, or international partner withdrawal would be material.",
            "Defense budget pressure from US fiscal concerns could slow sole-source contract award rates.",
        ],
        "priced_in": "F-35 production ramping and international sales pipeline converting. NATO budget increases sustaining export demand.",
        "watch": [
            "F-35 delivery count each quarter vs. target (156/year).",
            "International F-35 orders — any new country LOA (Letter of Offer and Acceptance).",
            "Hypersonic program contract awards — HALO, LRHW production decisions.",
        ],
    },

    "NOC": {
        "position": "Northrop Grumman is a prime defense contractor focused on aerospace systems, defense electronics, mission systems, and space. Its flagship program is the B-21 Raider stealth bomber — the first new US bomber in 30 years. It also produces the Ground Based Strategic Deterrent (GBSD), which will replace Minuteman III ICBMs. Revenue is predominantly US government.",
        "bull": [
            "B-21 is a sole-source program with no domestic competitor — Northrop is the only company that can produce it, providing a durable, high-margin revenue stream for decades.",
            "GBSD (now Sentinel) ICBM replacement is a $100B+ program — Northrop holds the prime contract.",
            "Space segment (satellites, missile warning) is growing with DoD and intelligence community investment in space domain awareness.",
        ],
        "bear": [
            "B-21 is in development and early production — costs are fixed-price, and overruns are absorbed by Northrop rather than the government.",
            "GBSD/Sentinel has faced cost growth concerns from DoD — any restructuring or quantity reduction would impair the program.",
            "Classified space program delays or technical challenges are not visible externally but can surface suddenly in earnings.",
        ],
        "priced_in": "B-21 production ramping on schedule and GBSD/Sentinel proceeding without quantity reduction. Fixed-price B-21 overrun risk is partially priced.",
        "watch": [
            "B-21 per-unit cost and delivery schedule — any Congressional concern about cost growth.",
            "GBSD/Sentinel program review outcomes — DoD cost-plus conversion discussions.",
            "Space segment classified program status — any delay signals in earnings commentary.",
        ],
    },

    "RTX": {
        "position": "RTX (formerly Raytheon Technologies) was formed by the merger of United Technologies and Raytheon. It operates four segments: Pratt & Whitney (jet engines), Collins Aerospace (avionics, interiors), Raytheon Missiles & Defense, and Raytheon Intelligence & Space. The Pratt & Whitney geared turbofan (GTF) engine has a contaminated powder metal issue requiring large-scale fleet inspections.",
        "bull": [
            "Commercial aerospace recovery (Pratt & Whitney GTF engine aftermarket) is a multi-year tailwind as global air travel continues to recover.",
            "Missile demand (Patriot, Stinger, AMRAAM) has dramatically outpaced production capacity — backlog is at record levels driven by Ukraine resupply and NATO restocking.",
            "Collins Aerospace avionics content per aircraft is growing — each new aircraft generation requires more connected and autonomous systems.",
        ],
        "bear": [
            "GTF powder metal inspection costs ($3B+ reserved) create a cash flow headwind that persists through 2026 as airlines ground aircraft for inspection.",
            "Missile production ramp is constrained by workforce and supply chain — backlog does not convert to revenue quickly.",
            "Defense budget risk: Raytheon's missile programs are large line items that attract scrutiny in a budget-constrained environment.",
        ],
        "priced_in": "GTF inspection program executing within reserved cost and missile backlog converting at guided rates. Commercial aerospace recovery is consensus.",
        "watch": [
            "GTF inspection completion rate and cost vs. $3B reserve.",
            "Patriot/AMRAAM delivery rate — supply chain bottleneck resolution.",
            "Commercial aftermarket MRO revenue growth at Pratt & Whitney.",
        ],
    },

    "GD": {
        "position": "General Dynamics operates combat systems (Abrams tank, Stryker), marine systems (nuclear submarine shipbuilding at Electric Boat), Gulfstream business jets, and IT services (GDIT). Electric Boat is the sole US producer of nuclear attack submarines — a program with no foreign competition. Gulfstream is recovering from supply chain challenges.",
        "bull": [
            "Virginia-class and Columbia-class submarine production is multi-decade and sole-source — Electric Boat revenue is one of the most durable in defense.",
            "Gulfstream G700/G800 backlog is at record levels — business jet demand from ultra-high-net-worth individuals and corporations is resilient.",
            "GDIT (IT services) benefits from DoD digital transformation and cloud migration programs.",
        ],
        "bear": [
            "Submarine production rate is constrained by workforce — the Navy wants to buy more than Electric Boat can produce.",
            "Abrams tank production ramp for international customers (Poland, Ukraine support) faces supply chain delays.",
            "Gulfstream delivery rate has been below backlog conversion targets — supply chain normalization is ongoing.",
        ],
        "priced_in": "Submarine production catching up to demand and Gulfstream deliveries ramping. Long-cycle defense programs provide earnings visibility.",
        "watch": [
            "Submarine delivery count (Virginia-class) vs. Navy target of 2.33 per year.",
            "Gulfstream delivery count and backlog coverage ratio.",
            "GDIT contract win rate — proxy for government IT services demand.",
        ],
    },

    "BA": {
        "position": "Boeing is the second-largest commercial aircraft manufacturer (duopoly with Airbus) and a major defense contractor. Its 737 MAX program has faced multiple crises — two fatal crashes, a 2024 mid-flight door plug blowout, and ongoing FAA production rate caps. Its defense segment (KC-46, T-7A, Starliner) has suffered significant fixed-price contract losses.",
        "bull": [
            "Commercial aircraft demand is structurally strong — airlines need to replace aging fleets and expand capacity. A 20,000+ aircraft backlog exists between Boeing and Airbus.",
            "If Boeing stabilizes 737 MAX production quality and the FAA lifts the rate cap, cash flow generation would be substantial.",
            "737 MAX and 787 are both in high demand — any production normalization converts directly to revenue.",
        ],
        "bear": [
            "Quality control problems appear systemic — multiple FAA investigations, whistleblower accounts, and independent audits suggest the issues are not isolated.",
            "Defense segment fixed-price losses (KC-46, T-7A, MQ-25, Starliner) total $20B+ — these programs continue to burn cash.",
            "Debt load ($50B+) constrains Boeing's ability to invest in the next aircraft program while managing current crises.",
        ],
        "priced_in": "Production quality issues being resolved and FAA rate cap being lifted. The market requires Boeing to execute, not just promise. Defense losses are partially priced.",
        "watch": [
            "FAA 737 MAX production rate authorization — current cap is 38/month, certification required for higher rates.",
            "787 delivery rate — Dreamliner is the cash flow engine.",
            "Defense contract losses — any additional charges on fixed-price programs.",
        ],
    },

    "HII": {
        "position": "Huntington Ingalls Industries is the largest US military shipbuilder, operating Newport News Shipbuilding (nuclear carriers and submarines) and Ingalls Shipbuilding (surface combatants, amphibious ships). It is the only US builder of nuclear aircraft carriers and, along with Electric Boat, one of two producers of nuclear submarines. Revenue is entirely US Navy and Coast Guard.",
        "bull": [
            "Nuclear shipbuilding is a protected US industrial base — HII is irreplaceable for aircraft carrier production and shares submarine work with General Dynamics.",
            "Navy shipbuilding budget is growing — the National Defense Strategy emphasizes naval competition with China, supporting multi-year ship programs.",
            "Long-cycle programs (carriers take 8+ years to build) provide exceptional revenue visibility.",
        ],
        "bear": [
            "Production rate for Virginia-class submarines and Ford-class carriers is below Navy targets — workforce and supply chain constraints are binding.",
            "Fixed-price elements in ship contracts expose HII to cost overruns on complex first-of-class vessels.",
            "Cost growth on CVN-82 (third Ford-class carrier) has drawn Congressional attention.",
        ],
        "priced_in": "Shipbuilding workforce growing to meet Navy demand and fixed-price exposure manageable. Long-cycle revenue provides stability.",
        "watch": [
            "Virginia-class submarine delivery rate vs. Navy two-per-year target.",
            "CVN-82 cost-at-completion estimate vs. original contract value.",
            "Navy shipbuilding budget in annual NDAA — quantity of ships authorized.",
        ],
    },

    "LDOS": {
        "position": "Leidos Holdings is the largest US defense IT services company. It provides software, systems integration, and managed services to the DoD, intelligence community, and civilian agencies. Its programs include DHMSM (military health IT), IT infrastructure for the Navy (NGEN), and classified intelligence work. Revenue is predominantly cost-plus government contracts.",
        "bull": [
            "DoD digital transformation and cloud migration programs are large, multi-year — Leidos has strong positioning in DISA and Navy IT infrastructure.",
            "Health IT segment (military electronic health records) is a long-term program with limited competition.",
            "Classified work provides revenue that is not visible to competitors — a buffer during public contract budget uncertainty.",
        ],
        "bear": [
            "Government IT services is a competitive, margin-compressed market — growth depends on winning new programs, which is inherently lumpy.",
            "Continuing resolution risk: prolonged CRs restrict new program starts and can pause existing contract spending.",
            "Defense IT consolidation means fewer but larger contracts — a loss on a large recompete could materially impair revenue.",
        ],
        "priced_in": "NGEN and DHMSM programs renewing on favorable terms and AI-driven IT services growing government book.",
        "watch": [
            "NGEN recompete outcome — large Navy IT infrastructure contract.",
            "Defense budget appropriations — any CR extension delays new contract awards.",
            "AI/ML contract wins in intelligence community — classified signals.",
        ],
    },

    "SAIC": {
        "position": "Science Applications International Corporation (SAIC) provides IT, systems integration, and engineering services to US government agencies — primarily DoD and intelligence community. It spun off Leidos in 2013 and has a smaller revenue base. It focuses on software-intensive programs, cybersecurity, and digital engineering. Nearly all revenue is US government.",
        "bull": [
            "Digital engineering and model-based systems engineering (MBSE) are growing DoD priorities — SAIC has invested in these capabilities.",
            "Cybersecurity services demand from government is structural — every major breach produces additional program funding.",
            "Smaller size than Leidos/SAIC competitors makes it more nimble for mid-size contract pursuits.",
        ],
        "bear": [
            "Revenue growth has been below peers — SAIC has lost several large recompetes in recent years.",
            "Thin margins in government IT services limit earnings leverage.",
            "Continuous resolution risk and budget uncertainty impair new award timing.",
        ],
        "priced_in": "Stable government IT services revenue with modest growth. No major program win assumed.",
        "watch": [
            "Book-to-bill ratio each quarter — new awards vs. revenue, target >1.0.",
            "Large single-award IDIQ wins — transformational contract opportunities.",
            "Defense digital engineering budget line items in NDAA.",
        ],
    },

    "CACI": {
        "position": "CACI International provides IT and professional services to the US intelligence community and DoD, with significant classified program exposure. It is known for intelligence analysis, cyber operations support, and enterprise IT. Classified revenue represents a significant and growing portion — providing defensibility against competitive pressure.",
        "bull": [
            "Intelligence community IT and analytics spending is growing — CACI's classified customer base insulates it from public sector budget debates.",
            "Cyber operations support is a high-priority growth area — CACI has won several classified cyber programs.",
            "International expansion (UK and Germany) adds revenue diversification from US budget cycles.",
        ],
        "bear": [
            "Classified revenue concentration means quarterly results can be opaque — program delays or contract transitions are not visible in advance.",
            "Competition for cleared talent (analysts, cyber professionals) drives wage inflation that pressures margins.",
            "Government contract audits (DCAA) can create working capital pressure on cost-plus programs.",
        ],
        "priced_in": "Classified program growth continuing and intelligence community budget remaining a protected priority.",
        "watch": [
            "Organic revenue growth rate vs. peer group — directional signal on program win rate.",
            "Employee headcount — proxy for classified program staffing.",
            "Intelligence community budget in classified annexes — not public but referenced in earnings calls.",
        ],
    },

    "LHX": {
        "position": "L3Harris Technologies was formed by the merger of L3 Technologies and Harris Corporation. It provides tactical radios, electronic warfare systems, night vision, space sensors, and maritime surveillance. Its products are used by US and allied military forces globally. Revenue is predominantly US government with growing international sales.",
        "bull": [
            "Tactical radio modernization (MUOS-capable, software-defined) is a multi-billion-dollar program across DoD services — L3Harris is a primary supplier.",
            "Electronic warfare demand is growing as near-peer competition escalates — jamming, spoofing protection, and spectrum awareness are budget priorities.",
            "International allies modernizing communications (Australia, UK, Canada) are expanding the export pipeline.",
        ],
        "bear": [
            "Integration of L3 and Harris businesses has taken longer than anticipated — some operational overlap has not been fully rationalized.",
            "Competition from Thales (France), Leonardo (Italy) in international radio markets limits pricing power.",
            "Defense spending prioritization could shift away from communications toward platforms (aircraft, ships) in a budget-constrained environment.",
        ],
        "priced_in": "Tactical radio modernization programs converting at guided rates and international sales growing. Integration synergies are largely priced.",
        "watch": [
            "Tactical radio order rate — MUOS and two-channel radio program awards.",
            "International revenue as % of total — growth directional signal.",
            "Electronic warfare contract awards — any large single award signals DoD priority.",
        ],
    },

    "KTOS": {
        "position": "Kratos Defense produces tactical unmanned aerial systems (drones), target drones, satellite communications ground equipment, and propulsion systems. Its UTAP-22 Mako and XQ-58 Valkyrie are low-cost attritable drones under development for collaborative combat aircraft concepts. Revenue is primarily US government with growing international interest.",
        "bull": [
            "Attritable drone concept (low-cost, expendable) is a strategic DoD priority — Kratos is better positioned than traditional primes for high-volume, low-margin drone production.",
            "Target drone business (providing realistic threat simulations for training) is growing with allied nation investments in air defense.",
            "Propulsion systems (jet engines for drones and missiles) is a growing segment as drone demand expands.",
        ],
        "bear": [
            "Attritable drone programs are in development — production contracts are not yet awarded at scale, creating revenue uncertainty.",
            "Kratos competes with much larger primes (Boeing MQ-28, General Atomics) for collaborative combat aircraft roles.",
            "Small revenue base makes any program delay or cancellation material to results.",
        ],
        "priced_in": "Attritable drone concept winning DoD production contracts and target drone business growing. High-risk, high-reward profile.",
        "watch": [
            "Collaborative combat aircraft program down-select — any production contract award.",
            "Target drone order volume — directional signal on DoD and allied training budgets.",
            "Propulsion backlog — jet engine orders for drone and missile programs.",
        ],
    },

    "RKLB": {
        "position": "Rocket Lab USA operates the Electron small launch vehicle (the second most frequently launched US rocket) and is developing Neutron, a medium-lift reusable rocket. It also sells spacecraft components and operates complete spacecraft buses for government and commercial customers. Revenue is split between launch services and space systems.",
        "bull": [
            "Electron is the leading small dedicated launch vehicle — reliability record and responsive launch cadence attract government and commercial small satellite customers.",
            "Space systems (spacecraft manufacturing) is growing faster than launch — national security satellite programs provide durable government revenue.",
            "Neutron development, if successful, addresses the medium-lift market currently dominated by SpaceX Falcon 9.",
        ],
        "bear": [
            "SpaceX Falcon 9 can rideshare small satellites at costs that pressure Electron's economics for commercial customers.",
            "Neutron development is expensive and high-risk — Rocket Lab must fund it while sustaining Electron operations.",
            "Government launch demand is lumpy — delays in national security satellite programs directly impact Rocket Lab launch revenue.",
        ],
        "priced_in": "Electron sustaining high cadence and space systems growing with national security satellite demand. Neutron success is optionality, not base case.",
        "watch": [
            "Electron launch cadence — target of 20+ launches per year.",
            "Space systems backlog — government satellite manufacturing contracts.",
            "Neutron development timeline and cost — any delay or cost increase.",
        ],
    },

    "ASTS": {
        "position": "AST SpaceMobile is developing a constellation of large satellites designed to provide direct-to-standard-cell-phone connectivity — without special hardware. Its BlueBird satellites passed initial technical tests with major carriers. Commercial service has not yet launched at scale. The company is pre-revenue on its core business and has significant capital requirements.",
        "bull": [
            "If technical performance is validated at scale, the addressable market is every unserved mobile user on Earth — a massive TAM that no terrestrial carrier can address.",
            "Major carrier partnerships (AT&T, Verizon, Rakuten, Vodafone) provide commercial distribution without requiring ASTS to build a retail business.",
            "Regulatory approvals in multiple countries create a barrier to entry for potential competitors.",
        ],
        "bear": [
            "Constellation deployment requires significant additional capital — dilution risk is high for existing shareholders.",
            "Latency and capacity constraints of space-based connectivity limit use cases — voice and basic data may be achievable but high-bandwidth applications are not.",
            "SpaceX Starlink direct-to-cell is a well-funded competitor from a company with dramatically more launch capacity.",
        ],
        "priced_in": "Commercial launch and carrier revenue commencing and BlueBird capacity meeting coverage commitments. High-risk, speculative position.",
        "watch": [
            "BlueBird constellation deployment progress — satellite count and coverage milestones.",
            "Commercial service launch with AT&T/Verizon — any formal service announcement.",
            "Capital raise terms — dilution level and balance sheet runway.",
        ],
    },

    "GSAT": {
        "position": "Globalstar operates a low earth orbit satellite constellation for voice and data communications. Its Apple partnership (providing emergency SOS and satellite messaging on iPhone) generates royalty revenue. It is pursuing a terrestrial spectrum (TLPS) overlay service using its Band 53/n53 spectrum. Revenue is divided between legacy satellite services and Apple royalties.",
        "bull": [
            "Apple contract provides recurring revenue that is not dependent on Globalstar's operational performance — a stable royalty base.",
            "TLPS spectrum represents a potential large-scale Wi-Fi offload service if carriers deploy it — optionality that is not in current consensus.",
            "Emergency satellite messaging use cases are expanding (Apple, other OEMs) as consumer adoption normalizes.",
        ],
        "bear": [
            "Legacy satellite services (consumer voice, asset tracking) are declining as terrestrial and other LEO services displace them.",
            "Apple contract terms are favorable to Apple — Globalstar's economics depend on Apple continuing to invest in and promote the service.",
            "TLPS spectrum deployment has been delayed repeatedly — regulatory and carrier adoption timeline is uncertain.",
        ],
        "priced_in": "Apple royalty stream continuing and TLPS spectrum eventually monetizing. Legacy business decline is known and priced.",
        "watch": [
            "Apple contract renewal terms — any renegotiation signal.",
            "TLPS deployment — any carrier commitment to deploy Band 53/n53 equipment.",
            "Non-Apple OEM satellite messaging deals — any Android OEM partnership.",
        ],
    },

    "IRDM": {
        "position": "Iridium Communications operates a global LEO satellite constellation providing voice and data services to maritime, aviation, government, and IoT customers. Its network covers 100% of Earth's surface including poles — unique among satellite operators. Its Iridium Certus broadband service is displacing older satellite terminals. Revenue is predominantly service revenue with high visibility.",
        "bull": [
            "Pole-to-pole coverage is unique — no other commercial satellite network provides reliable polar coverage, making Iridium indispensable for maritime and aviation operations in those regions.",
            "Iridium Certus L-band broadband is gaining adoption in maritime (ship tracking, crew welfare) and aviation (safety communications).",
            "IoT device tracking business (Iridium Short Burst Data) is growing with asset tracking and remote monitoring use cases.",
        ],
        "bear": [
            "Starlink maritime is competing aggressively on bandwidth and price — Iridium's L-band throughput is fundamentally limited relative to Ka-band.",
            "Government/DoD revenue is a significant portion — budget cycles and contract recompetes create periodic uncertainty.",
            "Next-generation constellation investment will be required in the 2030s — capital intensity will rise.",
        ],
        "priced_in": "Certus broadband adoption sustaining growth and IoT expanding. Starlink maritime competition risk is partially priced at current multiple.",
        "watch": [
            "Certus subscriber additions and ARPU trend.",
            "Maritime IoT device activations — proxy for supply chain and asset tracking demand.",
            "Government services contract renewals — DoD satellite communications recompetes.",
        ],
    },

    "PL": {
        "position": "Planet Labs operates the world's largest commercial Earth observation satellite constellation, providing daily imagery of the entire Earth's landmass. Its customers are government agencies, agriculture companies, financial institutions, and energy companies using satellite imagery for monitoring and analysis. Revenue is subscription-based. The company is not yet profitable.",
        "bull": [
            "Daily revisit rate at global scale is unique — no other commercial operator can image the entire Earth every day, creating a data moat.",
            "Government demand for satellite imagery is growing — NRO, NGA, and allied intelligence agencies are significant customers.",
            "AI analytics on top of imagery (change detection, crop yield, deforestation monitoring) is a higher-margin revenue layer being developed.",
        ],
        "bear": [
            "Competition from Maxar, Airbus Defence, and new entrants (Satellogic, iQPS) is intensifying — imagery is becoming commoditized.",
            "Path to profitability requires significant revenue growth — current burn rate requires additional capital or large government contract wins.",
            "Government contract dependence means any reduction in intelligence community imagery spending would be material.",
        ],
        "priced_in": "Government imagery contract growth and AI analytics adding margin. Profitability timeline is speculative — priced as an option on scale.",
        "watch": [
            "Government contract TCV — any large multi-year award from NRO, NGA, or allied agencies.",
            "Customer count and revenue per customer — trend toward larger deals.",
            "Cash burn rate and balance sheet runway — capital requirements.",
        ],
    },

    "SPCE": {
        "position": "Virgin Galactic operated a suborbital space tourism business (VSS Unity) and was developing Delta class spaceships for higher-frequency commercial operations. It suspended commercial spaceflight operations in 2023 to focus on Delta development. The company has minimal revenue and very high cash burn. It represents a highly speculative, pre-commercial position.",
        "bull": [
            "If Delta class vehicles achieve the targeted 125 flights per year at $450K+ per ticket, the economics are transformative vs. Unity's single-digit annual cadence.",
            "The Virgin brand and Branson legacy provide marketing value that other space startups cannot replicate.",
            "Space tourism is a nascent market with no ceiling established on demand — early adopters are paying and waitlists exist.",
        ],
        "bear": [
            "Delta development timeline and cost have not been disclosed with confidence — execution risk is very high for a company with limited capital.",
            "Blue Origin New Shepard is a direct competitor with Amazon's backing and is already flying passengers.",
            "Cash runway is limited — the company requires additional capital raises that will significantly dilute existing shareholders.",
        ],
        "priced_in": "Highly speculative. Current valuation reflects option value on Delta development succeeding. Do not treat as a research-grade position.",
        "watch": [
            "Delta class development milestone — first flight date and per-vehicle cost.",
            "Cash balance and burn rate — capital raise necessity timeline.",
            "Competitor Blue Origin cadence — any acceleration in New Shepard flights.",
        ],
    },

    "HEI": {
        "position": "HEICO Corporation is a leading supplier of FAA-approved aircraft replacement parts at prices 30-50% below OEM pricing. Its Parts Group sources or reverse-engineers aerospace components; its Electronic Technologies Group supplies defense and space electronics. HEICO is a rare combination of aerospace aftermarket and defense electronics — both driven by fleet age and defense modernization.",
        "bull": [
            "Aging global commercial aircraft fleet (average 14+ years) requires increasing parts replacement — HEICO's addressable market grows with fleet age.",
            "Pricing at 30-50% below OEM creates a structural cost advantage that airlines cannot easily replicate through OEM sourcing.",
            "Defense electronics growth provides a counter-cyclical balance to commercial aerospace cycles.",
        ],
        "bear": [
            "OEMs (GE, Pratt, CFM) are increasingly aggressive in protecting parts exclusivity through repair station restrictions and data withholding.",
            "Serial acquisitions drive HEICO's growth — integration risk and multiple compression if acquisition pace slows.",
            "Defense electronics segment faces the same budget cycle risk as other defense suppliers.",
        ],
        "priced_in": "Aftermarket parts demand growing with fleet age and acquisition pipeline sustaining revenue growth. Premium multiple reflects consistent execution.",
        "watch": [
            "FAA regulatory changes to PMA (Parts Manufacturer Approval) — any restriction would impact HEICO's model.",
            "Acquisition pace and multiples paid — any deterioration in deal economics.",
            "Commercial aircraft production rate — new aircraft delivery reduces average fleet age, a long-term headwind.",
        ],
    },

    "TDG": {
        "position": "TransDigm Group is a highly acquisitive aerospace components manufacturer with dominant market positions in niche proprietary parts. Its strategy is to acquire sole-source aerospace components businesses and extract pricing power. Components include actuators, pumps, ignition systems, and other specialized aerospace hardware. Aftermarket revenue (60%+ of total) is high-margin and recurring.",
        "bull": [
            "Sole-source positioning (no approved alternative supplier) in most product lines gives TransDigm extraordinary pricing power — commercial aerospace customers must buy from TransDigm.",
            "Aftermarket revenue scales with flight hours — commercial aviation recovery drives high-margin aftermarket growth.",
            "M&A strategy has a 30-year track record of value creation — the playbook is proven even if individual acquisitions carry integration risk.",
        ],
        "bear": [
            "Congressional scrutiny of defense parts pricing has intensified — DoD has flagged TransDigm for excessive profits on sole-source defense contracts.",
            "Debt load from acquisitive strategy is high — rising interest rates increase servicing costs.",
            "A commercial aviation downturn would hit the high-margin aftermarket segment hardest.",
        ],
        "priced_in": "Aftermarket recovery continuing with commercial aviation and M&A pipeline delivering accretive deals. Defense pricing scrutiny risk is partially priced.",
        "watch": [
            "Defense pricing audits — any DCAA finding or Congressional action on TransDigm parts pricing.",
            "Aftermarket revenue growth vs. OEM production rate — mix shift indicator.",
            "Debt refinancing activity and interest coverage ratio.",
        ],
    },

    "HWM": {
        "position": "Howmet Aerospace manufacturers precision castings, fasteners, and engineered structures for aerospace and defense. Its turbine blades and structural castings are used in jet engines (GE, Pratt, Rolls-Royce) and airframes (Boeing, Airbus). Engine component content per aircraft is growing as new engine architectures (LEAP, GTF) require more complex castings.",
        "bull": [
            "New engine programs (LEAP, GTF) have higher per-engine casting content than legacy engines — fleet transition creates a structural revenue uplift.",
            "Commercial aerospace production ramp (Boeing 737 MAX, Airbus A320neo) drives engine component demand with a predictable multi-year ramp.",
            "Defense jet engine demand (F-35, F414) provides a non-cyclical base.",
        ],
        "bear": [
            "Engine casting supply chain is a bottleneck in commercial aerospace production — any further disruption would impair Howmet's revenue conversion.",
            "GTF powder metal inspection (RTX issue) delays aircraft return to service — reducing near-term engine spare parts demand.",
            "Titanium supply chain was disrupted by Russia sanctions — raw material availability and pricing remain a risk.",
        ],
        "priced_in": "Commercial aerospace production ramp proceeding and engine casting capacity expanding. GTF inspection impact is partially known.",
        "watch": [
            "Boeing 737 MAX and Airbus A320neo delivery rates — primary demand driver.",
            "GTF spare engine demand — affected by inspection-driven removals.",
            "Titanium procurement — any supply chain normalization or new disruption.",
        ],
    },

    # ── Telecom ───────────────────────────────────────────────────────────────

    "T": {
        "position": "AT&T is a US wireless carrier and fiber broadband provider. It has refocused on its core connectivity businesses after divesting WarnerMedia. Its fiber buildout (AT&T Fiber) is competing with cable operators in broadband. Wireless service revenue is relatively stable. The company carries significant debt from past acquisitions.",
        "bull": [
            "AT&T Fiber is gaining broadband market share from cable operators — fiber is the superior product and AT&T is building past new locations at pace.",
            "Wireless postpaid phone subscribers are stable with improving ARPU as older plans are repriced.",
            "Free cash flow generation is improving as the WarnerMedia integration costs clear — supports debt reduction and dividend sustainability.",
        ],
        "bear": [
            "Debt load ($130B+) constrains capital allocation — AT&T cannot simultaneously invest in fiber, maintain the dividend, and reduce debt aggressively.",
            "Wireless market is saturated — growth requires taking share from Verizon and T-Mobile, which have strong competitive positions.",
            "Lead sheathed cable liability (legacy network infrastructure) is an emerging remediation cost uncertainty.",
        ],
        "priced_in": "Fiber subscriber growth continuing and wireless ARPU stable. Dividend sustainability at current debt levels is consensus.",
        "watch": [
            "AT&T Fiber net adds each quarter — competitive intensity vs. cable.",
            "Lead cable remediation cost disclosures — any formal liability estimate.",
            "Free cash flow vs. dividend coverage — safety margin.",
        ],
    },

    "VZ": {
        "position": "Verizon Communications is the largest US wireless carrier by revenue and the leader in enterprise wireless services. It has been investing in fixed wireless access (FWA) as a cable alternative and is pursuing fiber through the Frontier Communications acquisition. Network quality leadership is its primary competitive positioning.",
        "bull": [
            "Fixed wireless access (FWA) is adding broadband subscribers at low incremental cost — 5G spectrum enables a cable-competitive product without new fiber construction.",
            "Frontier acquisition adds a large fiber footprint in markets where Verizon previously lacked wireline assets.",
            "Enterprise wireless (private 5G networks, IoT) is a growing segment with higher margins than consumer wireless.",
        ],
        "bear": [
            "T-Mobile has been gaining wireless postpaid share consistently — Verizon's network premium is compressing as T-Mobile's mid-band 5G deployment matures.",
            "Frontier integration is complex and expensive — synergy realization will take years.",
            "FWA capacity is finite — adding too many FWA subscribers on the same spectrum used for wireless will create congestion.",
        ],
        "priced_in": "Frontier integration proceeding and FWA subscriber additions continuing. T-Mobile share pressure is consensus.",
        "watch": [
            "Wireless postpaid phone net adds — share trend vs. T-Mobile.",
            "FWA subscriber additions and churn — sustainable vs. introductory promotions.",
            "Frontier integration cost and synergy timeline.",
        ],
    },

    "TMUS": {
        "position": "T-Mobile US is the fastest-growing US wireless carrier, having completed the Sprint merger in 2020. Its mid-band 5G (2.5GHz from Sprint) gives it a nationwide network speed advantage over AT&T and Verizon. It is gaining postpaid phone share consistently and expanding into fixed wireless access and enterprise markets.",
        "bull": [
            "Mid-band 5G spectrum depth (100MHz+ in many markets) enables fixed wireless access as a viable home broadband alternative — a large TAM beyond its wireless base.",
            "Post-merger synergies from Sprint are being realized ahead of schedule — margin improvement is flowing through.",
            "Enterprise market penetration is early-stage — government and large enterprise wireless represent significant upside vs. T-Mobile's consumer-heavy mix.",
        ],
        "bear": [
            "Postpaid phone market growth is slowing — the easy share gains from Sprint integration and competitive promotions are diminishing.",
            "Fixed wireless capacity limitations become binding as subscriber count grows — spectrum reuse constraints will eventually limit FWA expansion.",
            "Both AT&T and Verizon are investing to close the mid-band gap — competitive intensity will increase.",
        ],
        "priced_in": "Postpaid share gains continuing and FWA reaching guided subscriber targets. Enterprise growth is incremental optionality.",
        "watch": [
            "Postpaid phone net adds vs. AT&T and Verizon — share trend.",
            "FWA subscriber additions vs. capacity limits in dense markets.",
            "Enterprise revenue growth — any acceleration signals market penetration.",
        ],
    },

    "CMCSA": {
        "position": "Comcast is the largest US cable operator providing broadband, video, and voice through Xfinity, plus the NBCUniversal media and entertainment portfolio. Broadband is the primary growth and profit driver. Video subscribers are in structural decline. Peacock streaming is scaling but loss-making. Theme parks (Universal) generate significant EBITDA.",
        "bull": [
            "Broadband ARPU is growing as video cord-cutting customers are repriced to broadband-only plans — revenue per home is resilient despite video loss.",
            "NBCU content (sports rights, Peacock) creates bundling opportunities that pure broadband operators cannot offer.",
            "Theme park expansion (Epic Universe Orlando opening 2025) is a new EBITDA driver independent of media cycle.",
        ],
        "bear": [
            "Fixed wireless access from T-Mobile and Verizon is taking broadband market share — net subscriber additions are under pressure.",
            "Peacock content spending ($3B+ annually) is a drag on FCF with an uncertain path to profitability.",
            "Video revenue decline is accelerating — the EBITDA contribution from video will become negligible within 3-5 years.",
        ],
        "priced_in": "Broadband ARPU growth offsetting subscriber losses and Peacock scaling to breakeven. Theme park expansion impact is in consensus.",
        "watch": [
            "Broadband subscriber net adds — any acceleration in losses to FWA would be significant.",
            "Broadband ARPU growth rate — pricing power vs. competitive pressure.",
            "Peacock subscriber count and ARPU — path to profitability.",
        ],
    },

    "CHTR": {
        "position": "Charter Communications is the second-largest US cable operator, providing broadband, video, and mobile services through Spectrum. It is executing a multi-billion-dollar network evolution to upgrade its infrastructure to 1.2GHz and then 2.5GHz multi-gigabit capable. Its Spectrum Mobile MVNO (using Verizon's network) is adding subscribers rapidly.",
        "bull": [
            "Network evolution to 1.2GHz/DOCSIS 4.0 will enable multi-gigabit symmetrical speeds — closing the speed gap with fiber and differentiated from T-Mobile FWA.",
            "Spectrum Mobile is growing rapidly with low incremental cost — mobile ARPU adds to broadband relationships.",
            "Rural broadband buildout (RDOF, BEAD subsidies) provides government-funded expansion into new markets.",
        ],
        "bear": [
            "Network evolution capex is $12B+ over multiple years — free cash flow is constrained during the build period.",
            "Fixed wireless competition is intensifying — T-Mobile and Verizon are taking share in Charter's markets.",
            "Video subscriber losses are accelerating — the linear TV bundle is unwinding faster than expected.",
        ],
        "priced_in": "Network evolution completing without material cost overrun and Spectrum Mobile growth continuing. FWA competitive impact is partially priced.",
        "watch": [
            "Broadband net adds — share loss to FWA competitors.",
            "Network evolution capex and completion timeline.",
            "Spectrum Mobile net adds — directional trend.",
        ],
    },

    "QCOM": {
        "position": "Qualcomm designs 5G modem chips and mobile application processors (Snapdragon) for smartphones, as well as automotive and IoT chips. Its licensing business (QTL) collects royalties on virtually all 5G handsets globally. Apple is its largest modem customer — a relationship that creates significant concentration risk as Apple develops in-house modems.",
        "bull": [
            "Snapdragon X Elite PC chips are gaining design wins — diversification into the PC market reduces smartphone concentration.",
            "Automotive Snapdragon digital cockpit and ADAS chips are a rapidly growing segment with multi-year design win to revenue cycles.",
            "QTL royalty stream is long-duration and durable — 5G licensing income is high-margin regardless of handset volume cycles.",
        ],
        "bear": [
            "Apple is developing its own modem (likely to appear in iPhones from 2026-2027) — Apple represents 20%+ of Qualcomm's chip revenue.",
            "Chinese smartphone market share has shifted to domestic chipmakers (Huawei Kirin, MediaTek) — Qualcomm's China handset exposure is declining.",
            "5G smartphone upgrade cycle is elongating — premium Snapdragon demand grows more slowly than initially forecast.",
        ],
        "priced_in": "Apple modem transition partially priced — full displacement timeline is 2026-2028. Automotive ramp is incremental upside not in consensus.",
        "watch": [
            "Apple modem development timeline — any iPhone launch without Qualcomm modem.",
            "Automotive design win announcements — vehicle launches using Snapdragon cockpit.",
            "China handset market share — MediaTek vs. Qualcomm premium segment.",
        ],
    },

    "NOK": {
        "position": "Nokia is a Finnish telecommunications equipment manufacturer selling 5G radio access network (RAN) hardware, core network software, and enterprise networking equipment. It is one of three global 5G RAN vendors (with Ericsson and Huawei). The ban on Huawei in Western markets has expanded Nokia's addressable market, but margins remain under pressure from competition.",
        "bull": [
            "Huawei exclusion from Western 5G markets is structural — Nokia and Ericsson are the only credible alternatives for most Western carriers.",
            "Enterprise private 5G networks are a growing opportunity — Nokia has a dedicated business unit targeting this market.",
            "India 5G rollout created a large new market where Nokia is a significant vendor.",
        ],
        "bear": [
            "Competitive intensity with Ericsson and Samsung is intense — pricing pressure is structural in RAN equipment markets.",
            "5G RAN spending cycle is maturing in Europe and the US — growth depends on new geographies or technology transitions (5G-A, Open RAN).",
            "Nokia's margin recovery has been slower than planned — cost structure improvements are ongoing.",
        ],
        "priced_in": "Huawei exclusion sustaining Nokia's market position and India/emerging market 5G rollout growing. Margin recovery is expected but partially in consensus.",
        "watch": [
            "5G RAN market share vs. Ericsson — any directional shift.",
            "India RAN order activity — Jio and Airtel network densification.",
            "Open RAN adoption rate — disruptive risk to traditional RAN vendors.",
        ],
    },

    "ERIC": {
        "position": "Ericsson is a Swedish telecom equipment manufacturer competing directly with Nokia. It sells 5G RAN, core network, and enterprise solutions. It acquired Vonage in 2022 to add cloud communication APIs. The Vonage integration has been challenging and the rationale questioned. Like Nokia, it benefits from Huawei exclusion in Western markets.",
        "bull": [
            "Huawei exclusion provides a structurally larger Western RAN market — Ericsson is often the preferred vendor among tier-1 US and European carriers.",
            "AT&T and Verizon multi-year RAN contracts provide revenue visibility.",
            "If Vonage API business scales, it represents a software revenue layer with higher margins than hardware.",
        ],
        "bear": [
            "Vonage acquisition has not delivered expected synergies — it was expensive ($6.2B) and its strategic fit with core RAN business remains unclear.",
            "5G RAN spending in the US and Europe is declining from peak — replacement cycle depends on 5G-Advanced or 6G timelines.",
            "Swedish government relations with China created complications around Huawei reciprocal restrictions.",
        ],
        "priced_in": "RAN market stabilizing and Vonage finding its place in the portfolio. Carrier capex cycle trough is largely priced.",
        "watch": [
            "US carrier capex guidance — AT&T and Verizon RAN spending plans.",
            "Vonage API revenue growth — software revenue trend.",
            "Open RAN adoption — both opportunity and threat for Ericsson.",
        ],
    },

    "JNPR": {
        "position": "Juniper Networks makes enterprise and carrier-grade routers, switches, and security appliances. Hewlett Packard Enterprise announced an acquisition of Juniper in January 2024, pending regulatory approval. If the deal closes, Juniper becomes part of HPE's networking portfolio alongside Aruba. The strategic logic is to create a challenger to Cisco in enterprise networking.",
        "bull": [
            "HPE acquisition at $40/share provides a near-term floor — the deal is expected to close pending regulatory clearance.",
            "AI-Native Networking (Mist AI, Marvis virtual assistant) positions Juniper as a software-differentiated competitor vs. Cisco.",
            "Carrier routing market is concentrated — Juniper holds second position behind Cisco and benefits from carrier capacity upgrades.",
        ],
        "bear": [
            "HPE acquisition regulatory risk — the UK CMA has reviewed the deal; any block would result in significant share price decline from current levels.",
            "If the deal closes, Juniper stockholders receive cash — no ongoing equity participation in the combined entity.",
            "Enterprise market share pressure from Cisco and Arista is intensifying even before the acquisition.",
        ],
        "priced_in": "HPE acquisition closing at announced terms. Spread is the primary investment consideration at current prices.",
        "watch": [
            "Regulatory approval timeline — UK CMA, EU, and US DOJ review status.",
            "Any deal amendment or revised terms.",
            "Enterprise switching market share while deal is pending — operational results still matter if deal is blocked.",
        ],
    },

    "CIEN": {
        "position": "Ciena Corporation provides optical and packet networking equipment for telecommunications carriers and cloud providers. Its WaveLogic coherent optical chips are the technology core — they are considered best-in-class for long-haul optical transport. AI-driven bandwidth demand is increasing the need for optical capacity upgrades. Revenue is lumpy due to large project-based orders.",
        "bull": [
            "AI data center interconnect and cloud provider backbone expansion is driving coherent optical demand — Ciena's WaveLogic advantage positions it to capture this growth.",
            "Market share is concentrated — Ciena competes with Nokia, Infinera (acquired by Nokia), and ADVA, but WaveLogic coherent performance is a recognized differentiator.",
            "AT&T and Verizon fiber buildouts require Ciena ROADM and coherent transport equipment at scale.",
        ],
        "bear": [
            "Revenue is lumpy — large projects at carriers mean quarterly results are variable and hard to predict.",
            "Indian carriers (Jio, Airtel) were a significant growth driver; any moderation in India optical buildout would impact results.",
            "Nokia's acquisition of Infinera creates a larger, more capable optical competitor.",
        ],
        "priced_in": "Coherent optical demand sustaining with AI-driven bandwidth growth and carrier fiber buildout. Nokia-Infinera competitive threat partially priced.",
        "watch": [
            "Order backlog and revenue guidance — forward visibility.",
            "India optical deployment activity — Jio and Airtel fiber buildout pace.",
            "AI data center interconnect RFPs — any large hyperscaler optical network award.",
        ],
    },

    "LUMN": {
        "position": "Lumen Technologies is a fiber and legacy copper infrastructure company serving enterprise and government customers. It faces significant operational and financial challenges — declining legacy revenue, high debt, and a recent debt restructuring. The company has a large fiber network asset that is underutilized. AI-driven bandwidth demand has created new interest in Lumen's dark fiber and long-haul network.",
        "bull": [
            "Lumen's dark fiber network spans 400,000+ route miles — AI companies and hyperscalers leasing dark fiber represent a new revenue opportunity without significant incremental capex.",
            "Microsoft announced a large fiber deal with Lumen — validation of the dark fiber thesis.",
            "Successful debt restructuring reduced near-term default risk and extended the financial runway.",
        ],
        "bear": [
            "Legacy copper and low-bandwidth services are declining faster than fiber revenue is growing — net revenue is still falling.",
            "Debt restructuring was complex and leaves the company with elevated leverage — financial flexibility remains constrained.",
            "Dark fiber deal pipeline is uncertain — Microsoft is announced, but the scope of future deals is unclear.",
        ],
        "priced_in": "Dark fiber deals continuing with additional hyperscaler customers and legacy revenue decline stabilizing. High-risk restructuring story.",
        "watch": [
            "Dark fiber contract announcements — any new hyperscaler or AI company deal.",
            "Revenue trend — when dark fiber revenue offsets legacy decline.",
            "Debt metrics — leverage ratio and covenant compliance.",
        ],
    },

    "COMM": {
        "position": "CommScope provides network infrastructure equipment — fiber cables, connectors, antennas, and distributed antenna systems (DAS) for in-building cellular coverage. It serves carriers, enterprises, and data centers. The company has significant debt from the ARRIS acquisition and has been exploring asset sales. Financial restructuring is an ongoing concern.",
        "bull": [
            "DAS market grows with indoor 5G coverage requirements — new buildings require CommScope in-building cellular infrastructure.",
            "Data center fiber and connectivity equipment benefits from AI-driven capacity expansion.",
            "Asset sales (Outdoor Wireless Networks, Home Networks) could reduce debt and simplify the business.",
        ],
        "bear": [
            "Debt level is very high ($10B+) relative to EBITDA — refinancing risk is significant as maturities approach.",
            "Carrier capex slowdown directly impairs CommScope's outdoor antenna and base station cable revenue.",
            "Business complexity across multiple end markets has made strategic focus difficult.",
        ],
        "priced_in": "Asset sales and debt restructuring providing a path to deleveraging. High-risk, distressed profile.",
        "watch": [
            "Asset sale announcements and proceeds — debt reduction trajectory.",
            "Debt maturity schedule and refinancing terms.",
            "Carrier capex guidance — outdoor infrastructure demand indicator.",
        ],
    },

    "LITE": {
        "position": "Lumentum Holdings makes optical components — lasers, modulators, and transceivers — used in telecommunications networks and consumer electronics (3D sensing for smartphones). Its coherent optical components compete with II-VI (now Coherent Corp) and Finisar. Apple's face ID uses Lumentum vertical-cavity surface-emitting lasers (VCSELs). Revenue is split between telecom and industrial/consumer.",
        "bull": [
            "AI data center optical interconnect demand (800G and beyond transceivers) is driving coherent component volume.",
            "VCSEL demand for 3D sensing (AR/VR headsets, automotive LiDAR) represents a growing non-telecom market.",
            "Telecom networking upgrade cycles (coherent optical for 400G/800G backbone) support component demand.",
        ],
        "bear": [
            "Telecom component market is highly competitive and cyclical — carrier capex slowdowns hit Lumentum's revenue directly.",
            "Apple VCSEL concentration risk — iPhone volume and face ID design decisions directly impact a significant revenue segment.",
            "Coherent Corp (II-VI merger) is a larger, better-resourced competitor in coherent optical.",
        ],
        "priced_in": "Telecom component recovery and AI data center optical demand growing. Apple concentration risk is known.",
        "watch": [
            "Telecom component order trend — recovery from inventory correction.",
            "Apple iPhone 3D sensing design continuity — any change in face ID architecture.",
            "800G coherent transceiver market share vs. Coherent Corp.",
        ],
    },

    "VIAV": {
        "position": "Viavi Solutions provides network test and measurement equipment for fiber networks, as well as anti-counterfeiting optical solutions (currency, government IDs). Its network and service enablement division tests fiber and 5G networks during construction and operation. The optical security products business (OVD: optically variable devices) provides stable, recurring revenue from government contract printing.",
        "bull": [
            "Fiber network buildout (BEAD, RDOF, carrier fiber expansion) requires test equipment at each installation — Viavi's fiber testing tools benefit from subsidy-funded buildout.",
            "5G network testing grows with carrier densification and private network deployments.",
            "Optical security (anti-counterfeiting) business provides a stable, non-cyclical revenue base.",
        ],
        "bear": [
            "Network test is a cyclical business tied to carrier and enterprise capex — slowdowns compress order volume.",
            "Optical security revenue growth is modest — currency printing contracts are stable but not high-growth.",
            "Competition from Spirent and EXFO in network testing puts pressure on pricing.",
        ],
        "priced_in": "Fiber test benefiting from BEAD and carrier buildout. Optical security provides stability.",
        "watch": [
            "BEAD deployment timeline — government subsidized fiber builds drive test equipment demand.",
            "Network test order backlog — directional signal for carrier capex.",
            "Currency contract renewals — optical security revenue stability.",
        ],
    },

    "FYBR": {
        "position": "Frontier Communications is a fiber broadband provider that has been converting its legacy copper network to fiber (Project Gigabit). Verizon announced an acquisition of Frontier in September 2024 at $20/share. If the deal closes, Frontier's fiber assets become part of Verizon's network strategy. Frontier emerged from bankruptcy in 2021 and has been executing a fiber buildout.",
        "bull": [
            "Verizon acquisition at $20/share provides a near-term floor — deal expected to close 2025.",
            "Fiber buildout has been executing on plan — over 5M locations passed with fiber, converting from copper.",
            "Fiber internet is a superior product to copper DSL — churn is lower and ARPU is higher.",
        ],
        "bear": [
            "Acquisition regulatory risk — any DOJ or FCC challenge could delay or block the deal.",
            "Standalone risk if deal falls through — Frontier's fiber buildout requires continued capital investment.",
            "Fiber market is becoming competitive — Comcast, Charter, and AT&T are all expanding fiber into Frontier markets.",
        ],
        "priced_in": "Verizon acquisition closing at announced terms. Spread reflects regulatory and execution risk.",
        "watch": [
            "DOJ and FCC regulatory review timeline and outcome.",
            "Fiber subscriber net adds while deal is pending.",
            "Any deal price amendment or competing bid.",
        ],
    },

    "LBRDK": {
        "position": "Liberty Broadband is a holding company whose primary asset is a ~26% equity stake in Charter Communications. It also holds a small stake in GCI (Alaska communications). Liberty Broadband trades at a discount to the underlying Charter value — the discount has historically been 15-25%. The rationale for holding is exposure to Charter with an additional discount.",
        "bull": [
            "Trades at a discount to net asset value — if Charter performs, Liberty Broadband should converge toward NAV.",
            "Merger into Charter has been discussed and would close the discount.",
            "Charter's fixed wireless and Spectrum Mobile growth flow through to Liberty Broadband's value.",
        ],
        "bear": [
            "The NAV discount may not close — holding company discounts are persistent and structural.",
            "All Charter risks (FWA competition, video decline, capex pressure) flow through to Liberty Broadband.",
            "Liquidity is lower than Charter directly — complex structure for a simple Charter exposure.",
        ],
        "priced_in": "NAV discount persisting at historical levels. Merger into Charter is optionality.",
        "watch": [
            "Liberty Broadband / Charter merger discussions — any announcement would close the discount.",
            "NAV discount vs. historical range — convergence or widening.",
            "Charter operational metrics — all Charter KPIs flow to Liberty Broadband value.",
        ],
    },

    "TDS": {
        "position": "Telephone and Data Systems is a regional wireless and fiber broadband company. It controls United States Cellular (USM) — a regional wireless carrier primarily in rural markets — and TDS Telecom, a fiber broadband provider in smaller markets. The company has explored strategic alternatives including a sale of USM. Revenue is split between wireless (USM) and wireline fiber.",
        "bull": [
            "T-Mobile has expressed interest in acquiring USM — a transaction would crystallize significant value for TDS shareholders.",
            "TDS Telecom fiber buildout in rural markets benefits from BEAD subsidies with limited competition.",
            "Rural wireless markets where USM operates have less competition than metro markets — ARPU is stable.",
        ],
        "bear": [
            "USM has been losing subscribers as T-Mobile's national network expands into rural markets where USM previously had coverage advantages.",
            "Fiber buildout capex is significant for a company of TDS's size — balance sheet is stretched.",
            "Strategic alternative process for USM has been ongoing without resolution — uncertainty impairs operational focus.",
        ],
        "priced_in": "USM sale process resulting in a transaction. Significant re-rating risk if USM is not sold.",
        "watch": [
            "USM sale process updates — any new buyer announcement or process closure.",
            "TDS Telecom fiber subscriber additions — broadband growth in rural markets.",
            "USM subscriber trend — postpaid phone net adds vs. churn.",
        ],
    },

    "USM": {
        "position": "United States Cellular is a regional wireless carrier operating primarily in rural and suburban markets across the Midwest and Southeast. It is majority-controlled by TDS. T-Mobile has entered into an agreement to acquire USM's wireless operations and a significant portion of its spectrum. If completed, USM would exit the wireless business.",
        "bull": [
            "T-Mobile acquisition of wireless operations at approximately $4.4B — provides near-term value crystallization.",
            "Spectrum assets being sold to T-Mobile are valuable at above-market prices — validates the spectrum value.",
            "Rural market stability — USM has strong brand loyalty in markets where it has operated for decades.",
        ],
        "bear": [
            "Post-acquisition, the remaining USM entity would be primarily towers — a much smaller and less valuable business.",
            "T-Mobile transaction regulatory approval is not guaranteed.",
            "If the deal falls through, USM faces an increasingly difficult competitive environment against T-Mobile's national network.",
        ],
        "priced_in": "T-Mobile acquisition closing at announced terms. Spread reflects regulatory and closing risk.",
        "watch": [
            "T-Mobile acquisition regulatory approval — FCC and DOJ review.",
            "Transaction closing timeline.",
            "Tower asset valuation post-acquisition — what the remaining entity is worth.",
        ],
    },

    "SATS": {
        "position": "EchoStar provides satellite broadband (HughesNet) and owns significant wireless spectrum (700MHz, AWS-4, H Block). It is exploring options to monetize its spectrum — including leasing or partnering with terrestrial wireless carriers. A potential merger with DISH Network (both controlled by Charlie Ergen) has been discussed. The balance sheet is under pressure.",
        "bull": [
            "Spectrum assets (700MHz, AWS-4) are strategically valuable to carriers seeking capacity — a spectrum monetization deal could unlock significant value.",
            "Satellite broadband (HughesNet) serves rural markets with limited alternatives — stable demand.",
            "DISH merger could rationalize the Ergen satellite/wireless portfolio.",
        ],
        "bear": [
            "HughesNet satellite broadband is losing subscribers to SpaceX Starlink — the low Earth orbit speed advantage is significant.",
            "Spectrum monetization requires a willing buyer — timeline and pricing are uncertain.",
            "Balance sheet is strained — debt maturity risk if spectrum monetization doesn't materialize.",
        ],
        "priced_in": "Spectrum monetization deal materializing. High-risk, distressed profile.",
        "watch": [
            "Spectrum lease or sale announcements — any carrier deal.",
            "HughesNet subscriber count — rate of Starlink displacement.",
            "Debt maturity schedule and refinancing options.",
        ],
    },

    "IDCC": {
        "position": "InterDigital is a wireless technology licensing company. It owns a large portfolio of patents essential to 3G, 4G, and 5G wireless standards and licenses them to handset manufacturers, chipmakers, and network equipment vendors. Revenue is predominantly royalty-based with minimal marginal cost. It also has a research function developing technologies for future standards.",
        "bull": [
            "5G royalty rates are higher than 4G — as 5G handset penetration grows, InterDigital's royalty base expands.",
            "Successful patent litigation and licensing renewals provide revenue step-ups that are difficult for licensees to avoid.",
            "Future standard participation (6G, Wi-Fi) creates a long-duration IP pipeline.",
        ],
        "bear": [
            "Licensees regularly challenge InterDigital's patents in inter partes review (IPR) proceedings — adverse rulings could impair royalty rates.",
            "Apple and Samsung negotiate hard on royalty rates — FRAND (fair, reasonable, and non-discriminatory) rate determinations by courts can go below expectations.",
            "5G handset volume growth is slowing in developed markets — royalty base growth rate moderates.",
        ],
        "priced_in": "5G royalty growth sustaining through handset penetration and licensing renewals at maintained rates. Litigation risk is ongoing.",
        "watch": [
            "Major licensing deal renewals (Apple, Samsung, Huawei) — terms and royalty rate direction.",
            "IPR and FRAND litigation outcomes — patent validity and rate determinations.",
            "5G handset global penetration — royalty base growth proxy.",
        ],
    },

    "SMCI": {
        "position": "Super Micro Computer designs and assembles high-performance servers, focusing on AI GPU-dense systems for data centers. Its Direct Liquid Cooling (DLC) technology for GPU servers has been adopted by several hyperscalers. SMCI has faced accounting and governance concerns — it delayed its annual report and faces SEC investigation. It is a Taiwanese-American company manufacturing in San Jose.",
        "bull": [
            "AI server demand is strong — SMCI's GPU-dense systems and early liquid cooling adoption positioned it ahead of peers.",
            "DLC technology is becoming standard in GPU server deployments — SMCI holds a technology and cost advantage in thermal management.",
            "Rapid product development cycle (faster than Dell/HPE) allows SMCI to support new NVIDIA GPU generations quickly.",
        ],
        "bear": [
            "Accounting irregularities and delayed financial filings are serious governance red flags — SEC investigation creates uncertainty.",
            "Auditor changes have delayed 10-K and 10-Q filings — potential NASDAQ delisting risk if filings remain late.",
            "As an integrator, margins are thin and revenue is volatile — SMCI is exposed to NVIDIA allocation decisions.",
        ],
        "priced_in": "Accounting issues resolved without material restatement and AI server demand sustaining. Governance risk is significant and not fully priced.",
        "watch": [
            "Annual report filing — completion and any restatement amount.",
            "SEC investigation resolution — any formal action or settlement.",
            "AI server order rate and backlog — operational performance behind the governance noise.",
        ],
    },

    "IBM": {
        "position": "IBM provides hybrid cloud infrastructure (Red Hat OpenShift), enterprise software, consulting, and the Watsonx AI platform. Red Hat is the primary growth driver. IBM's consulting arm deploys AI solutions for large enterprises. Its mainframe business (Z-series) generates stable, high-margin revenue from financial services customers.",
        "bull": [
            "Red Hat OpenShift is the enterprise Kubernetes standard — AI workload orchestration at scale runs on OpenShift in most large enterprises.",
            "Watsonx is positioned for regulated industries where proprietary model deployment and data sovereignty matter.",
            "Mainframe Z-series upgrade cycle drives predictable high-margin hardware revenue.",
        ],
        "bear": [
            "Consulting revenue growth is slowing as enterprise IT budgets tighten.",
            "Watsonx market penetration is modest vs. Microsoft Azure OpenAI and Google Vertex AI.",
            "Divestiture of legacy infrastructure services removed scale but low-growth segments remain.",
        ],
        "priced_in": "Red Hat sustaining 10%+ growth and Watsonx gaining enterprise AI platform traction.",
        "watch": [
            "Red Hat revenue growth rate.",
            "Watsonx deal size and enterprise customer count.",
            "Consulting revenue backlog.",
        ],
    },
}

# ── File updater ──────────────────────────────────────────────────────────────

_AUTOGEN_RE = re.compile(
    r"(<!-- AUTOGEN:BEGIN signal_history -->.*?<!-- AUTOGEN:END signal_history -->)",
    re.DOTALL,
)

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _build_section(heading: str, claim_type: str, body: str) -> str:
    return f"## {heading}\n\n<!-- claim_type: {claim_type} -->\n\n{body}\n"


def _build_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def update_page(path: Path, data: dict) -> bool:
    original = path.read_text(encoding="utf-8")

    # Extract frontmatter and rest
    fm_match = _FM_RE.match(original)
    if not fm_match:
        print(f"  SKIP {path.name} — no frontmatter")
        return False

    fm_raw = fm_match.group(1)
    rest = original[fm_match.end():]

    # Update last_updated in frontmatter
    fm_raw = re.sub(r"last_updated: .*", f"last_updated: {TODAY}", fm_raw)

    # Rebuild sections, preserving AUTOGEN block
    autogen_match = _AUTOGEN_RE.search(rest)
    autogen_block = autogen_match.group(0) if autogen_match else (
        "<!-- AUTOGEN:BEGIN signal_history -->\n<!-- claim_type: signal_summary -->\n\n"
        "_No signal firings recorded for this ticker._\n"
        "<!-- AUTOGEN:END signal_history -->"
    )

    # Get title from current H1
    h1_match = re.search(r"^# (.+)$", rest, re.MULTILINE)
    title = h1_match.group(0) if h1_match else f"# {path.stem}"

    pos = data["position"]
    bull = _build_bullets(data["bull"])
    bear = _build_bullets(data["bear"])
    priced = data["priced_in"]
    watch = _build_bullets(data["watch"])

    new_body = f"""{title}

{_build_section("Strategic position", "interpretation", pos)}
{_build_section("Bull case", "interpretation", bull)}
{_build_section("Bear case", "interpretation", bear)}
{_build_section("Priced in", "interpretation", priced)}
## Recent catalysts

<!-- claim_type: factual_claim -->

| Date | Event | Source | Horizon | Outcome |
|------|-------|--------|---------|---------|
| — | | | | |

## Signal history

{autogen_block}

{_build_section("Watch list", "risk_note", watch)}"""

    new_content = f"---\n{fm_raw}\n---\n\n{new_body}"

    if new_content == original:
        return False
    path.write_text(new_content, encoding="utf-8")
    return True


def main():
    updated = 0
    skipped = 0
    missing = 0

    for ticker, data in CONTENT.items():
        path = WIKI_DIR / f"{ticker}.md"
        if not path.exists():
            print(f"  MISSING {ticker}.md")
            missing += 1
            continue
        changed = update_page(path, data)
        if changed:
            print(f"  UPDATED {ticker}")
            updated += 1
        else:
            skipped += 1

    print(f"\nDone: {updated} updated, {skipped} unchanged, {missing} missing.")
    print(f"Tickers with no content: {set(p.stem for p in WIKI_DIR.glob('*.md')) - set(CONTENT)}")


if __name__ == "__main__":
    main()
