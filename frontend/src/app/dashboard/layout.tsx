import { DashboardNav } from "@/components/shell/DashboardNav";

export default function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  return (
    <>
      <DashboardNav />
      {children}
    </>
  );
}
