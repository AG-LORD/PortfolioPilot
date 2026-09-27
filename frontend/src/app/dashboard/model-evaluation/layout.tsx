import { redirect } from "next/navigation";

// The Research page is hidden unless NEXT_PUBLIC_SHOW_RESEARCH=true at build time.
export default function ResearchLayout({ children }: LayoutProps<"/dashboard/model-evaluation">) {
  if (process.env.NEXT_PUBLIC_SHOW_RESEARCH !== "true") redirect("/dashboard");
  return children;
}
