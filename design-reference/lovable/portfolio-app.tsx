import { Link, useNavigate } from "@tanstack/react-router";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  BriefcaseBusiness,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Info,
  Menu,
  Moon,
  Plus,
  Search,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const performance = [
  { m: "Oct", mix: 100000, nifty: 100000 }, { m: "Nov", mix: 100920, nifty: 100450 },
  { m: "Dec", mix: 101740, nifty: 101230 }, { m: "Jan", mix: 101180, nifty: 100610 },
  { m: "Feb", mix: 102960, nifty: 102140 }, { m: "Mar", mix: 103420, nifty: 101880 },
  { m: "Apr", mix: 104870, nifty: 103620 }, { m: "May", mix: 105430, nifty: 104780 },
  { m: "Jun", mix: 106210, nifty: 105140 }, { m: "Jul", mix: 107940, nifty: 106520 },
  { m: "Aug", mix: 108330, nifty: 107040 }, { m: "Sep", mix: 109000, nifty: 107690 },
];

const detailPrices = [
  { m: "Apr", v: 660 }, { m: "May", v: 682 }, { m: "Jun", v: 671 },
  { m: "Jul", v: 706 }, { m: "Aug", v: 719 }, { m: "Sep", v: 736 },
];

const selected = [
  { ticker: "HDFCBANK", sector: "Banking", estimate: "22.8%", weight: "20%", amount: "₹20,000.00", source: "ML" },
  { ticker: "TITAN", sector: "Consumer", estimate: "22.1%", weight: "20%", amount: "₹20,000.00", source: "ML" },
];

const excluded = [
  { ticker: "ADANIPORTS", sector: "Logistics", estimate: "−4.1%" },
  { ticker: "TCS", sector: "IT", estimate: "−1.2%" },
  { ticker: "WIPRO", sector: "IT", estimate: "−2.7%" },
];

const pie = [
  { name: "Cash", value: 60, color: "var(--chart-cash)" },
  { name: "HDFCBANK", value: 20, color: "var(--chart-one)" },
  { name: "TITAN", value: 20, color: "var(--chart-two)" },
];

function Brand() {
  return <Link to="/" className="flex items-center gap-2 font-bold text-foreground"><span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground"><BarChart3 size={17} /></span><span>PortfolioPilot</span></Link>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); }, [dark]);
  return <div className="min-h-screen bg-background text-foreground">
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Brand />
        <nav className="hidden items-center gap-1 md:flex">
          <Link to="/" activeOptions={{ exact: true }} activeProps={{ className: "bg-muted text-foreground" }} className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground">Portfolios</Link>
          <span className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground">Research</span>
          <Button variant="ghost" size="icon" aria-label="Toggle colour theme" onClick={() => setDark(!dark)}>{dark ? <Sun size={18} /> : <Moon size={18} />}</Button>
          <Button variant="ghost" size="sm">Sign out</Button>
        </nav>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation" onClick={() => setMobileOpen(!mobileOpen)}>{mobileOpen ? <X size={20} /> : <Menu size={20} />}</Button>
      </div>
      {mobileOpen && <div className="border-t border-border px-4 py-3 md:hidden"><div className="flex flex-col gap-1"><Link to="/" className="py-2 text-sm font-semibold" onClick={() => setMobileOpen(false)}>Portfolios</Link><span className="py-2 text-sm text-muted-foreground">Research</span><Button variant="outline" className="mt-2" onClick={() => setDark(!dark)}>{dark ? <Sun size={16}/> : <Moon size={16}/>} {dark ? "Light mode" : "Dark mode"}</Button></div></div>}
    </header>
    {children}
  </div>;
}

function Breadcrumbs({ current }: { current?: string }) {
  return <div className="mb-5 flex items-center gap-1 text-xs text-muted-foreground"><Link to="/" className="hover:text-foreground">Portfolios</Link>{current && <><ChevronRight size={13}/><span className="text-foreground">{current}</span></>}</div>;
}

