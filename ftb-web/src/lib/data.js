// Seed / fallback data — mirrors the Dispatch editorial schema.
// Used when the API is unreachable. Keys match the API response shape.

export const BRAND = {
  name: 'Dispatch',
  motto: 'The Internship Edition',
  established: 'EST. MMXXVI',
  city: 'BENGALURU',
  domain: 'dispatch.press',
}

export const EDITION = {
  no: 412,
  vol: 'I',
  verifiedToday: 82,
  spikedToday: 287,
  scrapedToday: 412,
  mergedToday: 43,
  spikedMonth: 4137,
  indiaEligible: 100,
  subscribers: 26840,
}

export const ROLE_CLUSTERS = [
  'Software', 'Data/AI', 'Design', 'Marketing', 'Product',
  'Finance', 'Business Dev', 'HR', 'Content', 'Legal', 'Operations',
]

export const CITIES = [
  'Bangalore', 'Mumbai', 'Delhi NCR', 'Gurgaon',
  'Hyderabad', 'Pune', 'Chennai', 'Remote',
]

export const LISTINGS = [
  { id: 'raz-fe', title: 'Frontend Developer Intern', org: 'Razorpay', editor: 'Ananya Iyer', cluster: 'Software', location: 'Bangalore', type: 'Hybrid', timing: 'Full-time', stipend: 40000, duration: '6 months', experience: 'Fresher', deadline: 'Jun 14', hoursAgo: 1, score: 94, tags: ['React', 'TypeScript', 'Fintech'], subchips: ['Frontend', 'Web', 'React', 'UI Developer'], similar: ['Full Stack', 'UI/UX', 'Mobile'], contact: 'campus@razorpay.com', applyLink: '#', desc: 'Builds merchant-facing dashboards used by some ten million businesses. The intern ships production React against an in-house design system and owns features end to end, paired with senior engineers.' },
  { id: 'zom-ds', title: 'Data Science Intern', org: 'Zomato', editor: 'Rohit Mehta', cluster: 'Data/AI', location: 'Gurgaon', type: 'Onsite', timing: 'Full-time', stipend: 35000, duration: '6 months', experience: 'Fresher', deadline: 'Jun 12', hoursAgo: 3, score: 91, tags: ['Python', 'ML', 'Analytics'], subchips: ['Data Science', 'ML', 'Analytics'], similar: ['Machine Learning', 'Data Engineering', 'Analytics'], contact: 'talent@zomato.com', applyLink: '#', desc: 'Works on demand-forecasting and delivery-time models against live order data. Python and SQL expected; a real curiosity about why people order what they order, preferred.' },
  { id: 'cred-ux', title: 'UI/UX Design Intern', org: 'CRED', editor: 'Priya Nair', cluster: 'Design', location: 'Bangalore', type: 'Hybrid', timing: 'Full-time', stipend: 30000, duration: '4 months', experience: 'Fresher', deadline: 'Jun 16', hoursAgo: 2, score: 90, tags: ['Figma', 'Product Design'], subchips: ['UI/UX', 'Product Design', 'Interaction'], similar: ['Graphic Design', 'Product', 'Motion'], contact: 'design@cred.club', applyLink: '#', desc: 'Crafts flows for one of India\'s most design-led fintechs. The intern prototypes in Figma, runs usability sessions, and is expected to defend decisions in critique.' },
  { id: 'groww-pm', title: 'Product Management Intern', org: 'Groww', editor: 'Karan Shah', cluster: 'Product', location: 'Bangalore', type: 'Hybrid', timing: 'Full-time', stipend: 45000, duration: '6 months', experience: 'Fresher', deadline: 'Jun 11', hoursAgo: 5, score: 89, tags: ['Fintech', 'Strategy'], subchips: ['Product', 'APM', 'Growth PM'], similar: ['Business Dev', 'Data/AI', 'Strategy'], contact: 'pm@groww.in', applyLink: '#', desc: 'Owns a slice of the investing experience used by some fifty million people. Writes specifications, interviews users, ships with engineering, and measures what actually moved.' },
  { id: 'ola-ml', title: 'Machine Learning Intern', org: 'Ola', editor: 'Sneha Rao', cluster: 'Data/AI', location: 'Bangalore', type: 'Onsite', timing: 'Full-time', stipend: 42000, duration: '6 months', experience: 'Fresher', deadline: 'Jun 13', hoursAgo: 2, score: 88, tags: ['PyTorch', 'ML'], subchips: ['ML', 'Deep Learning', 'Applied Science'], similar: ['Data Science', 'Backend', 'Research'], contact: 'ml@olacabs.com', applyLink: '#', desc: 'Improves routing and arrival-time models that move millions of rides a day. Prototyping in PyTorch; the work reaches production traffic during the term.' },
  { id: 'zep-mkt', title: 'Marketing Intern', org: 'Zepto', editor: 'Aditi Verma', cluster: 'Marketing', location: 'Mumbai', type: 'Onsite', timing: 'Full-time', stipend: 25000, duration: '3 months', experience: 'Fresher', deadline: 'Jun 10', hoursAgo: 4, score: 86, tags: ['Growth', 'Performance'], subchips: ['Marketing', 'Growth', 'Performance'], similar: ['Content', 'Social Media', 'Brand'], contact: 'growth@zepto.com', applyLink: '#', desc: 'Runs performance campaigns for ten-minute delivery. Owns budgets, reads dashboards daily, and learns paid acquisition where every rupee is accounted for.' },
  { id: 'mee-be', title: 'Backend Engineer Intern', org: 'Meesho', editor: 'Vikram Reddy', cluster: 'Software', location: 'Bangalore', type: 'Hybrid', timing: 'Full-time', stipend: 40000, duration: '6 months', experience: 'Fresher', deadline: 'Jun 15', hoursAgo: 7, score: 85, tags: ['Node.js', 'Distributed'], subchips: ['Backend', 'Server', 'API'], similar: ['Full Stack', 'Data Engineering', 'DevOps'], contact: 'eng@meesho.com', applyLink: '#', desc: 'Builds APIs that absorb festival-season traffic. Queues, caching, and the kind of scale that exposes naive code. Node.js expected.' },
  { id: 'dream-mob', title: 'Mobile App Developer Intern', org: 'Dream11', editor: 'Nikhil Joshi', cluster: 'Software', location: 'Mumbai', type: 'Hybrid', timing: 'Full-time', stipend: 38000, duration: '5 months', experience: 'Fresher', deadline: 'Jun 14', hoursAgo: 7, score: 83, tags: ['Flutter', 'Mobile'], subchips: ['Mobile', 'Flutter', 'Android'], similar: ['Frontend', 'Full Stack', 'UI/UX'], contact: 'careers@dream11.com', applyLink: '#', desc: 'Ships to one of India\'s highest-traffic mobile apps. Flutter, real-time updates, and sixty frames a second under match-day load.' },
  { id: 'una-content', title: 'Content Writer Intern', org: 'Unacademy', editor: 'Meera Pillai', cluster: 'Content', location: 'Remote', type: 'Remote', timing: 'Part-time', stipend: 18000, duration: '3 months', experience: 'Fresher', deadline: 'Jun 18', hoursAgo: 6, score: 84, tags: ['Content', 'SEO'], subchips: ['Content', 'Copywriting', 'SEO'], similar: ['Marketing', 'Social Media', 'Editorial'], contact: 'content@unacademy.com', applyLink: '#', desc: 'Writes learner-facing material that ranks and converts. Keyword research, editing, and a clear voice for students across the country.' },
  { id: 'zer-fin', title: 'Finance Intern', org: 'Zerodha', editor: 'Sanjay Gupta', cluster: 'Finance', location: 'Bangalore', type: 'Onsite', timing: 'Full-time', stipend: 30000, duration: '4 months', experience: 'Fresher', deadline: 'Jun 12', hoursAgo: 8, score: 82, tags: ['Equity Research', 'Markets'], subchips: ['Finance', 'Equity Research', 'Analyst'], similar: ['Data/AI', 'Business Dev', 'Strategy'], contact: 'careers@zerodha.com', applyLink: '#', desc: 'Sits with the research desk at India\'s largest broker. Builds models, drafts notes, and learns how markets actually price risk.' },
  { id: 'len-growth', title: 'Growth Intern', org: 'Lenskart', editor: 'Tanvi Desai', cluster: 'Marketing', location: 'Delhi NCR', type: 'Onsite', timing: 'Full-time', stipend: 28000, duration: '4 months', experience: 'Fresher', deadline: 'Jun 17', hoursAgo: 4, score: 81, tags: ['Growth', 'Retail'], subchips: ['Growth', 'Marketing', 'Retention'], similar: ['Marketing', 'Product', 'Business Dev'], contact: 'growth@lenskart.com', applyLink: '#', desc: 'Drives funnel experiments across web and retail. Runs A/B tests, reads cohorts, and ships growth loops that compound over the term.' },
  { id: 'cars-bd', title: 'Business Development Intern', org: 'Cars24', editor: 'Arjun Malhotra', cluster: 'Business Dev', location: 'Remote', type: 'Remote', timing: 'Full-time', stipend: 20000, duration: '3 months', experience: 'Fresher', deadline: 'Jun 19', hoursAgo: 9, score: 80, tags: ['B2B Sales', 'Partnerships'], subchips: ['Business Dev', 'Sales', 'Partnerships'], similar: ['Sales', 'Marketing', 'Operations'], contact: 'bd@cars24.com', applyLink: '#', desc: 'Builds the dealer-partner pipeline. Outreach, demonstrations, and closing — a quick education in how revenue is actually made.' },
  { id: 'boat-video', title: 'Video Editor Intern', org: 'boAt', editor: 'Riya Kapoor', cluster: 'Design', location: 'Mumbai', type: 'Hybrid', timing: 'Full-time', stipend: 22000, duration: '3 months', experience: 'Fresher', deadline: 'Jun 20', hoursAgo: 10, score: 79, tags: ['After Effects', 'Reels'], subchips: ['Video', 'Motion', 'Editing'], similar: ['Design', 'Content', 'Social Media'], contact: 'creative@boat-lifestyle.com', applyLink: '#', desc: 'Cuts short-form video for a brand built on the internet. After Effects and Premiere, and an instinct for what makes a viewer stop scrolling.' },
  { id: 'swig-hr', title: 'Human Resources Intern', org: 'Swiggy', editor: 'Deepika Menon', cluster: 'HR', location: 'Bangalore', type: 'Hybrid', timing: 'Full-time', stipend: 22000, duration: '4 months', experience: 'Fresher', deadline: 'Jun 16', hoursAgo: 11, score: 78, tags: ['Recruiting', 'People Ops'], subchips: ['HR', 'Recruiting', 'People Ops'], similar: ['Operations', 'Business Dev', 'Content'], contact: 'people@swiggy.in', applyLink: '#', desc: 'Supports campus hiring at scale. Coordinates drives, screens candidates, and sees how a five-thousand-person organisation grows.' },
  { id: 'fresh-sales', title: 'Sales Development Intern', org: 'Freshworks', editor: 'Harish Kumar', cluster: 'Business Dev', location: 'Chennai', type: 'Remote', timing: 'Full-time', stipend: 24000, duration: '4 months', experience: 'Fresher', deadline: 'Jun 21', hoursAgo: 5, score: 76, tags: ['SaaS', 'Outbound'], subchips: ['Sales', 'SDR', 'Business Dev'], similar: ['Business Dev', 'Marketing', 'Operations'], contact: 'sdr@freshworks.com', applyLink: '#', desc: 'Prospects and qualifies for a global software company. Learns outbound, objection handling, and the SaaS sales motion from the inside.' },
  { id: 'phonepe-gd', title: 'Graphic Design Intern', org: 'PhonePe', editor: 'Ishita Sharma', cluster: 'Design', location: 'Pune', type: 'Hybrid', timing: 'Full-time', stipend: 25000, duration: '4 months', experience: 'Fresher', deadline: 'Jun 18', hoursAgo: 6, score: 75, tags: ['Branding', 'Figma'], subchips: ['Graphic Design', 'Brand', 'Visual'], similar: ['UI/UX', 'Content', 'Motion'], contact: 'brand@phonepe.com', applyLink: '#', desc: 'Designs campaign and product assets for a large payments app. A strong sense of type and a clean grid go a long way here.' },
  { id: 'raz-legal', title: 'Legal Intern', org: 'Razorpay', editor: 'Neha Bansal', cluster: 'Legal', location: 'Mumbai', type: 'Onsite', timing: 'Full-time', stipend: 28000, duration: '3 months', experience: 'Fresher', deadline: 'Jun 15', hoursAgo: 12, score: 77, tags: ['Compliance', 'Contracts'], subchips: ['Legal', 'Compliance', 'Contracts'], similar: ['Finance', 'Operations', 'HR'], contact: 'legal@razorpay.com', applyLink: '#', desc: 'Reviews commercial contracts and supports fintech compliance — a rare look at how a regulated product is actually built.' },
  { id: 'dunzo-ops', title: 'Operations Intern', org: 'Dunzo', editor: 'Akash Singh', cluster: 'Operations', location: 'Bangalore', type: 'Onsite', timing: 'Full-time', stipend: 20000, duration: '3 months', experience: 'Fresher', deadline: 'Jun 22', hoursAgo: 13, score: 74, tags: ['Logistics', 'Excel'], subchips: ['Operations', 'Supply', 'Logistics'], similar: ['Business Dev', 'Data/AI', 'HR'], contact: 'ops@dunzo.com', applyLink: '#', desc: 'Keeps hyperlocal delivery moving. Tracks fleet metrics, clears bottlenecks, and learns operations where minutes carry cost.' },
  { id: 'nykaa-sm', title: 'Social Media Intern', org: 'Nykaa', editor: 'Pooja Agarwal', cluster: 'Marketing', location: 'Mumbai', type: 'Hybrid', timing: 'Part-time', stipend: 20000, duration: '3 months', experience: 'Fresher', deadline: 'Jun 23', hoursAgo: 14, score: 73, tags: ['Instagram', 'Community'], subchips: ['Social Media', 'Community', 'Content'], similar: ['Marketing', 'Content', 'Design'], contact: 'social@nykaa.com', applyLink: '#', desc: 'Runs the daily feed for a beauty retailer. Calendars, trends, and community replies that read as human rather than corporate.' },
  { id: 'postman-cs', title: 'Customer Success Intern', org: 'Postman', editor: 'Rahul Nanda', cluster: 'Operations', location: 'Bangalore', type: 'Remote', timing: 'Full-time', stipend: 22000, duration: '4 months', experience: 'Fresher', deadline: 'Jun 24', hoursAgo: 15, score: 70, tags: ['SaaS', 'Onboarding'], subchips: ['Customer Success', 'Support', 'Onboarding'], similar: ['Operations', 'Business Dev', 'Product'], contact: 'cs@postman.com', applyLink: '#', desc: 'Helps developer teams adopt the product. Onboarding calls, documentation, and turning confused users into fluent ones.' },
]

