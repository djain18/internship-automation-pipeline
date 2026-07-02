"""
field_clusters.py
-----------------
Defines field clusters for internship search metadata.

get_subchips(role)       → comma-joined synonyms for the same role (4-6 items)
get_similar_fields(role) → comma-joined related but distinct adjacent fields (3-5 items)
"""

# ORDER MATTERS: more specific clusters first, generic fallbacks last.
CLUSTERS = [
    # ── TECH: Specialised ──────────────────────────────────────────────────────
    {
        "keywords": ["algo trading", "algo-trading", "quant intern", "quantitative", "trading intern", "systematic trading"],
        "subchips": ["Quant Intern", "Algo Trading Intern", "Quantitative Analyst Intern", "Fintech Intern", "Trading Intern"],
        "similar_fields": ["Finance & Investments", "Data Science & ML", "Software Engineering"],
    },
    {
        "keywords": ["cad design", "cad drafter", "solidworks", "autocad", "mechanical design", "engineering design", "product design engineer"],
        "subchips": ["CAD Designer Intern", "Mechanical Design Intern", "CAD Drafter", "SolidWorks Intern", "Engineering Design Intern"],
        "similar_fields": ["Mechanical Engineering", "Industrial Design", "Manufacturing Engineering"],
    },
    {
        "keywords": ["devops", "cloud engineer", "aws intern", "gcp intern", "azure intern", "sre intern", "platform engineer", "kubernetes", "docker"],
        "subchips": ["DevOps Intern", "Cloud Engineer Intern", "Platform Engineer Intern", "SRE Intern", "Infrastructure Engineer Intern"],
        "similar_fields": ["Backend Development", "Software Engineering", "Cybersecurity"],
    },
    {
        "keywords": ["cybersecurity", "information security", "penetration test", "ethical hack", "soc analyst", "security analyst"],
        "subchips": ["Cybersecurity Intern", "Security Analyst Intern", "Penetration Tester", "Ethical Hacker", "SOC Analyst"],
        "similar_fields": ["DevOps & Cloud", "Software Engineering", "Data Engineering"],
    },
    # ── TECH: Data & AI ────────────────────────────────────────────────────────
    {
        "keywords": ["data engineer", "etl developer", "data pipeline", "big data", "analytics engineering intern", "cloud data intern"],
        "subchips": ["Data Engineer Intern", "ETL Developer Intern", "Data Pipeline Intern", "Analytics Engineering Intern", "Cloud Data Intern"],
        "similar_fields": ["Data Science & ML", "Backend Development", "DevOps & Cloud"],
    },
    {
        "keywords": ["data scientist", "data science", "machine learning", "ml engineer", "ai engineer", "deep learning", "nlp intern", "computer vision", "research scientist", "ai-ml", "agentic ai", "ai focus", "ai intern", "ai/ml"],
        "subchips": ["Data Science Intern", "ML Engineer Intern", "AI-ML Intern", "NLP Intern", "Deep Learning Intern"],
        "similar_fields": ["Data Analytics", "Data Engineering", "Software Engineering"],
    },
    {
        "keywords": ["data analyst", "business intelligence", "bi developer", "bi analyst", "analytics intern", "sql analyst", "data insights intern", "reporting analyst"],
        "subchips": ["Data Analyst Intern", "Business Intelligence Intern", "BI Analyst Intern", "Analytics Intern", "SQL Analyst Intern"],
        "similar_fields": ["Data Science & ML", "Business Analysis", "Product Management"],
    },
    # ── TECH: Web & Mobile ─────────────────────────────────────────────────────
    {
        "keywords": ["full stack", "fullstack", "mean stack", "mern stack"],
        "subchips": ["Full Stack Developer Intern", "Full Stack Engineer Intern", "MERN Stack Intern", "MEAN Stack Intern", "Software Developer Intern"],
        "similar_fields": ["Frontend Development", "Backend Development", "Mobile Development"],
    },
    {
        "keywords": ["mobile developer", "android developer", "ios developer", "flutter developer", "react native developer", "app developer"],
        "subchips": ["Mobile Developer Intern", "Android Developer Intern", "iOS Developer Intern", "Flutter Intern", "React Native Intern"],
        "similar_fields": ["Full Stack Development", "Frontend Development", "Software Engineering"],
    },
    {
        "keywords": ["frontend", "front-end", "react developer", "angular developer", "vue developer", "ui developer", "javascript developer", "web developer", "wordpress"],
        "subchips": ["Frontend Developer Intern", "Web Developer Intern", "React Developer Intern", "JavaScript Developer Intern", "UI Developer Intern"],
        "similar_fields": ["Full Stack Development", "UI/UX Design", "Mobile Development"],
    },
    {
        "keywords": ["backend", "back-end", "node.js", "django", "spring developer", "api developer", "server-side"],
        "subchips": ["Backend Developer Intern", "Backend Engineer Intern", "API Developer Intern", "Node.js Intern", "SDE Intern"],
        "similar_fields": ["Full Stack Development", "Data Engineering", "DevOps & Cloud"],
    },
    {
        "keywords": ["software engineer", "software developer", "software intern", "software development", "sde intern", "systems engineer", "paid intern", "zoho developer"],
        "subchips": ["Software Engineer Intern", "Software Developer Intern", "SDE Intern", "Backend Engineer Intern", "Systems Engineer Intern"],
        "similar_fields": ["Full Stack Development", "Data Engineering", "DevOps & Cloud"],
    },
    # ── DESIGN ─────────────────────────────────────────────────────────────────
    {
        "keywords": ["ui ux", "ui/ux", "ux designer", "product designer", "interaction designer", "user experience", "ux researcher", "web design intern", "figma"],
        "subchips": ["UI/UX Designer Intern", "Product Designer Intern", "UX Researcher Intern", "Interaction Designer Intern", "UI Designer Intern"],
        "similar_fields": ["Graphic Design", "Frontend Development", "Product Management"],
    },
    {
        "keywords": ["graphic design", "visual design", "brand design", "logo design", "illustration", "print designer", "creative designer", "visual intern"],
        "subchips": ["Graphic Designer Intern", "Visual Designer Intern", "Brand Designer Intern", "Creative Designer Intern", "Illustrator Intern"],
        "similar_fields": ["UI/UX Design", "Motion Graphics", "Video Editing"],
    },
    {
        "keywords": ["video edit", "vfx", "video production", "motion graphic", "after effects", "premiere pro", "film editor", "reel editor", "multimedia editor", "post production"],
        "subchips": ["Video Editor Intern", "Film Editor Intern", "Multimedia Editor Intern", "Post-Production Editor Intern", "Reel Editor Intern"],
        "similar_fields": ["Motion Graphics Design", "Graphic Design", "Content Creation"],
    },
    # ── MARKETING & CONTENT ────────────────────────────────────────────────────
    {
        "keywords": ["content writ", "copywrite", "copywriting", "scriptwriter", "blog writer", "creative writer", "technical writer", "content strategist", "content creator"],
        "subchips": ["Content Writer Intern", "Copywriter Intern", "Blog Writer Intern", "Creative Writer Intern", "Technical Writer Intern"],
        "similar_fields": ["Social Media Marketing", "SEO & Digital Marketing", "Brand Marketing"],
    },
    {
        "keywords": ["seo intern", "sem intern", "paid ads", "google ads", "email marketing", "performance marketing", "growth marketing", "ppc intern", "digital marketing"],
        "subchips": ["Digital Marketing Intern", "SEO Intern", "Performance Marketing Intern", "Email Marketing Intern", "Growth Marketing Intern"],
        "similar_fields": ["Social Media Marketing", "Content Writing", "Brand Marketing"],
    },
    {
        "keywords": ["social media", "community manager", "instagram marketing", "social media strateg", "content & social", "reels", "smo"],
        "subchips": ["Social Media Intern", "Social Media Manager Intern", "Community Manager Intern", "Content & Social Intern", "Social Media Strategist Intern"],
        "similar_fields": ["Digital Marketing", "Content Writing", "Influencer Marketing"],
    },
    {
        "keywords": ["brand intern", "brand strategy", "brand marketing", "growth intern", "growth hacker", "partnerships intern", "growth & partnership", "influencer marketing", "marketing coordination", "marketing intern", "market insights"],
        "subchips": ["Brand Marketing Intern", "Growth Intern", "Partnerships Intern", "Brand Strategy Intern", "Marketing Intern"],
        "similar_fields": ["Digital Marketing", "Social Media Marketing", "Business Development"],
    },
    # ── BUSINESS & STRATEGY ────────────────────────────────────────────────────
    {
        "keywords": ["product manager", "product management", "associate product manager", "apm intern", "product analyst", "product strategy", "product intern", "product developer"],
        "subchips": ["Product Manager Intern", "APM Intern", "Associate Product Manager Intern", "Product Strategy Intern", "Product Analyst Intern"],
        "similar_fields": ["Business Analysis", "Strategy & Operations", "UI/UX Design"],
    },
    {
        "keywords": ["business development", "bd intern", "sales intern", "inside sales", "b2b sales", "data sales", "bdr intern", "sdr intern", "lead generation", "business development executive", "account intern", "account executive intern", "sales & marketing"],
        "subchips": ["Business Development Intern", "Sales Intern", "BDR Intern", "Inside Sales Intern", "B2B Sales Intern"],
        "similar_fields": ["Partnerships & Growth", "Digital Marketing", "Strategy & Operations"],
    },
    # ── HR before Operations so "hr generalist" beats "generalist intern" ──────
    {
        "keywords": ["hr intern", "hr associate", "hr generalist", "hr executive", "hr operations", "human resource", "talent acquisition", "recruiter intern", "people operations", "hrbp", "recruitment intern"],
        "subchips": ["HR Intern", "Talent Acquisition Intern", "Recruiter Intern", "People Operations Intern", "Recruitment Specialist Intern"],
        "similar_fields": ["Learning & Development", "Employer Branding", "Strategy & Operations"],
    },
    # ── Customer Support before Operations so "customer support & operations" maps here ──
    {
        "keywords": ["customer support", "customer success", "cx intern", "client servicing", "technical support", "help desk", "account support"],
        "subchips": ["Customer Support Intern", "Customer Success Intern", "CX Intern", "Client Servicing Intern", "Technical Support Intern"],
        "similar_fields": ["Sales & Business Development", "Operations", "Account Management"],
    },
    {
        "keywords": ["event management", "event operations", "event coordinator", "event planning", "campus event", "conference management", "logistics intern", "hospitality", "ground coordinator"],
        "subchips": ["Event Management Intern", "Event Operations Intern", "Event Coordinator Intern", "Logistics Intern", "Conference Management Intern"],
        "similar_fields": ["Operations & Strategy", "Marketing Coordination", "Hospitality Management"],
    },
    {
        "keywords": ["founder", "generalist intern", "chief of staff", "strategy & operations", "business operations", "startup operations", "special projects", "strategy intern", "operations intern", "management assistant", "management associate", "management intern", "operations & ai", "ai automations"],
        "subchips": ["Founder's Office Intern", "Operations Intern", "Chief of Staff Intern", "Strategy & Operations Intern", "Generalist Intern"],
        "similar_fields": ["Business Development", "Product Management", "Strategy Consulting"],
    },
    {
        "keywords": ["consulting intern", "management consulting", "strategy consulting", "business analyst", "functional consultant", "strategic planning", "corporate strategy", "business consultant"],
        "subchips": ["Business Analyst Intern", "Strategy Intern", "Management Consulting Intern", "Strategy Consultant Intern", "Corporate Strategy Intern"],
        "similar_fields": ["Strategy & Operations", "Finance & Investments", "Product Management"],
    },
    {
        "keywords": ["market research", "consumer research", "competitive intelligence", "industry research", "research analyst", "research intern", "outreach intern", "policy research"],
        "subchips": ["Market Research Intern", "Research Analyst Intern", "Consumer Research Intern", "Competitive Intelligence Intern", "Industry Research Intern"],
        "similar_fields": ["Business Analysis", "Strategy Consulting", "Data Analytics"],
    },
    {
        "keywords": ["supply chain", "product sourcing", "category management", "category intern", "sourcing intern", "procurement intern", "merchandising intern", "inventory management", "vendor management"],
        "subchips": ["Supply Chain Intern", "Category Management Intern", "Sourcing Intern", "Procurement Intern", "Merchandising Intern"],
        "similar_fields": ["Operations & Logistics", "E-commerce Management", "Business Analysis"],
    },
    # ── FINANCE & LEGAL ────────────────────────────────────────────────────────
    {
        "keywords": ["audit intern", "accounting intern", "ca intern", "chartered accountant", "tax intern", "cma intern"],
        "subchips": ["Audit Intern", "Accounting Intern", "CA Intern", "Tax Intern", "Finance & Accounts Intern"],
        "similar_fields": ["Finance & Investments", "Strategy Consulting", "Legal & Compliance"],
    },
    {
        "keywords": ["finance intern", "investment banking", "venture capital", "private equity", "financial analysis", "equity research", "financial modelling", "investment associate", "wealth intern", "collections intern", "finance operations"],
        "subchips": ["Finance Intern", "Investment Banking Intern", "Financial Analyst Intern", "Equity Research Intern", "Corporate Finance Intern"],
        "similar_fields": ["Strategy Consulting", "Algo-Trading & Quant Finance", "Data Analytics"],
    },
    {
        "keywords": ["law intern", "legal intern", "compliance intern", "corporate law", "legal research", "contracts intern", "paralegal", "litigation"],
        "subchips": ["Legal Intern", "Law Intern", "Corporate Law Intern", "Compliance Intern", "Legal Research Intern"],
        "similar_fields": ["Policy & Research", "Regulatory Affairs", "Finance & Investments"],
    },
    {
        "keywords": ["public policy", "design thinking", "social impact", "development sector", "csr intern", "social innovation", "rural development", "urban planning", "ngo"],
        "subchips": ["Public Policy Intern", "Social Impact Intern", "Policy Research Intern", "Development Sector Intern", "Design Thinking Intern"],
        "similar_fields": ["Legal & Compliance", "Market Research", "NGO & Non-Profit"],
    },
]


def get_subchips(role: str) -> str:
    r = role.lower()
    for cluster in CLUSTERS:
        if any(kw in r for kw in cluster["keywords"]):
            return ", ".join(cluster["subchips"])
    return ""


def get_similar_fields(role: str) -> str:
    r = role.lower()
    for cluster in CLUSTERS:
        if any(kw in r for kw in cluster["keywords"]):
            return ", ".join(cluster["similar_fields"])
    return ""