function PortfolioTabs({ active }: { active: "current" | "plan" }) {
  return <div className="flex border-b border-border"><Link to="/portfolio" className={cn("px-4 py-3 text-sm font-semibold", active === "current" ? "border-b-2 border-primary text-primary" : "text-muted-foreground")}>Current</Link><Link to="/portfolio/plan" className={cn("px-4 py-3 text-sm font-semibold", active === "plan" ? "border-b-2 border-primary text-primary" : "text-muted-foreground")}>Plan</Link></div>;
}

function PageTitle({ eyebrow, title, action }: { eyebrow?: string; title: string; action?: ReactNode }) {
  return <div className="mb-6 flex items-start justify-between gap-4"><div>{eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-muted-foreground">{eyebrow}</p>}<h1 className="text-2xl font-bold sm:text-3xl">{title}</h1></div>{action}</div>;
}

const spark = [{v:20},{v:24},{v:23},{v:30},{v:29},{v:36},{v:41},{v:39},{v:48}];

export function DashboardPage() {
  const [guide, setGuide] = useState(true);
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const steps = [
    ["Create your portfolio", "Set your capital and risk preference. PortfolioPilot uses these as guardrails."],
    ["Review a proposed plan", "See what the model would include, leave out, and why—before anything changes."],
    ["Place orders yourself", "Use the clear checklist at your own broker. PortfolioPilot never places orders."],
    ["Keep track", "Record completed orders and see your portfolio progress in one place."],
  ];
  const currentStep = steps[step] ?? ["Create your portfolio", "Set your capital and risk preference."];
  return <AppShell><main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
    <Breadcrumbs />
    <PageTitle title="Your portfolios" eyebrow="Overview" action={<Button><Plus size={17}/> Create portfolio</Button>} />
    <div className="grid gap-5 lg:grid-cols-3">
      <article className="group rounded-lg border border-border bg-card p-5 shadow-sm transition hover:border-primary/40">
        <div className="mb-7 flex items-start justify-between"><div><div className="mb-2 flex items-center gap-2"><h2 className="font-bold">Long term growth</h2><span className="rounded-full bg-warning/15 px-2 py-1 text-[11px] font-semibold text-warning-foreground">Aggressive</span></div><p className="text-xs text-muted-foreground">2 stocks · Updated today</p></div><div className="h-12 w-28"><ResponsiveContainer><AreaChart data={spark}><defs><linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--primary)" stopOpacity={0.3}/><stop offset="100%" stopColor="var(--primary)" stopOpacity={0}/></linearGradient></defs><Area type="monotone" dataKey="v" stroke="var(--primary)" fill="url(#sparkFill)" strokeWidth={2} /></AreaChart></ResponsiveContainer></div></div>
        <p className="text-xs text-muted-foreground">Current value</p><p className="mt-1 text-2xl font-bold tabular-nums">₹1,09,000.00</p><p className="mt-2 flex items-center gap-1 text-sm font-semibold text-success"><ArrowUpRight size={15}/> ₹9,000.00 (9.0%)</p>
        <Button variant="outline" className="mt-7 w-full justify-between" onClick={() => navigate({ to: "/portfolio" })}>Open portfolio <ArrowRight size={16}/></Button>
      </article>
      <button className="flex min-h-64 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/40 p-5 text-center transition hover:border-primary/50" onClick={() => {}}><span className="mb-4 grid size-11 place-items-center rounded-full bg-muted text-muted-foreground"><Plus size={20}/></span><span className="font-semibold">Create another portfolio</span><span className="mt-1 max-w-52 text-sm text-muted-foreground">Try a different goal or risk profile.</span></button>
    </div>
  </main>
  {guide && <div className="fixed inset-0 z-50 grid place-items-center bg-overlay p-4"><div role="dialog" aria-modal="true" className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-2xl"><div className="mb-7 flex items-start justify-between"><div><p className="text-xs font-bold uppercase tracking-widest text-primary">Getting started · {step + 1} of 4</p><h2 className="mt-2 text-xl font-bold">{currentStep[0]}</h2></div><Button variant="ghost" size="icon" aria-label="Close guide" onClick={() => setGuide(false)}><X size={18}/></Button></div><div className="mb-8 rounded-md bg-muted p-5"><div className="mb-4 grid size-11 place-items-center rounded-md bg-primary text-primary-foreground">{step === 0 ? <BriefcaseBusiness/> : step === 1 ? <Search/> : step === 2 ? <CheckCircle2/> : <BarChart3/>}</div><p className="leading-7 text-muted-foreground">{currentStep[1]}</p></div><div className="flex items-center justify-between"><div className="flex gap-1.5">{steps.map((_, i) => <span key={i} className={cn("h-1.5 rounded-full transition-all", i === step ? "w-7 bg-primary" : "w-2 bg-border")}/>)}</div><Button onClick={() => step < 3 ? setStep(step + 1) : setGuide(false)}>{step < 3 ? <>Next <ArrowRight size={16}/></> : <>Explore portfolios <Check size={16}/></>}</Button></div></div></div>}
  </AppShell>;
}

function Metric({ label, value, note, info }: { label: string; value: string; note?: string; info?: string }) {
  return <div className="rounded-lg border border-border bg-card p-5"><div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">{label}{info && <span title={info} className="cursor-help"><Info size={14}/></span>}</div><p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>{note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}</div>;
}

function PerformanceChart({ portfolioLabel = "This mix" }: { portfolioLabel?: string }) {
  return <div className="h-72 w-full"><ResponsiveContainer><LineChart data={performance} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}><CartesianGrid stroke="var(--border)" vertical={false}/><XAxis dataKey="m" tickLine={false} axisLine={false} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}/><YAxis width={56} tickLine={false} axisLine={false} tickFormatter={(v) => `₹${Math.round(v/1000)}k`} tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}/><ChartTooltip contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 6 }} formatter={(v) => [`₹${Number(v).toLocaleString("en-IN")}.00`]}/><Line type="monotone" name={portfolioLabel} dataKey="mix" stroke="var(--primary)" strokeWidth={2.5} dot={false}/><Line type="monotone" name="NIFTY 50" dataKey="nifty" stroke="var(--chart-benchmark)" strokeWidth={2} strokeDasharray="5 5" dot={false}/></LineChart></ResponsiveContainer></div>;
}