export const SPIKED = [
  { title: 'Data Entry Intern — ₹2,000 registration fee', filed: '"QuickEarn Solutions"', reason: 'PAY-TO-WORK', note: 'A real internship never charges to apply.' },
  { title: 'Remote Marketing Intern — USA / UK applicants only', filed: '"GlobalReach Media"', reason: 'NOT INDIA-ELIGIBLE', note: 'No work authorisation for students here.' },
  { title: 'Earn ₹5,000 a day from home — DM "Interested"', filed: 'Personal post', reason: 'NO LINK · SPAM', note: 'No company, no role, no way to apply.' },
]

export const RAN = {
  title: 'Frontend Developer Intern', org: 'Razorpay', location: 'Bangalore',
  stipend: 40000, score: 94, note: 'Real company · India-eligible · live link · graded 94.',
}

export const PROCESS = [
  { n: '01', head: 'The Wire', body: 'Overnight a scraper pulls every internship posted to LinkedIn — hundreds of them, raw and unsorted.', figure: '412', figLabel: 'filed by dawn' },
  { n: '02', head: 'The Desk', body: 'An editor reads each one and spikes the fee scams, the international-only roles, and the "DM me" posts with no link.', figure: '−287', figLabel: 'spiked', red: true },
  { n: '03', head: 'The Merge', body: 'The same role filed by ten recruiters is collapsed into a single clean entry.', figure: '−43', figLabel: 'duplicates merged' },
  { n: '04', head: 'The Grade', body: 'What survives is graded 0–100 on freshness — posts under six hours old score highest — and on source quality.', figure: '0–100', figLabel: 'each entry' },
  { n: '05', head: 'The Edition', body: 'Around eighty verified roles go to the board. The best six are set in type and delivered at eight.', figure: '82', figLabel: 'to print' },
]

