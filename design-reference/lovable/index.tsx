import { createFileRoute } from "@tanstack/react-router";
import { DashboardPage } from "@/components/portfolio-app";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Your portfolios — PortfolioPilot" },
      { name: "description", content: "View and manage your Indian stock portfolios with PortfolioPilot." },
      { property: "og:title", content: "Your portfolios — PortfolioPilot" },
      { property: "og:description", content: "View and manage your Indian stock portfolios with PortfolioPilot." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: DashboardPage,
});