function Donut({ center = "₹1L" }: { center?: string }) {
  return <div className="relative h-56"><ResponsiveContainer><PieChart><Pie data={pie} dataKey="value" innerRadius={62} outerRadius={86} paddingAngle={2} stroke="none">{pie.map((p) => <Cell key={p.name} fill={p.color}/>)}</Pie><ChartTooltip formatter={(v) => `${v}%`} contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 6 }}/></PieChart></ResponsiveContainer><div className="pointer-events-none absolute inset-0 grid place-items-center text-center"><div><p className="text-xs text-muted-foreground">Capital</p><p className="font-bold">{center}</p></div></div></div>;
}

function Section({ title, subtitle, children, action }: { title: string; subtitle?: string; children: ReactNode; action?: ReactNode }) {
  return <section className="py-7"><div className="mb-5 flex items-start justify-between gap-4"><div><h2 className="text-lg font-bold">{title}</h2>{subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}</div>{action}</div>{children}</section>;
}

export function CurrentPortfolioPage() {
  return <AppShell><main className="mx-auto max-w-7xl px-4 py-8 sm:px-6"><Breadcrumbs current="Long term growth"/><PageTitle eyebrow="Aggressive · ₹1,00,000.00 capital" title="Long term growth"/><PortfolioTabs active="current"/>
    <div className="mt-6 flex items-center justify-between rounded-lg border border-success/25 bg-success/10 p-4"><div className="flex items-center gap-3"><CheckCircle2 className="text-success" size={20}/><div><p className="font-semibold">Active plan: 0 of 2 orders remaining ✓</p><p className="text-xs text-muted-foreground">All orders from 27 Sep have been recorded.</p></div></div><Link to="/portfolio/plan" className="text-sm font-semibold text-primary">View plan</Link></div>
    <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4"><Metric label="Portfolio value" value="₹1,09,000.00" note="As of 27 Sep 2026"/><Metric label="Total P&L" value="+₹9,000.00" note="+9.0% overall"/><Metric label="Invested" value="₹40,000.00" note="Across 2 stocks"/><Metric label="Cash available" value="₹60,000.00" note="60% of capital"/></div>
    <Section title="Portfolio value" subtitle="Past year compared with NIFTY 50"><div className="rounded-lg border border-border bg-card p-3 sm:p-5"><div className="mb-3 flex gap-5 text-xs"><span className="flex items-center gap-2"><i className="h-0.5 w-5 bg-primary"/>Portfolio</span><span className="flex items-center gap-2"><i className="h-0.5 w-5 bg-chart-benchmark"/>NIFTY 50</span></div><PerformanceChart portfolioLabel="Portfolio"/></div></Section>
    <div className="grid gap-6 lg:grid-cols-[0.8fr_1.4fr]"><Section title="Holdings mix"><div className="rounded-lg border border-border bg-card p-4"><Donut/><div className="space-y-3">{pie.map(p => <div key={p.name} className="flex items-center justify-between text-sm"><span className="flex items-center gap-2"><i className="size-2.5 rounded-sm" style={{background:p.color}}/>{p.name}</span><span className="font-semibold">{p.value}%</span></div>)}</div></div></Section><Section title="Holdings"><div className="table-wrap"><table><thead><tr><th>Holding</th><th>Shares</th><th>Avg. price</th><th>Value</th><th>P&L</th></tr></thead><tbody><tr><td><strong>HDFCBANK</strong><small>Banking</small></td><td>27</td><td>₹735.60</td><td>₹20,000.00</td><td className="text-success">+₹2,140.00</td></tr><tr><td><strong>TITAN</strong><small>Consumer</small></td><td>4</td><td>₹4,884.00</td><td>₹20,000.00</td><td className="text-success">+₹1,060.00</td></tr><tr><td><strong>Cash</strong><small>Available</small></td><td>—</td><td>—</td><td>₹60,000.00</td><td>—</td></tr></tbody></table></div></Section></div>
    <Section title="Transactions" subtitle="Orders recorded in PortfolioPilot"><div className="divide-y divide-border rounded-lg border border-border bg-card">{[{t:"HDFCBANK",d:"27 Sep 2026",v:"27 shares at ₹735.60"},{t:"TITAN",d:"27 Sep 2026",v:"4 shares at ₹4,884.00"}].map(x=><div key={x.t} className="flex items-center justify-between gap-4 p-4"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-md bg-success/10 text-success"><ArrowDownRight size={17}/></span><div><p className="text-sm font-bold">Bought {x.t}</p><p className="text-xs text-muted-foreground">{x.d} · {x.v}</p></div></div><span className="text-xs font-semibold text-success">Recorded</span></div>)}</div></Section>
  </main></AppShell>;
}

type DrawerStock = typeof selected[number] | null;

export function PlanPage() {
  const [active, setActive] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [drawer, setDrawer] = useState<DrawerStock>(null);
  const [advanced, setAdvanced] = useState(false);
  const [orders, setOrders] = useState([{ticker:"HDFCBANK", shares:"27", price:"735.60", checked:false, amount:"₹19,861.20"},{ticker:"TITAN", shares:"4", price:"4884.00", checked:false, amount:"₹19,536.00"}]);
  const updateOrder = (i:number, key:"shares"|"price"|"checked", value:string|boolean) => setOrders(orders.map((o,n)=>n===i?{...o,[key]:value}:o));
  return <AppShell><main className="mx-auto max-w-7xl px-4 py-8 sm:px-6"><Breadcrumbs current="Long term growth"/><PageTitle eyebrow="Recommendation · 27 Sep 2026" title="Long term growth" action={<span className="rounded-full bg-warning/15 px-3 py-1.5 text-xs font-semibold text-warning-foreground">Aggressive</span>}/><PortfolioTabs active="plan"/>
    <section className="mt-6 overflow-hidden rounded-lg border border-border bg-card"><div className="grid lg:grid-cols-[1.5fr_0.8fr]"><div className="p-5 sm:p-7"><p className="text-xs font-bold uppercase tracking-widest text-primary">{active ? "Your active plan (since 27 Sep)" : "Proposed plan"}</p><h2 className="mt-3 max-w-2xl text-2xl font-bold leading-snug">Invest ₹40,000 in 2 stocks · keep ₹60,000 in cash</h2><p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">3 of your 5 stocks were left out: the model expects them to fall.</p><div className="mt-6 grid max-w-xl grid-cols-2 gap-3"><Metric label="Estimated yearly return" value="9.0%" info="A model estimate, not a guaranteed return."/><Metric label="Expected yearly swings" value="7.4%" info="The model's estimate of how much this mix may move in a year."/></div>{!active && <Button className="mt-6" onClick={()=>setConfirm(true)}>Adopt this plan <ArrowRight size={16}/></Button>}</div><div className="border-t border-border bg-muted/30 p-4 lg:border-l lg:border-t-0"><Donut/><div className="grid grid-cols-3 gap-2 text-center text-xs"><span><i className="mx-auto mb-1 block size-2 rounded-full bg-primary"/>20% HDFC</span><span><i className="mx-auto mb-1 block size-2 rounded-full bg-chart-two"/>20% TITAN</span><span><i className="mx-auto mb-1 block size-2 rounded-full bg-chart-cash"/>60% cash</span></div></div></div></section>
    {active && <Section title="Order checklist" subtitle="Tick orders after you place them at your broker."><div className="table-wrap"><table><thead><tr><th className="w-12"></th><th>Side</th><th>Ticker</th><th>Shares</th><th>Price</th><th>Fees</th><th>Amount</th></tr></thead><tbody>{orders.map((o,i)=><tr key={o.ticker}><td><input aria-label={`Select ${o.ticker} order`} type="checkbox" checked={o.checked} onChange={e=>updateOrder(i,"checked",e.target.checked)} className="size-4 accent-primary"/></td><td><span className="text-xs font-bold text-success">BUY</span></td><td><strong>{o.ticker}</strong></td><td><input aria-label={`${o.ticker} shares`} value={o.shares} onChange={e=>updateOrder(i,"shares",e.target.value)} className="w-20 rounded-md border border-input bg-background px-2 py-1.5"/></td><td><div className="flex items-center"><span className="mr-1 text-muted-foreground">₹</span><input aria-label={`${o.ticker} price`} value={o.price} onChange={e=>updateOrder(i,"price",e.target.value)} className="w-28 rounded-md border border-input bg-background px-2 py-1.5"/></div></td><td>₹0.00</td><td className="font-semibold">{o.amount}</td></tr>)}</tbody></table></div><div className="mt-4 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center"><p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck size={15}/>PortfolioPilot never places orders.</p><Button disabled={!orders.some(o=>o.checked)}>Record ticked orders</Button></div></Section>}
    <Section title="In your plan" subtitle="Stocks selected by the model within your risk limits"><div className="table-wrap"><table><thead><tr><th>Stock</th><th>Estimate</th><th>Weight</th><th>Amount</th><th>Source</th><th></th></tr></thead><tbody>{selected.map(s=><tr key={s.ticker}><td><strong>{s.ticker}</strong><small>{s.sector}</small></td><td className="font-semibold text-success">{s.estimate}</td><td>{s.weight}</td><td>{s.amount}</td><td><span className="rounded bg-muted px-2 py-1 text-[11px] font-bold">{s.source}</span></td><td className="text-right"><Button variant="outline" size="sm" onClick={()=>setDrawer(s)}>Why? <CircleHelp size={14}/></Button></td></tr>)}</tbody></table></div></Section>
    <Section title="Considered, not bought" subtitle="These stocks did not meet the model's threshold"><div className="table-wrap"><table><thead><tr><th>Stock</th><th>Estimate</th><th>Reason</th></tr></thead><tbody>{excluded.map(s=><tr key={s.ticker}><td><strong>{s.ticker}</strong><small>{s.sector}</small></td><td className="font-semibold text-destructive">{s.estimate}</td><td><span className="inline-flex items-center gap-1.5 text-sm"><ArrowDownRight size={15} className="text-destructive"/>Expected to fall</span></td></tr>)}</tbody></table></div></Section>
    <Section title="Past year of this mix vs NIFTY 50 (for context only)" subtitle="Both start at ₹1,00,000.00. This is historical context, not a forecast."><div className="rounded-lg border border-border bg-card p-3 sm:p-5"><div className="mb-3 flex gap-5 text-xs"><span className="flex items-center gap-2"><i className="h-0.5 w-5 bg-primary"/>This mix</span><span className="flex items-center gap-2"><i className="h-0.5 w-5 bg-chart-benchmark"/>NIFTY 50</span></div><PerformanceChart/></div></Section>
    <div className="mb-10 rounded-lg border border-border bg-card"><Button variant="ghost" className="h-auto w-full justify-between rounded-lg px-5 py-4" onClick={()=>setAdvanced(!advanced)}><span>Advanced details</span><ChevronDown size={17} className={cn("transition", advanced && "rotate-180")}/></Button>{advanced && <div className="grid gap-5 border-t border-border p-5 text-sm sm:grid-cols-3"><div><p className="text-muted-foreground">Maximum per stock</p><p className="mt-1 font-bold">20%</p></div><div><p className="text-muted-foreground">Target volatility</p><p className="mt-1 font-bold">25%</p></div><div><p className="text-muted-foreground">Model source</p><p className="mt-1 font-bold">ML</p></div></div>}</div>
  </main>
  {confirm && <div className="fixed inset-0 z-50 grid place-items-center bg-overlay p-4"><div role="dialog" aria-modal="true" className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-2xl"><div className="mb-4 grid size-11 place-items-center rounded-md bg-primary/10 text-primary"><CheckCircle2/></div><h2 className="text-xl font-bold">Adopt this plan?</h2><p className="mt-3 text-sm leading-6 text-muted-foreground">Nothing is bought. Next you'll get a list of orders to place at your broker.</p><div className="mt-7 flex justify-end gap-2"><Button variant="outline" onClick={()=>setConfirm(false)}>Cancel</Button><Button onClick={()=>{setActive(true);setConfirm(false)}}>Adopt plan</Button></div></div></div>}
  {drawer && <><div className="fixed inset-0 z-50 bg-overlay" onClick={()=>setDrawer(null)}/><aside className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-border bg-background p-6 shadow-2xl"><div className="flex items-start justify-between"><div><p className="text-xs font-bold uppercase tracking-widest text-primary">Why it is in your plan</p><h2 className="mt-2 text-2xl font-bold">{drawer.ticker}</h2><p className="text-sm text-muted-foreground">{drawer.sector}</p></div><Button variant="ghost" size="icon" aria-label="Close details" onClick={()=>setDrawer(null)}><X size={18}/></Button></div><div className="mt-7 grid grid-cols-2 gap-3"><Metric label="Estimated return" value={drawer.estimate}/><Metric label="Portfolio weight" value={drawer.weight}/></div><div className="mt-7"><h3 className="font-bold">Recent price movement</h3><div className="mt-3 h-44 rounded-lg border border-border bg-card p-2"><ResponsiveContainer><AreaChart data={detailPrices}><defs><linearGradient id="detailFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--primary)" stopOpacity={0.28}/><stop offset="100%" stopColor="var(--primary)" stopOpacity={0}/></linearGradient></defs><XAxis dataKey="m" hide/><YAxis hide domain={["dataMin - 10","dataMax + 10"]}/><Area type="monotone" dataKey="v" stroke="var(--primary)" strokeWidth={2} fill="url(#detailFill)"/></AreaChart></ResponsiveContainer></div></div><div className="mt-7"><h3 className="font-bold">What the model sees</h3><div className="mt-3 space-y-3">{[["Price trend","Recent direction has been positive."],["Risk fit","The 20% weight stays within your per-stock limit."],["Diversification","Adds exposure to the "+drawer.sector.toLowerCase()+" sector."]].map(([a,b])=><div key={a} className="rounded-md border border-border p-4"><p className="text-sm font-semibold">{a}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{b}</p></div>)}</div></div><p className="mt-7 text-xs leading-5 text-muted-foreground">Model estimates can be wrong. Use this as decision support, not a guarantee.</p></aside></>}
  </AppShell>;
}