export const LETTERS = [
  { body: 'I found my Razorpay interview in a morning edition. The role was two hours old when it reached me. I have not opened LinkedIn since.', name: 'Sneha K.', meta: 'Computer Science, final year · Bangalore' },
  { body: 'As a design student I could never surface non-engineering roles. Dispatch files UI/UX internships to me every morning without my asking.', name: 'Riya M.', meta: 'Design student · Mumbai' },
  { body: 'Every scam I used to nearly fall for, this paper has already thrown out before I wake up. That is the whole value.', name: 'Arjun P.', meta: 'Commerce graduate · Pune' },
]

export const NOTES = [
  { q: 'Is it genuinely free?', a: 'Yes — free for students, and intended to stay that way. The paper earns its keep elsewhere. We do not charge readers and we do not sell your address.' },
  { q: 'How are the scams kept out?', a: 'An editor — a language model — reads every filed post and spikes registration fees, "earn ₹X a day" schemes, typing jobs, posts with no apply link, and roles that are not open to students in India. Edge cases are checked by hand.' },
  { q: 'Is the paper only for engineers?', a: 'No. The board carries Design, Marketing, Finance, HR, Content, Legal and Operations alongside Software. Every field receives its own edition.' },
  { q: 'What exactly arrives at eight?', a: 'A single short email: the five or six freshest, highest-graded roles matched to your fields and cities. No digest, no advertising.' },
  { q: 'Will you fill my inbox?', a: 'One email a day, at most. We use your address for the edition and nothing else. One click unsubscribes, at any time.' },
]
