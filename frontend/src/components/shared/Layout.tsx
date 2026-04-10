import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { LayoutDashboard, Briefcase, Sparkles } from "lucide-react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: any[]) {
  return twMerge(clsx(inputs));
}

const SidebarLink = ({
  to,
  icon: Icon,
  children,
}: {
  to: string;
  icon: any;
  children: React.ReactNode;
}) => (
  <NavLink
    to={to}
    className={({ isActive }) =>
      cn(
        "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 group",
        isActive
          ? "bg-primary/20 text-primary border border-primary/30"
          : "text-muted-foreground hover:bg-white/5 hover:text-foreground",
      )
    }
  >
    <Icon className="w-5 h-5 transition-transform group-hover:scale-110" />
    <span className="font-medium">{children}</span>
  </NavLink>
);

export const Layout = () => {
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border flex flex-col glass z-10">
        <div className="p-8 flex items-center gap-2">
          <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(16,185,129,0.3)]">
            <Sparkles className="text-primary-foreground w-6 h-6" />
          </div>
          <span className="text-xl font-bold tracking-tight">TalentForge</span>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-2">
          <SidebarLink to="/" icon={LayoutDashboard}>
            Dashboard
          </SidebarLink>
          <SidebarLink to="/jobs" icon={Briefcase}>
            Job Roles
          </SidebarLink>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto relative custom-scrollbar">
        {/* Decorative Background Elements */}
        <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[120px] -z-0"></div>
        <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-accent/5 rounded-full blur-[100px] -z-0"></div>

        <div className="p-8 relative z-1">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
